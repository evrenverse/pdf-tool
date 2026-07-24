"""pdf-tool batch command — combined fill + write + sign operations."""

import json
import math
import shutil
import sys
import tempfile
from pathlib import Path

import typer
from pypdf import PdfReader

from pdf_tool.commands.common import (
    MAX_BATCH_ITEMS,
    atomic_output,
    ensure_input_size,
    ensure_json_size,
)


def _validate_sign_op(sign_data: object) -> str | None:
    """Validate the sign op object upfront; return an error message or None."""
    if not isinstance(sign_data, dict):
        return "sign: must be an object"
    for key in ("image", "page", "position"):
        if key not in sign_data:
            return f'sign: missing required key: "{key}"'
    page = sign_data["page"]
    if isinstance(page, bool) or not isinstance(page, int):
        return "sign.page: must be an integer (0-indexed)"
    pos = sign_data["position"]
    if (
        not isinstance(pos, list)
        or len(pos) != 4
        or any(
            isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v)
            for v in pos
        )
    ):
        return "sign.position: must be [x, y, w, h] (four numbers, top-left origin)"
    if pos[2] <= 0 or pos[3] <= 0:
        return "sign.position: width and height must be positive"
    if not Path(str(sign_data["image"])).exists():
        return f"sign.image not found: {sign_data['image']}"
    if "passphrase" in sign_data:
        return (
            "sign.passphrase is not accepted in JSON; use "
            "PDF_TOOL_CERT_PASSPHRASE or sign.no_passphrase"
        )
    if sign_data.get("no_passphrase") not in (None, True, False):
        return "sign.no_passphrase: must be a boolean"
    return None


def _run_fill_validation(current: str, fill_values: dict) -> None:
    """Validate fill values with the same hardening as the fill command.

    Raises typer.Exit(1) on unknown fields or invalid checkbox/radio values.
    """
    from PyPDFForm import PdfWrapper

    from pdf_tool.commands.fill import _check_field_values

    pdf = PdfWrapper(current)
    if not pdf.widgets:
        typer.echo("Error: fill requested but no form fields found", err=True)
        raise typer.Exit(code=1)

    available = set(pdf.widgets.keys())
    missing = [name for name in fill_values if name not in available]
    if missing:
        typer.echo(f'Error: unknown field: "{missing[0]}"', err=True)
        typer.echo(f"Available fields: {', '.join(sorted(available))}", err=True)
        raise typer.Exit(code=1)

    invalid = _check_field_values(current, fill_values, missing)
    if invalid:
        entry = invalid[0]
        allowed = ", ".join(json.dumps(a, ensure_ascii=False) for a in entry["allowed"])
        value_repr = json.dumps(entry["value"], ensure_ascii=False)
        typer.echo(
            f'Error: invalid value for "{entry["field"]}": {value_repr} (allowed: {allowed})',
            err=True,
        )
        raise typer.Exit(code=1)


def batch(
    file: Path = typer.Argument(..., help="Path to the PDF file."),
    operations: str = typer.Argument(
        ..., help="Path to JSON file with operations, or '-' for stdin."
    ),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output file path."),
    output_json: bool = typer.Option(
        False,
        "--json",
        help='Structured result: {"operations": [...], "count": N, "output": "..."}.',
    ),
) -> None:
    """Combined fill + write + sign in one atomic, all-or-nothing operation.

    The fill step applies the same validation + value normalization as the
    fill command (unknown fields and invalid checkbox/radio values abort);
    write and sign op objects are validated upfront.
    """
    if not file.exists():
        typer.echo(f"Error: file not found: {file}", err=True)
        raise typer.Exit(code=1)
    ensure_input_size(file)

    # Read operations
    if operations == "-":
        raw = sys.stdin.read()
    else:
        ops_path = Path(operations)
        if not ops_path.exists():
            typer.echo(f"Error: operations file not found: {operations}", err=True)
            raise typer.Exit(code=1)
        raw = ops_path.read_text()
    ensure_json_size(raw)

    try:
        ops = json.loads(raw)
    except json.JSONDecodeError as e:
        typer.echo(f"Error: invalid JSON: {e}", err=True)
        raise typer.Exit(code=1)

    if not isinstance(ops, dict):
        typer.echo("Error: JSON must be an object with fill/write/sign keys", err=True)
        raise typer.Exit(code=1)
    unknown = sorted(set(ops) - {"fill", "write", "sign"})
    if unknown:
        typer.echo(f'Error: unknown batch key: "{unknown[0]}"', err=True)
        raise typer.Exit(code=1)
    if "fill" in ops and not isinstance(ops["fill"], dict):
        typer.echo("Error: fill must be an object", err=True)
        raise typer.Exit(code=1)
    if "write" in ops and not isinstance(ops["write"], list):
        typer.echo("Error: write must be an array", err=True)
        raise typer.Exit(code=1)
    if "sign" in ops:
        error = _validate_sign_op(ops["sign"])
        if error is not None:
            typer.echo(f"Error: {error}", err=True)
            raise typer.Exit(code=1)
    if not any(ops.get(name) for name in ("fill", "write", "sign")):
        typer.echo("Error: batch contains no operations", err=True)
        raise typer.Exit(code=1)
    fill_count = len(ops.get("fill", {})) if isinstance(ops.get("fill"), dict) else 0
    write_count = len(ops.get("write", [])) if isinstance(ops.get("write"), list) else 0
    sign_count = 1 if ops.get("sign") else 0
    if fill_count + write_count + sign_count > MAX_BATCH_ITEMS:
        typer.echo(f"Error: batch exceeds {MAX_BATCH_ITEMS} operations", err=True)
        raise typer.Exit(code=2)

    # Upfront op validation (all-or-nothing: nothing runs on a bad op object)
    if ops.get("write"):
        from pdf_tool.commands.write import _validate_overlays

        total_pages = len(PdfReader(str(file)).pages)
        error = _validate_overlays(ops["write"], total_pages)
        if error is not None:
            typer.echo(f"Error: {error}", err=True)
            raise typer.Exit(code=1)
    output_path = str(output) if output else str(file)
    op_count = 0
    summary = []

    with tempfile.TemporaryDirectory() as tmpdir:
        current = str(file)

        # Step 1: Fill (same hardening + normalization as the fill command)
        if ops.get("fill"):
            from PyPDFForm import PdfWrapper

            from pdf_tool.commands.fill import _normalize_field_values

            _run_fill_validation(current, ops["fill"])
            pdf = PdfWrapper(current)
            pdf.fill(_normalize_field_values(current, ops["fill"]))
            next_path = str(Path(tmpdir) / "after_fill.pdf")
            pdf.write(next_path)
            current = next_path
            op_count += 1
            summary.append(f"Filled: {len(ops['fill'])} form fields")

        # Step 2: Write
        if ops.get("write"):
            from pdf_tool.commands.write import _apply_overlays

            next_path = str(Path(tmpdir) / "after_write.pdf")
            _apply_overlays(current, ops["write"], next_path)
            current = next_path
            op_count += 1
            summary.append(f"Written: {len(ops['write'])} text overlays")

        # Step 3: Sign
        if ops.get("sign"):
            sign_data = ops["sign"]
            img = sign_data["image"]
            pg = sign_data["page"]
            pos = sign_data["position"]
            next_path = str(Path(tmpdir) / "after_sign.pdf")

            if "certificate" in sign_data:
                from pdf_tool.commands.sign import (
                    _apply_crypto_signature,
                    _certificate_passphrase,
                )

                passphrase = _certificate_passphrase(
                    None,
                    bool(sign_data.get("no_passphrase", False)),
                )

                _apply_crypto_signature(
                    current,
                    next_path,
                    img,
                    pg,
                    pos[0],
                    pos[1],
                    pos[2],
                    pos[3],
                    sign_data["certificate"],
                    passphrase,
                )
                op_count += 1
                summary.append(f"Signed: visual + PAdES cryptographic on page {pg}")
            else:
                from pdf_tool.commands.sign import _apply_visual_signature

                _apply_visual_signature(current, next_path, img, pg, pos[0], pos[1], pos[2], pos[3])
                op_count += 1
                summary.append(f"Signed: visual on page {pg}")

            current = next_path

        # Copy final result to output (atomic)
        with atomic_output(output_path) as tmp:
            shutil.copy2(current, tmp)

    if output_json:
        envelope = {
            "operations": summary,
            "count": op_count,
            "output": Path(output_path).name,
        }
        typer.echo(json.dumps(envelope, indent=2, ensure_ascii=False))
    else:
        typer.echo(f"Batch: {op_count} operations on {Path(output_path).name}")
        for line in summary:
            typer.echo(f"  - {line}")
