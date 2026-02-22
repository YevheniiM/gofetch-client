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

logger = logging.getLogger(__name__)


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
        page_size = DEFAULT_PAGE_SIZE
        current_offset = offset
        items_yielded = 0

        while True:
            response = self._http.get(
                f"/api/v1/jobs/{self._job_id}/results/",
                params={
                    "offset": current_offset,
                    "limit": page_size,
                },
            )

            items = response.get("results", response.get("items", []))
            if not items:
                break

            for item in items:
                if limit is not None and items_yielded >= limit:
                    return

                item = {**item, "runId": self._job_id}
                yield item
                items_yielded += 1

            current_offset += len(items)

            total = response.get("total", 0)
            if current_offset >= total:
                break

    def list_items(
        self,
        offset: int = 0,
        limit: int | None = None,
        clean: bool | None = None,
        fields: list[str] | None = None,
        omit: list[str] | None = None,
        unwind: str | None = None,
        desc: bool | None = None,
    ) -> list[dict[str, Any]]:
        """Get all items as a list."""
        return list(
            self.iterate_items(
                offset=offset,
                limit=limit,
                clean=clean,
                fields=fields,
                omit=omit,
                unwind=unwind,
                desc=desc,
            )
        )

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
        page_size = DEFAULT_PAGE_SIZE
        current_offset = offset
        items_yielded = 0

        while True:
            response = await self._http.get(
                f"/api/v1/jobs/{self._job_id}/results/",
                params={
                    "offset": current_offset,
                    "limit": page_size,
                },
            )

            items = response.get("results", response.get("items", []))
            if not items:
                break

            for item in items:
                if limit is not None and items_yielded >= limit:
                    return

                item = {**item, "runId": self._job_id}
                yield item
                items_yielded += 1

            current_offset += len(items)

            total = response.get("total", 0)
            if current_offset >= total:
                break

    async def list_items(
        self,
        offset: int = 0,
        limit: int | None = None,
        clean: bool | None = None,
        fields: list[str] | None = None,
        omit: list[str] | None = None,
        unwind: str | None = None,
        desc: bool | None = None,
    ) -> list[dict[str, Any]]:
        """Get all items as a list."""
        return [
            item async for item in self.iterate_items(
                offset=offset,
                limit=limit,
                clean=clean,
                fields=fields,
                omit=omit,
                unwind=unwind,
                desc=desc,
            )
        ]

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
