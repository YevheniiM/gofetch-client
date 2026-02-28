"""Tests for BaseScraper."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from gofetch.scrapers.base import BaseScraper
from gofetch.types import RunStatus

# ---------------------------------------------------------------------------
# Minimal concrete subclass for testing
# ---------------------------------------------------------------------------


class _StubScraper(BaseScraper):
    """Concrete subclass that satisfies the abstract interface."""

    IGNORED_ERRORS = ["not_found", "no_items"]
    IGNORED_NOTES = ["Profile is private", "No videos found"]

    def run(self, *args: Any, **kwargs: Any) -> RunStatus:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# _filter_items tests
# ---------------------------------------------------------------------------


class TestFilterItems:

    def test_items_with_matching_error_are_filtered(self) -> None:
        scraper = _StubScraper(client=MagicMock(), scraper_type="instagram")
        items = [{"id": "1", "error": "not_found"}]
        assert scraper._filter_items(items) == []

    def test_items_with_matching_note_are_filtered(self) -> None:
        scraper = _StubScraper(client=MagicMock(), scraper_type="instagram")
        items = [{"id": "1", "note": "Profile is private"}]
        assert scraper._filter_items(items) == []

    def test_items_with_non_matching_error_are_kept(self) -> None:
        scraper = _StubScraper(client=MagicMock(), scraper_type="instagram")
        items = [{"id": "1", "error": "unknown_error"}]
        assert scraper._filter_items(items) == [{"id": "1", "error": "unknown_error"}]

    def test_items_with_non_matching_note_are_kept(self) -> None:
        scraper = _StubScraper(client=MagicMock(), scraper_type="instagram")
        items = [{"id": "1", "note": "Some other note"}]
        assert scraper._filter_items(items) == [{"id": "1", "note": "Some other note"}]

    def test_items_with_no_error_or_note_are_kept(self) -> None:
        scraper = _StubScraper(client=MagicMock(), scraper_type="instagram")
        items = [{"id": "1", "username": "nike"}]
        assert scraper._filter_items(items) == [{"id": "1", "username": "nike"}]

    def test_items_with_empty_string_error_are_kept(self) -> None:
        scraper = _StubScraper(client=MagicMock(), scraper_type="instagram")
        items = [{"id": "1", "error": ""}]
        assert scraper._filter_items(items) == [{"id": "1", "error": ""}]

    def test_items_with_empty_string_note_are_kept(self) -> None:
        scraper = _StubScraper(client=MagicMock(), scraper_type="instagram")
        items = [{"id": "1", "note": ""}]
        assert scraper._filter_items(items) == [{"id": "1", "note": ""}]

    def test_item_with_matching_error_and_non_matching_note_is_filtered(self) -> None:
        scraper = _StubScraper(client=MagicMock(), scraper_type="instagram")
        items = [{"id": "1", "error": "not_found", "note": "Some other note"}]
        assert scraper._filter_items(items) == []

    def test_item_with_non_matching_error_and_matching_note_is_filtered(self) -> None:
        scraper = _StubScraper(client=MagicMock(), scraper_type="instagram")
        items = [{"id": "1", "error": "unknown_error", "note": "Profile is private"}]
        assert scraper._filter_items(items) == []

    def test_empty_items_returns_empty_list(self) -> None:
        scraper = _StubScraper(client=MagicMock(), scraper_type="instagram")
        assert scraper._filter_items([]) == []


# ---------------------------------------------------------------------------
# fetch() tests
# ---------------------------------------------------------------------------


class TestFetch:

    def test_fetch_reads_default_dataset_id(self) -> None:
        mock_client = MagicMock()
        mock_dataset = MagicMock()
        mock_dataset.iterate_items.return_value = [{"id": "1"}]
        mock_client.dataset.return_value = mock_dataset

        scraper = _StubScraper(client=mock_client, scraper_type="instagram")
        run_data = {"defaultDatasetId": "ds-456", "id": "job-123"}
        result = scraper.fetch(run_data)

        mock_client.dataset.assert_called_once_with("ds-456")
        assert result == [{"id": "1"}]

    def test_fetch_falls_back_to_id(self) -> None:
        mock_client = MagicMock()
        mock_dataset = MagicMock()
        mock_dataset.iterate_items.return_value = [{"id": "1"}]
        mock_client.dataset.return_value = mock_dataset

        scraper = _StubScraper(client=mock_client, scraper_type="instagram")
        run_data = {"id": "job-123"}
        result = scraper.fetch(run_data)

        mock_client.dataset.assert_called_once_with("job-123")
        assert result == [{"id": "1"}]

    def test_fetch_raises_when_no_dataset_id(self) -> None:
        mock_client = MagicMock()
        scraper = _StubScraper(client=mock_client, scraper_type="instagram")

        with pytest.raises(ValueError, match="No dataset ID"):
            scraper.fetch({})

    def test_fetch_calls_filter_items(self) -> None:
        mock_client = MagicMock()
        mock_dataset = MagicMock()
        mock_dataset.iterate_items.return_value = [
            {"id": "1", "username": "nike"},
            {"id": "2", "error": "not_found"},
            {"id": "3", "note": "Profile is private"},
        ]
        mock_client.dataset.return_value = mock_dataset

        scraper = _StubScraper(client=mock_client, scraper_type="instagram")
        result = scraper.fetch({"defaultDatasetId": "ds-456"})

        assert len(result) == 1
        assert result[0]["id"] == "1"
