"""Tests for pdf-tool sign command."""

from typer.testing import CliRunner

from pdf_tool.cli import app

runner = CliRunner()


def test_sign_visual(simple_pdf, signature_png, tmp_path):
    output = tmp_path / "signed.pdf"
    result = runner.invoke(
        app,
        [
            "sign",
            str(simple_pdf),
            "--signature",
            str(signature_png),
            "--page",
            "1",
            "--position",
            "350,650,150,50",
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0
    assert "Signed:" in result.output or "signed" in result.output.lower()
    assert output.exists()
    assert output.stat().st_size > simple_pdf.stat().st_size


def test_sign_visual_verifiable(simple_pdf, signature_png, tmp_path):
    """Verify the signed PDF is a valid PDF."""
    output = tmp_path / "signed.pdf"
    runner.invoke(
        app,
        [
            "sign",
            str(simple_pdf),
            "--signature",
            str(signature_png),
            "--page",
            "0",
            "--position",
            "100,100,200,60",
            "--output",
            str(output),
        ],
    )
    from pypdf import PdfReader

    reader = PdfReader(str(output))
    assert len(reader.pages) == 2


def test_sign_missing_signature(simple_pdf):
    result = runner.invoke(
        app,
        [
            "sign",
            str(simple_pdf),
            "--signature",
            "nonexistent.png",
            "--page",
            "0",
            "--position",
            "100,100,200,60",
        ],
    )
    assert result.exit_code == 1


def test_sign_page_out_of_range(simple_pdf, signature_png):
    result = runner.invoke(
        app,
        [
            "sign",
            str(simple_pdf),
            "--signature",
            str(signature_png),
            "--page",
            "99",
            "--position",
            "100,100,200,60",
        ],
    )
    assert result.exit_code == 1


def test_sign_crypto_with_output(simple_pdf, signature_png, p12_certificate, tmp_path):
    output = tmp_path / "signed.pdf"
    result = runner.invoke(
        app,
        [
            "sign",
            str(simple_pdf),
            "--signature",
            str(signature_png),
            "--page",
            "0",
            "--position",
            "100,100,200,60",
            "--certificate",
            str(p12_certificate),
            "--output",
            str(output),
        ],
        env={"PDF_TOOL_CERT_PASSPHRASE": "test"},
    )
    assert result.exit_code == 0
    from pypdf import PdfReader

    reader = PdfReader(str(output))
    assert len(reader.pages) == 2
    assert "/AcroForm" in reader.trailer["/Root"]  # signature field present


def test_sign_crypto_in_place_keeps_valid_pdf(simple_pdf, signature_png, p12_certificate):
    """CRITICAL: in-place crypto sign must not destroy the file."""
    result = runner.invoke(
        app,
        [
            "sign",
            str(simple_pdf),
            "--signature",
            str(signature_png),
            "--page",
            "0",
            "--position",
            "100,100,200,60",
            "--certificate",
            str(p12_certificate),
        ],
        env={"PDF_TOOL_CERT_PASSPHRASE": "test"},
    )
    assert result.exit_code == 0
    from pypdf import PdfReader

    reader = PdfReader(str(simple_pdf))  # must still be a readable, signed PDF
    assert len(reader.pages) == 2
    assert "/AcroForm" in reader.trailer["/Root"]


def test_sign_does_not_accept_passphrase_on_command_line(simple_pdf, signature_png):
    result = runner.invoke(
        app,
        [
            "sign",
            str(simple_pdf),
            "--signature",
            str(signature_png),
            "--page",
            "0",
            "--position",
            "100,100,200,60",
            "--passphrase",
            "secret",
        ],
    )
    assert result.exit_code != 0
    assert "No such option" in result.output


def test_sign_visual_in_place(simple_pdf, signature_png):
    """In-place visual sign stays a valid PDF (atomic write)."""
    size_before = simple_pdf.stat().st_size
    result = runner.invoke(
        app,
        [
            "sign",
            str(simple_pdf),
            "--signature",
            str(signature_png),
            "--page",
            "0",
            "--position",
            "100,100,200,60",
        ],
    )
    assert result.exit_code == 0
    from pypdf import PdfReader

    reader = PdfReader(str(simple_pdf))
    assert len(reader.pages) == 2
    assert simple_pdf.stat().st_size > size_before
