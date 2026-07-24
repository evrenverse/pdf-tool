"""Tests for pdf-tool fill command."""

import json

import pytest
from typer.testing import CliRunner

from pdf_tool.cli import app

runner = CliRunner()


def test_fill_text_fields(form_pdf, tmp_path):
    output = tmp_path / "filled.pdf"
    changes = json.dumps({"Company": "Example LLC", "Date": "01.01.2026"})
    result = runner.invoke(
        app, ["fill", str(form_pdf), "-", "--output", str(output)], input=changes
    )
    assert result.exit_code == 0
    assert "Filled:" in result.output or "filled" in result.output.lower()
    assert output.exists()


def test_fill_checkbox(form_pdf, tmp_path):
    output = tmp_path / "filled.pdf"
    changes = json.dumps({"TermsAccepted": True})
    result = runner.invoke(
        app, ["fill", str(form_pdf), "-", "--output", str(output)], input=changes
    )
    assert result.exit_code == 0


def test_fill_from_file(form_pdf, tmp_path):
    output = tmp_path / "filled.pdf"
    changes_file = tmp_path / "changes.json"
    changes_file.write_text(json.dumps({"Company": "File LLC"}))
    result = runner.invoke(app, ["fill", str(form_pdf), str(changes_file), "--output", str(output)])
    assert result.exit_code == 0


def test_fill_no_form_fields(simple_pdf):
    changes = json.dumps({"Company": "Example LLC"})
    result = runner.invoke(app, ["fill", str(simple_pdf), "-"], input=changes)
    assert result.exit_code == 1
    assert "no form fields" in result.output.lower() or "write" in result.output.lower()


def test_fill_flatten(form_pdf, tmp_path):
    output = tmp_path / "filled.pdf"
    changes = json.dumps({"Company": "Example LLC"})
    result = runner.invoke(
        app, ["fill", str(form_pdf), "-", "--output", str(output), "--flatten"], input=changes
    )
    assert result.exit_code == 0


# --- --validate-only / --json tests ---


@pytest.fixture
def radio_form_pdf(tmp_path):
    """PDF with a two-option radio group 'Anrede'."""
    from io import BytesIO

    from PyPDFForm import Fields, PdfWrapper
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    path = tmp_path / "radio.pdf"
    packet = BytesIO()
    c = canvas.Canvas(packet, pagesize=A4)
    c.drawString(50, 700, "Anrede:")
    c.save()
    packet.seek(0)
    wrapper = PdfWrapper(packet)
    wrapper.bulk_create_fields(
        [
            Fields.RadioGroup(
                name="Anrede",
                page_number=1,
                x=[100.0, 150.0],
                y=[500.0, 500.0],
            )
        ]
    )
    wrapper.write(str(path))
    return path


def test_validate_only_all_valid(form_pdf):
    before = form_pdf.read_bytes()
    changes = json.dumps({"Company": "Example LLC", "TermsAccepted": True})
    result = runner.invoke(app, ["fill", str(form_pdf), "-", "--validate-only"], input=changes)
    assert result.exit_code == 0
    assert "Valid: Company" in result.output
    assert "Valid: TermsAccepted" in result.output
    assert "nothing written" in result.output
    assert form_pdf.read_bytes() == before  # input untouched


def test_validate_only_never_writes_output(form_pdf, tmp_path):
    output = tmp_path / "out.pdf"
    changes = json.dumps({"Company": "Example LLC"})
    result = runner.invoke(
        app,
        ["fill", str(form_pdf), "-", "--validate-only", "--output", str(output)],
        input=changes,
    )
    assert result.exit_code == 0
    assert not output.exists()


def test_validate_only_missing_field(form_pdf):
    changes = json.dumps({"NichtDa": "x"})
    result = runner.invoke(app, ["fill", str(form_pdf), "-", "--validate-only"], input=changes)
    assert result.exit_code == 1
    assert "Missing: NichtDa" in result.output


def test_validate_only_invalid_checkbox_value(form_pdf):
    changes = json.dumps({"TermsAccepted": "Maybe"})
    result = runner.invoke(app, ["fill", str(form_pdf), "-", "--validate-only"], input=changes)
    assert result.exit_code == 1
    assert "Invalid value" in result.output
    assert "TermsAccepted" in result.output
    assert "Yes" in result.output  # allowed values listed


def test_validate_only_checkbox_string_on_value_ok(form_pdf):
    changes = json.dumps({"TermsAccepted": "Yes"})
    result = runner.invoke(app, ["fill", str(form_pdf), "-", "--validate-only"], input=changes)
    assert result.exit_code == 0


def test_validate_only_radio_index_ok(radio_form_pdf):
    changes = json.dumps({"Anrede": 1})
    result = runner.invoke(
        app, ["fill", str(radio_form_pdf), "-", "--validate-only"], input=changes
    )
    assert result.exit_code == 0


def test_validate_only_radio_invalid(radio_form_pdf):
    changes = json.dumps({"Anrede": 5})
    result = runner.invoke(
        app, ["fill", str(radio_form_pdf), "-", "--validate-only", "--json"], input=changes
    )
    assert result.exit_code == 1
    data = json.loads(result.output)
    invalid = data["invalid_value"][0]
    assert invalid["field"] == "Anrede"
    assert invalid["value"] == 5
    assert "0" in invalid["allowed"]
    assert "1" in invalid["allowed"]


def test_validate_only_json_envelope(form_pdf):
    changes = json.dumps({"Company": "ok", "NichtDa": "x", "TermsAccepted": "Maybe"})
    result = runner.invoke(
        app, ["fill", str(form_pdf), "-", "--validate-only", "--json"], input=changes
    )
    assert result.exit_code == 1
    data = json.loads(result.output)
    assert set(data) == {"valid", "missing", "invalid_value", "warnings"}
    assert data["valid"] == ["Company"]
    assert data["missing"] == ["NichtDa"]
    assert data["invalid_value"][0]["field"] == "TermsAccepted"
    assert isinstance(data["warnings"], list)


def test_fill_json_mode(form_pdf, tmp_path):
    output = tmp_path / "filled.pdf"
    changes = json.dumps({"Company": "Example LLC"})
    result = runner.invoke(
        app, ["fill", str(form_pdf), "-", "--output", str(output), "--json"], input=changes
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["filled"] == ["Company"]
    assert data["missing"] == []
    assert data["invalid_value"] == []
    assert isinstance(data["warnings"], list)
    assert output.exists()


def test_fill_json_missing_field_not_written(form_pdf, tmp_path):
    output = tmp_path / "filled.pdf"
    changes = json.dumps({"NichtDa": "x"})
    result = runner.invoke(
        app, ["fill", str(form_pdf), "-", "--output", str(output), "--json"], input=changes
    )
    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data["filled"] == []
    assert data["missing"] == ["NichtDa"]
    assert not output.exists()


# --- validate-OK => fill-correct contract (normalization round-trips) ---


def _read_field(pdf_path, name):
    result = runner.invoke(app, ["read", str(pdf_path), "--fields", name, "--json"])
    assert result.exit_code == 0
    return json.loads(result.output)["fields"][0]


def test_fill_checkbox_off_string_unchecks(form_pdf, tmp_path):
    """CRITICAL: validate-OK 'Off' must produce an UNCHECKED box when filled."""
    changes = json.dumps({"TermsAccepted": "Off"})
    validated = runner.invoke(app, ["fill", str(form_pdf), "-", "--validate-only"], input=changes)
    assert validated.exit_code == 0
    output = tmp_path / "filled.pdf"
    filled = runner.invoke(
        app, ["fill", str(form_pdf), "-", "--output", str(output)], input=changes
    )
    assert filled.exit_code == 0
    field = _read_field(output, "TermsAccepted")
    assert field["checked"] is False
    assert field["value"] == "Off"


def test_fill_checkbox_on_string_checks(form_pdf, tmp_path):
    changes = json.dumps({"TermsAccepted": "Yes"})
    validated = runner.invoke(app, ["fill", str(form_pdf), "-", "--validate-only"], input=changes)
    assert validated.exit_code == 0
    output = tmp_path / "filled.pdf"
    filled = runner.invoke(
        app, ["fill", str(form_pdf), "-", "--output", str(output)], input=changes
    )
    assert filled.exit_code == 0
    field = _read_field(output, "TermsAccepted")
    assert field["checked"] is True
    assert field["value"] == "Yes"


def test_fill_radio_export_value_selects(radio_form_pdf, tmp_path):
    """IMPORTANT: validate-OK export value '1' must actually select the option."""
    changes = json.dumps({"Anrede": "1"})
    validated = runner.invoke(
        app, ["fill", str(radio_form_pdf), "-", "--validate-only"], input=changes
    )
    assert validated.exit_code == 0
    output = tmp_path / "filled.pdf"
    filled = runner.invoke(
        app, ["fill", str(radio_form_pdf), "-", "--output", str(output)], input=changes
    )
    assert filled.exit_code == 0
    field = _read_field(output, "Anrede")
    assert field["value"] == "1"  # selected, not silently no-oped


def test_fill_radio_int_index_selects(radio_form_pdf, tmp_path):
    changes = json.dumps({"Anrede": 1})
    output = tmp_path / "filled.pdf"
    filled = runner.invoke(
        app, ["fill", str(radio_form_pdf), "-", "--output", str(output)], input=changes
    )
    assert filled.exit_code == 0
    field = _read_field(output, "Anrede")
    assert field["value"] == "1"


def test_validate_only_json_no_form_fields(simple_pdf):
    """No-AcroForm PDF in JSON mode must emit the envelope, not plain stderr."""
    changes = json.dumps({"Company": "x"})
    result = runner.invoke(
        app, ["fill", str(simple_pdf), "-", "--validate-only", "--json"], input=changes
    )
    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data["valid"] == []
    assert data["missing"] == ["Company"]
    assert data["invalid_value"] == []
    assert "error" in data
    assert "no form fields" in data["error"].lower()


def test_validate_only_radio_uses_unified_vocabulary(radio_form_pdf):
    """Radio validation keeps working after radio_group -> radio rename."""
    from pdf_tool.commands.field_info import extract_field_info

    fields = extract_field_info(str(radio_form_pdf))
    assert fields[0]["type"] == "radio"
    changes = json.dumps({"Anrede": 0})
    result = runner.invoke(
        app, ["fill", str(radio_form_pdf), "-", "--validate-only"], input=changes
    )
    assert result.exit_code == 0
