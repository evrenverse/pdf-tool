"""Tests for pdf-tool info command."""

import json

from typer.testing import CliRunner

from pdf_tool.cli import app

runner = CliRunner()


def test_info_simple_pdf(simple_pdf):
    result = runner.invoke(app, ["info", str(simple_pdf)])
    assert result.exit_code == 0
    assert "Pages: 2" in result.output
    assert "Page" in result.output


def test_info_form_pdf(form_pdf):
    result = runner.invoke(app, ["info", str(form_pdf)])
    assert result.exit_code == 0
    assert "Form Fields:" in result.output
    assert "Company" in result.output
    assert "Date" in result.output
    assert "TermsAccepted" in result.output


def test_info_json(simple_pdf):
    result = runner.invoke(app, ["info", str(simple_pdf), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["pages"] == 2
    assert len(data["page_details"]) == 2


def test_info_json_with_forms(form_pdf):
    result = runner.invoke(app, ["info", str(form_pdf), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data["form_fields"]) == 3
    field_names = {f["field_id"] for f in data["form_fields"]}
    assert "Company" in field_names
    assert "Date" in field_names
    assert "TermsAccepted" in field_names


def test_info_file_not_found():
    result = runner.invoke(app, ["info", "nonexistent.pdf"])
    assert result.exit_code == 1
    assert "not found" in result.output.lower() or "Error" in result.output


def test_info_encrypted_pdf_clean_error(encrypted_pdf):
    result = runner.invoke(app, ["info", str(encrypted_pdf)])
    assert result.exit_code == 1
    assert "encrypted" in result.output.lower()
    assert result.exception is None or isinstance(result.exception, SystemExit)


def test_info_json_uses_read_vocabulary(form_pdf):
    """info reports field_id + read's type vocabulary (checkbox, not dropdown etc.)."""
    result = runner.invoke(app, ["info", str(form_pdf), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    by_id = {f["field_id"]: f for f in data["form_fields"]}
    assert by_id["TermsAccepted"]["type"] == "checkbox"
    assert by_id["Company"]["type"] == "text"
    assert "name" not in by_id["Company"]
