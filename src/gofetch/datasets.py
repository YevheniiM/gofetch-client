"""Datasets client for GoFetch API.

The Datasets product: a subscription feed of rows you pull, read and ack, plus a
paid one-shot download of everything new. Not to be confused with
:class:`~gofetch.dataset.DatasetClient`, which fetches one scraper job's results.

There are no dataset webhooks. Polling is the only delivery mechanism, so
:meth:`DatasetFeedClient.pull_and_iterate` and
:meth:`DatasetFeedClient.download` are the product surface, not sugar.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import httpx

from gofetch.constants import DATASET_MAX_PAGE_SIZE, IDEMPOTENCY_KEY_HEADER
from gofetch.exceptions import DatasetConflictError, ValidationError
from gofetch.http import _handle_error_response
from gofetch.types import ListPage

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

    from gofetch.dataset_batch import AsyncDatasetBatchClient, DatasetBatchClient
    from gofetch.dataset_export import AsyncDatasetExportClient, DatasetExportClient
    from gofetch.http import AsyncHTTPClient, HTTPClient

DATASETS_PATH = "/api/v1/datasets/"

# A pull answered anything else has no batch for you: `unavailable`,
# `quota_exhausted` and `nothing_available` are data, not errors.
PULL_STATUSES_WITH_BATCH = frozenset({"ok", "open_batch_exists"})

# `daily_quota` and `batch_size` are the only writable config fields; `band`,
# `ack_ttl_hours` and `is_active` are read-only and DRF drops them SILENTLY, so
# sending one would look like it worked.
CONFIG_FIELDS = ("daily_quota", "batch_size")


def clamp_limit(limit: int) -> int:
    """Cap a page size at what the server will actually serve.

    The API clamps a larger ``limit`` instead of rejecting it, so a caller who
    asked for 500 would otherwise believe they got 500.
    """
    return min(limit, DATASET_MAX_PAGE_SIZE)


def _config_payload(
    daily_quota: int | None, batch_size: int | None, extra: dict[str, Any]
) -> dict[str, Any]:
    if extra:
        field = sorted(extra)[0]
        raise ValidationError(
            f"{', '.join(sorted(extra))} cannot be set through the API. Only "
            f"{' and '.join(CONFIG_FIELDS)} are writable; the server drops the "
            f"rest silently, so this would look like it worked.",
            field=field,
        )
    body = {"daily_quota": daily_quota, "batch_size": batch_size}
    payload = {k: v for k, v in body.items() if v is not None}
    if not payload:
        raise ValidationError(f"Nothing to update: pass {' or '.join(CONFIG_FIELDS)}.")
    return payload


def _as_page(response: dict[str, Any], offset: int, limit: int) -> ListPage:
    rows = response.get("results", response.get("items", []))
    return ListPage(
        rows,
        offset=response.get("offset", offset),
        limit=response.get("limit", limit),
        total=response.get("total", len(rows)),
    )


def list_page(http: HTTPClient, path: str, *, limit: int, offset: int) -> ListPage:
    """One page of a paginated dataset route."""
    limit = clamp_limit(limit)
    return _as_page(http.get(path, params={"limit": limit, "offset": offset}), offset, limit)


async def alist_page(
    http: AsyncHTTPClient, path: str, *, limit: int, offset: int
) -> ListPage:
    """One page of a paginated dataset route."""
    limit = clamp_limit(limit)
    response = await http.get(path, params={"limit": limit, "offset": offset})
    return _as_page(response, offset, limit)


def iter_rows(http: HTTPClient, path: str, *, page_size: int) -> Iterator[dict[str, Any]]:
    """Every row of a paginated dataset route, one page at a time."""
    offset = 0
    while True:
        page = list_page(http, path, limit=page_size, offset=offset)
        yield from page
        offset += len(page)
        if not page or offset >= page.total:
            return


async def aiter_rows(
    http: AsyncHTTPClient, path: str, *, page_size: int
) -> AsyncIterator[dict[str, Any]]:
    """Every row of a paginated dataset route, one page at a time."""
    offset = 0
    while True:
        page = await alist_page(http, path, limit=page_size, offset=offset)
        for row in page:
            yield row
        offset += len(page)
        if not page or offset >= page.total:
            return


def _fresh_expected_items(error: DatasetConflictError) -> int:
    """The ceiling to retry a ``quote_stale`` refusal with."""
    quote = error.quote or {}
    items = quote.get("items") or {}
    expected = items.get("new")
    if not isinstance(expected, int):
        raise error
    return expected


def _put_presigned(url: str, body: bytes) -> None:
    """PUT straight to S3.

    Deliberately NOT ``self._http``: the presigned URL is signed for a bare PUT,
    so an ``X-API-Key`` header, a JSON content type or the client's ``base_url``
    would all break the signature. No timeout, because the index file is tens of
    megabytes and the transfer is unbounded.
    """
    with httpx.Client(timeout=None) as client:
        response = client.put(url, content=body)
    if response.status_code >= 400:
        _handle_error_response(response)


async def _aput_presigned(url: str, body: bytes) -> None:
    """PUT straight to S3. See :func:`_put_presigned`."""
    async with httpx.AsyncClient(timeout=None) as client:
        response = await client.put(url, content=body)
    if response.status_code >= 400:
        _handle_error_response(response)


class DatasetCollectionClient:
    """Every Datasets-product dataset this API key's organization owns."""

    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    def list(self, *, limit: int = 25, offset: int = 0) -> ListPage:
        """One page of dataset list rows.

        The list row is a different shape from the overview
        :meth:`DatasetFeedClient.get` returns — do not treat them as one type.
        A paused dataset is listed, carrying ``is_active: false``.
        """
        return list_page(self._http, DATASETS_PATH, limit=limit, offset=offset)

    def iterate(
        self, *, page_size: int = DATASET_MAX_PAGE_SIZE
    ) -> Iterator[dict[str, Any]]:
        """Iterate every dataset list row. A lazy generator."""
        return iter_rows(self._http, DATASETS_PATH, page_size=page_size)

    def feed(self, slug: str) -> DatasetFeedClient:
        """Get the client for one dataset. Same as ``client.dataset_feed(slug)``."""
        return DatasetFeedClient(http=self._http, slug=slug)


class DatasetFeedClient:
    """One Datasets-product dataset: pull/ack delivery and paid downloads."""

    def __init__(self, http: HTTPClient, slug: str) -> None:
        self._http = http
        self._slug = slug
        self._path = f"{DATASETS_PATH}{slug}/"

    def get(self) -> dict[str, Any]:
        """The dataset overview: config, pool depth, quota, open batch, quote.

        **This is not a free status poll.** The server settles a batch that is
        due on the way past, which can expire it or bill and settle it. Call it
        when you want the state, not on a tight loop.
        """
        return self._http.get(self._path)

    def update_config(
        self,
        *,
        daily_quota: int | None = None,
        batch_size: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Change the delivery pace. Returns the full overview, not a config object.

        Only ``daily_quota`` and ``batch_size`` are writable. ``band``,
        ``ack_ttl_hours`` and ``is_active`` are read-only and the server drops
        them without saying so, so passing one raises ``ValidationError`` here
        rather than answering 200 having changed nothing.
        """
        return self._http.patch(
            f"{self._path}config/",
            json=_config_payload(daily_quota, batch_size, kwargs),
        )

    def pull(self) -> dict[str, Any]:
        """Open a batch, or re-serve the one already open.

        Returns ``{"status", "batch", "constraints"}``. A batch is yours only
        when ``status`` is ``ok`` or ``open_batch_exists``; the other statuses
        (``unavailable``, ``quota_exhausted``, ``nothing_available``) are data,
        not errors, and carry no new rows.

        Pulling is idempotent while a batch is open — a re-pull re-serves the
        same batch byte-identically rather than topping it up. Credits are
        reserved here and spent at the ack.
        """
        return self._http.post(f"{self._path}pull/")

    def batches(self, *, limit: int = 25, offset: int = 0) -> ListPage:
        """One page of this dataset's batch history."""
        return list_page(self._http, f"{self._path}batches/", limit=limit, offset=offset)

    def iterate_batches(
        self, *, page_size: int = DATASET_MAX_PAGE_SIZE
    ) -> Iterator[dict[str, Any]]:
        """Iterate every batch. A lazy generator."""
        return iter_rows(self._http, f"{self._path}batches/", page_size=page_size)

    def batch(self, batch_id: str) -> DatasetBatchClient:
        """Get the client for one batch. ``batch_id`` is a string (``api-…``/``dl-…``)."""
        from gofetch.dataset_batch import DatasetBatchClient

        return DatasetBatchClient(http=self._http, slug=self._slug, batch_id=batch_id)

    def pull_and_iterate(
        self,
        *,
        auto_ack: bool = True,
        page_size: int = DATASET_MAX_PAGE_SIZE,
    ) -> Iterator[dict[str, Any]]:
        """Pull a batch, yield every row, then ack — the whole delivery loop.

        **Persist each row durably before the generator ends.** The ack is what
        ledgers and charges the rows, and it runs only after the last row has
        been yielded. Break out of this generator, or let an exception escape
        it, and nothing is acked and nothing is charged: the batch stays open
        and a later ``pull()`` re-serves it byte-identically.

        Yields nothing at all when the pull has no batch for you.

        Args:
            auto_ack: Ack the batch on clean exhaustion. ``False`` leaves it
                open — you must ack it yourself, or it expires after
                ``config.ack_ttl_hours`` and the rows go back to the pool.
            page_size: Rows per request, clamped to 100 by the server.
        """
        response = self.pull()
        batch = response.get("batch")
        if response.get("status") not in PULL_STATUSES_WITH_BATCH or not batch:
            return

        rows = self.batch(batch["batch_id"])
        yield from rows.iterate_rows(page_size=page_size)
        if auto_ack:
            rows.ack()

    def quote(self) -> dict[str, Any]:
        """What a download would cost right now. Free, and bills nothing.

        Money fields (``price_per_1000``, ``amount``, ``balance``) are decimal
        strings — use them verbatim.
        """
        return self._http.get(f"{self._path}download/")

    def download(
        self,
        *,
        expected_items: int | None = None,
        format: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Buy everything new as one file. **This moves money.**

        Quotes first, then claims at most ``expected_items`` rows — a ceiling,
        not an equality: a claim larger than it is refused with a fresh quote, a
        smaller one proceeds and says ``fewer_than_quoted`` in ``constraints``.
        Returns the 202 receipt: ``export_id``, ``status``, ``billed_items`` and
        ``billed_amount`` (a decimal string — do not float it). Poll the export
        with ``feed.export(export_id).wait_for_ready()``.

        Args:
            expected_items: The ceiling. Defaults to ``quote()["items"]["new"]``.
            format: ``jsonl`` (default) or ``csv`` where the dataset has columns.
            idempotency_key: **One key per intended purchase**, reused across
                every retry of that purchase — that is what stops a retry buying
                a second time. Defaults to a fresh ``uuid4().hex``, which the
                automatic HTTP retries reuse because they resend the same
                request. A generated key dies with the process, so **pass your
                own** if the purchase must survive a restart: only the original
                key replays the first result instead of buying again.

        Raises:
            DatasetConflictError: On a 409. ``quote_stale`` is retried once
                automatically with the fresh ceiling and the same key (a refusal
                releases the key, so nothing was billed).
                ``download_in_progress`` is never retried — it means the
                purchase may already have happened.
            InsufficientCreditsError: On a 402, with ``.constraints``.
        """
        key = idempotency_key or uuid4().hex
        if expected_items is None:
            expected_items = self.quote()["items"]["new"]

        path = f"{self._path}download/"
        headers = {IDEMPOTENCY_KEY_HEADER: key}
        body: dict[str, Any] = {"expected_items": expected_items}
        if format is not None:
            body["format"] = format

        try:
            return self._http.post(path, json=body, headers=headers)
        except DatasetConflictError as e:
            if e.code != "quote_stale":
                raise
            body["expected_items"] = _fresh_expected_items(e)
            return self._http.post(path, json=body, headers=headers)

    def exports(self, *, limit: int = 25, offset: int = 0) -> ListPage:
        """One page of this dataset's exports, **without** ``url``.

        A presigned link cannot be stored, so only the detail route
        (``export(id).get()``) mints one.
        """
        return list_page(self._http, f"{self._path}exports/", limit=limit, offset=offset)

    def iterate_exports(
        self, *, page_size: int = DATASET_MAX_PAGE_SIZE
    ) -> Iterator[dict[str, Any]]:
        """Iterate every export. A lazy generator."""
        return iter_rows(self._http, f"{self._path}exports/", page_size=page_size)

    def export(self, export_id: str) -> DatasetExportClient:
        """Get the client for one export. ``export_id`` is a UUID."""
        from gofetch.dataset_export import DatasetExportClient

        return DatasetExportClient(http=self._http, slug=self._slug, export_id=export_id)

    def owned_index_upload_url(self, *, filename: str | None = None) -> dict[str, Any]:
        """A presigned S3 PUT for your owned-creator index.

        Returns ``{"url", "key", "bucket", "expires_in", "method"}``. Pass
        ``key`` back to :meth:`owned_index_load` verbatim — the server only
        accepts a key it issued.
        """
        return self._http.post(
            f"{self._path}owned-index/upload-url/",
            json={"filename": filename} if filename else {},
        )

    def owned_index_load(self, key: str) -> dict[str, Any]:
        """Queue the uploaded index for loading. Returns a 202, not an outcome.

        Nothing reports the result directly: read
        ``get()["owned_index"]["latest_load"]`` afterwards.

        **A refused load replaces the live index anyway.** ``index_missing``,
        ``index_too_small``, ``index_skip_rate`` and ``index_shrunk`` all mean
        the same thing — your previous index is gone, re-upload.
        """
        return self._http.post(f"{self._path}owned-index/load/", json={"key": key})

    def upload_owned_index(self, path: str) -> dict[str, Any]:
        """Upload an owned-index file and queue it: upload-url, PUT, load.

        The file is read into memory and PUT straight to S3 without the API key,
        because the presigned URL is signed for a bare request. See
        :meth:`owned_index_load` for what a refusal costs you.
        """
        upload = self.owned_index_upload_url(filename=os.path.basename(path))
        with open(path, "rb") as fh:
            _put_presigned(upload["url"], fh.read())
        return self.owned_index_load(upload["key"])


class AsyncDatasetCollectionClient:
    """Every Datasets-product dataset this API key's organization owns."""

    def __init__(self, http: AsyncHTTPClient) -> None:
        self._http = http

    async def list(self, *, limit: int = 25, offset: int = 0) -> ListPage:
        """One page of dataset list rows.

        The list row is a different shape from the overview
        :meth:`AsyncDatasetFeedClient.get` returns — do not treat them as one
        type. A paused dataset is listed, carrying ``is_active: false``.
        """
        return await alist_page(self._http, DATASETS_PATH, limit=limit, offset=offset)

    def iterate(
        self, *, page_size: int = DATASET_MAX_PAGE_SIZE
    ) -> AsyncIterator[dict[str, Any]]:
        """Iterate every dataset list row. A lazy generator."""
        return aiter_rows(self._http, DATASETS_PATH, page_size=page_size)

    def feed(self, slug: str) -> AsyncDatasetFeedClient:
        """Get the client for one dataset. Same as ``client.dataset_feed(slug)``."""
        return AsyncDatasetFeedClient(http=self._http, slug=slug)


class AsyncDatasetFeedClient:
    """One Datasets-product dataset: pull/ack delivery and paid downloads."""

    def __init__(self, http: AsyncHTTPClient, slug: str) -> None:
        self._http = http
        self._slug = slug
        self._path = f"{DATASETS_PATH}{slug}/"

    async def get(self) -> dict[str, Any]:
        """The dataset overview: config, pool depth, quota, open batch, quote.

        **This is not a free status poll.** The server settles a batch that is
        due on the way past, which can expire it or bill and settle it. Call it
        when you want the state, not on a tight loop.
        """
        return await self._http.get(self._path)

    async def update_config(
        self,
        *,
        daily_quota: int | None = None,
        batch_size: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Change the delivery pace. Returns the full overview, not a config object.

        Only ``daily_quota`` and ``batch_size`` are writable. ``band``,
        ``ack_ttl_hours`` and ``is_active`` are read-only and the server drops
        them without saying so, so passing one raises ``ValidationError`` here
        rather than answering 200 having changed nothing.
        """
        return await self._http.patch(
            f"{self._path}config/",
            json=_config_payload(daily_quota, batch_size, kwargs),
        )

    async def pull(self) -> dict[str, Any]:
        """Open a batch, or re-serve the one already open.

        Returns ``{"status", "batch", "constraints"}``. A batch is yours only
        when ``status`` is ``ok`` or ``open_batch_exists``; the other statuses
        (``unavailable``, ``quota_exhausted``, ``nothing_available``) are data,
        not errors, and carry no new rows.

        Pulling is idempotent while a batch is open — a re-pull re-serves the
        same batch byte-identically rather than topping it up. Credits are
        reserved here and spent at the ack.
        """
        return await self._http.post(f"{self._path}pull/")

    async def batches(self, *, limit: int = 25, offset: int = 0) -> ListPage:
        """One page of this dataset's batch history."""
        return await alist_page(self._http, f"{self._path}batches/", limit=limit, offset=offset)

    def iterate_batches(
        self, *, page_size: int = DATASET_MAX_PAGE_SIZE
    ) -> AsyncIterator[dict[str, Any]]:
        """Iterate every batch. A lazy generator."""
        return aiter_rows(self._http, f"{self._path}batches/", page_size=page_size)

    def batch(self, batch_id: str) -> AsyncDatasetBatchClient:
        """Get the client for one batch. ``batch_id`` is a string (``api-…``/``dl-…``)."""
        from gofetch.dataset_batch import AsyncDatasetBatchClient

        return AsyncDatasetBatchClient(http=self._http, slug=self._slug, batch_id=batch_id)

    async def pull_and_iterate(
        self,
        *,
        auto_ack: bool = True,
        page_size: int = DATASET_MAX_PAGE_SIZE,
    ) -> AsyncIterator[dict[str, Any]]:
        """Pull a batch, yield every row, then ack — the whole delivery loop.

        **Persist each row durably before the generator ends.** The ack is what
        ledgers and charges the rows, and it runs only after the last row has
        been yielded. Break out of this generator, or let an exception escape
        it, and nothing is acked and nothing is charged: the batch stays open
        and a later ``pull()`` re-serves it byte-identically.

        Yields nothing at all when the pull has no batch for you.

        Args:
            auto_ack: Ack the batch on clean exhaustion. ``False`` leaves it
                open — you must ack it yourself, or it expires after
                ``config.ack_ttl_hours`` and the rows go back to the pool.
            page_size: Rows per request, clamped to 100 by the server.
        """
        response = await self.pull()
        batch = response.get("batch")
        if response.get("status") not in PULL_STATUSES_WITH_BATCH or not batch:
            return

        rows = self.batch(batch["batch_id"])
        async for row in rows.iterate_rows(page_size=page_size):
            yield row
        if auto_ack:
            await rows.ack()

    async def quote(self) -> dict[str, Any]:
        """What a download would cost right now. Free, and bills nothing.

        Money fields (``price_per_1000``, ``amount``, ``balance``) are decimal
        strings — use them verbatim.
        """
        return await self._http.get(f"{self._path}download/")

    async def download(
        self,
        *,
        expected_items: int | None = None,
        format: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Buy everything new as one file. **This moves money.**

        Quotes first, then claims at most ``expected_items`` rows — a ceiling,
        not an equality: a claim larger than it is refused with a fresh quote, a
        smaller one proceeds and says ``fewer_than_quoted`` in ``constraints``.
        Returns the 202 receipt: ``export_id``, ``status``, ``billed_items`` and
        ``billed_amount`` (a decimal string — do not float it). Poll the export
        with ``feed.export(export_id).wait_for_ready()``.

        Args:
            expected_items: The ceiling. Defaults to ``quote()["items"]["new"]``.
            format: ``jsonl`` (default) or ``csv`` where the dataset has columns.
            idempotency_key: **One key per intended purchase**, reused across
                every retry of that purchase — that is what stops a retry buying
                a second time. Defaults to a fresh ``uuid4().hex``, which the
                automatic HTTP retries reuse because they resend the same
                request. A generated key dies with the process, so **pass your
                own** if the purchase must survive a restart: only the original
                key replays the first result instead of buying again.

        Raises:
            DatasetConflictError: On a 409. ``quote_stale`` is retried once
                automatically with the fresh ceiling and the same key (a refusal
                releases the key, so nothing was billed).
                ``download_in_progress`` is never retried — it means the
                purchase may already have happened.
            InsufficientCreditsError: On a 402, with ``.constraints``.
        """
        key = idempotency_key or uuid4().hex
        if expected_items is None:
            expected_items = (await self.quote())["items"]["new"]

        path = f"{self._path}download/"
        headers = {IDEMPOTENCY_KEY_HEADER: key}
        body: dict[str, Any] = {"expected_items": expected_items}
        if format is not None:
            body["format"] = format

        try:
            return await self._http.post(path, json=body, headers=headers)
        except DatasetConflictError as e:
            if e.code != "quote_stale":
                raise
            body["expected_items"] = _fresh_expected_items(e)
            return await self._http.post(path, json=body, headers=headers)

    async def exports(self, *, limit: int = 25, offset: int = 0) -> ListPage:
        """One page of this dataset's exports, **without** ``url``.

        A presigned link cannot be stored, so only the detail route
        (``export(id).get()``) mints one.
        """
        return await alist_page(self._http, f"{self._path}exports/", limit=limit, offset=offset)

    def iterate_exports(
        self, *, page_size: int = DATASET_MAX_PAGE_SIZE
    ) -> AsyncIterator[dict[str, Any]]:
        """Iterate every export. A lazy generator."""
        return aiter_rows(self._http, f"{self._path}exports/", page_size=page_size)

    def export(self, export_id: str) -> AsyncDatasetExportClient:
        """Get the client for one export. ``export_id`` is a UUID."""
        from gofetch.dataset_export import AsyncDatasetExportClient

        return AsyncDatasetExportClient(http=self._http, slug=self._slug, export_id=export_id)

    async def owned_index_upload_url(self, *, filename: str | None = None) -> dict[str, Any]:
        """A presigned S3 PUT for your owned-creator index.

        Returns ``{"url", "key", "bucket", "expires_in", "method"}``. Pass
        ``key`` back to :meth:`owned_index_load` verbatim — the server only
        accepts a key it issued.
        """
        return await self._http.post(
            f"{self._path}owned-index/upload-url/",
            json={"filename": filename} if filename else {},
        )

    async def owned_index_load(self, key: str) -> dict[str, Any]:
        """Queue the uploaded index for loading. Returns a 202, not an outcome.

        Nothing reports the result directly: read
        ``get()["owned_index"]["latest_load"]`` afterwards.

        **A refused load replaces the live index anyway.** ``index_missing``,
        ``index_too_small``, ``index_skip_rate`` and ``index_shrunk`` all mean
        the same thing — your previous index is gone, re-upload.
        """
        return await self._http.post(f"{self._path}owned-index/load/", json={"key": key})

    async def upload_owned_index(self, path: str) -> dict[str, Any]:
        """Upload an owned-index file and queue it: upload-url, PUT, load.

        The file is read into memory and PUT straight to S3 without the API key,
        because the presigned URL is signed for a bare request. See
        :meth:`owned_index_load` for what a refusal costs you.
        """
        upload = await self.owned_index_upload_url(filename=os.path.basename(path))
        with open(path, "rb") as fh:
            await _aput_presigned(upload["url"], fh.read())
        return await self.owned_index_load(upload["key"])
