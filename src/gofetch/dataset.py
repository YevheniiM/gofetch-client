"""
Dataset client for GoFetch API.

Provides Apify-compatible interface for fetching scraper results.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

    from gofetch.http import AsyncHTTPClient, HTTPClient

from gofetch.constants import DEFAULT_PAGE_SIZE
from gofetch.types import ListPage

logger = logging.getLogger(__name__)


def _page_items(response: dict[str, Any], job_id: str) -> list[dict[str, Any]]:
    return [
        {**item, "runId": job_id}
        for item in response.get("results", response.get("items", []))
    ]


class DatasetClient:
    """
    Dataset client that wraps GoFetch results API with Apify-compatible interface.

    Provides the same methods as Apify's DatasetClient:
    - iterate_items() for iterating over all results
    - list_items() for getting results as a list
    - delete() for cleanup (logs warning in GoFetch)
    """

    def __init__(
        self,
        http: HTTPClient,
        job_id: str,
    ) -> None:
        self._http = http
        self._job_id = job_id

    def _iter_pages(self, offset: int) -> Iterator[tuple[list[dict[str, Any]], int]]:
        """Yield (items, server total) per page until the results are exhausted."""
        while True:
            response = self._http.get(
                f"/api/v1/jobs/{self._job_id}/results/",
                params={"offset": offset, "limit": DEFAULT_PAGE_SIZE},
            )
            items = _page_items(response, self._job_id)
            total = response.get("total", 0)
            yield items, total
            offset += len(items)
            if not items or offset >= total:
                return

    def iterate_items(
        self,
        offset: int = 0,
        limit: int | None = None,
        clean: bool | None = None,
        fields: list[str] | None = None,
        omit: list[str] | None = None,
        unwind: str | None = None,
        desc: bool | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Iterate over all items in the dataset.

        Yields individual result items. This is a true lazy generator.
        """
        items_yielded = 0
        for items, _total in self._iter_pages(offset):
            for item in items:
                if limit is not None and items_yielded >= limit:
                    return
                yield item
                items_yielded += 1

    def list_items(
        self,
        offset: int = 0,
        limit: int | None = None,
        clean: bool | None = None,
        fields: list[str] | None = None,
        omit: list[str] | None = None,
        unwind: str | None = None,
        desc: bool | None = None,
    ) -> ListPage:
        """Get all items as a :class:`~gofetch.ListPage` (a ``list`` with Apify page attributes)."""
        collected: list[dict[str, Any]] = []
        total = 0
        for items, page_total in self._iter_pages(offset):
            total = page_total
            collected.extend(items)
            if limit is not None and len(collected) >= limit:
                break
        if limit is not None:
            collected = collected[:limit]
        return ListPage(collected, offset=offset, limit=limit, total=total, desc=bool(desc))

    def get_info(self) -> dict[str, Any]:
        """Get dataset/job information."""
        job = self._http.get(f"/api/v1/jobs/{self._job_id}/")
        return {
            "id": self._job_id,
            "name": f"gofetch-{self._job_id}",
            "itemCount": job.get("items_scraped", 0),
            "createdAt": job.get("created_at"),
            "modifiedAt": job.get("updated_at"),
        }

    def delete(self) -> None:
        """Delete the dataset (no-op in GoFetch, logs warning)."""
        logger.warning(
            "dataset.delete() is a no-op in GoFetch. "
            "GoFetch manages dataset retention automatically."
        )


class AsyncDatasetClient:
    """Async dataset client for GoFetch API."""

    def __init__(
        self,
        http: AsyncHTTPClient,
        job_id: str,
    ) -> None:
        self._http = http
        self._job_id = job_id

    async def _iter_pages(self, offset: int) -> AsyncIterator[tuple[list[dict[str, Any]], int]]:
        """Yield (items, server total) per page until the results are exhausted."""
        while True:
            response = await self._http.get(
                f"/api/v1/jobs/{self._job_id}/results/",
                params={"offset": offset, "limit": DEFAULT_PAGE_SIZE},
            )
            items = _page_items(response, self._job_id)
            total = response.get("total", 0)
            yield items, total
            offset += len(items)
            if not items or offset >= total:
                return

    async def iterate_items(
        self,
        offset: int = 0,
        limit: int | None = None,
        clean: bool | None = None,
        fields: list[str] | None = None,
        omit: list[str] | None = None,
        unwind: str | None = None,
        desc: bool | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Iterate over all items in the dataset. Async generator."""
        items_yielded = 0
        async for items, _total in self._iter_pages(offset):
            for item in items:
                if limit is not None and items_yielded >= limit:
                    return
                yield item
                items_yielded += 1

    async def list_items(
        self,
        offset: int = 0,
        limit: int | None = None,
        clean: bool | None = None,
        fields: list[str] | None = None,
        omit: list[str] | None = None,
        unwind: str | None = None,
        desc: bool | None = None,
    ) -> ListPage:
        """Get all items as a :class:`~gofetch.ListPage` (a ``list`` with Apify page attributes)."""
        collected: list[dict[str, Any]] = []
        total = 0
        async for items, page_total in self._iter_pages(offset):
            total = page_total
            collected.extend(items)
            if limit is not None and len(collected) >= limit:
                break
        if limit is not None:
            collected = collected[:limit]
        return ListPage(collected, offset=offset, limit=limit, total=total, desc=bool(desc))

    async def get_info(self) -> dict[str, Any]:
        """Get dataset/job information."""
        job = await self._http.get(f"/api/v1/jobs/{self._job_id}/")
        return {
            "id": self._job_id,
            "name": f"gofetch-{self._job_id}",
            "itemCount": job.get("items_scraped", 0),
            "createdAt": job.get("created_at"),
            "modifiedAt": job.get("updated_at"),
        }

    async def delete(self) -> None:
        """Delete the dataset (no-op in GoFetch, logs warning)."""
        logger.warning(
            "dataset.delete() is a no-op in GoFetch. "
            "GoFetch manages dataset retention automatically."
        )
