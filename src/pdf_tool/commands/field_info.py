"""Field hierarchy extraction for PDF AcroForm fields.

Walks the field tree to build fully-qualified field IDs, classifies field types,
and extracts type-specific metadata (checkbox values, radio options, choice options).
"""

import json
from pathlib import Path

import typer
from pypdf import PdfReader

from pdf_tool.commands.common import (
    ensure_input_size,
    ensure_not_encrypted,
    resolve_inherited,
    walk_field_chain,
)

# Bit 15 (0-indexed: bit 16 in 1-indexed) of /Ff flags indicates radio button
_RADIO_FLAG_BIT = 1 << 15
# Bit 16 (0-indexed: bit 17 in 1-indexed) of /Ff flags indicates pushbutton
_PUSHBUTTON_FLAG_BIT = 1 << 16


def _get_fully_qualified_name(annot: dict) -> str:
    """Build the fully-qualified field name by walking the /Parent chain.

    E.g., "section.subsection.field" if the field has nested parents.
    """
    parts = [str(node.get("/T")) for node in walk_field_chain(annot) if node.get("/T")]
    parts.reverse()
    return ".".join(parts) if parts else ""


def _classify_field(annot: dict) -> str:
    """Classify into read's vocabulary: text/checkbox/radio/choice/signature/pushbutton."""
    ft = resolve_inherited(annot, "/FT")

    if ft == "/Tx":
        return "text"
    if ft == "/Ch":
        return "choice"
    if ft == "/Sig":
        return "signature"
    if ft == "/Btn":
        flags = _get_field_flags(annot)
        if flags & _RADIO_FLAG_BIT:
            return "radio"
        if flags & _PUSHBUTTON_FLAG_BIT:
            return "pushbutton"
        return "checkbox"
    return "unknown"


def _get_field_flags(annot: dict) -> int:
    """Get the /Ff flags value, checking parent chain if needed."""
    ff = resolve_inherited(annot, "/Ff")
    return int(ff) if ff is not None else 0


def _extract_checkbox_values(annot: dict) -> dict:
    """Extract checked and unchecked values from checkbox appearance streams."""
    ap = annot.get("/AP")
    if not ap:
        return {"checked_value": "Yes", "unchecked_value": "Off"}

    normal = ap.get("/N")
    if not normal or not hasattr(normal, "keys"):
        return {"checked_value": "Yes", "unchecked_value": "Off"}

    keys = [str(k) for k in normal]
    checked = "Yes"
    unchecked = "Off"
    for k in keys:
        clean = k.lstrip("/")
        if clean.lower() == "off":
            unchecked = clean
        else:
            checked = clean
    return {"checked_value": checked, "unchecked_value": unchecked}


def _extract_radio_options(annot: dict, page_num: int) -> list[dict]:
    """Extract radio button options from a radio group's Kids."""
    parent = annot.get("/Parent")
    if parent is None:
        return []

    parent_obj = parent.get_object()
    kids = parent_obj.get("/Kids")
    if not kids:
        return []

    options: list[dict] = []
    for kid_ref in kids:
        kid = kid_ref.get_object()
        rect = kid.get("/Rect")
        rect_floats = [float(v) for v in rect] if rect else []

        # Get value from appearance stream
        ap = kid.get("/AP")
        value = ""
        if ap:
            normal = ap.get("/N")
            if normal and hasattr(normal, "keys"):
                for k in normal:
                    clean = str(k).lstrip("/")
                    if clean.lower() != "off":
                        value = clean
                        break

        options.append(
            {
                "value": value,
                "rect": rect_floats,
            }
        )

    return options


def _extract_choice_options(annot: dict) -> list[str]:
    """Extract choice options from the /Opt array."""
    opt = resolve_inherited(annot, "/Opt")

    if not opt:
        return []

    options: list[str] = []
    for item in opt:
        if isinstance(item, (list, tuple)):
            # [export_value, display_value] pairs
            options.append(str(item[1]) if len(item) > 1 else str(item[0]))
        else:
            options.append(str(item))
    return options


def extract_field_info(file_path: str) -> list[dict]:
    """Extract structured form field information from a PDF.

    Walks the AcroForm field tree to produce fully-qualified field IDs,
    classifies field types, and extracts type-specific metadata.

    Args:
        file_path: Path to the PDF file.

    Returns:
        List of field dicts sorted by page then top-left position. Each dict has:
        - field_id: Fully-qualified field name (e.g., "section.field")
        - type: One of "text", "checkbox", "radio", "choice", "signature", "pushbutton", "unknown"
        - page: Zero-based page number
        - rect: [x0, y0, x1, y1] bounding box
        Plus type-specific keys:
        - checkbox: checked_value, unchecked_value
        - radio: radio_options (list of {value, rect})
        - choice: choice_options (list of strings)
    """
    reader = PdfReader(file_path)
    fields: list[dict] = []
    # Track seen field IDs to avoid duplicates from radio group kids
    seen_ids: set[str] = set()
    collapsed: dict[str, int] = {}

    for page_num, page in enumerate(reader.pages):
        for annot_ref in page.get("/Annots", []):
            annot = annot_ref.get_object()
            if annot.get("/Subtype") != "/Widget":
                continue

            field_id = _get_fully_qualified_name(annot)
            if not field_id:
                continue

            # Skip duplicate IDs (e.g., individual radio buttons in a group)
            if field_id in seen_ids:
                # Radio kids carry no own /T; a second widget WITH /T is a
                # genuine duplicate field name that gets collapsed.
                if annot.get("/T"):
                    collapsed[field_id] = collapsed.get(field_id, 0) + 1
                continue
            seen_ids.add(field_id)

            field_type = _classify_field(annot)

            rect = annot.get("/Rect")
            rect_floats = [float(v) for v in rect] if rect and len(rect) == 4 else []

            entry: dict = {
                "field_id": field_id,
                "type": field_type,
                "page": page_num,
                "rect": rect_floats,
            }

            if field_type == "checkbox":
                entry.update(_extract_checkbox_values(annot))
            elif field_type == "radio":
                entry["radio_options"] = _extract_radio_options(annot, page_num)
            elif field_type == "choice":
                entry["choice_options"] = _extract_choice_options(annot)

            fields.append(entry)

    # Sort by page, then by vertical position (top of page = higher y in PDF coords,
    # so sort descending y0 for top-to-bottom), then by x0 left-to-right
    if collapsed:
        names = ", ".join(sorted(collapsed))
        typer.echo(
            f"Warning: {sum(collapsed.values())} duplicate field name(s) collapsed "
            f"({names}) — only the first occurrence per name is shown",
            err=True,
        )

    fields.sort(
        key=lambda f: (
            f["page"],
            -f["rect"][1] if len(f["rect"]) >= 2 else 0,
            f["rect"][0] if len(f["rect"]) >= 1 else 0,
        )
    )

    return fields


def field_info(
    file: Path = typer.Argument(..., help="Path to the PDF file."),
    output_json: bool = typer.Option(False, "--json", help="Output the field list as JSON."),
) -> None:
    """Show fill-planning metadata for every form field.

    Reports field_id, type, page, rect plus the values fill needs to know
    BEFORE writing: checkbox on/off values, radio options, choice options.
    Workflow: field-info -> fill --validate-only -> fill.
    """
    if not file.exists():
        typer.echo(f"Error: file not found: {file}", err=True)
        raise typer.Exit(code=1)

    ensure_input_size(file)
    ensure_not_encrypted(file)

    fields = extract_field_info(str(file))

    if output_json:
        typer.echo(json.dumps(fields, indent=2, ensure_ascii=False))
        return

    if not fields:
        typer.echo("No form fields found.")
        return

    for f in fields:
        extra = ""
        if f["type"] == "checkbox":
            extra = f' on="{f["checked_value"]}" off="{f["unchecked_value"]}"'
        elif f["type"] == "radio":
            options = ", ".join(o["value"] for o in f["radio_options"])
            extra = f" options: [{options}]"
        elif f["type"] == "choice":
            extra = f" options: [{', '.join(f['choice_options'])}]"
        rect = ", ".join(str(round(v, 1)) for v in f["rect"])
        typer.echo(f'[{f["type"]:<11}] "{f["field_id"]}" (page {f["page"]}) rect=[{rect}]{extra}')
