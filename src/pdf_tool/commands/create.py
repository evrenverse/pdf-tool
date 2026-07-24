"""pdf-tool create command — generate a new PDF from Markdown content.

Renders Markdown (headings, paragraphs, **bold**/*italic*, bullet & numbered
lists, horizontal rules and simple pipe tables) into a clean, multi-page PDF via
reportlab Platypus. An installed DejaVu Sans family is preferred; ReportLab's
bundled Bitstream Vera family provides a portable embedded fallback.

The supported character set depends on the selected font. No bundled font
provides every Unicode script.
"""

import html
import os
import re
import sys
from importlib.resources import files
from pathlib import Path
from typing import Annotated

import typer

# Prefer a user-supplied family, then common Linux DejaVu paths.
_DEJAVU_NAMES = {
    "DejaVuSans": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "DejaVuSans-Bold": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "DejaVuSans-Oblique": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
    "DejaVuSans-BoldOblique": "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf",
}


def _register_font() -> str:
    """Register an embeddable font family and return its base name.

    Prefer DejaVu Sans and fall back to ReportLab's bundled Bitstream Vera.
    ``PDF_TOOL_FONT_DIR`` may point to a directory containing the four DejaVu
    files named below.
    """
    from reportlab.lib.fonts import addMapping
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    font_dir = os.environ.get("PDF_TOOL_FONT_DIR")
    dejavu = {
        name: str(Path(font_dir) / Path(path).name) if font_dir else path
        for name, path in _DEJAVU_NAMES.items()
    }
    if all(Path(p).is_file() for p in dejavu.values()):
        try:
            for name, path in dejavu.items():
                pdfmetrics.registerFont(TTFont(name, path))
            # (family, bold, italic) -> font name, so <b>/<i> markup resolves.
            addMapping("DejaVuSans", 0, 0, "DejaVuSans")
            addMapping("DejaVuSans", 1, 0, "DejaVuSans-Bold")
            addMapping("DejaVuSans", 0, 1, "DejaVuSans-Oblique")
            addMapping("DejaVuSans", 1, 1, "DejaVuSans-BoldOblique")
            return "DejaVuSans"
        except Exception:  # pragma: no cover - defensive, falls back to Vera
            pass

    vera_dir = files("reportlab").joinpath("fonts")
    vera = {
        "Vera": vera_dir.joinpath("Vera.ttf"),
        "VeraBd": vera_dir.joinpath("VeraBd.ttf"),
        "VeraIt": vera_dir.joinpath("VeraIt.ttf"),
        "VeraBI": vera_dir.joinpath("VeraBI.ttf"),
    }
    for name, vera_path in vera.items():
        pdfmetrics.registerFont(TTFont(name, str(vera_path)))
    addMapping("Vera", 0, 0, "Vera")
    addMapping("Vera", 1, 0, "VeraBd")
    addMapping("Vera", 0, 1, "VeraIt")
    addMapping("Vera", 1, 1, "VeraBI")
    return "Vera"


def _inline(text: str) -> str:
    """Escape XML special chars, then map **bold**/*italic*/`code` to reportlab markup."""
    out = html.escape(text, quote=False)
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    out = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*", r"<i>\1</i>", out)
    out = re.sub(r"`(.+?)`", r"<font face='Courier'>\1</font>", out)
    return out


def _build_styles(base_font: str):
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

    bold = "DejaVuSans-Bold" if base_font == "DejaVuSans" else "VeraBd"
    ss = getSampleStyleSheet()
    return {
        "body": ParagraphStyle(
            "Body", parent=ss["BodyText"], fontName=base_font, fontSize=10.5, leading=15
        ),
        "li": ParagraphStyle(
            "Li",
            parent=ss["BodyText"],
            fontName=base_font,
            fontSize=10.5,
            leading=15,
            leftIndent=16,
            bulletIndent=4,
        ),
        "h1": ParagraphStyle("H1", fontName=bold, fontSize=18, leading=22, spaceAfter=10),
        "h2": ParagraphStyle(
            "H2", fontName=bold, fontSize=14, leading=18, spaceBefore=8, spaceAfter=6
        ),
        "h3": ParagraphStyle(
            "H3", fontName=bold, fontSize=12, leading=15, spaceBefore=6, spaceAfter=4
        ),
        "bold_font": bold,
    }


def _table_rows(lines: list[str]) -> list[list[str]]:
    """Parse pipe-table lines into a list of cell-rows, dropping the `---` divider."""
    rows = []
    for ln in lines:
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if cells and all(set(c) <= {"-", ":", " "} and c for c in cells):
            continue  # separator row (| --- | --- |)
        rows.append(cells)
    return rows


def _markdown_to_flowables(md: str, styles: dict):
    """Convert a small Markdown subset into reportlab Platypus flowables."""
    from reportlab.lib import colors
    from reportlab.platypus import HRFlowable, Paragraph, Spacer, Table, TableStyle

    flow: list = []
    lines = md.replace("\r\n", "\n").split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        # Horizontal rule
        if re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", stripped):
            flow.append(Spacer(1, 4))
            flow.append(HRFlowable(width="100%", thickness=0.6, color=colors.grey))
            flow.append(Spacer(1, 6))
            i += 1
            continue
        # Headings
        m = re.match(r"(#{1,3})\s+(.*)", stripped)
        if m:
            level = len(m.group(1))
            flow.append(Paragraph(_inline(m.group(2)), styles[f"h{level}"]))
            i += 1
            continue
        # Pipe table (consecutive lines starting with '|')
        if stripped.startswith("|"):
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i])
                i += 1
            rows = _table_rows(block)
            if rows:
                data = [[Paragraph(_inline(c), styles["body"]) for c in r] for r in rows]
                tbl = Table(data, hAlign="LEFT")
                tbl.setStyle(
                    TableStyle(
                        [
                            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
                            ("FONTNAME", (0, 0), (-1, 0), styles["bold_font"]),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 5),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                            ("TOPPADDING", (0, 0), (-1, -1), 3),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                        ]
                    )
                )
                flow.append(tbl)
                flow.append(Spacer(1, 8))
            continue
        # List block (bullet or numbered)
        if re.match(r"([-*+]\s+|\d+\.\s+)", stripped):
            while i < len(lines) and re.match(r"\s*([-*+]\s+|\d+\.\s+)", lines[i]):
                item = lines[i].strip()
                num = re.match(r"(\d+)\.\s+(.*)", item)
                if num:
                    bullet, body = f"{num.group(1)}.", num.group(2)
                else:
                    bullet, body = "•", re.sub(r"^[-*+]\s+", "", item)
                flow.append(Paragraph(_inline(body), styles["li"], bulletText=bullet))
                i += 1
            flow.append(Spacer(1, 4))
            continue
        # Paragraph (gather following non-blank, non-structural lines)
        para = [stripped]
        i += 1
        while i < len(lines):
            nxt = lines[i].strip()
            if (
                not nxt
                or re.match(r"(#{1,3}\s|[-*+]\s|\d+\.\s|\|)", nxt)
                or re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", nxt)
            ):
                break
            para.append(nxt)
            i += 1
        flow.append(Paragraph(_inline(" ".join(para)), styles["body"]))
        flow.append(Spacer(1, 6))
    return flow


def create(
    output: Annotated[Path, typer.Argument(help="Output PDF path.")],
    source: Annotated[str, typer.Argument(help="Markdown source file, or '-' for stdin.")] = "-",
    title: Annotated[str | None, typer.Option("--title", help="PDF title metadata.")] = None,
    page_size: Annotated[str, typer.Option("--page-size", help="Page size: a4 or letter.")] = "a4",
) -> None:
    """Create a new PDF from Markdown content with an embedded font."""
    if source == "-":
        md = sys.stdin.read()
    else:
        src_path = Path(source)
        if not src_path.exists():
            typer.echo(f"Error: source file not found: {source}", err=True)
            raise typer.Exit(code=1)
        md = src_path.read_text(encoding="utf-8")

    if not md.strip():
        typer.echo("Error: source content is empty", err=True)
        raise typer.Exit(code=1)

    from reportlab.lib.pagesizes import A4, LETTER
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate

    pagesize = LETTER if page_size.lower() == "letter" else A4
    base_font = _register_font()
    styles = _build_styles(base_font)
    flowables = _markdown_to_flowables(md, styles)

    from pdf_tool.commands.common import atomic_output

    n_blocks = len(flowables)  # doc.build() drains the story list, so count first.
    with atomic_output(output) as temporary:
        doc = SimpleDocTemplate(
            str(temporary),
            pagesize=pagesize,
            title=title or output.stem,
            leftMargin=2 * cm,
            rightMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
        )
        doc.build(flowables)

        from pypdf import PdfReader

        pages = len(PdfReader(str(temporary)).pages)
    typer.echo(
        f"Created: {output.name} ({pages} page{'s' if pages != 1 else ''}, "
        f"{n_blocks} blocks, font={base_font})"
    )
