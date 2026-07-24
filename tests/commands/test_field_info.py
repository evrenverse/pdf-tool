"""Tests for field hierarchy extraction."""

import json

from typer.testing import CliRunner

from pdf_tool.cli import app
from pdf_tool.commands.field_info import extract_field_info

runner = CliRunner()


class TestExtractFieldInfo:
    def test_returns_list_of_fields(self, form_pdf):
        fields = extract_field_info(str(form_pdf))
        assert isinstance(fields, list)
        assert len(fields) > 0

    def test_each_field_has_required_keys(self, form_pdf):
        fields = extract_field_info(str(form_pdf))
        required_keys = {"field_id", "type", "page", "rect"}
        for field in fields:
            assert required_keys.issubset(field.keys()), (
                f"Field {field} missing keys: {required_keys - field.keys()}"
            )

    def test_fields_sorted_by_page(self, form_pdf):
        fields = extract_field_info(str(form_pdf))
        pages = [f["page"] for f in fields]
        assert pages == sorted(pages)

    def test_text_fields_detected(self, form_pdf):
        fields = extract_field_info(str(form_pdf))
        text_fields = [f for f in fields if f["type"] == "text"]
        assert len(text_fields) >= 2  # Company and Date

    def test_checkbox_field_detected(self, form_pdf):
        fields = extract_field_info(str(form_pdf))
        checkboxes = [f for f in fields if f["type"] == "checkbox"]
        assert len(checkboxes) >= 1

    def test_checkbox_has_values(self, form_pdf):
        fields = extract_field_info(str(form_pdf))
        checkboxes = [f for f in fields if f["type"] == "checkbox"]
        assert len(checkboxes) >= 1
        cb = checkboxes[0]
        assert "checked_value" in cb
        assert "unchecked_value" in cb

    def test_field_ids_are_strings(self, form_pdf):
        fields = extract_field_info(str(form_pdf))
        for field in fields:
            assert isinstance(field["field_id"], str)
            assert len(field["field_id"]) > 0

    def test_rects_are_float_lists(self, form_pdf):
        fields = extract_field_info(str(form_pdf))
        for field in fields:
            assert isinstance(field["rect"], list)
            assert len(field["rect"]) == 4
            for v in field["rect"]:
                assert isinstance(v, float)

    def test_no_form_fields_returns_empty(self, simple_pdf):
        fields = extract_field_info(str(simple_pdf))
        assert fields == []

    def test_fields_in_visual_reading_order(self, form_pdf):
        """Fields on the same page should be sorted top-to-bottom, left-to-right."""
        fields = extract_field_info(str(form_pdf))
        # All fields are on page 0 in the form fixture
        page_0 = [f for f in fields if f["page"] == 0]
        if len(page_0) >= 2:
            # In PDF coordinates, higher y = higher on page
            # Our sort is descending y (top first), so first field should have
            # higher y than the last
            first_y = page_0[0]["rect"][1]
            last_y = page_0[-1]["rect"][1]
            assert first_y >= last_y


# --- CLI tests ---


class TestFieldInfoCli:
    def test_json_lists_fields(self, form_pdf):
        result = runner.invoke(app, ["field-info", str(form_pdf), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        by_id = {f["field_id"]: f for f in data}
        assert {"Company", "Date", "TermsAccepted"} <= set(by_id)
        assert by_id["TermsAccepted"]["type"] == "checkbox"
        assert by_id["TermsAccepted"]["checked_value"] == "Yes"
        assert by_id["TermsAccepted"]["unchecked_value"] == "Off"
        assert len(by_id["Company"]["rect"]) == 4

    def test_plain_output_compact(self, form_pdf):
        result = runner.invoke(app, ["field-info", str(form_pdf)])
        assert result.exit_code == 0
        assert "TermsAccepted" in result.output
        assert "checkbox" in result.output
        assert 'on="Yes"' in result.output
        assert "Company" in result.output
        assert "page 0" in result.output

    def test_no_form_fields(self, simple_pdf):
        result = runner.invoke(app, ["field-info", str(simple_pdf)])
        assert result.exit_code == 0
        assert "No form fields" in result.output

    def test_no_form_fields_json(self, simple_pdf):
        result = runner.invoke(app, ["field-info", str(simple_pdf), "--json"])
        assert result.exit_code == 0
        assert json.loads(result.output) == []

    def test_file_not_found(self):
        result = runner.invoke(app, ["field-info", "nonexistent.pdf"])
        assert result.exit_code == 1


class TestClassifyField:
    def test_pushbutton_flag_detected(self):
        from pdf_tool.commands.field_info import _classify_field

        assert _classify_field({"/FT": "/Btn", "/Ff": 1 << 16}) == "pushbutton"

    def test_plain_btn_is_checkbox(self):
        from pdf_tool.commands.field_info import _classify_field

        assert _classify_field({"/FT": "/Btn", "/Ff": 0}) == "checkbox"

    def test_radio_flag_detected(self):
        from pdf_tool.commands.field_info import _classify_field

        assert _classify_field({"/FT": "/Btn", "/Ff": 1 << 15}) == "radio"

    def test_signature_detected(self):
        from pdf_tool.commands.field_info import _classify_field

        assert _classify_field({"/FT": "/Sig"}) == "signature"


def test_field_info_encrypted_pdf_clean_error(encrypted_pdf):
    result = runner.invoke(app, ["field-info", str(encrypted_pdf)])
    assert result.exit_code == 1
    assert "encrypted" in result.output.lower()
    assert result.exception is None or isinstance(result.exception, SystemExit)


class TestParentCycleGuards:
    class FakeNode(dict):
        def get_object(self):
            return self

    def test_fully_qualified_name_survives_cycle(self):
        from pdf_tool.commands.field_info import _get_fully_qualified_name

        a = self.FakeNode({"/T": "a"})
        b = self.FakeNode({"/T": "b", "/Parent": a})
        a["/Parent"] = b
        assert _get_fully_qualified_name(a) == "b.a"

    def test_classify_field_survives_cycle(self):
        from pdf_tool.commands.field_info import _classify_field

        a = self.FakeNode()
        b = self.FakeNode({"/Parent": a})
        a["/Parent"] = b
        assert _classify_field(a) == "unknown"

    def test_field_flags_survive_cycle(self):
        from pdf_tool.commands.field_info import _get_field_flags

        a = self.FakeNode()
        a["/Parent"] = a
        assert _get_field_flags(a) == 0


def test_field_info_warns_on_collapsed_duplicates(form_pdf, tmp_path):
    from tests.commands.test_read import _duplicate_field

    dup_pdf = _duplicate_field(form_pdf, tmp_path / "dup.pdf", "Date")
    result = runner.invoke(app, ["field-info", str(dup_pdf)])
    assert result.exit_code == 0
    assert "duplicate" in result.stderr.lower()
    assert "Date" in result.stderr
