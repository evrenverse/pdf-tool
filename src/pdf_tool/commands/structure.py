"""Form structure detection for non-fillable PDFs.

Extracts labels, horizontal lines, checkbox rectangles, and row boundaries
from PDFs that lack AcroForm fields, using pdfplumber geometry analysis.
"""

import pdfplumber


def _is_wide_horizontal_line(
    line: dict,
    page_width: float,
    min_width_ratio: float = 0.5,
) -> bool:
    """Check if a line is horizontal and spans more than min_width_ratio of page width."""
    x0, x1 = float(line["x0"]), float(line["x1"])
    top, bottom = float(line["top"]), float(line["bottom"])
    line_width = abs(x1 - x0)
    line_height = abs(bottom - top)
    # Horizontal: negligible vertical extent, wide enough
    return line_height < 2 and line_width > page_width * min_width_ratio


def _is_checkbox_rect(rect: dict, min_size: float = 5, max_size: float = 15) -> bool:
    """Check if a rectangle looks like a checkbox (small square, aspect ratio ~1:1)."""
    w = abs(float(rect["x1"]) - float(rect["x0"]))
    h = abs(float(rect["bottom"]) - float(rect["top"]))
    if w < min_size or w > max_size or h < min_size or h > max_size:
        return False
    aspect = w / h if h > 0 else 0
    return 0.7 <= aspect <= 1.4


def extract_form_structure(file_path: str) -> dict:
    """Extract form structure from a non-fillable PDF.

    Uses pdfplumber to analyze page geometry and detect:
    - Text labels with exact coordinates
    - Horizontal lines (>50% page width) as row boundaries
    - Checkbox rectangles (small squares 5-15px)
    - Row boundaries derived from line positions
    - Page metadata (width, height)

    Args:
        file_path: Path to the PDF file.

    Returns:
        Dict with keys: pages, labels, lines, checkboxes, row_boundaries.
    """
    pages_meta: list[dict] = []
    all_labels: list[dict] = []
    all_lines: list[dict] = []
    all_checkboxes: list[dict] = []
    all_boundaries: list[dict] = []

    with pdfplumber.open(file_path) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            page_width = float(page.width)
            page_height = float(page.height)
            pages_meta.append(
                {
                    "page": page_idx,
                    "width": page_width,
                    "height": page_height,
                }
            )

            # Extract text labels with coordinates
            words = page.extract_words()
            all_labels.extend(
                {
                    "text": word["text"],
                    "x0": float(word["x0"]),
                    "top": float(word["top"]),
                    "x1": float(word["x1"]),
                    "bottom": float(word["bottom"]),
                    "page": page_idx,
                }
                for word in words
            )

            # Extract horizontal lines
            all_lines.extend(
                {
                    "x0": float(line["x0"]),
                    "x1": float(line["x1"]),
                    "top": float(line["top"]),
                    "page": page_idx,
                }
                for line in page.lines
                if _is_wide_horizontal_line(line, page_width)
            )

            # Extract checkbox rectangles
            all_checkboxes.extend(
                {
                    "x0": float(rect["x0"]),
                    "top": float(rect["top"]),
                    "width": round(abs(float(rect["x1"]) - float(rect["x0"])), 1),
                    "height": round(abs(float(rect["bottom"]) - float(rect["top"])), 1),
                    "page": page_idx,
                }
                for rect in page.rects
                if _is_checkbox_rect(rect)
            )

    # Row boundaries: unique vertical positions of horizontal lines, sorted
    seen_boundaries: set[tuple[int, float]] = set()
    for line in all_lines:
        key = (line["page"], round(line["top"], 1))
        if key not in seen_boundaries:
            seen_boundaries.add(key)
            all_boundaries.append(
                {
                    "top": round(line["top"], 1),
                    "page": line["page"],
                }
            )
    all_boundaries.sort(key=lambda b: (b["page"], b["top"]))

    return {
        "pages": pages_meta,
        "labels": all_labels,
        "lines": all_lines,
        "checkboxes": all_checkboxes,
        "row_boundaries": all_boundaries,
    }
