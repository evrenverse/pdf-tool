"""pdf-tool sign command — visual and cryptographic PDF signatures."""

import os
import stat
import sys
from io import BytesIO
from pathlib import Path

import typer
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

from pdf_tool.commands.common import atomic_output, ensure_input_size


def _apply_visual_signature(
    input_path: str,
    output_path: str,
    signature_path: str,
    page_num: int,
    x: float,
    y: float,
    width: float,
    height: float,
) -> None:
    """Place signature image on PDF page via reportlab overlay."""
    reader = PdfReader(input_path)
    writer = PdfWriter(clone_from=reader)

    for i, page in enumerate(writer.pages):
        if i == page_num:
            page_height = float(page.mediabox.height)
            page_width = float(page.mediabox.width)

            packet = BytesIO()
            c = canvas.Canvas(packet, pagesize=(page_width, page_height))
            # Convert top-left y to bottom-left y
            rl_y = page_height - y - height
            c.drawImage(
                signature_path,
                x,
                rl_y,
                width,
                height,
                preserveAspectRatio=True,
                mask="auto",
            )
            c.save()
            packet.seek(0)

            overlay = PdfReader(packet)
            page.merge_page(overlay.pages[0])

    with atomic_output(output_path) as tmp, open(tmp, "wb") as f:
        writer.write(f)


def _apply_crypto_signature(
    input_path: str,
    output_path: str,
    signature_path: str,
    page_num: int,
    x: float,
    y: float,
    width: float,
    height: float,
    certificate_path: str,
    passphrase: str,
) -> None:
    """Apply visual + cryptographic signature via pyHanko."""
    from pyhanko import stamp
    from pyhanko.pdf_utils import images
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import fields, signers

    signer = signers.SimpleSigner.load_pkcs12(
        pfx_file=certificate_path,
        passphrase=passphrase.encode() if passphrase else None,
    )

    with open(input_path, "rb") as inf:
        w = IncrementalPdfFileWriter(inf)

        page = w.prev.root["/Pages"]["/Kids"][page_num].get_object()
        media_box = page["/MediaBox"]
        page_height = float(media_box[3])

        rl_y = page_height - y - height

        fields.append_signature_field(
            w,
            sig_field_spec=fields.SigFieldSpec(
                "Signature1",
                box=(
                    round(x),
                    round(rl_y),
                    round(x + width),
                    round(rl_y + height),
                ),
                on_page=page_num,
            ),
        )

        meta = signers.PdfSignatureMetadata(field_name="Signature1")

        pdf_signer = signers.PdfSigner(
            meta,
            signer=signer,
            stamp_style=stamp.TextStampStyle(
                stamp_text="",
                background=images.PdfImage(signature_path),
            ),
        )

        # Atomic temp write: pyhanko still lazily reads the (open) input
        # while signing — writing directly to output_path == input_path
        # truncated the very file being read and destroyed it.
        with atomic_output(output_path) as tmp, open(tmp, "wb") as outf:
            pdf_signer.sign_pdf(w, output=outf)


def _certificate_passphrase(passphrase_file: Path | None, no_passphrase: bool) -> str:
    """Resolve a certificate passphrase without accepting it on the command line."""
    from_environment = os.environ.get("PDF_TOOL_CERT_PASSPHRASE")
    selected = sum((passphrase_file is not None, from_environment is not None, no_passphrase))
    if selected > 1:
        typer.echo(
            "Error: choose exactly one passphrase source: --passphrase-file, "
            "PDF_TOOL_CERT_PASSPHRASE, or --no-passphrase",
            err=True,
        )
        raise typer.Exit(code=1)

    if passphrase_file is not None:
        if not passphrase_file.is_file():
            typer.echo(f"Error: passphrase file not found: {passphrase_file}", err=True)
            raise typer.Exit(code=1)
        if os.name == "posix" and stat.S_IMODE(passphrase_file.stat().st_mode) & 0o077:
            typer.echo(
                "Error: passphrase file must not be readable by group or others (run chmod 600)",
                err=True,
            )
            raise typer.Exit(code=1)
        return passphrase_file.read_text(encoding="utf-8").rstrip("\r\n")

    if from_environment is not None:
        return from_environment
    if no_passphrase:
        return ""
    if sys.stdin.isatty():
        return typer.prompt("Certificate passphrase", hide_input=True)

    typer.echo(
        "Error: provide --passphrase-file, set PDF_TOOL_CERT_PASSPHRASE, or use --no-passphrase",
        err=True,
    )
    raise typer.Exit(code=1)


def sign(
    file: Path = typer.Argument(..., help="Path to the PDF file."),
    signature: Path = typer.Option(
        ..., "--signature", "-s", help="Path to signature image (transparent PNG)."
    ),
    page: int = typer.Option(..., "--page", "-p", help="Target page (0-indexed)."),
    position: str = typer.Option(
        ..., "--position", help="Position and size: x,y,w,h (top-left origin)."
    ),
    certificate: Path | None = typer.Option(
        None, "--certificate", "-c", help="PKCS#12 (.pfx/.p12) for cryptographic signature."
    ),
    passphrase_file: Path | None = typer.Option(
        None,
        "--passphrase-file",
        help="Read the certificate passphrase from a private file (mode 0600 on POSIX).",
    ),
    no_passphrase: bool = typer.Option(
        False,
        "--no-passphrase",
        help="The certificate intentionally has an empty passphrase.",
    ),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output file path."),
) -> None:
    """Place signature image and optionally apply cryptographic signature."""
    if not file.exists():
        typer.echo(f"Error: file not found: {file}", err=True)
        raise typer.Exit(code=1)
    ensure_input_size(file)

    if not signature.exists():
        typer.echo(f"Error: signature image not found: {signature}", err=True)
        raise typer.Exit(code=1)

    # Parse position
    try:
        parts = [float(p.strip()) for p in position.split(",")]
        if len(parts) != 4:
            raise ValueError
        x, y, w, h = parts
    except ValueError:
        typer.echo("Error: --position must be x,y,w,h (four numbers)", err=True)
        raise typer.Exit(code=1)

    # Validate page
    reader = PdfReader(str(file))
    total_pages = len(reader.pages)
    if page < 0 or page >= total_pages:
        typer.echo(f"Error: page {page} out of range (0-{total_pages - 1})", err=True)
        raise typer.Exit(code=1)

    output_path = str(output) if output else str(file)

    if certificate:
        if not certificate.exists():
            typer.echo(f"Error: certificate not found: {certificate}", err=True)
            raise typer.Exit(code=1)
        passphrase = _certificate_passphrase(passphrase_file, no_passphrase)
        try:
            _apply_crypto_signature(
                str(file),
                output_path,
                str(signature),
                page,
                x,
                y,
                w,
                h,
                str(certificate),
                passphrase,
            )
            typer.echo(
                f"Signed: {Path(output_path).name} "
                f"(visual + PAdES cryptographic signature on page {page})"
            )
        except Exception as e:
            typer.echo(f"Error: signing failed: {e}", err=True)
            raise typer.Exit(code=1)
    else:
        _apply_visual_signature(str(file), output_path, str(signature), page, x, y, w, h)
        typer.echo(f"Signed: {Path(output_path).name} (visual signature on page {page})")
