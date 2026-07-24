"""Tests for pdf-tool find command."""

import json

import pytest
from typer.testing import CliRunner

from pdf_tool.cli import app

runner = CliRunner()


@pytest.fixture
def filled_form_pdf(form_pdf, tmp_path):
    output = tmp_path / "filled.pdf"
    changes = json.dumps({"Company": "Acme LLC"})
    result = runner.invoke(
        app, ["fill", str(form_pdf), "-", "--output", str(output)], input=changes
    )
    assert result.exit_code == 0
    return output


def test_find_basic_plain(simple_pdf):
    result = runner.invoke(app, ["find", str(simple_pdf), "Organization"])
    assert result.exit_code == 0
    assert "p0" in result.output
    assert "Organization" in result.output
    # plain format: p0 (x0,y0)-(x1,y1): "..."
    assert ")-(" in result.output


def test_find_case_insensitive_default(simple_pdf):
    result = runner.invoke(app, ["find", str(simple_pdf), "STADT"])
    assert result.exit_code == 0
    assert "Stadt" in result.output


def test_find_exact_is_case_sensitive(simple_pdf):
    miss = runner.invoke(app, ["find", str(simple_pdf), "STADT", "--exact"])
    assert miss.exit_code == 1
    hit = runner.invoke(app, ["find", str(simple_pdf), "Stadt", "--exact"])
    assert hit.exit_code == 0


def test_find_multiword_line_match(simple_pdf):
    """Words on the same line are joined, so multi-word queries hit."""
    result = runner.invoke(app, ["find", str(simple_pdf), "Organization: Stadt", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["total"] >= 1
    assert "Stadt" in data["matches"][0]["text"]


def test_find_json_structure(simple_pdf):
    result = runner.invoke(app, ["find", str(simple_pdf), "Organization", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert set(data) == {"matches", "total", "truncated"}
    assert data["truncated"] is False
    match = data["matches"][0]
    assert match["page"] == 0
    assert match["kind"] == "text"
    assert len(match["bbox"]) == 4
    assert all(isinstance(v, float) for v in match["bbox"])


def test_find_pages_filter(multipage_pdf):
    result = runner.invoke(app, ["find", str(multipage_pdf), "Title", "--pages", "0,2", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert sorted({m["page"] for m in data["matches"]}) == [0, 2]


def test_find_pages_invalid_spec(multipage_pdf):
    result = runner.invoke(app, ["find", str(multipage_pdf), "Title", "--pages", "abc"])
    assert result.exit_code == 1
    assert "invalid" in result.output.lower()


def test_find_max_truncation_json(multipage_pdf):
    # "page" matches 2 lines per page x 5 pages = 10 line matches
    result = runner.invoke(app, ["find", str(multipage_pdf), "page", "--max", "3", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data["matches"]) == 3
    assert data["total"] == 10
    assert data["truncated"] is True


def test_find_max_truncation_plain_notice(multipage_pdf):
    result = runner.invoke(app, ["find", str(multipage_pdf), "page", "--max", "3"])
    assert result.exit_code == 0
    assert "3 of 10" in result.output
    assert "--max" in result.output


def test_find_form_field_by_name(filled_form_pdf):
    """Finding 'Company' surfaces the form field, not only painted text."""
    result = runner.invoke(app, ["find", str(filled_form_pdf), "Company", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    kinds = {m["kind"] for m in data["matches"]}
    assert "form_field" in kinds
    assert "text" in kinds  # painted label "Company:" also matches
    form_match = next(m for m in data["matches"] if m["kind"] == "form_field")
    assert form_match["field_id"] == "Company"
    assert form_match["value"] == "Acme LLC"
    assert form_match["page"] == 0


def test_find_form_field_by_value(filled_form_pdf):
    result = runner.invoke(app, ["find", str(filled_form_pdf), "ACME", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    form_matches = [m for m in data["matches"] if m["kind"] == "form_field"]
    assert any(m["field_id"] == "Company" for m in form_matches)


def test_find_form_field_plain(filled_form_pdf):
    result = runner.invoke(app, ["find", str(filled_form_pdf), "TermsAccepted"])
    assert result.exit_code == 0
    assert "[form_field]" in result.output
    assert "TermsAccepted" in result.output


def test_find_no_matches_exit_one(simple_pdf):
    result = runner.invoke(app, ["find", str(simple_pdf), "Zzz_not_there"])
    assert result.exit_code == 1
    assert "No matches" in result.output


def test_find_no_matches_json(simple_pdf):
    result = runner.invoke(app, ["find", str(simple_pdf), "Zzz_not_there", "--json"])
    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data == {"matches": [], "total": 0, "truncated": False}


def test_find_file_not_found():
    result = runner.invoke(app, ["find", "nonexistent.pdf", "x"])
    assert result.exit_code == 1


def test_find_max_must_be_positive(simple_pdf):
    result = runner.invoke(app, ["find", str(simple_pdf), "x", "--max", "0"])
    assert result.exit_code == 1
    assert "--max" in result.output


def test_find_warns_when_form_extraction_fails(simple_pdf, monkeypatch):
    """A corrupt AcroForm must not silently drop form-field matching."""

    def boom(*args, **kwargs):
        raise RuntimeError("corrupt AcroForm")

    monkeypatch.setattr("pdf_tool.commands.find._extract_form_field_values", boom)
    result = runner.invoke(app, ["find", str(simple_pdf), "Organization"])
    assert result.exit_code == 0  # text matches still work
    assert "Warning" in result.output
    assert "form field" in result.output.lower()


def test_find_encrypted_pdf_clean_error(encrypted_pdf):
    result = runner.invoke(app, ["find", str(encrypted_pdf), "x"])
    assert result.exit_code == 1
    assert "encrypted" in result.output.lower()
    assert result.exception is None or isinstance(result.exception, SystemExit)


def test_find_no_text_layer_hint(tmp_path):
    """No matches on a text-less (scanned) PDF hints at visual rendering."""
    from pypdf import PdfWriter

    path = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    with open(path, "wb") as fh:
        writer.write(fh)
    result = runner.invoke(app, ["find", str(path), "anything"])
    assert result.exit_code == 1
    assert "no text layer" in result.stderr.lower()
