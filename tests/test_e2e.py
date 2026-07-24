"""End-to-end test: full agent workflow with pdf-tool."""

import json

import pdfplumber
from typer.testing import CliRunner

from pdf_tool.cli import app

runner = CliRunner()


def test_e2e_form_workflow(form_pdf, tmp_path):
    """Simulate: info → fill → read → verify."""
    # 1. Info
    result = runner.invoke(app, ["info", str(form_pdf), "--json"])
    assert result.exit_code == 0
    info = json.loads(result.output)
    assert len(info["form_fields"]) >= 2

    # 2. Fill
    filled = tmp_path / "filled.pdf"
    changes = json.dumps({"Company": "E2E Example LLC", "Date": "04.03.2026"})
    result = runner.invoke(
        app, ["fill", str(form_pdf), "-", "--output", str(filled)], input=changes
    )
    assert result.exit_code == 0

    # 3. Read back
    result = runner.invoke(app, ["read", str(filled), "--page", "0", "--json"])
    assert result.exit_code == 0


def test_e2e_overlay_workflow(simple_pdf, signature_png, tmp_path):
    """Simulate: info → read → write → sign → verify."""
    # 1. Info — no form fields
    result = runner.invoke(app, ["info", str(simple_pdf), "--json"])
    assert result.exit_code == 0
    info = json.loads(result.output)
    assert len(info["form_fields"]) == 0

    # 2. Read to get positions
    result = runner.invoke(app, ["read", str(simple_pdf), "--page", "0", "--json"])
    assert result.exit_code == 0
    page_data = json.loads(result.output)
    assert len(page_data["words"]) > 0

    # 3. Write text at positions
    written = tmp_path / "written.pdf"
    overlays = json.dumps(
        [
            {"page": 0, "x": 200, "y": 150, "text": "Example LLC"},
            {"page": 0, "x": 200, "y": 200, "text": "04.03.2026"},
        ]
    )
    result = runner.invoke(
        app, ["write", str(simple_pdf), "-", "--output", str(written)], input=overlays
    )
    assert result.exit_code == 0

    # 4. Sign
    signed = tmp_path / "signed.pdf"
    result = runner.invoke(
        app,
        [
            "sign",
            str(written),
            "--signature",
            str(signature_png),
            "--page",
            "1",
            "--position",
            "350,650,150,50",
            "--output",
            str(signed),
        ],
    )
    assert result.exit_code == 0

    # 5. Verify
    with pdfplumber.open(str(signed)) as pdf:
        assert len(pdf.pages) == 2
        text = pdf.pages[0].extract_text()
        assert "Example LLC" in text


def test_e2e_batch_workflow(form_pdf, signature_png, tmp_path):
    """Simulate: batch with fill + write + sign."""
    output = tmp_path / "batched.pdf"
    ops = json.dumps(
        {
            "fill": {"Company": "Batch E2E LLC"},
            "write": [{"page": 0, "x": 300, "y": 300, "text": "Extra info"}],
            "sign": {
                "image": str(signature_png),
                "page": 0,
                "position": [350, 650, 150, 50],
            },
        }
    )
    result = runner.invoke(app, ["batch", str(form_pdf), "-", "--output", str(output)], input=ops)
    assert result.exit_code == 0
    assert output.exists()
