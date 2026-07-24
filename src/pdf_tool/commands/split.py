"""Split PDF into individual pages or page selections (0-indexed)."""

from pathlib import Path

import typer
from pypdf import PdfReader, PdfWriter

from pdf_tool.commands.common import atomic_output, ensure_input_size, ensure_not_encrypted
from pdf_tool.commands.read import _parse_pages_spec


def split(
    file: Path = typer.Argument(..., help="Path to the PDF file."),
    output_dir: Path | None = typer.Option(
        None, "--output-dir", help="Directory for individual pages (page_<n>.pdf, 0-indexed)."
    ),
    pages: str | None = typer.Option(
        None,
        "--pages",
        help=(
            "Pages to extract, 0-indexed like read/find: '0,2,5' or '0-3,7' "
            "(comma lists + inclusive ranges)."
        ),
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Output file for the extracted pages."
    ),
) -> None:
    """Split PDF into individual pages or extract a page selection (0-indexed)."""
    if not file.exists():
        typer.echo(f"Error: {file} not found", err=True)
        raise typer.Exit(1)

    ensure_input_size(file)
    ensure_not_encrypted(file)
    reader = PdfReader(str(file))
    total_pages = len(reader.pages)

    if pages and output:
        try:
            page_list = _parse_pages_spec(pages, total_pages)
        except ValueError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1)
        writer = PdfWriter()
        # append() (vs add_page) keeps document-level structures like /AcroForm
        writer.append(reader, pages=page_list)
        with atomic_output(output) as tmp, open(tmp, "wb") as f:
            writer.write(f)
        typer.echo(f"Extracted {len(page_list)} pages ({pages}) -> {output}")
    elif output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        for i in range(total_pages):
            writer = PdfWriter()
            writer.append(reader, pages=[i])
            out_path = output_dir / f"page_{i}.pdf"
            with atomic_output(out_path) as tmp, open(tmp, "wb") as f:
                writer.write(f)
        typer.echo(f"Split {total_pages} pages -> {output_dir}")
    else:
        typer.echo("Error: provide --output-dir or --pages + --output", err=True)
        raise typer.Exit(1)
