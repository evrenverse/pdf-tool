"""Tests for pdf-tool merge command."""

from pypdf import PdfReader
from typer.testing import CliRunner

from pdf_tool.cli import app

runner = CliRunner()


def test_merge_two_pdfs(simple_pdf, tmp_path):
    """Merge two copies of the same PDF → output has double the pages."""
    output = tmp_path / "merged.pdf"
    result = runner.invoke(
        app, ["merge", str(simple_pdf), str(simple_pdf), "--output", str(output)]
    )
    assert result.exit_code == 0
    assert output.exists()
    reader = PdfReader(str(output))
    original = PdfReader(str(simple_pdf))
    assert len(reader.pages) == len(original.pages) * 2
    assert "Merged 2 files" in result.output


def test_merge_three_pdfs(simple_pdf, multipage_pdf, tmp_path):
    """Merge three PDFs with different page counts."""
    output = tmp_path / "merged.pdf"
    result = runner.invoke(
        app,
        [
            "merge",
            str(simple_pdf),
            str(multipage_pdf),
            str(simple_pdf),
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0
    reader = PdfReader(str(output))
    # simple_pdf=2 pages, multipage_pdf=5 pages, simple_pdf=2 pages → 9 total
    assert len(reader.pages) == 9
    assert "Merged 3 files" in result.output


def test_merge_nonexistent_file(simple_pdf, tmp_path):
    """Merge with a nonexistent file → error exit."""
    output = tmp_path / "merged.pdf"
    result = runner.invoke(
        app, ["merge", str(simple_pdf), "nonexistent.pdf", "--output", str(output)]
    )
    assert result.exit_code == 1
    assert "not found" in result.output.lower() or "error" in result.output.lower()


def test_merge_preserves_form_fields(acroform_pdf, simple_pdf, tmp_path):
    """Merging keeps the AcroForm — form fields survive for standard tools."""
    import json

    output = tmp_path / "merged.pdf"
    result = runner.invoke(
        app, ["merge", str(acroform_pdf), str(simple_pdf), "--output", str(output)]
    )
    assert result.exit_code == 0
    # Document-level /AcroForm must survive (standard tools resolve fields via it)
    acro_fields = PdfReader(str(output)).get_fields()
    assert acro_fields is not None
    assert {"Company", "Terms"} <= set(acro_fields)
    # and the pdf-tool fast path still sees them
    fields = runner.invoke(app, ["read", str(output), "--fields", "Company,Terms", "--json"])
    assert fields.exit_code == 0
    assert json.loads(fields.output)["missing"] == []


def test_merge_encrypted_input_clean_error(simple_pdf, encrypted_pdf, tmp_path):
    output = tmp_path / "merged.pdf"
    result = runner.invoke(
        app, ["merge", str(simple_pdf), str(encrypted_pdf), "--output", str(output)]
    )
    assert result.exit_code == 1
    assert "encrypted" in result.output.lower()
    assert not output.exists()
