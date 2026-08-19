"""Tests for DatasetClient and AsyncDatasetClient."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from gofetch import ListPage
from gofetch.dataset import AsyncDatasetClient, DatasetClient


def _page(results: list[dict], *, offset: int, total: int) -> dict:
    return {"total": total, "offset": offset, "limit": 100, "count": len(results), "results": results}


class TestListItems:

    def test_returns_page_that_is_still_a_list(self) -> None:
        http = MagicMock()
        http.get.return_value = _page([{"a": 1}, {"a": 2}], offset=0, total=2)

        page = DatasetClient(http=http, job_id="job-1").list_items()

        assert isinstance(page, ListPage)
        assert isinstance(page, list)  # existing callers keep len()/iteration/indexing
        assert len(page) == 2
        assert page.items == [{"a": 1, "runId": "job-1"}, {"a": 2, "runId": "job-1"}]
        assert page.total == 2
        assert page.offset == 0
        assert page.limit is None

    def test_limit_truncates_but_total_is_the_servers(self) -> None:
        http = MagicMock()
        http.get.return_value = _page([{"a": 1}, {"a": 2}, {"a": 3}], offset=0, total=3)

        page = DatasetClient(http=http, job_id="job-1").list_items(limit=2)

        assert len(page) == 2
        assert page.limit == 2
        assert page.total == 3

    def test_pages_until_total(self) -> None:
        http = MagicMock()
        http.get.side_effect = [
            _page([{"a": 1}], offset=0, total=2),
            _page([{"a": 2}], offset=1, total=2),
        ]

        page = DatasetClient(http=http, job_id="job-1").list_items()

        assert len(page) == 2
        assert http.get.call_count == 2

    def test_empty_dataset(self) -> None:
        http = MagicMock()
        http.get.return_value = _page([], offset=0, total=0)

        page = DatasetClient(http=http, job_id="job-1").list_items()

        assert page == []
        assert page.total == 0

    def test_iterate_items_unchanged(self) -> None:
        http = MagicMock()
        http.get.side_effect = [
            _page([{"a": 1}, {"a": 2}], offset=0, total=3),
            _page([{"a": 3}], offset=2, total=3),
        ]

        items = list(DatasetClient(http=http, job_id="job-1").iterate_items(limit=3))

        assert [i["a"] for i in items] == [1, 2, 3]
        assert all(i["runId"] == "job-1" for i in items)


class TestAsyncListItems:

    @pytest.mark.asyncio
    async def test_returns_page(self) -> None:
        http = MagicMock()
        http.get = AsyncMock(return_value=_page([{"a": 1}, {"a": 2}, {"a": 3}], offset=0, total=3))

        page = await AsyncDatasetClient(http=http, job_id="job-1").list_items(limit=2)

        assert isinstance(page, ListPage)
        assert page.items == [{"a": 1, "runId": "job-1"}, {"a": 2, "runId": "job-1"}]
        assert page.total == 3
        assert page.limit == 2
