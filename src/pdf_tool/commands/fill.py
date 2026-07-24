"""pdf-tool fill command — fill AcroForm fields by name."""

import json
import sys
from pathlib import Path

import typer
from pypdf import PdfReader
from PyPDFForm import PdfWrapper

from pdf_tool.commands.common import (
    atomic_output,
    ensure_input_size,
    ensure_json_size,
    walk_field_chain,
)
from pdf_tool.commands.field_info import extract_field_info
from pdf_tool.commands.validation import check_bounding_boxes


def _normalize_field_value(field: dict, value: object) -> object:
    """Map an accepted user value to the form PyPDFForm needs for filling.

    Single source of truth for the validate/fill contract: a value is valid
    if and only if this normalization yields something PyPDFForm fills to
    exactly the validated state.

    - checkbox: on-value string -> True, off-value string ("Off") -> False
      (PyPDFForm coerces ANY non-empty raw string to truthy, so strings must
      never reach it), booleans pass through
    - radio: option export-value string -> 0-based int index (PyPDFForm
      selects radios by index; a raw export string silently no-ops),
      int indices pass through
    - everything else: unchanged
    """
    if field["type"] == "checkbox" and isinstance(value, str):
        if value == field["checked_value"]:
            return True
        if value == field["unchecked_value"]:
            return False
    elif field["type"] == "radio" and isinstance(value, str):
        options = [o["value"] for o in field["radio_options"]]
        if value in options:
            return options.index(value)
    return value


def _normalize_field_values(file_path: str, field_values: dict) -> dict:
    """Apply :func:`_normalize_field_value` to every known field in the dict."""
    info = {f["field_id"]: f for f in extract_field_info(file_path)}
    return {
        name: (_normalize_field_value(info[name], value) if name in info else value)
        for name, value in field_values.items()
    }


def _check_field_values(file_path: str, field_values: dict, missing: list[str]) -> list[dict]:
    """Validate checkbox/radio values against their allowed on-values/options.

    Returns a list of ``{"field": ..., "value": ..., "allowed": [...]}`` dicts.
    Text and choice fields accept any value. A value counts as valid exactly
    when :func:`_normalize_field_value` turns it into a well-typed fill value
    (bool for checkboxes, in-range int index for radios) — the same
    normalization the fill path applies before writing.
    """
    info = {f["field_id"]: f for f in extract_field_info(file_path)}
    invalid: list[dict] = []
    for name, value in field_values.items():
        if name in missing:
            continue
        field = info.get(name)
        if field is None:
            continue
        normalized = _normalize_field_value(field, value)
        if field["type"] == "checkbox":
            allowed = [True, False, field["checked_value"], field["unchecked_value"]]
            if not isinstance(normalized, bool):
                invalid.append({"field": name, "value": value, "allowed": allowed})
        elif field["type"] == "radio":
            options = [o["value"] for o in field["radio_options"]]
            indices = list(range(len(options)))
            is_index = (
                isinstance(normalized, int)
                and not isinstance(normalized, bool)
                and normalized in indices
            )
            if not is_index:
                invalid.append({"field": name, "value": value, "allowed": options + indices})
    return invalid


def _extract_field_boxes(file_path: str) -> list[dict]:
    """Extract bounding boxes from PDF form field annotations via pypdf."""
    fields: list[dict] = []
    reader = PdfReader(file_path)
    for page_num, page in enumerate(reader.pages):
        for annot_ref in page.get("/Annots", []):
            annot = annot_ref.get_object()
            if annot.get("/Subtype") != "/Widget":
                continue
            rect = annot.get("/Rect")
            if not rect or len(rect) != 4:
                continue
            bbox = [float(v) for v in rect]
            parts = [str(node.get("/T")) for node in walk_field_chain(annot) if node.get("/T")]
            parts.reverse()
            fields.append(
                {
                    "name": ".".join(parts),
                    "entry_bounding_box": bbox,
                    "page_number": page_num,
                }
            )
    return fields


def fill(
    file: Path = typer.Argument(..., help="Path to the PDF file."),
    changes: str = typer.Argument(
        ..., help="Path to JSON file with field values, or '-' for stdin."
    ),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output file path."),
    flatten: bool = typer.Option(False, "--flatten", help="Lock fields after filling."),
    validate_only: bool = typer.Option(
        False,
        "--validate-only",
        help=(
            "Check the values JSON against the form WITHOUT writing anything: "
            "field existence plus checkbox/radio allowed values (see field-info). "
            "--output and --flatten are ignored in this mode. Exit 0 only if "
            "every field is valid. Combine with --json for machine-readable "
            "verdicts. Validate-OK guarantees fill produces exactly the "
            "validated state."
        ),
    ),
    output_json: bool = typer.Option(
        False,
        "--json",
        help=(
            'Structured JSON result: {"filled"/"valid": [...], "missing": [...], '
            '"invalid_value": [{"field", "value", "allowed"}], "warnings": [...]}.'
        ),
    ),
) -> None:
    """Fill AcroForm fields by name.

    Use 'pdf-tool field-info' to discover field names, checkbox on-values and
    radio options first, and 'fill --validate-only' to dry-run the values JSON
    before writing. Checkbox on/off strings (e.g. "Yes"/"Off") and radio
    option export values (e.g. "1") are normalized to the bool/index form the
    PDF needs, so "Off" really unchecks and an export value really selects —
    in both normal fill and validate mode. Field names come from the PDF's
    widget list; type metadata from the annotation tree (field-info).
    """
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
        raw = changes_path.read_text()
    ensure_json_size(raw)

    try:
        field_values = json.loads(raw)
    except json.JSONDecodeError as e:
        typer.echo(f"Error: invalid JSON: {e}", err=True)
        raise typer.Exit(code=1)

    if not isinstance(field_values, dict):
        typer.echo("Error: JSON must be an object with field names as keys", err=True)
        raise typer.Exit(code=1)

    # Open PDF and check for form fields
    try:
        pdf = PdfWrapper(str(file))
    except Exception as e:
        typer.echo(f"Error: cannot open PDF: {e}", err=True)
        raise typer.Exit(code=1)

    if not pdf.widgets:
        if output_json:
            envelope = {
                "valid" if validate_only else "filled": [],
                "missing": list(field_values),
                "invalid_value": [],
                "warnings": [],
                "error": "no form fields found in this PDF; "
                'use "pdf-tool write" to place text at coordinates instead',
            }
            typer.echo(json.dumps(envelope, indent=2, ensure_ascii=False))
        else:
            typer.echo(
                "Error: no form fields found in this PDF.\n"
                'Hint: use "pdf-tool write" to place text at coordinates instead.',
                err=True,
            )
        raise typer.Exit(code=1)

    # Pre-validate bounding boxes (warnings only)
    warnings: list[str] = []
    try:
        field_boxes = _extract_field_boxes(str(file))
        warnings = check_bounding_boxes(field_boxes)
    except Exception:
        pass  # Validation is best-effort, never block filling
    if not output_json:
        for warning in warnings:
            typer.echo(f"Warning: {warning}", err=True)

    available = set(pdf.widgets.keys())
    missing = [name for name in field_values if name not in available]

    if validate_only:
        invalid = _check_field_values(str(file), field_values, missing)
        invalid_names = {entry["field"] for entry in invalid}
        valid = [n for n in field_values if n not in missing and n not in invalid_names]
        success = not missing and not invalid
        if output_json:
            envelope = {
                "valid": valid,
                "missing": missing,
                "invalid_value": invalid,
                "warnings": warnings,
            }
            typer.echo(json.dumps(envelope, indent=2, ensure_ascii=False))
        else:
            by_name = {entry["field"]: entry for entry in invalid}
            for name in field_values:
                if name in missing:
                    typer.echo(f"Missing: {name}")
                elif name in by_name:
                    entry = by_name[name]
                    allowed = ", ".join(json.dumps(a, ensure_ascii=False) for a in entry["allowed"])
                    value_repr = json.dumps(entry["value"], ensure_ascii=False)
                    typer.echo(f"Invalid value: {name} = {value_repr} (allowed: {allowed})")
                else:
                    typer.echo(f"Valid: {name}")
            typer.echo(
                f"Validated {len(field_values)} fields: {len(valid)} valid, "
                f"{len(missing)} missing, {len(invalid)} invalid — nothing written"
            )
        raise typer.Exit(code=0 if success else 1)

    # Validate field names (normal fill: any unknown field aborts, nothing written)
    if missing:
        if output_json:
            envelope = {
                "filled": [],
                "missing": missing,
                "invalid_value": [],
                "warnings": warnings,
            }
            typer.echo(json.dumps(envelope, indent=2, ensure_ascii=False))
        else:
            typer.echo(f'Error: unknown field: "{missing[0]}"', err=True)
            typer.echo(f"Available fields: {', '.join(sorted(available))}", err=True)
        raise typer.Exit(code=1)

    # Fill fields — normalize first (same mapping --validate-only accepts):
    # checkbox on/off strings -> bool, radio export values -> int index
    pdf.fill(_normalize_field_values(str(file), field_values), flatten=flatten)

    output_path = str(output) if output else str(file)
    with atomic_output(output_path) as tmp:
        pdf.write(str(tmp))

    # Output summary
    if output_json:
        envelope = {
            "filled": list(field_values),
            "missing": [],
            "invalid_value": [],
            "warnings": warnings,
        }
        typer.echo(json.dumps(envelope, indent=2, ensure_ascii=False))
    else:
        typer.echo(f"Filled: {len(field_values)} fields in {Path(output_path).name}")
        for name, value in field_values.items():
            typer.echo(f"  - {name} = {json.dumps(value, ensure_ascii=False)}")
