"""Merge multiple PDF files into one."""

from pathlib import Path
from typing import Annotated

import typer
from pypdf import PdfReader, PdfWriter

from pdf_tool.commands.common import atomic_output, ensure_input_size, ensure_not_encrypted


def merge(
    files: Annotated[list[Path], typer.Argument(help="PDF files to merge.")],
    output: Path = typer.Option(..., "--output", "-o", help="Output file path."),
) -> None:
    """Merge multiple PDFs into a single file (form fields are preserved)."""
    writer = PdfWriter()
    total_pages = 0

    for file_path in files:
        if not file_path.exists():
            typer.echo(f"Error: {file_path} not found", err=True)
            raise typer.Exit(1)
        ensure_input_size(file_path)
        ensure_not_encrypted(file_path)
        reader = PdfReader(str(file_path))
        # append() (vs add_page) keeps document-level structures like /AcroForm
        writer.append(reader)
        total_pages += len(reader.pages)

    with atomic_output(output) as tmp, open(tmp, "wb") as f:
        writer.write(f)

    typer.echo(f"Merged {len(files)} files ({total_pages} pages) -> {output}")
