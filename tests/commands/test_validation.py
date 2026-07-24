"""Tests for bounding box pre-validation."""

from pdf_tool.commands.validation import check_bounding_boxes


def _field(
    entry_box: list[float],
    label_box: list[float] | None = None,
    page: int = 0,
    font_size: float | None = None,
) -> dict:
    """Helper to build a field dict."""
    f: dict = {
        "entry_bounding_box": entry_box,
        "page_number": page,
    }
    if label_box is not None:
        f["label_bounding_box"] = label_box
    if font_size is not None:
        f["entry_text"] = {"font_size": font_size}
    return f


class TestNoOverlaps:
    def test_non_overlapping_fields_return_empty(self):
        fields = [
            _field(entry_box=[0, 0, 50, 20]),
            _field(entry_box=[100, 0, 150, 20]),
        ]
        assert check_bounding_boxes(fields) == []

    def test_empty_list_returns_empty(self):
        assert check_bounding_boxes([]) == []

    def test_single_field_no_errors(self):
        fields = [_field(entry_box=[0, 0, 100, 20])]
        assert check_bounding_boxes(fields) == []

    def test_touching_boxes_no_overlap(self):
        """Boxes that share an edge but don't overlap should not trigger errors."""
        fields = [
            _field(entry_box=[0, 0, 50, 20]),
            _field(entry_box=[50, 0, 100, 20]),
        ]
        assert check_bounding_boxes(fields) == []


class TestOverlappingEntries:
    def test_overlapping_entries_detected(self):
        fields = [
            _field(entry_box=[0, 0, 60, 20]),
            _field(entry_box=[50, 0, 120, 20]),
        ]
        errors = check_bounding_boxes(fields)
        assert len(errors) == 1
        assert "overlaps" in errors[0]

    def test_overlap_only_on_same_page(self):
        """Fields on different pages should not report overlap."""
        fields = [
            _field(entry_box=[0, 0, 60, 20], page=0),
            _field(entry_box=[0, 0, 60, 20], page=1),
        ]
        assert check_bounding_boxes(fields) == []

    def test_label_entry_overlap_detected(self):
        fields = [
            _field(entry_box=[100, 0, 200, 20], label_box=[0, 0, 110, 20]),
        ]
        errors = check_bounding_boxes(fields)
        assert len(errors) == 1
        assert "overlaps" in errors[0]


class TestEntryBoxTooSmall:
    def test_box_smaller_than_font_size(self):
        # Box height = 8, default font_size = 10
        fields = [_field(entry_box=[0, 0, 100, 8])]
        errors = check_bounding_boxes(fields)
        assert len(errors) == 1
        assert "font_size" in errors[0]

    def test_box_equal_to_font_size_ok(self):
        # Box height = 10, default font_size = 10
        fields = [_field(entry_box=[0, 0, 100, 10])]
        assert check_bounding_boxes(fields) == []

    def test_custom_font_size(self):
        # Box height = 12, but font_size = 14
        fields = [_field(entry_box=[0, 0, 100, 12], font_size=14)]
        errors = check_bounding_boxes(fields)
        assert len(errors) == 1
        assert "font_size" in errors[0]


class TestMaxErrorsCap:
    def test_max_20_errors(self):
        # Create 25 fields all overlapping at the same spot on the same page
        fields = [_field(entry_box=[0, 0, 50, 20]) for _ in range(25)]
        errors = check_bounding_boxes(fields)
        assert len(errors) == 20


class TestWarningsIncludeFieldNames:
    def test_overlap_warning_names_both_fields(self):
        fields = [
            {"name": "Company", "entry_bounding_box": [0, 0, 100, 20], "page_number": 0},
            {"name": "Date", "entry_bounding_box": [50, 0, 150, 20], "page_number": 0},
        ]
        errors = check_bounding_boxes(fields)
        assert errors
        assert any("Company" in e and "Date" in e for e in errors)

    def test_small_box_warning_names_field(self):
        fields = [{"name": "Tiny", "entry_bounding_box": [0, 0, 100, 5], "page_number": 0}]
        errors = check_bounding_boxes(fields)
        assert errors
        assert any("Tiny" in e for e in errors)

    def test_index_fallback_without_name(self):
        fields = [{"entry_bounding_box": [0, 0, 100, 5], "page_number": 0}]
        errors = check_bounding_boxes(fields)
        assert errors
        assert any("field[0]" in e for e in errors)
