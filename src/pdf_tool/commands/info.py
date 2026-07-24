"""pdf-tool info command — show file structure and form fields."""

import json
from pathlib import Path

import pdfplumber
import typer

from pdf_tool.commands.common import ensure_input_size, ensure_not_encrypted
from pdf_tool.commands.structure import extract_form_structure


def _detect_page_size_label(width: float, height: float) -> str:
    """Detect common page size labels (A4, Letter, etc.)."""
    w, h = round(width), round(height)
    sizes = {
        (595, 842): "A4",
        (842, 595): "A4",
        (612, 792): "Letter",
        (792, 612): "Letter",
        (842, 1191): "A3",
        (1191, 842): "A3",
    }
    label = sizes.get((w, h), "")
    orientation = "portrait" if height > width else "landscape"
    if label:
        return f"{label} {orientation}"
    return f"{orientation}"


def _get_form_fields(file_path: str) -> list[dict]:
    """List form fields via the shared AcroForm extractor.

    Same vocabulary and keys as read --fields: field_id, type
    (text/checkbox/radio/choice/signature/pushbutton), page, value
    (+ derived 'checked' for checkboxes).
    """
    from pdf_tool.commands.read import _extract_form_field_values

    try:
        return _extract_form_field_values(file_path, include_empty=True)
    except Exception:
        return []


def info(
    file: Path = typer.Argument(..., help="Path to the PDF file."),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show PDF file structure: pages, dimensions, and form fields."""
    if not file.exists():
        typer.echo(f"Error: file not found: {file}", err=True)
        raise typer.Exit(code=1)

    ensure_input_size(file)
    ensure_not_encrypted(file)

    with pdfplumber.open(str(file)) as pdf:
        pages = []
        for i, page in enumerate(pdf.pages):
            w = round(float(page.width), 1)
            h = round(float(page.height), 1)
            pages.append(
                {
                    "page": i,
                    "width": w,
                    "height": h,
                    "label": _detect_page_size_label(w, h),
                }
            )

    form_fields = _get_form_fields(str(file))

    # When no AcroForm fields, detect form structure from page geometry
    structure = None
    if not form_fields:
        structure = extract_form_structure(str(file))

    if output_json:
        data = {
            "file": str(file.name),
            "pages": len(pages),
            "page_details": pages,
            "form_fields": form_fields,
        }
        if structure is not None:
            data["form_structure"] = structure
        typer.echo(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        typer.echo(f"File: {file.name} | Pages: {len(pages)}")
        typer.echo()
        for p in pages:
            typer.echo(f"Page {p['page']:>2}: {p['width']} x {p['height']} pt ({p['label']})")

        if form_fields:
            typer.echo(f"\nForm Fields: {len(form_fields)}")
            for f in form_fields:
                ftype = f.get("type", "text")
                extra = ""
                if ftype == "checkbox":
                    checked = "yes" if f.get("checked") else "no"
                    extra = f", checked: {checked}"
                typer.echo(f'  [{ftype:<10}] "{f["field_id"]}" (page {f["page"]}{extra})')
        else:
            typer.echo("\nForm Fields: none")

        if structure is not None:
            typer.echo("\nStructure Analysis:")
            typer.echo(f"  Labels: {len(structure['labels'])}")
            typer.echo(f"  Lines: {len(structure['lines'])}")
            typer.echo(f"  Checkboxes: {len(structure['checkboxes'])}")
            typer.echo(f"  Row Boundaries: {len(structure['row_boundaries'])}")
