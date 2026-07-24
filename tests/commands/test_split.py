"""Tests for pdf-tool split command (0-indexed pages, like read/find)."""

import json

from pypdf import PdfReader
from typer.testing import CliRunner

from pdf_tool.cli import app

runner = CliRunner()


def test_split_into_individual_pages(multipage_pdf, tmp_path):
    """Split a 5-page PDF into individual page files named by 0-indexed page."""
    output_dir = tmp_path / "pages"
    result = runner.invoke(app, ["split", str(multipage_pdf), "--output-dir", str(output_dir)])
    assert result.exit_code == 0
    assert output_dir.exists()
    page_files = sorted(output_dir.glob("page_*.pdf"))
    assert len(page_files) == 5
    assert [p.name for p in page_files] == [f"page_{i}.pdf" for i in range(5)]
    for pf in page_files:
        reader = PdfReader(str(pf))
        assert len(reader.pages) == 1
    assert "Split 5 pages" in result.output


def test_split_extract_range_zero_indexed(multipage_pdf, tmp_path):
    """--pages 0-2 extracts the FIRST three pages (0-indexed, like read/find)."""
    output = tmp_path / "range.pdf"
    result = runner.invoke(
        app, ["split", str(multipage_pdf), "--pages", "0-2", "--output", str(output)]
    )
    assert result.exit_code == 0
    reader = PdfReader(str(output))
    assert len(reader.pages) == 3
    # page 0 of the source contains "Page 1 Title"
    assert "Page 1 Title" in reader.pages[0].extract_text()
    assert "Page 3 Title" in reader.pages[2].extract_text()


def test_split_extract_scattered_pages(multipage_pdf, tmp_path):
    """Comma lists work like read --pages."""
    output = tmp_path / "scattered.pdf"
    result = runner.invoke(
        app, ["split", str(multipage_pdf), "--pages", "0,2,4", "--output", str(output)]
    )
    assert result.exit_code == 0
    reader = PdfReader(str(output))
    assert len(reader.pages) == 3
    assert "Page 5 Title" in reader.pages[2].extract_text()


def test_split_single_page_token(multipage_pdf, tmp_path):
    """A single page number works (formerly raised raw ValueError)."""
    output = tmp_path / "single.pdf"
    result = runner.invoke(
        app, ["split", str(multipage_pdf), "--pages", "3", "--output", str(output)]
    )
    assert result.exit_code == 0
    reader = PdfReader(str(output))
    assert len(reader.pages) == 1
    assert "Page 4 Title" in reader.pages[0].extract_text()


def test_split_out_of_range_errors(multipage_pdf, tmp_path):
    """Out-of-range pages error cleanly (formerly silent empty PDF, exit 0)."""
    output = tmp_path / "oops.pdf"
    result = runner.invoke(
        app, ["split", str(multipage_pdf), "--pages", "7-9", "--output", str(output)]
    )
    assert result.exit_code == 1
    assert "out of range" in result.output.lower()
    assert not output.exists()


def test_split_invalid_token_errors(multipage_pdf, tmp_path):
    output = tmp_path / "oops.pdf"
    result = runner.invoke(
        app, ["split", str(multipage_pdf), "--pages", "abc", "--output", str(output)]
    )
    assert result.exit_code == 1
    assert "invalid" in result.output.lower()
    assert not output.exists()


def test_split_preserves_form_fields(acroform_pdf, tmp_path):
    """Splitting keeps the AcroForm — fields stay visible to standard tools."""
    output = tmp_path / "page0.pdf"
    result = runner.invoke(
        app, ["split", str(acroform_pdf), "--pages", "0", "--output", str(output)]
    )
    assert result.exit_code == 0
    # Document-level /AcroForm must survive (standard tools resolve fields via it)
    acro_fields = PdfReader(str(output)).get_fields()
    assert acro_fields is not None
    assert "Company" in acro_fields
    info = runner.invoke(app, ["read", str(output), "--fields", "Company,Terms", "--json"])
    assert info.exit_code == 0
    data = json.loads(info.output)
    assert data["missing"] == []


def test_split_encrypted_pdf_clean_error(encrypted_pdf, tmp_path):
    result = runner.invoke(
        app, ["split", str(encrypted_pdf), "--output-dir", str(tmp_path / "pages")]
    )
    assert result.exit_code == 1
    assert "encrypted" in result.output.lower()


def test_split_missing_options(simple_pdf):
    result = runner.invoke(app, ["split", str(simple_pdf)])
    assert result.exit_code == 1
    assert "provide" in result.output.lower() or "error" in result.output.lower()


def test_split_nonexistent_file(tmp_path):
    output_dir = tmp_path / "pages"
    result = runner.invoke(app, ["split", "nonexistent.pdf", "--output-dir", str(output_dir)])
    assert result.exit_code == 1
    assert "not found" in result.output.lower() or "error" in result.output.lower()
