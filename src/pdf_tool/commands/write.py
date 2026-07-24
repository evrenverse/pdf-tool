"""pdf-tool write command — text overlay at x,y coordinates."""

import json
import math
import sys
from io import BytesIO
from pathlib import Path

import pdfplumber
import typer
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

from pdf_tool.commands.common import (
    MAX_BATCH_ITEMS,
    atomic_output,
    ensure_input_size,
    ensure_json_size,
    read_utf8,
)


def _detect_and_transform_overlays(
    overlays: list[dict],
    page_heights: dict[int, float],
    page_widths: dict[int, float] | None = None,
) -> list[dict]:
    """Auto-detect coordinate system and transform overlays to reportlab coords.

    Supports three coordinate systems:
    - Image coordinates: overlay contains image_width/image_height keys.
      Scales x/y by (pdf_dim / image_dim) ratio.
    - PDF coordinates: overlay contains pdf_width/pdf_height keys.
      Bottom-left origin, flips y: y = pdf_height - y.
    - Legacy format: no width/height keys.
      Top-left origin, passes through unchanged (y-flip happens in _apply_overlays).
    """
    transformed = []
    for overlay in overlays:
        item = dict(overlay)
        page = item.get("page", 0)
        pdf_page_height = page_heights.get(page, 842.0)
        pdf_page_width = (page_widths or {}).get(page, 595.0)

        if "image_width" in item and "image_height" in item:
            # Image coordinates: scale to PDF dimensions
            scale_x = pdf_page_width / item["image_width"]
            scale_y = pdf_page_height / item["image_height"]
            item["x"] = item["x"] * scale_x
            item["y"] = item["y"] * scale_y
            del item["image_width"]
            del item["image_height"]
        elif "pdf_width" in item and "pdf_height" in item:
            # PDF coordinates (bottom-left origin): flip y
            item["y"] = item["pdf_height"] - item["y"]
            del item["pdf_width"]
            del item["pdf_height"]

        # Legacy format: no transformation, pass through unchanged
        transformed.append(item)
    return transformed


def _validate_overlays(overlays: object, total_pages: int) -> str | None:
    """Validate overlay op objects upfront; return an error message or None.

    Checks: list shape, required keys (page, x, y, text), numeric coordinates, integer
    in-range page, known font names — so bad ops fail cleanly instead of
    raising KeyError mid-render.
    """
    from reportlab.pdfbase.pdfmetrics import standardFonts

    if not isinstance(overlays, list):
        return "JSON must be an array of overlay objects"
    allowed = {
        "page",
        "x",
        "y",
        "text",
        "font",
        "font_size",
        "image_width",
        "image_height",
        "pdf_width",
        "pdf_height",
    }
    for i, item in enumerate(overlays):
        if not isinstance(item, dict):
            return f"overlay[{i}]: must be an object"
        unknown = sorted(set(item) - allowed)
        if unknown:
            return f'overlay[{i}]: unknown key: "{unknown[0]}"'
        for key in ("page", "x", "y", "text"):
            if key not in item:
                return f'overlay[{i}]: missing required key: "{key}"'
        for key in ("x", "y"):
            if (
                isinstance(item[key], bool)
                or not isinstance(item[key], int | float)
                or not math.isfinite(item[key])
            ):
                return f"overlay[{i}].{key}: must be a number"
        if not isinstance(item["text"], str):
            return f"overlay[{i}].text: must be a string"
        page = item["page"]
        if isinstance(page, bool) or not isinstance(page, int):
            return f"overlay[{i}].page: must be an integer"
        if page < 0 or page >= total_pages:
            return f"overlay[{i}].page: {page} out of range (0-{total_pages - 1})"
        font = item.get("font", "Helvetica")
        if font not in standardFonts:
            return f'overlay[{i}].font: unknown font "{font}" (known: {", ".join(standardFonts)})'
        font_size = item.get("font_size", 11)
        if (
            isinstance(font_size, bool)
            or not isinstance(font_size, int | float)
            or not math.isfinite(font_size)
            or font_size <= 0
        ):
            return f"overlay[{i}].font_size: must be a positive number"
        image_keys = {"image_width", "image_height"} & set(item)
        pdf_keys = {"pdf_width", "pdf_height"} & set(item)
        if image_keys and image_keys != {"image_width", "image_height"}:
            return f"overlay[{i}]: image_width and image_height must be provided together"
        if pdf_keys and pdf_keys != {"pdf_width", "pdf_height"}:
            return f"overlay[{i}]: pdf_width and pdf_height must be provided together"
        if image_keys and pdf_keys:
            return f"overlay[{i}]: image and PDF coordinate dimensions are mutually exclusive"
        for key in image_keys | pdf_keys:
            value = item[key]
            if (
                isinstance(value, bool)
                or not isinstance(value, int | float)
                or not math.isfinite(value)
                or value <= 0
            ):
                return f"overlay[{i}].{key}: must be a positive number"
    return None


def _get_page_dimensions(file_path: str) -> tuple[dict[int, float], dict[int, float]]:
    """Get page heights and widths from a PDF using pdfplumber."""
    heights: dict[int, float] = {}
    widths: dict[int, float] = {}
    with pdfplumber.open(file_path) as pdf:
        for i, page in enumerate(pdf.pages):
            heights[i] = float(page.height)
            widths[i] = float(page.width)
    return heights, widths


def _warn_on_unrepresentable_glyphs(overlays: list[dict]) -> None:
    """Warn when overlay text contains glyphs the standard fonts cannot encode.

    Standard PDF fonts (Helvetica & friends) are WinAnsi/cp1252-only; CJK and
    other non-Latin glyphs are silently dropped or garbled by reportlab.
    """
    dropped: set[str] = set()
    for item in overlays:
        for ch in str(item.get("text", "")):
            try:
                ch.encode("cp1252")
            except UnicodeEncodeError:
                dropped.add(ch)
    if dropped:
        sample = "".join(sorted(dropped)[:10])
        typer.echo(
            f"Warning: {len(dropped)} character(s) not representable in WinAnsi "
            f"(standard PDF fonts) will be dropped or garbled: {sample} — "
            "use Latin-1 text, or build a Unicode page via 'pdf-tool create' and merge",
            err=True,
        )


def _apply_overlays(input_path: str, overlays: list[dict], output_path: str) -> None:
    """Apply text overlays to a PDF using reportlab + pypdf."""
    _warn_on_unrepresentable_glyphs(overlays)
    reader = PdfReader(input_path)
    # Merge into writer-owned page clones. Mutating reader-owned pages causes
    # pypdf to use a deprecated content-replacement path and can lose linked
    # document objects.
    writer = PdfWriter(clone_from=reader)

    # Group overlays by page
    by_page: dict[int, list[dict]] = {}
    for overlay in overlays:
        pg = overlay["page"]
        by_page.setdefault(pg, []).append(overlay)

    for page_num, page in enumerate(writer.pages):
        page_height = float(page.mediabox.height)
        page_width = float(page.mediabox.width)

        if page_num in by_page:
            packet = BytesIO()
            c = canvas.Canvas(packet, pagesize=(page_width, page_height))

            for item in by_page[page_num]:
                font = item.get("font", "Helvetica")
                font_size = item.get("font_size", 11)
                c.setFont(font, font_size)
                # Convert top-left origin to bottom-left origin
                rl_y = page_height - item["y"]
                c.drawString(item["x"], rl_y, item["text"])

            c.save()
            packet.seek(0)

            overlay_reader = PdfReader(packet)
            page.merge_page(overlay_reader.pages[0])

    with atomic_output(output_path) as tmp, open(tmp, "wb") as f:
        writer.write(f)


def write(
    file: Path = typer.Argument(..., help="Path to the PDF file."),
    changes: str = typer.Argument(
        ...,
        help=(
            "Path to JSON file with text overlays, or '-' for stdin. Schema: "
            '[{"page": 0, "x": 100, "y": 200, "text": "...", "font": "Helvetica", '
            '"font_size": 11}]. Coordinates: top-left origin by default; add '
            "image_width+image_height for image-pixel coordinates (from a rendered "
            "PNG), or pdf_width+pdf_height for bottom-left PDF coordinates."
        ),
    ),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output file path."),
) -> None:
    """Write text at x,y coordinates (overlay). For PDFs without form fields."""
    if not file.exists():
        typer.echo(f"Error: file not found: {file}", err=True)
        raise typer.Exit(code=1)
    ensure_input_size(file)

    # Read changes
    if changes == "-":
        raw = sys.stdin.read()
    else:
        changes_path = Path(changes)
        if not changes_path.exists():
            typer.echo(f"Error: changes file not found: {changes}", err=True)
            raise typer.Exit(code=1)
        raw = read_utf8(changes_path, "changes file")
    ensure_json_size(raw)

    try:
        overlays = json.loads(raw)
    except json.JSONDecodeError as e:
        typer.echo(f"Error: invalid JSON: {e}", err=True)
        raise typer.Exit(code=1)
    if isinstance(overlays, list) and len(overlays) > MAX_BATCH_ITEMS:
        typer.echo(f"Error: overlay batch exceeds {MAX_BATCH_ITEMS} items", err=True)
        raise typer.Exit(code=2)

    # Validate ops upfront (shape, keys, numbers, page range, fonts)
    reader = PdfReader(str(file))
    total_pages = len(reader.pages)
    error = _validate_overlays(overlays, total_pages)
    if error is not None:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(code=1)

    # Rotated pages: read reports rotated/viewer space, the overlay is placed
    # against the unrotated mediabox — coordinates from read will land wrong.
    targeted = sorted({item.get("page", 0) for item in overlays})
    for pg_num in targeted:
        rotation = (reader.pages[pg_num].rotation or 0) % 360
        if rotation:
            typer.echo(
                f"Warning: page {pg_num} is rotated ({rotation}°); read/write "
                "coordinates disagree — overlay is placed on the unrotated mediabox",
                err=True,
            )

    # Auto-detect coordinate system and transform overlays
    page_heights, page_widths = _get_page_dimensions(str(file))
    overlays = _detect_and_transform_overlays(overlays, page_heights, page_widths)

    output_path = str(output) if output else str(file)
    _apply_overlays(str(file), overlays, output_path)

    typer.echo(f"Written: {len(overlays)} text overlays on {Path(output_path).name}")
    for item in overlays:
        typer.echo(f'  - Page {item["page"]} ({item["x"]}, {item["y"]}): "{item["text"]}"')
