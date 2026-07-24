"""pdf-tool read command — extract text with positions."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pdfplumber
import typer

from pdf_tool.commands.common import (
    ensure_input_size,
    ensure_not_encrypted,
    walk_field_chain,
)
from pdf_tool.commands.common import resolve_inherited as _resolve_inherited

# ---------------------------------------------------------------------------
# AcroForm value extraction (lightweight, uses pypdf)
# ---------------------------------------------------------------------------


def _field_type(annot: object) -> str:
    """Map a widget's (inherited) /FT to a human-readable field type."""
    ft = _resolve_inherited(annot, "/FT")
    ft_str = str(ft) if ft is not None else ""
    if ft_str == "/Tx":
        return "text"
    if ft_str == "/Ch":
        return "choice"
    if ft_str == "/Sig":
        return "signature"
    if ft_str == "/Btn":
        flags = int(_resolve_inherited(annot, "/Ff") or 0)
        if flags & (1 << 15):
            return "radio"
        if flags & (1 << 16):
            return "pushbutton"
        return "checkbox"
    return "unknown"


def _extract_form_field_values(file_path: str, include_empty: bool = False) -> list[dict]:
    """Return ``{"field_id": ..., "value": ..., "type": ..., "page": ...}`` dicts.

    By default only fields that actually carry a non-empty ``/V`` value are
    returned. With ``include_empty=True`` every named field is returned and
    fields without a value get ``value=None`` (existence vs. value distinction
    for the ``--fields`` fast path).

    Checkbox fields additionally carry a derived ``checked`` boolean:
    ``True`` (value equals the on-value), ``False`` (explicit "Off"), or
    ``None`` (no ``/V`` at all — untouched). The raw ``value`` keeps the
    as-stated string, so the "Off"-string vs ``None`` asymmetry stays visible.
    """
    from pypdf import PdfReader

    reader = PdfReader(file_path)
    results: list[dict] = []
    seen: set[str] = set()
    collapsed: dict[str, int] = {}

    for page_num, page in enumerate(reader.pages):
        for annot_ref in page.get("/Annots", []):
            annot = annot_ref.get_object()
            if annot.get("/Subtype") != "/Widget":
                continue

            # Build fully-qualified name (cycle-guarded walk)
            parts = [str(node.get("/T")) for node in walk_field_chain(annot) if node.get("/T")]
            parts.reverse()
            field_id = ".".join(parts)

            if not field_id:
                continue
            if field_id in seen:
                # Radio kids share the parent's name (no own /T) — legit.
                # A second widget WITH its own /T is a genuine duplicate.
                if annot.get("/T"):
                    collapsed[field_id] = collapsed.get(field_id, 0) + 1
                continue
            seen.add(field_id)

            # Get value — walk parent chain if needed
            val = _resolve_inherited(annot, "/V")

            val_str: str | None = None
            if val is not None:
                val_str = str(val).strip()
                if not val_str or val_str == "/":
                    val_str = None
                elif val_str.startswith("/"):
                    # Strip leading "/" from name-objects (e.g., "/Off" -> "Off")
                    val_str = val_str[1:]

            if val_str is None and not include_empty:
                continue

            entry: dict = {
                "field_id": field_id,
                "value": val_str,
                "type": _field_type(annot),
                "page": page_num,
            }
            if entry["type"] == "checkbox":
                from pdf_tool.commands.field_info import _extract_checkbox_values

                checked_value = _extract_checkbox_values(annot)["checked_value"]
                entry["checked"] = None if val_str is None else val_str == checked_value
            results.append(entry)

    if collapsed:
        names = ", ".join(sorted(collapsed))
        typer.echo(
            f"Warning: {sum(collapsed.values())} duplicate field name(s) collapsed "
            f"({names}) — only the first occurrence per name is shown",
            err=True,
        )
    return results


def _parse_pages_spec(spec: str, total_pages: int) -> list[int]:
    """Parse a ``--pages`` spec like ``"0,2,5"`` or ``"0-3,7"`` into a page list.

    Accepts comma-separated 0-indexed page numbers and inclusive ranges
    (``start-end``). Returns a sorted, de-duplicated list.

    Raises:
        ValueError: On malformed tokens or out-of-range pages.
    """

    def check_bounds(p: int) -> int:
        if p >= total_pages:
            raise ValueError(f"page {p} out of range (0-{total_pages - 1})")
        return p

    pages: set[int] = set()
    for token in spec.split(","):
        token = token.strip()
        if match := re.fullmatch(r"(\d+)-(\d+)", token):
            start, end = int(match.group(1)), int(match.group(2))
            if start > end:
                raise ValueError(f"invalid range '{token}' (start > end)")
            # Bounds-check BEFORE materializing — huge ranges must fail fast
            check_bounds(start)
            check_bounds(end)
            pages.update(range(start, end + 1))
        elif token.isdigit():
            pages.add(check_bounds(int(token)))
        else:
            raise ValueError(f"invalid page token '{token}' (expected e.g. '0,2,5' or '0-3')")
    if not pages:
        raise ValueError("no pages given")
    return sorted(pages)


def _read_named_fields(
    file: Path, requested: list[str], values_only: bool, output_json: bool
) -> None:
    """Fast path for --fields: read only named form fields, no text extraction."""
    try:
        all_fields = _extract_form_field_values(str(file), include_empty=True)
    except Exception as exc:
        typer.echo(f"Error: failed to read form fields: {exc}", err=True)
        raise typer.Exit(code=1)

    by_id = {f["field_id"]: f for f in all_fields}
    found = [by_id[name] for name in requested if name in by_id]
    missing = [name for name in requested if name not in by_id]

    if values_only:
        flat = {name: (by_id[name]["value"] if name in by_id else None) for name in requested}
        typer.echo(json.dumps(flat, indent=2, ensure_ascii=False))
    elif output_json:
        typer.echo(json.dumps({"fields": found, "missing": missing}, indent=2, ensure_ascii=False))
    else:
        for name in requested:
            if name in by_id:
                value = by_id[name]["value"]
                typer.echo(f"{name}: {value if value is not None else ''}")
            else:
                typer.echo(f"{name}: (missing)")

    raise typer.Exit(code=0 if found else 1)


def _render_all_pages(
    file_path: str,
    output_dir: str,
    max_dim: int = 1000,
    dpi: int = 200,
    page_nums: list[int] | None = None,
) -> list[Path]:
    """Render pages of a PDF to PNG images with adaptive resizing.

    Renders all pages by default, or only ``page_nums`` (0-indexed) when given.
    Output files are named page_<n>.png after the 0-indexed page number,
    matching --page/--pages numbering.
    """
    from pdf2image import convert_from_path

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    if page_nums is None:
        indexed = list(enumerate(convert_from_path(file_path, dpi=dpi)))
    else:
        indexed = []
        for p in page_nums:
            img = convert_from_path(file_path, dpi=dpi, first_page=p + 1, last_page=p + 1)[0]
            indexed.append((p, img))
    saved: list[Path] = []
    for page_idx, img in indexed:
        w, h = img.size
        if w > max_dim or h > max_dim:
            scale = min(max_dim / w, max_dim / h)
            img = img.resize((int(w * scale), int(h * scale)))
        dest = output_path / f"page_{page_idx}.png"
        img.save(str(dest), "PNG")
        saved.append(dest)
    return saved


def _validate_overlay_spec(data: object) -> str | None:
    """Validate the --overlay JSON; return an error message or None.

    Expected shape: {"form_fields": [{"page_number": 0,
    "entry_bounding_box": [x0, y0, x1, y1],
    "label_bounding_box": [x0, y0, x1, y1]}, ...]} — page_number 0-indexed.
    """
    if not isinstance(data, dict) or not isinstance(data.get("form_fields"), list):
        return "--overlay JSON must be an object with a 'form_fields' array"
    for i, field in enumerate(data["form_fields"]):
        if not isinstance(field, dict):
            return f"form_fields[{i}]: must be an object"
        page_number = field.get("page_number", 0)
        if isinstance(page_number, bool) or not isinstance(page_number, int):
            return f"form_fields[{i}].page_number: must be a 0-indexed integer"
        for key in ("entry_bounding_box", "label_bounding_box"):
            box = field.get(key)
            if box is None:
                continue
            if (
                not isinstance(box, list)
                or len(box) != 4
                or any(isinstance(v, bool) or not isinstance(v, int | float) for v in box)
            ):
                return f"form_fields[{i}].{key}: must be [x0, y0, x1, y1] (four numbers)"
    return None


def _draw_overlay(image_path: str, data: dict, page_num: int) -> None:
    """Draw bounding boxes from a validated overlay spec onto a page image.

    Red rectangles for entry_bounding_box, blue for label_bounding_box.
    """
    from PIL import Image, ImageDraw

    img = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(img)

    for field in data.get("form_fields", []):
        # page_number is 0-indexed, like --page
        if field.get("page_number", 0) != page_num:
            continue
        entry = field.get("entry_bounding_box")
        label = field.get("label_bounding_box")
        if entry:
            draw.rectangle(entry, outline="red", width=2)
        if label:
            draw.rectangle(label, outline="blue", width=2)

    img.save(image_path)


def _extract_tables(
    file_path: str,
    page_nums: list[int] | None = None,
    table_idx: int | None = None,
) -> list[dict]:
    """Extract tables from a PDF (all pages, or only ``page_nums`` when given)."""
    all_tables: list[dict] = []
    with pdfplumber.open(file_path) as pdf:
        if page_nums is not None:
            indexed = [(p, pdf.pages[p]) for p in page_nums]
        else:
            indexed = list(enumerate(pdf.pages))
        for actual_page, pg in indexed:
            for t_idx, table in enumerate(pg.extract_tables()):
                if table_idx is not None and t_idx != table_idx:
                    continue
                if table:
                    all_tables.append(
                        {
                            "page": actual_page,
                            "table_index": t_idx,
                            "headers": table[0],
                            "rows": table[1:],
                        }
                    )
    return all_tables


def read(
    file: Path = typer.Argument(..., help="Path to the PDF file."),
    page: int | None = typer.Option(None, "--page", "-p", help="Page number (0-indexed)."),
    pages: str | None = typer.Option(
        None,
        "--pages",
        help=(
            "Comma-separated 0-indexed pages, ranges allowed: '0,2,5' or '0-3,7'. "
            "Reads N scattered pages in ONE call — never loop with --page. "
            "Also filters --tables and --image <dir>. Mutually exclusive with --page. "
            "JSON output is ALWAYS an array (one object per page); only --page "
            "returns a single object."
        ),
    ),
    fields: str | None = typer.Option(
        None,
        "--fields",
        help=(
            "Comma-separated form field names: 'Company,Date,TermsAccepted'. Reads ONLY these "
            "AcroForm values (fast path, skips text extraction). N fields = ONE call, "
            "never a per-field loop. Unknown names are reported as missing, found fields "
            "are still returned. Add --values-only for a flat name->value JSON map. "
            "Checkboxes report raw 'value' as-stated (explicit 'Off' string vs null when "
            "untouched) plus a derived 'checked' boolean in JSON: true=on-value, "
            "false=explicit Off, null=untouched."
        ),
    ),
    values_only: bool = typer.Option(
        False,
        "--values-only",
        help=(
            'With --fields: output a flat JSON map {"Company": "Example LLC", "Date": null} '
            "for direct value access without jq. Missing fields become null."
        ),
    ),
    clip_range: str | None = typer.Option(
        None, "--range", "-r", help="Clip region: x0,y0,x1,y1 (top-left origin)."
    ),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON."),
    image: Path | None = typer.Option(
        None,
        "--image",
        "-i",
        help=(
            "Render page as PNG to this path; with a directory, renders pages as "
            "page_<n>.png (0-indexed, matching --page/--pages)."
        ),
    ),
    tables: bool = typer.Option(False, "--tables", help="Extract all tables."),
    table: int | None = typer.Option(None, "--table", help="Extract specific table (0-indexed)."),
    overlay: Path | None = typer.Option(
        None,
        "--overlay",
        help=(
            "Draw bounding boxes on the rendered image. JSON shape: "
            '{"form_fields": [{"page_number": 0, "entry_bounding_box": '
            '[x0,y0,x1,y1], "label_bounding_box": [x0,y0,x1,y1]}]} — '
            "page_number 0-indexed; entry boxes red, label boxes blue."
        ),
    ),
) -> None:
    """Extract text with positions from PDF pages.

    Scattered reads happen in ONE invocation — never loop per item:
    use --pages 0,2,5 for a sparse page set and --fields Company,Date
    (optionally with --values-only) for a handful of named form fields.
    """
    if not file.exists():
        typer.echo(f"Error: file not found: {file}", err=True)
        raise typer.Exit(code=1)

    ensure_input_size(file)
    ensure_not_encrypted(file)

    if page is not None and pages is not None:
        typer.echo("Error: --page and --pages are mutually exclusive", err=True)
        raise typer.Exit(code=1)

    if values_only and fields is None:
        typer.echo("Error: --values-only requires --fields", err=True)
        raise typer.Exit(code=1)

    if fields is not None:
        conflicts = [
            flag
            for flag, given in [
                ("--page", page is not None),
                ("--pages", pages is not None),
                ("--tables", tables),
                ("--table", table is not None),
                ("--range", clip_range is not None),
                ("--image", image is not None),
                ("--overlay", overlay is not None),
            ]
            if given
        ]
        if conflicts:
            typer.echo(
                "Error: --fields reads named form fields only; "
                f"do not combine with {', '.join(conflicts)}",
                err=True,
            )
            raise typer.Exit(code=1)
        requested = [name.strip() for name in fields.split(",") if name.strip()]
        if not requested:
            typer.echo("Error: --fields requires at least one field name", err=True)
            raise typer.Exit(code=1)
        _read_named_fields(file, requested, values_only, output_json)
        return

    overlay_spec: dict | None = None
    if overlay is not None:
        if image is None or page is None:
            typer.echo("Error: --overlay requires both --image and --page", err=True)
            raise typer.Exit(code=1)
        try:
            overlay_spec = json.loads(Path(overlay).read_text())
        except (OSError, json.JSONDecodeError) as exc:
            typer.echo(f"Error: cannot read --overlay JSON: {exc}", err=True)
            raise typer.Exit(code=1)
        overlay_error = _validate_overlay_spec(overlay_spec)
        if overlay_error is not None:
            typer.echo(f"Error: {overlay_error}", err=True)
            raise typer.Exit(code=1)

    with pdfplumber.open(str(file)) as pdf:
        total_pages = len(pdf.pages)

        if page is not None and (page < 0 or page >= total_pages):
            typer.echo(f"Error: page {page} out of range (0-{total_pages - 1})", err=True)
            raise typer.Exit(code=1)

        page_list: list[int] | None = None
        if pages is not None:
            try:
                page_list = _parse_pages_spec(pages, total_pages)
            except ValueError as exc:
                typer.echo(f"Error: {exc}", err=True)
                raise typer.Exit(code=1)

        if page is not None:
            pages_to_read = [(page, pdf.pages[page])]
        elif page_list is not None:
            pages_to_read = [(p, pdf.pages[p]) for p in page_list]
        else:
            pages_to_read = list(enumerate(pdf.pages))

        # Parse clip range
        clip: tuple[float, float, float, float] | None = None
        if clip_range:
            try:
                parts = [float(x.strip()) for x in clip_range.split(",")]
                if len(parts) != 4:
                    raise ValueError
                clip = (parts[0], parts[1], parts[2], parts[3])
            except ValueError:
                typer.echo("Error: --range must be x0,y0,x1,y1 (four numbers)", err=True)
                raise typer.Exit(code=1)

        # Handle image rendering
        if image is not None:
            if image.is_dir() or (not image.suffix and page is None):
                # Batch mode: render all (or --pages-selected) pages to directory
                if page is not None:
                    typer.echo("Error: batch mode (directory) renders all pages", err=True)
                    raise typer.Exit(code=1)
                saved = _render_all_pages(str(file), str(image), page_nums=page_list)
                typer.echo(f"Rendered {len(saved)} pages to {image}/")
                for p in saved:
                    typer.echo(f"  - {p.name}")
                return
            # Single page mode
            if page is None:
                if page_list is not None:
                    typer.echo(
                        "Error: --image with a single output file takes --page; "
                        "use --pages with a directory to render multiple pages",
                        err=True,
                    )
                else:
                    typer.echo(
                        "Error: --image requires --page (or use a directory for all pages)",
                        err=True,
                    )
                raise typer.Exit(code=1)
            pg = pdf.pages[page]
            img = pg.to_image()
            img.save(str(image))
            w, h = round(float(pg.width)), round(float(pg.height))
            if overlay_spec is not None:
                _draw_overlay(str(image), overlay_spec, page)
                typer.echo(f"Rendered page {page} to {image} ({w}x{h} px) with overlay")
            else:
                typer.echo(f"Rendered page {page} to {image} ({w}x{h} px)")
            return

        # Handle table extraction
        if tables or table is not None:
            table_pages = [page] if page is not None else page_list
            extracted = _extract_tables(str(file), page_nums=table_pages, table_idx=table)
            if output_json:
                typer.echo(json.dumps({"tables": extracted}, indent=2, ensure_ascii=False))
            else:
                if not extracted:
                    typer.echo("No tables found.")
                for tbl in extracted:
                    typer.echo(f"Page {tbl['page']}, Table {tbl['table_index']}:")
                    if tbl["headers"]:
                        typer.echo("  " + " | ".join(str(h) for h in tbl["headers"]))
                    for row in tbl["rows"]:
                        typer.echo("  " + " | ".join(str(c) for c in row))
                    typer.echo()
            return

        # Collect AcroForm field values once (shared across pages)
        form_fields: list[dict] = []
        try:
            form_fields = _extract_form_field_values(str(file))
        except Exception as exc:
            typer.echo(
                f"Warning: could not read form fields ({exc}); showing page text only",
                err=True,
            )

        for page_num, pg in pages_to_read:
            rotation = (getattr(pg, "rotation", 0) or 0) % 360
            if rotation:
                typer.echo(
                    f"Warning: page {page_num} is rotated ({rotation}°); read/write "
                    "coordinates disagree — text positions are reported in rotated "
                    "viewer space, write targets the unrotated mediabox",
                    err=True,
                )

        all_pages_data = []
        for page_num, pg in pages_to_read:
            page_width = round(float(pg.width), 1)
            page_height = round(float(pg.height), 1)

            target = pg
            if clip:
                target = pg.crop(clip)

            words = target.extract_words()
            word_list = [
                {
                    "text": word["text"],
                    "x0": round(float(word["x0"]), 1),
                    "y0": round(float(word["top"]), 1),
                    "x1": round(float(word["x1"]), 1),
                    "y1": round(float(word["bottom"]), 1),
                }
                for word in words
            ]

            # Filter form fields for this page
            page_form_fields = [f for f in form_fields if f["page"] == page_num]

            page_data: dict = {
                "page": page_num,
                "size": {"width": page_width, "height": page_height},
                "words": word_list,
            }
            if page_form_fields:
                page_data["form_fields"] = page_form_fields

            all_pages_data.append(page_data)

        if sum(len(p["words"]) for p in all_pages_data) == 0 and not form_fields:
            typer.echo(
                "Hint: no text layer found — likely a scanned PDF; render it visually "
                "instead (read --image <dir>) and inspect the PNGs",
                err=True,
            )

        if output_json:
            # Stable shape: --page -> single object; everything else -> array
            payload: object = all_pages_data[0] if page is not None else all_pages_data
            typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            for page_data in all_pages_data:
                size = page_data["size"]
                typer.echo(f"Page: {page_data['page']} | Size: {size['width']}x{size['height']} pt")
                for i, word in enumerate(page_data["words"], 1):
                    coords = f"({word['x0']}, {word['y0']})-({word['x1']}, {word['y1']})"
                    typer.echo(f'[L{i}]  "{word["text"]}" {coords}')
                # Print form field values
                for ff in page_data.get("form_fields", []):
                    typer.echo(f'[FORM]  "{ff["field_id"]}": "{ff["value"]}"')
                typer.echo()
