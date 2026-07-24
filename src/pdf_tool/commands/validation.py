"""Bounding box pre-validation for PDF form fields.

Checks for overlapping entry/label boxes and entry boxes that are too small
for their font size, before filling.
"""

DEFAULT_FONT_SIZE = 10
MAX_ERRORS = 20


def _boxes_overlap(
    box_a: list[float],
    box_b: list[float],
) -> bool:
    """Check if two axis-aligned bounding boxes [x0, y0, x1, y1] overlap.

    Returns False if they merely touch (shared edge) without interior overlap.
    """
    ax0, ay0, ax1, ay1 = box_a
    bx0, by0, bx1, by1 = box_b
    # No overlap if one is completely left, right, above, or below the other
    return not (ax1 <= bx0 or bx1 <= ax0 or ay1 <= by0 or by1 <= ay0)


def check_bounding_boxes(fields: list[dict]) -> list[str]:
    """Validate bounding boxes for a list of form field dicts.

    Each field dict should have:
        - entry_bounding_box: [x0, y0, x1, y1]
        - label_bounding_box: [x0, y0, x1, y1] (optional)
        - page_number: int
        - entry_text: dict with font_size (optional, default 10)

    Checks:
        1. Pairwise overlaps between all entry and label boxes on the same page.
        2. Entry box height >= font_size.

    Returns:
        List of error messages (empty means no issues). Capped at MAX_ERRORS.
    """
    errors: list[str] = []

    # Collect all boxes grouped by page for overlap checks
    # Each item: (label, box, field_index)
    page_boxes: dict[int, list[tuple[str, list[float], int]]] = {}

    for i, field in enumerate(fields):
        page = field.get("page_number", 0)
        if page not in page_boxes:
            page_boxes[page] = []

        ref = f'"{field["name"]}"' if field.get("name") else f"field[{i}]"
        entry_box = field.get("entry_bounding_box")
        if entry_box and len(entry_box) == 4:
            page_boxes[page].append((f"{ref}.entry", entry_box, i))

        label_box = field.get("label_bounding_box")
        if label_box and len(label_box) == 4:
            page_boxes[page].append((f"{ref}.label", label_box, i))

    # Check pairwise overlaps on each page
    for page, boxes in page_boxes.items():
        for a_idx in range(len(boxes)):
            if len(errors) >= MAX_ERRORS:
                return errors
            for b_idx in range(a_idx + 1, len(boxes)):
                if len(errors) >= MAX_ERRORS:
                    return errors
                a_label, a_box, _ = boxes[a_idx]
                b_label, b_box, _ = boxes[b_idx]
                if _boxes_overlap(a_box, b_box):
                    errors.append(f"Page {page}: {a_label} overlaps {b_label} ({a_box} vs {b_box})")

    # Check entry box height vs font size
    for i, field in enumerate(fields):
        if len(errors) >= MAX_ERRORS:
            return errors

        entry_box = field.get("entry_bounding_box")
        if not entry_box or len(entry_box) != 4:
            continue

        entry_text = field.get("entry_text") or {}
        font_size = entry_text.get("font_size", DEFAULT_FONT_SIZE)

        # Height is abs(y1 - y0)
        box_height = abs(entry_box[3] - entry_box[1])
        if box_height < font_size:
            ref = f'"{field["name"]}"' if field.get("name") else f"field[{i}]"
            errors.append(f"{ref}.entry: box height {box_height:.1f} < font_size {font_size}")

    return errors
