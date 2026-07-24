"""Tests for pdf-tool read command."""

import json
import shutil
from pathlib import Path

import pytest
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from typer.testing import CliRunner

from pdf_tool.cli import app

runner = CliRunner()

# Page rendering shells out to Poppler, an optional dependency. Skip rather
# than fail where it is absent, so a plain checkout still runs the suite.
needs_poppler = pytest.mark.skipif(
    shutil.which("pdftoppm") is None, reason="Poppler (pdftoppm) not installed"
)


@pytest.fixture
def filled_form_pdf(form_pdf, tmp_path) -> Path:
    """form_pdf with Company and Date filled (TermsAccepted left unchecked)."""
    output = tmp_path / "filled.pdf"
    changes = json.dumps({"Company": "Acme LLC", "Date": "10.06.2026"})
    result = runner.invoke(
        app, ["fill", str(form_pdf), "-", "--output", str(output)], input=changes
    )
    assert result.exit_code == 0
    return output


def test_read_all_pages(simple_pdf):
    result = runner.invoke(app, ["read", str(simple_pdf)])
    assert result.exit_code == 0
    assert "Page: 0" in result.output
    assert "Organization:" in result.output
    assert "Stadt" in result.output


def test_read_single_page(simple_pdf):
    result = runner.invoke(app, ["read", str(simple_pdf), "--page", "0"])
    assert result.exit_code == 0
    assert "Organization:" in result.output
    assert "Unterschrift:" not in result.output


def test_read_page_1(simple_pdf):
    result = runner.invoke(app, ["read", str(simple_pdf), "--page", "1"])
    assert result.exit_code == 0
    assert "Seite" in result.output
    assert "Unterschrift:" in result.output
    assert "Organization:" not in result.output


def test_read_json(simple_pdf):
    result = runner.invoke(app, ["read", str(simple_pdf), "--page", "0", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["page"] == 0
    assert "words" in data
    words = [w["text"] for w in data["words"]]
    assert "Organization:" in words


def test_read_json_has_coordinates(simple_pdf):
    result = runner.invoke(app, ["read", str(simple_pdf), "--page", "0", "--json"])
    data = json.loads(result.output)
    word = data["words"][0]
    assert "x0" in word
    assert "y0" in word
    assert "x1" in word
    assert "y1" in word
    assert isinstance(word["x0"], float)


def test_read_range(simple_pdf):
    result = runner.invoke(app, ["read", str(simple_pdf), "--page", "0", "--range", "0,0,300,120"])
    assert result.exit_code == 0
    assert "Organization:" in result.output


def test_read_image(simple_pdf, tmp_path):
    out_img = tmp_path / "page0.png"
    result = runner.invoke(app, ["read", str(simple_pdf), "--page", "0", "--image", str(out_img)])
    assert result.exit_code == 0
    assert out_img.exists()
    assert out_img.stat().st_size > 0


def test_read_page_out_of_range(simple_pdf):
    result = runner.invoke(app, ["read", str(simple_pdf), "--page", "99"])
    assert result.exit_code == 1
    assert "out of range" in result.output.lower()


def test_read_file_not_found():
    result = runner.invoke(app, ["read", "nonexistent.pdf"])
    assert result.exit_code == 1


# --- Table extraction tests ---


def _make_table_pdf(path: Path) -> Path:
    """Create a PDF with a table using reportlab."""
    doc = SimpleDocTemplate(str(path), pagesize=A4)
    data = [
        ["Name", "Age", "City"],
        ["Alice", "30", "Berlin"],
        ["Bob", "25", "Munich"],
    ]
    table = Table(data)
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ]
        )
    )
    doc.build([table])
    return path


def test_read_tables_json(tmp_path):
    pdf_path = _make_table_pdf(tmp_path / "table.pdf")
    result = runner.invoke(app, ["read", str(pdf_path), "--tables", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "tables" in data
    assert len(data["tables"]) >= 1
    tbl = data["tables"][0]
    assert tbl["page"] == 0
    assert tbl["table_index"] == 0
    assert tbl["headers"] == ["Name", "Age", "City"]
    assert len(tbl["rows"]) == 2
    assert tbl["rows"][0] == ["Alice", "30", "Berlin"]


def test_read_tables_plain(tmp_path):
    pdf_path = _make_table_pdf(tmp_path / "table.pdf")
    result = runner.invoke(app, ["read", str(pdf_path), "--tables"])
    assert result.exit_code == 0
    assert "Name" in result.output
    assert "Alice" in result.output
    assert "Page 0" in result.output


def test_read_specific_table(tmp_path):
    pdf_path = _make_table_pdf(tmp_path / "table.pdf")
    result = runner.invoke(app, ["read", str(pdf_path), "--table", "0", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data["tables"]) == 1


def test_read_tables_no_tables(simple_pdf):
    """PDF without tables returns empty list."""
    result = runner.invoke(app, ["read", str(simple_pdf), "--tables", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["tables"] == []


# --- Batch image rendering tests ---


@needs_poppler
def test_read_image_batch(simple_pdf, tmp_path):
    """Render all pages of a multi-page PDF to a directory."""
    output_dir = tmp_path / "pages"
    output_dir.mkdir()
    result = runner.invoke(app, ["read", str(simple_pdf), "--image", str(output_dir)])
    assert result.exit_code == 0
    assert (output_dir / "page_0.png").exists()
    assert (output_dir / "page_1.png").exists()
    assert (output_dir / "page_0.png").stat().st_size > 0
    assert (output_dir / "page_1.png").stat().st_size > 0
    assert "Rendered 2 pages" in result.output


@needs_poppler
def test_read_image_batch_multipage(multipage_pdf, tmp_path):
    """Render all 5 pages of a multi-page PDF to a directory."""
    output_dir = tmp_path / "pages"
    output_dir.mkdir()
    result = runner.invoke(app, ["read", str(multipage_pdf), "--image", str(output_dir)])
    assert result.exit_code == 0
    for i in range(5):
        assert (output_dir / f"page_{i}.png").exists()
    assert "Rendered 5 pages" in result.output


# --- Overlay tests ---


def test_read_image_with_overlay(simple_pdf, tmp_path):
    """Render page with overlay draws bounding boxes without crashing."""
    out_img = tmp_path / "page0.png"
    fields_json = tmp_path / "fields.json"
    fields_json.write_text(
        json.dumps(
            {
                "form_fields": [
                    {
                        "page_number": 0,
                        "label_bounding_box": [10, 10, 200, 30],
                        "entry_bounding_box": [210, 10, 400, 30],
                    },
                    {
                        "page_number": 1,
                        "label_bounding_box": [10, 50, 200, 70],
                        "entry_bounding_box": [210, 50, 400, 70],
                    },
                ]
            }
        )
    )
    result = runner.invoke(
        app,
        [
            "read",
            str(simple_pdf),
            "--page",
            "0",
            "--image",
            str(out_img),
            "--overlay",
            str(fields_json),
        ],
    )
    assert result.exit_code == 0
    assert out_img.exists()
    assert out_img.stat().st_size > 0
    assert "with overlay" in result.output


# --- --pages tests ---


def test_read_pages_selection(multipage_pdf):
    """--pages reads exactly the requested pages, skipping the rest."""
    result = runner.invoke(app, ["read", str(multipage_pdf), "--pages", "0,2,4"])
    assert result.exit_code == 0
    # Page contents are "Page <n> Title"; words are printed individually as "<word>"
    assert "Page: 0" in result.output
    assert "Page: 2" in result.output
    assert "Page: 4" in result.output
    assert "Page: 1" not in result.output
    assert "Page: 3" not in result.output
    assert '"1"' in result.output  # from "Page 1 Title"
    assert '"5"' in result.output  # from "Page 5 Title"
    assert '"2"' not in result.output  # page 1 (content "Page 2 Title") skipped


def test_read_pages_json(multipage_pdf):
    result = runner.invoke(app, ["read", str(multipage_pdf), "--pages", "0,2", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert [p["page"] for p in data] == [0, 2]


def test_read_pages_single_page_json_is_array(multipage_pdf):
    """--pages ALWAYS yields the array shape, even for one page (stable for jq)."""
    result = runner.invoke(app, ["read", str(multipage_pdf), "--pages", "3", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert [p["page"] for p in data] == [3]


def test_read_pages_range_token(multipage_pdf):
    result = runner.invoke(app, ["read", str(multipage_pdf), "--pages", "1-3", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert [p["page"] for p in data] == [1, 2, 3]


def test_read_pages_mixed_and_deduplicated(multipage_pdf):
    result = runner.invoke(app, ["read", str(multipage_pdf), "--pages", "2,0-1,2", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert [p["page"] for p in data] == [0, 1, 2]


def test_read_pages_mutually_exclusive_with_page(multipage_pdf):
    result = runner.invoke(app, ["read", str(multipage_pdf), "--pages", "0", "--page", "1"])
    assert result.exit_code == 1
    assert "mutually exclusive" in result.output.lower()


def test_read_pages_out_of_range(multipage_pdf):
    result = runner.invoke(app, ["read", str(multipage_pdf), "--pages", "0,99"])
    assert result.exit_code == 1
    assert "out of range" in result.output.lower()


def test_read_pages_invalid_token(multipage_pdf):
    result = runner.invoke(app, ["read", str(multipage_pdf), "--pages", "0,abc"])
    assert result.exit_code == 1
    assert "invalid" in result.output.lower()


def test_read_pages_reversed_range(multipage_pdf):
    result = runner.invoke(app, ["read", str(multipage_pdf), "--pages", "3-1"])
    assert result.exit_code == 1
    assert "start > end" in result.output


def test_read_pages_negative_token(multipage_pdf):
    result = runner.invoke(app, ["read", str(multipage_pdf), "--pages", "-1"])
    assert result.exit_code == 1
    assert "invalid" in result.output.lower()


def test_read_pages_huge_range_rejected_fast(multipage_pdf):
    """Out-of-range range ends are rejected BEFORE the range is materialized."""
    import time

    start = time.monotonic()
    result = runner.invoke(app, ["read", str(multipage_pdf), "--pages", "0-99999999"])
    elapsed = time.monotonic() - start
    assert result.exit_code == 1
    assert "out of range" in result.output.lower()
    assert elapsed < 5  # materializing the range first took ~14s / ~4GB


def test_read_pages_whitespace_tolerant(multipage_pdf):
    result = runner.invoke(app, ["read", str(multipage_pdf), "--pages", " 0 , 2 ", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert [p["page"] for p in data] == [0, 2]


@needs_poppler
def test_read_pages_image_batch_renders_only_selected(multipage_pdf, tmp_path):
    """--pages filters batch image rendering to the selected pages."""
    output_dir = tmp_path / "pages"
    output_dir.mkdir()
    result = runner.invoke(
        app, ["read", str(multipage_pdf), "--pages", "0,2", "--image", str(output_dir)]
    )
    assert result.exit_code == 0
    assert "Rendered 2 pages" in result.output
    assert (output_dir / "page_0.png").exists()
    assert (output_dir / "page_2.png").exists()
    assert not (output_dir / "page_1.png").exists()
    assert not (output_dir / "page_3.png").exists()
    assert not (output_dir / "page_4.png").exists()


def test_read_pages_image_single_file_error(multipage_pdf, tmp_path):
    """--pages with a single-file --image target errors with a clear message."""
    result = runner.invoke(
        app,
        ["read", str(multipage_pdf), "--pages", "0,2", "--image", str(tmp_path / "x.png")],
    )
    assert result.exit_code == 1
    assert "--pages" in result.output
    assert "directory" in result.output.lower()


def _make_two_page_table_pdf(path: Path) -> Path:
    """Create a PDF with one table per page."""
    from reportlab.platypus import PageBreak

    doc = SimpleDocTemplate(str(path), pagesize=A4)
    style = TableStyle([("GRID", (0, 0), (-1, -1), 1, colors.black)])
    table_one = Table([["Alpha"], ["first"]])
    table_one.setStyle(style)
    table_two = Table([["Beta"], ["second"]])
    table_two.setStyle(style)
    doc.build([table_one, PageBreak(), table_two])
    return path


def test_read_pages_tables_filtered(tmp_path):
    """--pages filters table extraction to the selected pages."""
    pdf_path = _make_two_page_table_pdf(tmp_path / "tables.pdf")
    result = runner.invoke(app, ["read", str(pdf_path), "--tables", "--pages", "1", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data["tables"]) == 1
    assert data["tables"][0]["page"] == 1
    assert data["tables"][0]["headers"] == ["Beta"]


# --- --fields tests ---


def test_read_fields_json_happy_path(filled_form_pdf):
    result = runner.invoke(
        app, ["read", str(filled_form_pdf), "--fields", "Company,Date", "--json"]
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["missing"] == []
    by_id = {f["field_id"]: f for f in data["fields"]}
    assert by_id["Company"]["value"] == "Acme LLC"
    assert by_id["Date"]["value"] == "10.06.2026"
    assert "type" in by_id["Company"]
    assert "page" in by_id["Company"]
    # Fast path: no text/word dump in the output
    assert "words" not in data


def test_read_fields_plain(filled_form_pdf):
    result = runner.invoke(app, ["read", str(filled_form_pdf), "--fields", "Company,Date"])
    assert result.exit_code == 0
    assert "Company: Acme LLC" in result.output
    assert "Date: 10.06.2026" in result.output


def test_read_fields_partial_missing_exit_zero(filled_form_pdf):
    result = runner.invoke(
        app, ["read", str(filled_form_pdf), "--fields", "Company,NichtDa", "--json"]
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["missing"] == ["NichtDa"]
    assert [f["field_id"] for f in data["fields"]] == ["Company"]


def test_read_fields_all_missing_exit_one(filled_form_pdf):
    result = runner.invoke(app, ["read", str(filled_form_pdf), "--fields", "Foo,Bar", "--json"])
    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data["fields"] == []
    assert data["missing"] == ["Foo", "Bar"]


def test_read_fields_plain_missing_marker(filled_form_pdf):
    result = runner.invoke(app, ["read", str(filled_form_pdf), "--fields", "Company,NichtDa"])
    assert result.exit_code == 0
    assert "Company: Acme LLC" in result.output
    assert "NichtDa: (missing)" in result.output


def test_read_fields_existing_but_empty_is_not_missing(form_pdf):
    """An unfilled field exists -> value null, NOT listed under missing."""
    result = runner.invoke(app, ["read", str(form_pdf), "--fields", "Date", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["missing"] == []
    assert data["fields"][0]["field_id"] == "Date"
    assert data["fields"][0]["value"] is None


def test_read_fields_plain_existing_but_empty(form_pdf):
    """Plain mode: an unfilled-but-existing field prints an empty value, not (missing)."""
    result = runner.invoke(app, ["read", str(form_pdf), "--fields", "Date"])
    assert result.exit_code == 0
    assert "Date:" in result.output
    assert "(missing)" not in result.output


def test_read_fields_mutually_exclusive_with_page(filled_form_pdf):
    result = runner.invoke(
        app, ["read", str(filled_form_pdf), "--fields", "Company", "--page", "0"]
    )
    assert result.exit_code == 1
    assert "--fields" in result.output


@pytest.mark.parametrize(
    "extra_args",
    [
        ["--tables"],
        ["--table", "0"],
        ["--range", "0,0,100,100"],
        ["--image", "out.png"],
        ["--overlay", "fields.json"],
    ],
    ids=["tables", "table", "range", "image", "overlay"],
)
def test_read_fields_rejects_other_modes(filled_form_pdf, extra_args):
    """--fields must not silently ignore other read modes — explicit error."""
    result = runner.invoke(app, ["read", str(filled_form_pdf), "--fields", "Company", *extra_args])
    assert result.exit_code == 1
    assert "--fields" in result.output
    assert extra_args[0] in result.output


# --- --values-only tests ---


def test_read_values_only(filled_form_pdf):
    result = runner.invoke(
        app, ["read", str(filled_form_pdf), "--fields", "Company,NichtDa", "--values-only"]
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data == {"Company": "Acme LLC", "NichtDa": None}


def test_read_values_only_all_missing_exit_one(filled_form_pdf):
    result = runner.invoke(app, ["read", str(filled_form_pdf), "--fields", "Nope", "--values-only"])
    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data == {"Nope": None}


def test_read_values_only_requires_fields(filled_form_pdf):
    result = runner.invoke(app, ["read", str(filled_form_pdf), "--values-only"])
    assert result.exit_code == 1
    assert "--fields" in result.output


def test_read_overlay_requires_image_and_page(simple_pdf, tmp_path):
    """--overlay without --image and --page should fail."""
    fields_json = tmp_path / "fields.json"
    fields_json.write_text(json.dumps({"form_fields": []}))
    result = runner.invoke(
        app,
        ["read", str(simple_pdf), "--overlay", str(fields_json)],
    )
    assert result.exit_code == 1
    assert "requires" in result.output.lower()


# --- checkbox "checked" normalization tests ---


def _strip_checkbox_value(src: Path, dest: Path, field_name: str) -> Path:
    """Copy a PDF, removing /V from the named checkbox (simulates 'untouched')."""
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import NameObject

    reader = PdfReader(str(src))
    writer = PdfWriter()
    writer.append(reader)
    for page in writer.pages:
        for annot_ref in page.get("/Annots", []):
            annot = annot_ref.get_object()
            if str(annot.get("/T", "")) == field_name and NameObject("/V") in annot:
                del annot[NameObject("/V")]
    with open(dest, "wb") as fh:
        writer.write(fh)
    return dest


def test_read_fields_checkbox_checked_true(form_pdf, tmp_path):
    filled = tmp_path / "checked.pdf"
    result = runner.invoke(
        app,
        ["fill", str(form_pdf), "-", "--output", str(filled)],
        input=json.dumps({"TermsAccepted": True}),
    )
    assert result.exit_code == 0
    result = runner.invoke(app, ["read", str(filled), "--fields", "TermsAccepted", "--json"])
    assert result.exit_code == 0
    field = json.loads(result.output)["fields"][0]
    assert field["value"] == "Yes"  # raw value unchanged
    assert field["checked"] is True


def test_read_fields_checkbox_checked_false_explicit_off(form_pdf):
    """PyPDFForm-created checkboxes carry an explicit /V /Off -> checked false."""
    result = runner.invoke(app, ["read", str(form_pdf), "--fields", "TermsAccepted", "--json"])
    assert result.exit_code == 0
    field = json.loads(result.output)["fields"][0]
    assert field["value"] == "Off"
    assert field["checked"] is False


def test_read_fields_checkbox_checked_null_untouched(form_pdf, tmp_path):
    stripped = _strip_checkbox_value(form_pdf, tmp_path / "untouched.pdf", "TermsAccepted")
    result = runner.invoke(app, ["read", str(stripped), "--fields", "TermsAccepted", "--json"])
    assert result.exit_code == 0
    field = json.loads(result.output)["fields"][0]
    assert field["value"] is None
    assert field["checked"] is None


def test_read_fields_text_field_has_no_checked_key(filled_form_pdf):
    result = runner.invoke(app, ["read", str(filled_form_pdf), "--fields", "Company", "--json"])
    assert result.exit_code == 0
    field = json.loads(result.output)["fields"][0]
    assert "checked" not in field


def test_read_values_only_checkbox_stays_raw(form_pdf):
    """--values-only keeps the raw as-stated value (no derived boolean)."""
    result = runner.invoke(
        app, ["read", str(form_pdf), "--fields", "TermsAccepted", "--values-only"]
    )
    assert result.exit_code == 0
    assert json.loads(result.output) == {"TermsAccepted": "Off"}


def test_read_encrypted_pdf_clean_error(encrypted_pdf):
    result = runner.invoke(app, ["read", str(encrypted_pdf)])
    assert result.exit_code == 1
    assert "encrypted" in result.output.lower()
    assert result.exception is None or isinstance(result.exception, SystemExit)


def _duplicate_field(src: Path, dest: Path, field_name: str) -> Path:
    """Copy a PDF adding a second widget with the SAME field name."""
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import ArrayObject, DictionaryObject, FloatObject, NameObject

    reader = PdfReader(str(src))
    writer = PdfWriter()
    writer.append(reader)
    page = writer.pages[0]
    annots = page["/Annots"]
    source = None
    for ref in annots:
        obj = ref.get_object()
        if str(obj.get("/T", "")) == field_name:
            source = obj
            break
    assert source is not None
    dup = DictionaryObject()
    for key, value in source.items():
        if key not in ("/Rect", "/P"):
            dup[NameObject(key)] = value
    dup[NameObject("/Rect")] = ArrayObject(
        [FloatObject(10), FloatObject(10), FloatObject(110), FloatObject(30)]
    )
    annots.append(writer._add_object(dup))
    with open(dest, "wb") as fh:
        writer.write(fh)
    return dest


def test_read_fields_warns_on_collapsed_duplicates(form_pdf, tmp_path):
    """Two widgets with the same field name -> stderr warning, not silence."""
    dup_pdf = _duplicate_field(form_pdf, tmp_path / "dup.pdf", "Company")
    result = runner.invoke(app, ["read", str(dup_pdf), "--fields", "Company"])
    assert result.exit_code == 0
    assert "duplicate" in result.stderr.lower()
    assert "Company" in result.stderr


def test_read_fields_no_duplicate_warning_on_clean_pdf(form_pdf):
    result = runner.invoke(app, ["read", str(form_pdf), "--fields", "Company"])
    assert result.exit_code == 0
    assert "duplicate" not in result.stderr.lower()


# --- audit round: JSON shape, overlay validation, extraction warnings ---


def test_read_full_doc_json_is_array_even_for_single_page(tmp_path):
    """Without --page, JSON is ALWAYS an array — even for a 1-page document."""
    from pypdf import PdfWriter

    path = tmp_path / "one_page.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    with open(path, "wb") as fh:
        writer.write(fh)
    result = runner.invoke(app, ["read", str(path), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    assert len(data) == 1


def test_read_overlay_bare_list_clean_error(simple_pdf, tmp_path):
    """A bare list instead of {'form_fields': [...]} errors cleanly."""
    out_img = tmp_path / "page0.png"
    fields_json = tmp_path / "fields.json"
    fields_json.write_text(json.dumps([{"page_number": 0}]))
    result = runner.invoke(
        app,
        [
            "read",
            str(simple_pdf),
            "--page",
            "0",
            "--image",
            str(out_img),
            "--overlay",
            str(fields_json),
        ],
    )
    assert result.exit_code == 1
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert "form_fields" in result.output


def test_read_overlay_invalid_box_clean_error(simple_pdf, tmp_path):
    out_img = tmp_path / "page0.png"
    fields_json = tmp_path / "fields.json"
    fields_json.write_text(
        json.dumps({"form_fields": [{"page_number": 0, "entry_bounding_box": [1, 2]}]})
    )
    result = runner.invoke(
        app,
        [
            "read",
            str(simple_pdf),
            "--page",
            "0",
            "--image",
            str(out_img),
            "--overlay",
            str(fields_json),
        ],
    )
    assert result.exit_code == 1
    assert "entry_bounding_box" in result.output


def test_read_warns_when_form_extraction_fails(simple_pdf, monkeypatch):
    """Form-extraction failure must warn on stderr, not silently drop fields."""

    def boom(*args, **kwargs):
        raise RuntimeError("corrupt AcroForm")

    monkeypatch.setattr("pdf_tool.commands.read._extract_form_field_values", boom)
    result = runner.invoke(app, ["read", str(simple_pdf), "--page", "0"])
    assert result.exit_code == 0
    assert "warning" in result.stderr.lower()
    assert "form field" in result.stderr.lower()


def test_read_no_text_layer_hint(tmp_path):
    """A page set without any text layer (scan) hints at visual rendering."""
    from pypdf import PdfWriter

    path = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    with open(path, "wb") as fh:
        writer.write(fh)
    result = runner.invoke(app, ["read", str(path)])
    assert result.exit_code == 0
    assert "no text layer" in result.stderr.lower()
    assert "--image" in result.stderr


def test_read_text_pdf_has_no_text_layer_hint(simple_pdf):
    result = runner.invoke(app, ["read", str(simple_pdf)])
    assert result.exit_code == 0
    assert "no text layer" not in result.stderr.lower()


def _rotated_pdf(src: Path, dest: Path, degrees: int = 90) -> Path:
    """Copy a PDF with page 0 rotated."""
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(str(src))
    writer = PdfWriter()
    writer.append(reader)
    writer.pages[0].rotate(degrees)
    with open(dest, "wb") as fh:
        writer.write(fh)
    return dest


def test_read_warns_on_rotated_page(simple_pdf, tmp_path):
    rotated = _rotated_pdf(simple_pdf, tmp_path / "rot.pdf")
    result = runner.invoke(app, ["read", str(rotated), "--page", "0", "--json"])
    assert result.exit_code == 0
    json.loads(result.stdout)  # stdout JSON stays parseable
    assert "rotated" in result.stderr.lower()
    assert "page 0" in result.stderr.lower()


def test_read_no_rotation_warning_on_straight_page(simple_pdf, tmp_path):
    rotated = _rotated_pdf(simple_pdf, tmp_path / "rot.pdf")
    result = runner.invoke(app, ["read", str(rotated), "--page", "1"])
    assert result.exit_code == 0
    assert "rotated" not in result.stderr.lower()
