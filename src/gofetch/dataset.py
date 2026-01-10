"""
Dataset client for GoFetch API.

Provides Apify-compatible interface for fetching scraper results.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

    from gofetch.http import AsyncHTTPClient, HTTPClient

from gofetch.constants import DEFAULT_PAGE_SIZE


class DatasetClient:
    """
    Dataset client that wraps GoFetch results API with Apify-compatible interface.

    Provides the same methods as Apify's DatasetClient:
    - iterate_items() for iterating over all results
    - list_items() for getting results as a list
    - delete() for cleanup (no-op in GoFetch)

    Usage:
        client = GoFetchClient(api_key="...")
        run = actor.call(run_input={...})

        dataset = client.dataset(run["defaultDatasetId"])
        items = list(dataset.iterate_items())
    """

    def __init__(
        self,
        http: HTTPClient,
        job_id: str,
    ) -> None:
        """
        Initialize dataset client.

        Args:
            http: HTTP client for API requests
            job_id: Job ID (same as dataset ID in GoFetch)
        """
        self._http = http
        self._job_id = job_id

    def iterate_items(
        self,
        offset: int = 0,
        limit: int | None = None,
        clean: bool | None = None,  # Ignored, Apify compat
        fields: list[str] | None = None,  # Ignored, Apify compat
        omit: list[str] | None = None,  # Ignored, Apify compat
        unwind: str | None = None,  # Ignored, Apify compat
        desc: bool | None = None,  # Ignored, Apify compat
    ) -> Iterator[dict[str, Any]]:
        """
        Iterate over all items in the dataset.

        Equivalent to Apify's dataset.iterate_items().

        Args:
            offset: Number of items to skip
            limit: Maximum number of items to return (None for all)
            clean: Ignored (Apify compatibility)
            fields: Ignored (Apify compatibility)
            omit: Ignored (Apify compatibility)
            unwind: Ignored (Apify compatibility)
            desc: Ignored (Apify compatibility)

        Yields:
            Individual result items from the scraper

        Example:
            for item in dataset.iterate_items():
                print(item["id"], item.get("caption"))
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

            items = response.get("items", [])
            if not items:
                break

            for item in items:
                if limit is not None and items_yielded >= limit:
                    return

                # Add metadata like Apify does
                item["runId"] = self._job_id
                yield item
                items_yielded += 1

            current_offset += len(items)

            # Check if we've fetched all items
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
        """
        Get all items as a list.

        Equivalent to list(dataset.iterate_items()).

        Args:
            offset: Number of items to skip
            limit: Maximum number of items to return
            clean: Ignored (Apify compatibility)
            fields: Ignored (Apify compatibility)
            omit: Ignored (Apify compatibility)
            unwind: Ignored (Apify compatibility)
            desc: Ignored (Apify compatibility)

        Returns:
            List of all result items
        """
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
        """
        Get dataset/job information.

        Returns:
            Dict with dataset info including item count
        """
        job = self._http.get(f"/api/v1/jobs/{self._job_id}/")
        return {
            "id": self._job_id,
            "name": f"gofetch-{self._job_id}",
            "itemCount": job.get("items_scraped", 0),
            "createdAt": job.get("created_at"),
            "modifiedAt": job.get("updated_at"),
        }

    def delete(self) -> None:
        """
        Delete the dataset (cleanup).

        In GoFetch, this is a no-op as results are stored in S3
        with automatic expiration. Kept for Apify API compatibility.

        Note: You can optionally cancel the job if it's still running
        by uncommenting the line below.
        """
        # No-op for GoFetch - results auto-expire in S3
        # Could optionally cancel job: self._http.delete(f"/api/v1/jobs/{self._job_id}/")
        pass


class AsyncDatasetClient:
    """
    Async dataset client for GoFetch API.

    Same interface as DatasetClient but uses async/await.
    """

    def __init__(
        self,
        http: AsyncHTTPClient,
        job_id: str,
    ) -> None:
        """Initialize async dataset client."""
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
    ) -> list[dict[str, Any]]:
        """
        Get all items from the dataset.

        Note: For async, this returns a list instead of an async iterator
        for simplicity. Use offset/limit for pagination.

        Args:
            offset: Number of items to skip
            limit: Maximum number of items to return

        Returns:
            List of result items
        """
        page_size = DEFAULT_PAGE_SIZE
        current_offset = offset
        all_items: list[dict[str, Any]] = []
        items_fetched = 0

        while True:
            response = await self._http.get(
                f"/api/v1/jobs/{self._job_id}/results/",
                params={
                    "offset": current_offset,
                    "limit": page_size,
                },
            )

            items = response.get("items", [])
            if not items:
                break

            for item in items:
                if limit is not None and items_fetched >= limit:
                    return all_items

                item["runId"] = self._job_id
                all_items.append(item)
                items_fetched += 1

            current_offset += len(items)

            total = response.get("total", 0)
            if current_offset >= total:
                break

        return all_items

    async def list_items(
        self,
        offset: int = 0,
        limit: int | None = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Get all items as a list."""
        return await self.iterate_items(offset=offset, limit=limit)

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
        """Delete the dataset (no-op in GoFetch)."""
        pass
