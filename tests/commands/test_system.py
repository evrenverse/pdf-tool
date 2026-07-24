import json

from typer.testing import CliRunner

from pdf_tool.cli import app

runner = CliRunner()


def test_capabilities_json():
    result = runner.invoke(app, ["capabilities", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["tool"] == "pdf-tool"
    assert payload["contract_version"] == "1"
    assert "batch" in payload["schemas"]


def test_doctor_json():
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["tool"] == "pdf-tool"
    assert payload["status"] in {"ok", "degraded"}
    assert any(check["name"] == "poppler" for check in payload["checks"])


def test_schema_and_version_json():
    schema_result = runner.invoke(app, ["schema", "batch"])
    assert schema_result.exit_code == 0, schema_result.output
    assert json.loads(schema_result.output)["title"] == "pdf-tool batch input"

    version_result = runner.invoke(app, ["version", "--json"])
    assert version_result.exit_code == 0, version_result.output
    assert json.loads(version_result.output)["contract_version"] == "1"


def test_unknown_required_dependency_is_usage_error():
    result = runner.invoke(app, ["doctor", "--require", "ghost"])
    assert result.exit_code == 2
    assert "unknown optional dependency" in result.output
