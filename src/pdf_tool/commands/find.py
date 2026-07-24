"""pdf-tool find command — locate text and form fields without page dumps."""

from __future__ import annotations

import json
from pathlib import Path

import pdfplumber
import typer

from pdf_tool.commands.common import ensure_input_size, ensure_not_encrypted
from pdf_tool.commands.read import _extract_form_field_values, _parse_pages_spec


def _matches(needle: str, haystack: str, exact: bool) -> bool:
    """Substring match, case-insensitive unless ``exact``."""
    if exact:
        return needle in haystack
    return needle.lower() in haystack.lower()


def find(
    file: Path = typer.Argument(..., help="Path to the PDF file."),
    text: str = typer.Argument(..., help="Text to search for (substring)."),
    exact: bool = typer.Option(
        False,
        "--exact",
        help=(
            "Case-sensitive SUBSTRING matching (default: case-insensitive substring). "
            "Note: unlike xlsx/docx find --exact, this is NOT a full-cell/full-line match."
        ),
    ),
    pages: str | None = typer.Option(
        None, "--pages", help="Limit search to these pages: '0,2,5' or '0-3,7' (0-indexed)."
    ),
    max_results: int = typer.Option(
        50, "--max", help="Maximum matches to output; truncation is reported explicitly."
    ),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Locate a label, value, or form field in ONE call — never page-dump + grep.

    Matches line-level page text (multi-word queries like 'Ort, Date' work)
    AND AcroForm field names/values. Workflow: find the label, then
    'read --fields <name>' for form values or use the bbox for write/overlay
    coordinates. Exits 1 when nothing matches.
    """
    if not file.exists():
        typer.echo(f"Error: file not found: {file}", err=True)
        raise typer.Exit(code=1)

    ensure_input_size(file)
    ensure_not_encrypted(file)

    if max_results < 1:
        typer.echo("Error: --max must be >= 1", err=True)
        raise typer.Exit(code=1)

    matches: list[dict] = []
    with pdfplumber.open(str(file)) as pdf:
        total_pages = len(pdf.pages)

        page_list: list[int] | None = None
        if pages is not None:
            try:
                page_list = _parse_pages_spec(pages, total_pages)
            except ValueError as exc:
                typer.echo(f"Error: {exc}", err=True)
                raise typer.Exit(code=1)
        selected = page_list if page_list is not None else list(range(total_pages))

        try:
            form_fields = _extract_form_field_values(str(file), include_empty=True)
        except Exception as exc:
            form_fields = []
            typer.echo(
                f"Warning: could not read form fields ({exc}); searching page text only",
                err=True,
            )
        form_by_page: dict[int, list[dict]] = {}
        for f in form_fields:
            form_by_page.setdefault(f["page"], []).append(f)

        saw_text = False
        for p in selected:
            for line in pdf.pages[p].extract_text_lines():
                saw_text = True
                if _matches(text, line["text"], exact):
                    matches.append(
                        {
                            "page": p,
                            "text": line["text"],
                            "bbox": [
                                round(float(line["x0"]), 1),
                                round(float(line["top"]), 1),
                                round(float(line["x1"]), 1),
                                round(float(line["bottom"]), 1),
                            ],
                            "kind": "text",
                        }
                    )
            for f in form_by_page.get(p, []):
                candidates = [f["field_id"]] + ([f["value"]] if f["value"] is not None else [])
                if any(_matches(text, c, exact) for c in candidates):
                    matches.append(
                        {
                            "page": p,
                            "field_id": f["field_id"],
                            "value": f["value"],
                            "kind": "form_field",
                        }
                    )

    total = len(matches)
    truncated = total > max_results
    shown = matches[:max_results]

    if output_json:
        envelope = {"matches": shown, "total": total, "truncated": truncated}
        typer.echo(json.dumps(envelope, indent=2, ensure_ascii=False))
    else:
        if not shown:
            typer.echo("No matches found.")
        for m in shown:
            if m["kind"] == "form_field":
                value_repr = json.dumps(m["value"], ensure_ascii=False)
                typer.echo(f"p{m['page']} [form_field] {m['field_id']} = {value_repr}")
            else:
                b = m["bbox"]
                typer.echo(f'p{m["page"]} ({b[0]},{b[1]})-({b[2]},{b[3]}): "{m["text"]}"')
        if truncated:
            typer.echo(f"... truncated: showing {max_results} of {total} matches (raise --max)")

    if total == 0:
        if not saw_text:
            typer.echo(
                "Hint: no text layer found — likely a scanned PDF; render it visually "
                "instead (read --image <dir>) and inspect the PNGs",
                err=True,
            )
        raise typer.Exit(code=1)
