"""Tests for pdf-tool write command."""

import json

import pdfplumber
import pytest
from typer.testing import CliRunner

from pdf_tool.cli import app
from pdf_tool.commands.write import _detect_and_transform_overlays, _validate_overlays

runner = CliRunner()


def test_write_single_text(simple_pdf, tmp_path):
    output = tmp_path / "written.pdf"
    changes = json.dumps([{"page": 0, "x": 200, "y": 150, "text": "Test Value"}])
    result = runner.invoke(
        app, ["write", str(simple_pdf), "-", "--output", str(output)], input=changes
    )
    assert result.exit_code == 0
    assert "Written:" in result.output or "written" in result.output.lower()
    assert output.exists()


def test_write_multiple_texts(simple_pdf, tmp_path):
    output = tmp_path / "written.pdf"
    changes = json.dumps(
        [
            {"page": 0, "x": 200, "y": 100, "text": "Value 1"},
            {"page": 0, "x": 200, "y": 150, "text": "Value 2"},
            {"page": 1, "x": 200, "y": 100, "text": "Value 3"},
        ]
    )
    result = runner.invoke(
        app, ["write", str(simple_pdf), "-", "--output", str(output)], input=changes
    )
    assert result.exit_code == 0
    assert "3" in result.output


def test_write_with_font_size(simple_pdf, tmp_path):
    output = tmp_path / "written.pdf"
    changes = json.dumps([{"page": 0, "x": 200, "y": 100, "text": "Big Text", "font_size": 18}])
    result = runner.invoke(
        app, ["write", str(simple_pdf), "-", "--output", str(output)], input=changes
    )
    assert result.exit_code == 0


def test_write_verifiable(simple_pdf, tmp_path):
    """Write text and verify it appears in the output PDF."""
    output = tmp_path / "written.pdf"
    changes = json.dumps([{"page": 0, "x": 200, "y": 150, "text": "UNIQUE_TEST_STRING_12345"}])
    runner.invoke(app, ["write", str(simple_pdf), "-", "--output", str(output)], input=changes)
    with pdfplumber.open(str(output)) as pdf:
        text = pdf.pages[0].extract_text()
        assert "UNIQUE_TEST_STRING_12345" in text


def test_write_invalid_page(simple_pdf):
    changes = json.dumps([{"page": 99, "x": 100, "y": 100, "text": "test"}])
    result = runner.invoke(app, ["write", str(simple_pdf), "-"], input=changes)
    assert result.exit_code == 1
    assert "out of range" in result.output.lower()


@pytest.mark.parametrize(
    ("overlay", "message"),
    [
        ({"x": 1, "y": 2, "text": "x"}, '"page"'),
        ({"page": 0, "x": 1, "y": 2, "text": 3}, "text"),
        ({"page": 0, "x": 1, "y": 2, "text": "x", "font_size": 0}, "font_size"),
        ({"page": 0, "x": 1, "y": 2, "text": "x", "image_width": 10}, "together"),
        (
            {
                "page": 0,
                "x": 1,
                "y": 2,
                "text": "x",
                "image_width": 10,
                "image_height": 10,
                "pdf_width": 10,
                "pdf_height": 10,
            },
            "mutually exclusive",
        ),
        ({"page": 0, "x": 1, "y": 2, "text": "x", "ghost": True}, "unknown key"),
    ],
)
def test_overlay_contract_rejects_ambiguous_or_unsafe_values(overlay, message):
    assert message in (_validate_overlays([overlay], 1) or "")


def test_write_from_file(simple_pdf, tmp_path):
    output = tmp_path / "written.pdf"
    changes_file = tmp_path / "changes.json"
    changes_file.write_text(json.dumps([{"page": 0, "x": 200, "y": 100, "text": "From File"}]))
    result = runner.invoke(
        app, ["write", str(simple_pdf), str(changes_file), "--output", str(output)]
    )
    assert result.exit_code == 0


# --- Dual coordinate system tests ---


def test_legacy_format_passes_through():
    """Legacy format (no width/height keys) passes through unchanged."""
    overlays = [{"page": 0, "x": 100.0, "y": 200.0, "text": "Hello"}]
    page_heights = {0: 842.0}
    page_widths = {0: 595.0}
    result = _detect_and_transform_overlays(overlays, page_heights, page_widths)
    assert result[0]["x"] == 100.0
    assert result[0]["y"] == 200.0
    assert result[0]["text"] == "Hello"


def test_image_coordinates_scaled():
    """Image coordinates get scaled by pdf_dim / image_dim ratio."""
    overlays = [
        {
            "page": 0,
            "x": 500.0,
            "y": 400.0,
            "text": "Scaled",
            "image_width": 1000.0,
            "image_height": 800.0,
        }
    ]
    page_heights = {0: 800.0}
    page_widths = {0: 600.0}
    result = _detect_and_transform_overlays(overlays, page_heights, page_widths)
    # scale_x = 600/1000 = 0.6, scale_y = 800/800 = 1.0
    assert result[0]["x"] == 300.0  # 500 * 0.6
    assert result[0]["y"] == 400.0  # 400 * 1.0
    assert "image_width" not in result[0]
    assert "image_height" not in result[0]


def test_pdf_coordinates_y_flipped():
    """PDF coordinates get y-flipped: y = pdf_height - y."""
    overlays = [
        {
            "page": 0,
            "x": 100.0,
            "y": 100.0,
            "text": "Flipped",
            "pdf_width": 595.0,
            "pdf_height": 842.0,
        }
    ]
    page_heights = {0: 842.0}
    page_widths = {0: 595.0}
    result = _detect_and_transform_overlays(overlays, page_heights, page_widths)
    assert result[0]["x"] == 100.0  # x unchanged
    assert result[0]["y"] == 742.0  # 842 - 100
    assert "pdf_width" not in result[0]
    assert "pdf_height" not in result[0]


def test_mixed_coordinate_systems():
    """Different overlays can use different coordinate systems."""
    overlays = [
        {"page": 0, "x": 50.0, "y": 50.0, "text": "Legacy"},
        {
            "page": 0,
            "x": 100.0,
            "y": 100.0,
            "text": "Image",
            "image_width": 1000.0,
            "image_height": 1000.0,
        },
        {
            "page": 0,
            "x": 100.0,
            "y": 100.0,
            "text": "PDF",
            "pdf_width": 595.0,
            "pdf_height": 842.0,
        },
    ]
    page_heights = {0: 842.0}
    page_widths = {0: 595.0}
    result = _detect_and_transform_overlays(overlays, page_heights, page_widths)
    # Legacy: unchanged
    assert result[0]["x"] == 50.0
    assert result[0]["y"] == 50.0
    # Image: scaled (595/1000=0.595, 842/1000=0.842)
    assert abs(result[1]["x"] - 59.5) < 0.01
    assert abs(result[1]["y"] - 84.2) < 0.01
    # PDF: y-flipped (842-100=742)
    assert result[2]["x"] == 100.0
    assert result[2]["y"] == 742.0


def test_write_warns_on_rotated_page(simple_pdf, tmp_path):
    """Overlays targeting a rotated page warn that coordinates disagree."""
    from tests.commands.test_read import _rotated_pdf

    rotated = _rotated_pdf(simple_pdf, tmp_path / "rot.pdf")
    output = tmp_path / "out.pdf"
    overlays = json.dumps([{"page": 0, "x": 100, "y": 100, "text": "X"}])
    result = runner.invoke(
        app, ["write", str(rotated), "-", "--output", str(output)], input=overlays
    )
    assert result.exit_code == 0
    assert "rotated" in result.stderr.lower()


def test_write_no_rotation_warning_on_straight_page(simple_pdf, tmp_path):
    from tests.commands.test_read import _rotated_pdf

    rotated = _rotated_pdf(simple_pdf, tmp_path / "rot.pdf")
    output = tmp_path / "out.pdf"
    overlays = json.dumps([{"page": 1, "x": 100, "y": 100, "text": "X"}])
    result = runner.invoke(
        app, ["write", str(rotated), "-", "--output", str(output)], input=overlays
    )
    assert result.exit_code == 0
    assert "rotated" not in result.stderr.lower()


def test_write_warns_on_non_winansi_glyphs(simple_pdf, tmp_path):
    """CJK and other non-WinAnsi glyphs are lost by standard fonts — warn."""
    output = tmp_path / "out.pdf"
    overlays = json.dumps([{"page": 0, "x": 100, "y": 100, "text": "Vertrag 中文 OK"}])
    result = runner.invoke(
        app, ["write", str(simple_pdf), "-", "--output", str(output)], input=overlays
    )
    assert result.exit_code == 0
    assert "winansi" in result.stderr.lower() or "not representable" in result.stderr.lower()
    assert "中" in result.stderr


def test_write_no_glyph_warning_for_latin1(simple_pdf, tmp_path):
    output = tmp_path / "out.pdf"
    overlays = json.dumps([{"page": 0, "x": 100, "y": 100, "text": "Müller — Größe"}])
    result = runner.invoke(
        app, ["write", str(simple_pdf), "-", "--output", str(output)], input=overlays
    )
    assert result.exit_code == 0
    assert "not representable" not in result.stderr.lower()
