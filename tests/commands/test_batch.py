"""Tests for pdf-tool batch command."""

import json

from typer.testing import CliRunner

from pdf_tool.cli import app

runner = CliRunner()


def test_batch_fill_only(form_pdf, tmp_path):
    output = tmp_path / "batched.pdf"
    ops = json.dumps({"fill": {"Company": "Batch LLC"}})
    result = runner.invoke(app, ["batch", str(form_pdf), "-", "--output", str(output)], input=ops)
    assert result.exit_code == 0
    assert output.exists()


def test_batch_write_only(simple_pdf, tmp_path):
    output = tmp_path / "batched.pdf"
    ops = json.dumps({"write": [{"page": 0, "x": 200, "y": 100, "text": "Batch text"}]})
    result = runner.invoke(app, ["batch", str(simple_pdf), "-", "--output", str(output)], input=ops)
    assert result.exit_code == 0


def test_batch_sign_only(simple_pdf, signature_png, tmp_path):
    output = tmp_path / "batched.pdf"
    ops = json.dumps(
        {
            "sign": {
                "image": str(signature_png),
                "page": 0,
                "position": [100, 100, 200, 60],
            }
        }
    )
    result = runner.invoke(app, ["batch", str(simple_pdf), "-", "--output", str(output)], input=ops)
    assert result.exit_code == 0


def test_batch_combined(form_pdf, signature_png, tmp_path):
    output = tmp_path / "batched.pdf"
    ops = json.dumps(
        {
            "fill": {"Company": "Combined LLC"},
            "write": [{"page": 0, "x": 300, "y": 300, "text": "Extra"}],
            "sign": {
                "image": str(signature_png),
                "page": 0,
                "position": [350, 650, 150, 50],
            },
        }
    )
    result = runner.invoke(app, ["batch", str(form_pdf), "-", "--output", str(output)], input=ops)
    assert result.exit_code == 0


def test_batch_empty(simple_pdf, tmp_path):
    output = tmp_path / "batched.pdf"
    ops = json.dumps({})
    result = runner.invoke(app, ["batch", str(simple_pdf), "-", "--output", str(output)], input=ops)
    assert result.exit_code == 1
    assert "no operations" in result.output.lower()
    assert not output.exists()


def test_batch_rejects_unknown_key(simple_pdf, tmp_path):
    output = tmp_path / "batched.pdf"
    result = runner.invoke(
        app,
        ["batch", str(simple_pdf), "-", "--output", str(output)],
        input=json.dumps({"ghost": {}}),
    )
    assert result.exit_code == 1
    assert "unknown batch key" in result.output.lower()
    assert not output.exists()


def test_batch_rejects_wrong_operation_shape(simple_pdf, tmp_path):
    output = tmp_path / "batched.pdf"
    result = runner.invoke(
        app,
        ["batch", str(simple_pdf), "-", "--output", str(output)],
        input=json.dumps({"write": {}}),
    )
    assert result.exit_code == 1
    assert "write must be an array" in result.output.lower()
    assert not output.exists()


# --- hardening: batch routes fill through validation + normalization ---


def _read_field(pdf_path, name):
    result = runner.invoke(app, ["read", str(pdf_path), "--fields", name, "--json"])
    assert result.exit_code == 0
    return json.loads(result.output)["fields"][0]


def test_batch_fill_off_string_unchecks(form_pdf, tmp_path):
    """Batch must apply the same checkbox normalization as fill ('Off' unchecks)."""
    output = tmp_path / "out.pdf"
    ops = json.dumps({"fill": {"TermsAccepted": "Off"}})
    result = runner.invoke(app, ["batch", str(form_pdf), "-", "--output", str(output)], input=ops)
    assert result.exit_code == 0
    field = _read_field(output, "TermsAccepted")
    assert field["checked"] is False


def test_batch_fill_unknown_field_errors(form_pdf, tmp_path):
    """Unknown fields must abort (formerly exit 0 'Filled: 1')."""
    output = tmp_path / "out.pdf"
    ops = json.dumps({"fill": {"NichtDa": "x"}})
    result = runner.invoke(app, ["batch", str(form_pdf), "-", "--output", str(output)], input=ops)
    assert result.exit_code == 1
    assert "unknown field" in result.output.lower()
    assert not output.exists()


def test_batch_fill_invalid_checkbox_value_errors(form_pdf, tmp_path):
    output = tmp_path / "out.pdf"
    ops = json.dumps({"fill": {"TermsAccepted": "Maybe"}})
    result = runner.invoke(app, ["batch", str(form_pdf), "-", "--output", str(output)], input=ops)
    assert result.exit_code == 1
    assert "invalid value" in result.output.lower()
    assert "allowed" in result.output.lower()
    assert not output.exists()


def test_batch_sign_missing_position_clean_error(form_pdf, signature_png, tmp_path):
    """Missing 'position' must be a clean error, not a KeyError traceback."""
    output = tmp_path / "out.pdf"
    ops = json.dumps({"sign": {"image": str(signature_png), "page": 0}})
    result = runner.invoke(app, ["batch", str(form_pdf), "-", "--output", str(output)], input=ops)
    assert result.exit_code == 1
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert "position" in result.output.lower()


def test_batch_write_missing_keys_clean_error(form_pdf, tmp_path):
    """Write ops missing required keys must error cleanly, not traceback."""
    output = tmp_path / "out.pdf"
    ops = json.dumps({"write": [{"page": 0, "x": 100}]})
    result = runner.invoke(app, ["batch", str(form_pdf), "-", "--output", str(output)], input=ops)
    assert result.exit_code == 1
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert '"y"' in result.output or "y" in result.output


def test_batch_json_envelope(form_pdf, tmp_path):
    output = tmp_path / "out.pdf"
    ops = json.dumps({"fill": {"Company": "Batch LLC"}})
    result = runner.invoke(
        app, ["batch", str(form_pdf), "-", "--output", str(output), "--json"], input=ops
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["count"] == 1
    assert any("Filled" in op for op in data["operations"])
    assert data["output"] == "out.pdf"
