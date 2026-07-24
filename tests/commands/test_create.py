"""Tests for pdf-tool create command (Markdown -> clean PDF)."""

import pdfplumber
from pypdf import PdfReader
from typer.testing import CliRunner

from pdf_tool.cli import app

runner = CliRunner()


def _text(path) -> str:
    with pdfplumber.open(str(path)) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages)


def test_create_from_markdown_file(tmp_path):
    """Render a markdown file into a PDF that exists and carries the text."""
    md = tmp_path / "doc.md"
    md.write_text("# Proposal\n\nSehr geehrte Damen und Herren,\n\nwir bieten an.\n")
    out = tmp_path / "doc.pdf"
    result = runner.invoke(app, ["create", str(out), str(md)])
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert len(PdfReader(str(out)).pages) >= 1
    text = _text(out)
    assert "Proposal" in text
    assert "Sehr geehrte Damen und Herren" in text


def test_create_preserves_umlauts_and_euro(tmp_path):
    """The whole point: ä/ö/ü/ß and € survive — never transliterated to ae/oe/ue."""
    md = tmp_path / "u.md"
    md.write_text("# Größe\n\nGeschäftsführer Mörike, Straße 1, Gebühr 1.234,56 €.\n")
    out = tmp_path / "u.pdf"
    result = runner.invoke(app, ["create", str(out), str(md)])
    assert result.exit_code == 0, result.output
    text = _text(out)
    assert "Größe" in text
    assert "Geschäftsführer" in text
    assert "Straße" in text
    assert "€" in text
    # Regression guard: no ASCII transliteration leaked in.
    assert "Geschaeftsfuehrer" not in text
    assert "Strasse" not in text


def test_create_from_stdin(tmp_path):
    """Markdown via stdin ('-') instead of a file."""
    out = tmp_path / "s.pdf"
    result = runner.invoke(app, ["create", str(out), "-"], input="## Titel\n\nInhalt über alles.\n")
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert "Titel" in _text(out)


def test_create_lists_and_table(tmp_path):
    """Bullet list + pipe table render and their cell text is present."""
    md = tmp_path / "t.md"
    md.write_text(
        "## References\n\n"
        "- Project A\n- Project B\n\n"
        "| Customer | Year |\n| --- | --- |\n| Example City | 2025 |\n"
    )
    out = tmp_path / "t.pdf"
    result = runner.invoke(app, ["create", str(out), str(md)])
    assert result.exit_code == 0, result.output
    text = _text(out)
    assert "Project A" in text and "Project B" in text
    assert "Example City" in text and "2025" in text


def test_create_bold_does_not_leak_markup(tmp_path):
    """Inline **bold**/*italic* must not leave literal asterisks in the output."""
    md = tmp_path / "b.md"
    md.write_text("Das ist **wichtig** und *kursiv*.\n")
    out = tmp_path / "b.pdf"
    result = runner.invoke(app, ["create", str(out), str(md)])
    assert result.exit_code == 0, result.output
    text = _text(out)
    assert "wichtig" in text and "kursiv" in text
    assert "**" not in text


def test_create_missing_source(tmp_path):
    """A nonexistent source file is a clean error exit, not a traceback."""
    out = tmp_path / "x.pdf"
    result = runner.invoke(app, ["create", str(out), str(tmp_path / "nope.md")])
    assert result.exit_code == 1
    assert "not found" in result.output.lower() or "error" in result.output.lower()
