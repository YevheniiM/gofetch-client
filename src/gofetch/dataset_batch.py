"""Dataset batch client for GoFetch API.

One pulled batch: read its rows, ack it (which ledgers and charges them), or
re-export an acked one as a file for free.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from gofetch.constants import DATASET_MAX_PAGE_SIZE
from gofetch.datasets import DATASETS_PATH, aiter_rows, alist_page, iter_rows, list_page
from gofetch.exceptions import APIError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

    from gofetch.http import AsyncHTTPClient, HTTPClient
    from gofetch.types import ListPage


class DatasetBatchClient:
    """One batch of a Datasets-product dataset."""

    def __init__(self, http: HTTPClient, slug: str, batch_id: str) -> None:
        self._http = http
        self._batch_id = batch_id
        self._path = f"{DATASETS_PATH}{slug}/batches/{batch_id}/"

    def get(self) -> dict[str, Any] | None:
        """The batch, with its ``manifest`` and ``constraints``. None if not found.

        ``billed_amount`` and ``price_per_1000_at_open`` are decimal strings.
        Bill from ``billed_rows``, never from ``row_count``: an ack can charge
        for fewer rows than the batch advertises and says why in
        ``constraints``.
        """
        try:
            return self._http.get(self._path)
        except APIError as e:
            if e.status_code == 404:
                return None
            raise

    def rows(self, *, limit: int = 25, offset: int = 0) -> ListPage:
        """One page of the batch's rows. Byte-identical across re-reads.

        Rows are opaque per-dataset objects. An acked batch stays readable
        forever.

        Raises:
            BatchExpiredError: The batch expired before it was acked, so its
                rows went back to the pool. **Nothing was billed** — pull again.
        """
        return list_page(self._http, f"{self._path}rows/", limit=limit, offset=offset)

    def iterate_rows(
        self, *, page_size: int = DATASET_MAX_PAGE_SIZE
    ) -> Iterator[dict[str, Any]]:
        """Iterate every row of the batch. A lazy generator. See :meth:`rows`."""
        return iter_rows(self._http, f"{self._path}rows/", page_size=page_size)

    def ack(self) -> dict[str, Any]:
        """Settle the batch: the rows are ledgered and **charged** here.

        Idempotent — acking an already-acked batch returns it and charges
        nothing. Persist the rows durably before calling this.

        Raises:
            DatasetConflictError: The batch expired (pull again), or the ledger
                diverged. ``reservation_divergence`` is not retryable.
        """
        return self._http.post(f"{self._path}ack/")

    def export(self, *, format: str | None = None) -> dict[str, Any]:
        """Rebuild this acked batch as a file. Free, any format, any number of times.

        The rows were paid for at the ack, so handing them back costs nothing.
        Returns the 202 receipt; poll it with
        ``feed.export(result["export_id"]).wait_for_ready()``.

        Raises:
            DatasetConflictError: ``batch_not_acked`` — only an acked batch has
                rows to export.
            APIError: 400 ``unsupported_format``; the accepted values are in
                ``err.details["supported_formats"]``.
        """
        return self._http.post(
            f"{self._path}export/", json={"format": format} if format else {}
        )


class AsyncDatasetBatchClient:
    """One batch of a Datasets-product dataset."""

    def __init__(self, http: AsyncHTTPClient, slug: str, batch_id: str) -> None:
        self._http = http
        self._batch_id = batch_id
        self._path = f"{DATASETS_PATH}{slug}/batches/{batch_id}/"

    async def get(self) -> dict[str, Any] | None:
        """The batch, with its ``manifest`` and ``constraints``. None if not found.

        ``billed_amount`` and ``price_per_1000_at_open`` are decimal strings.
        Bill from ``billed_rows``, never from ``row_count``: an ack can charge
        for fewer rows than the batch advertises and says why in
        ``constraints``.
        """
        try:
            return await self._http.get(self._path)
        except APIError as e:
            if e.status_code == 404:
                return None
            raise

    async def rows(self, *, limit: int = 25, offset: int = 0) -> ListPage:
        """One page of the batch's rows. Byte-identical across re-reads.

        Rows are opaque per-dataset objects. An acked batch stays readable
        forever.

        Raises:
            BatchExpiredError: The batch expired before it was acked, so its
                rows went back to the pool. **Nothing was billed** — pull again.
        """
        return await alist_page(self._http, f"{self._path}rows/", limit=limit, offset=offset)

    def iterate_rows(
        self, *, page_size: int = DATASET_MAX_PAGE_SIZE
    ) -> AsyncIterator[dict[str, Any]]:
        """Iterate every row of the batch. A lazy generator. See :meth:`rows`."""
        return aiter_rows(self._http, f"{self._path}rows/", page_size=page_size)

    async def ack(self) -> dict[str, Any]:
        """Settle the batch: the rows are ledgered and **charged** here.

        Idempotent — acking an already-acked batch returns it and charges
        nothing. Persist the rows durably before calling this.

        Raises:
            DatasetConflictError: The batch expired (pull again), or the ledger
                diverged. ``reservation_divergence`` is not retryable.
        """
        return await self._http.post(f"{self._path}ack/")

    async def export(self, *, format: str | None = None) -> dict[str, Any]:
        """Rebuild this acked batch as a file. Free, any format, any number of times.

        The rows were paid for at the ack, so handing them back costs nothing.
        Returns the 202 receipt; poll it with
        ``feed.export(result["export_id"]).wait_for_ready()``.

        Raises:
            DatasetConflictError: ``batch_not_acked`` — only an acked batch has
                rows to export.
            APIError: 400 ``unsupported_format``; the accepted values are in
                ``err.details["supported_formats"]``.
        """
        return await self._http.post(
            f"{self._path}export/", json={"format": format} if format else {}
        )
