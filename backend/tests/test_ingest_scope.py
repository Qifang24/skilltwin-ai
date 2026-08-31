"""Knowledge ingest scope safeguards for multi-programme source PDFs."""

from __future__ import annotations

import pytest

from app.rag.loader import LoadedPage
from scripts.ingest_knowledge import _select_pages


def _pages() -> list[LoadedPage]:
    return [LoadedPage(page_index=i, printed_page=str(i), text=f"page {i}") for i in range(1, 6)]


def test_select_pages_keeps_the_declared_inclusive_physical_range() -> None:
    result = _select_pages(_pages(), {"physical_page_range": [2, 4]})
    assert [page.page_index for page in result] == [2, 3, 4]


@pytest.mark.parametrize("value", [[0, 3], [4, 3], [1], ["1", 3]])
def test_select_pages_rejects_invalid_ranges(value: object) -> None:
    with pytest.raises(ValueError):
        _select_pages(_pages(), {"physical_page_range": value})
