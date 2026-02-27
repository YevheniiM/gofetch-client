"""
Base scraper interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar

from gofetch.constants import (
    GOOGLE_NEWS_IGNORED_ERRORS,
    GOOGLE_NEWS_IGNORED_NOTES,
    INSTAGRAM_IGNORED_ERRORS,
    INSTAGRAM_IGNORED_NOTES,
    REDDIT_IGNORED_ERRORS,
    REDDIT_IGNORED_NOTES,
    TIKTOK_IGNORED_ERRORS,
    TIKTOK_IGNORED_NOTES,
    YOUTUBE_IGNORED_ERRORS,
    YOUTUBE_IGNORED_NOTES,
)

if TYPE_CHECKING:
    from gofetch.client import GoFetchClient
    from gofetch.types import RunStatus

# Module-level registry
_PLATFORM_ERRORS: dict[str, list[str]] = {
    "instagram": INSTAGRAM_IGNORED_ERRORS,
    "instagram_profile": INSTAGRAM_IGNORED_ERRORS,
    "instagram_posts": INSTAGRAM_IGNORED_ERRORS,
    "tiktok": TIKTOK_IGNORED_ERRORS,
    "youtube": YOUTUBE_IGNORED_ERRORS,
    "reddit": REDDIT_IGNORED_ERRORS,
    "google_news": GOOGLE_NEWS_IGNORED_ERRORS,
}

_PLATFORM_NOTES: dict[str, list[str]] = {
    "instagram": INSTAGRAM_IGNORED_NOTES,
    "instagram_profile": INSTAGRAM_IGNORED_NOTES,
    "instagram_posts": INSTAGRAM_IGNORED_NOTES,
    "tiktok": TIKTOK_IGNORED_NOTES,
    "youtube": YOUTUBE_IGNORED_NOTES,
    "reddit": REDDIT_IGNORED_NOTES,
    "google_news": GOOGLE_NEWS_IGNORED_NOTES,
}


class BaseScraper(ABC):
    """Abstract base class for platform-specific scrapers."""

    IGNORED_ERRORS: ClassVar[list[str]] = []
    IGNORED_NOTES: ClassVar[list[str]] = []

    def __init__(self, client: GoFetchClient, scraper_type: str) -> None:
        self._client = client
        self._scraper_type = scraper_type
        self._actor = client.actor(scraper_type)
        # Auto-load platform-specific filters if not overridden by subclass
        if not self.IGNORED_ERRORS:
            self.IGNORED_ERRORS = _PLATFORM_ERRORS.get(scraper_type, [])
        if not self.IGNORED_NOTES:
            self.IGNORED_NOTES = _PLATFORM_NOTES.get(scraper_type, [])

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
