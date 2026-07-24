from hypothesis import given
from hypothesis import strategies as st

from pdf_tool.commands.read import _parse_pages_spec


@given(st.lists(st.integers(min_value=0, max_value=999), min_size=1, max_size=50))
def test_page_selection_round_trips_valid_lists(pages):
    total_pages = max(pages) + 1
    specification = ",".join(str(page) for page in pages)

    assert _parse_pages_spec(specification, total_pages) == sorted(set(pages))


@given(
    st.integers(min_value=0, max_value=500),
    st.integers(min_value=0, max_value=500),
)
def test_page_selection_normalizes_ranges(left, right):
    start, end = sorted((left, right))
    specification = f"{start}-{end}"

    assert _parse_pages_spec(specification, end + 1) == list(range(start, end + 1))
