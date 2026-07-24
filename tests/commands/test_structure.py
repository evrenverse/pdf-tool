"""Tests for pdf-tool structure detection (non-fillable PDF form analysis)."""

import json
from pathlib import Path

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from typer.testing import CliRunner

from pdf_tool.cli import app
from pdf_tool.commands.structure import extract_form_structure

runner = CliRunner()


@pytest.fixture
def structured_pdf(fixtures_dir: Path) -> Path:
    """Create a non-fillable PDF with labels, lines, and checkbox-like rectangles."""
    path = fixtures_dir / "structured.pdf"
    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4

    # Page 1: Labels + horizontal lines + checkbox rectangles
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 80, "Company:")
    c.drawString(50, height - 120, "Anschrift:")
    c.drawString(50, height - 160, "Date:")

    # Horizontal lines (spanning >50% of page width)
    c.setLineWidth(0.5)
    c.line(40, height - 90, width - 40, height - 90)
    c.line(40, height - 130, width - 40, height - 130)
    c.line(40, height - 170, width - 40, height - 170)

    # Checkbox-like small rectangles (~10x10)
    c.rect(50, height - 210, 10, 10, stroke=1, fill=0)
    c.drawString(70, height - 208, "Terms akzeptiert")
    c.rect(50, height - 240, 10, 10, stroke=1, fill=0)
    c.drawString(70, height - 238, "Datenschutz akzeptiert")

    c.showPage()

    # Page 2: minimal content
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 80, "Unterschrift:")
    c.line(40, height - 90, width - 40, height - 90)
    c.showPage()

    c.save()
    return path


# --- Unit tests for extract_form_structure ---


class TestExtractFormStructure:
    def test_returns_required_keys(self, structured_pdf: Path):
        result = extract_form_structure(str(structured_pdf))
        assert "pages" in result
        assert "labels" in result
        assert "lines" in result
        assert "checkboxes" in result
        assert "row_boundaries" in result

    def test_pages_metadata(self, structured_pdf: Path):
        result = extract_form_structure(str(structured_pdf))
        assert len(result["pages"]) == 2
        for page in result["pages"]:
            assert "width" in page
            assert "height" in page
            assert "page" in page

    def test_detects_labels(self, structured_pdf: Path):
        result = extract_form_structure(str(structured_pdf))
        labels = result["labels"]
        assert len(labels) > 0
        # Check that labels have coordinate fields
        for label in labels:
            assert "text" in label
            assert "x0" in label
            assert "top" in label
            assert "x1" in label
            assert "bottom" in label
            assert "page" in label

    def test_finds_known_labels(self, structured_pdf: Path):
        result = extract_form_structure(str(structured_pdf))
        label_texts = [label["text"] for label in result["labels"]]
        assert any("Company" in t for t in label_texts)
        assert any("Anschrift" in t for t in label_texts)
        assert any("Date" in t for t in label_texts)

    def test_detects_horizontal_lines(self, structured_pdf: Path):
        result = extract_form_structure(str(structured_pdf))
        lines = result["lines"]
        # We drew 4 horizontal lines total (3 on page 1, 1 on page 2)
        assert len(lines) >= 3

        for line in lines:
            assert "x0" in line
            assert "x1" in line
            assert "top" in line
            assert "page" in line

    def test_detects_checkboxes(self, structured_pdf: Path):
        result = extract_form_structure(str(structured_pdf))
        checkboxes = result["checkboxes"]
        assert len(checkboxes) >= 2

        for cb in checkboxes:
            assert "x0" in cb
            assert "top" in cb
            assert "width" in cb
            assert "height" in cb
            assert "page" in cb

    def test_row_boundaries_from_lines(self, structured_pdf: Path):
        result = extract_form_structure(str(structured_pdf))
        boundaries = result["row_boundaries"]
        assert len(boundaries) > 0

        for boundary in boundaries:
            assert "top" in boundary
            assert "page" in boundary

    def test_empty_pdf(self, fixtures_dir: Path):
        """A PDF with no form-like content should return empty lists."""
        path = fixtures_dir / "empty.pdf"
        c = canvas.Canvas(str(path), pagesize=A4)
        c.showPage()
        c.save()

        result = extract_form_structure(str(path))
        assert len(result["pages"]) == 1
        page = result["pages"][0]
        assert page["page"] == 0
        assert abs(page["width"] - A4[0]) < 1
        assert abs(page["height"] - A4[1]) < 1
        assert result["labels"] == []
        assert result["lines"] == []
        assert result["checkboxes"] == []
        assert result["row_boundaries"] == []


# --- Integration tests: info command with structure fallback ---


class TestInfoStructureFallback:
    def test_info_shows_structure_for_non_fillable(self, structured_pdf: Path):
        """When no AcroForm fields, info should show structure analysis."""
        result = runner.invoke(app, ["info", str(structured_pdf)])
        assert result.exit_code == 0
        assert "Form Fields: none" in result.output
        assert "Structure Analysis" in result.output
        assert "Labels:" in result.output
        assert "Lines:" in result.output
        assert "Checkboxes:" in result.output

    def test_info_json_includes_structure(self, structured_pdf: Path):
        """JSON output should include form_structure when no AcroForm fields."""
        result = runner.invoke(app, ["info", str(structured_pdf), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "form_structure" in data
        assert "labels" in data["form_structure"]
        assert "lines" in data["form_structure"]
        assert "checkboxes" in data["form_structure"]

    def test_info_no_structure_when_form_fields_exist(self, form_pdf: Path):
        """When AcroForm fields exist, structure analysis should NOT appear."""
        result = runner.invoke(app, ["info", str(form_pdf)])
        assert result.exit_code == 0
        assert "Structure Analysis" not in result.output

    def test_info_json_no_structure_when_form_fields_exist(self, form_pdf: Path):
        """JSON output should NOT include form_structure when AcroForm fields exist."""
        result = runner.invoke(app, ["info", str(form_pdf), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "form_structure" not in data
