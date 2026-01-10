"""
Base scraper interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from gofetch.client import GoFetchClient
    from gofetch.types import RunStatus


class BaseScraper(ABC):
    """Abstract base class for platform-specific scrapers."""

    IGNORED_ERRORS: ClassVar[list[str]] = []
    IGNORED_NOTES: ClassVar[list[str]] = []

    def __init__(self, client: GoFetchClient, scraper_type: str) -> None:
        self._client = client
        self._scraper_type = scraper_type
        self._actor = client.actor(scraper_type)

    @abstractmethod
    def run(self, *args: Any, **kwargs: Any) -> RunStatus:
        raise NotImplementedError

    def fetch(self, run_data: dict[str, Any]) -> list[dict[str, Any]]:
        dataset_id = run_data.get("defaultDatasetId") or run_data.get("id")
        if not dataset_id:
            raise ValueError("No dataset ID in run data")
        dataset = self._client.dataset(dataset_id)
        items = list(dataset.iterate_items())
        return self._filter_items(items)

    def _filter_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        filtered = []
        for item in items:
            error = item.get("error")
            note = item.get("note")
            if error and error in self.IGNORED_ERRORS:
                continue
            if note and note in self.IGNORED_NOTES:
                continue
            filtered.append(item)
        return filtered
