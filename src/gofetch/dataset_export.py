"""Dataset export client for GoFetch API.

One built file: poll it to ``ready``, retry a failed or expired build for free,
and stream it to disk.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import httpx

from gofetch.actor import _next_poll_interval
from gofetch.constants import DEFAULT_POLL_INTERVAL
from gofetch.datasets import DATASETS_PATH
from gofetch.exceptions import APIError, TimeoutError
from gofetch.http import _handle_error_response

if TYPE_CHECKING:
    from gofetch.http import AsyncHTTPClient, HTTPClient

# `failed` and `expired` are terminal but recoverable: `retry()` rebuilds either
# one for free. Nothing writes `expired`, so a `ready` export past its
# `expires_at` presigns a dead key — treat `expires_at` as authoritative.
EXPORT_TERMINAL_STATUSES = frozenset({"ready", "failed", "expired"})


def _stream_to(url: str, path: str) -> None:
    """GET a presigned URL straight to disk.

    Deliberately NOT ``self._http``: the URL is signed for a bare GET, so the
    ``X-API-Key`` header, the JSON content type and the client's ``base_url``
    would all break it. No timeout, because the file is unbounded.
    """
    with httpx.Client(timeout=None) as client, client.stream("GET", url) as response:
        if response.status_code >= 400:
            response.read()
            _handle_error_response(response)
        with open(path, "wb") as fh:
            for chunk in response.iter_bytes():
                fh.write(chunk)


async def _astream_to(url: str, path: str) -> None:
    """GET a presigned URL straight to disk. See :func:`_stream_to`."""
    async with httpx.AsyncClient(timeout=None) as client, client.stream("GET", url) as response:
        if response.status_code >= 400:
            await response.aread()
            _handle_error_response(response)
        with open(path, "wb") as fh:
            async for chunk in response.aiter_bytes():
                fh.write(chunk)


def _no_url(export: dict[str, Any]) -> TimeoutError:
    return TimeoutError(
        f"Export {export.get('id')} is {export.get('status')} and has no download "
        f"URL. A `ready` export past its expires_at presigns a dead key; call "
        f"retry() to rebuild it, which is free.",
    )


class DatasetExportClient:
    """One export of a Datasets-product dataset."""

    def __init__(self, http: HTTPClient, slug: str, export_id: str) -> None:
        self._http = http
        self._export_id = export_id
        self._path = f"{DATASETS_PATH}{slug}/exports/{export_id}/"

    def get(self) -> dict[str, Any] | None:
        """The export, plus a freshly signed ``url``. None if not found.

        ``url`` is a presigned GET minted per call and never stored; it is
        ``None`` unless ``status`` is ``ready``. Check ``expires_at`` rather
        than trusting ``ready``: nothing marks an aged export expired, so a
        stale one signs a dead key. Rebuild it with :meth:`retry`.
        """
        try:
            return self._http.get(self._path)
        except APIError as e:
            if e.status_code == 404:
                return None
            raise

    def wait_for_ready(self, *, wait_secs: int | None = None) -> dict[str, Any] | None:
        """Poll until the export stops building.

        Args:
            wait_secs: Maximum wait in seconds. None waits indefinitely.

        Returns:
            The export dict once ``status`` is ``ready``, ``failed`` or
            ``expired``; None if the export does not exist.

        Raises:
            TimeoutError: ``wait_secs`` elapsed while it was still building.
        """
        start = time.monotonic()
        poll_interval = DEFAULT_POLL_INTERVAL

        while True:
            export = self.get()
            if export is None or export.get("status") in EXPORT_TERMINAL_STATUSES:
                return export

            if wait_secs is not None and (time.monotonic() - start) >= wait_secs:
                raise TimeoutError(
                    f"Export {self._export_id} was still {export.get('status')} "
                    f"after {wait_secs}s.",
                    timeout_seconds=wait_secs,
                )

            time.sleep(poll_interval)
            poll_interval = _next_poll_interval(poll_interval)

    def retry(self) -> dict[str, Any]:
        """Rebuild this export. Never a new batch, never a quote, never a charge.

        This is the only rebuild path: a plain re-``download()`` would be a new
        purchase the moment anything has been added since.

        Raises:
            DatasetConflictError: ``export_already_ready`` — the file is built,
                download it instead.
        """
        return self._http.post(f"{self._path}retry/")

    def download_to(self, path: str) -> str:
        """Stream the built file to ``path``. Returns ``path``.

        Raises:
            TimeoutError: The export is not ``ready``, or its link has gone —
                call :meth:`retry`, which is free.
        """
        export = self.get() or {}
        url = export.get("url")
        if not url:
            raise _no_url(export)
        _stream_to(url, path)
        return path


class AsyncDatasetExportClient:
    """One export of a Datasets-product dataset."""

    def __init__(self, http: AsyncHTTPClient, slug: str, export_id: str) -> None:
        self._http = http
        self._export_id = export_id
        self._path = f"{DATASETS_PATH}{slug}/exports/{export_id}/"

    async def get(self) -> dict[str, Any] | None:
        """The export, plus a freshly signed ``url``. None if not found.

        ``url`` is a presigned GET minted per call and never stored; it is
        ``None`` unless ``status`` is ``ready``. Check ``expires_at`` rather
        than trusting ``ready``: nothing marks an aged export expired, so a
        stale one signs a dead key. Rebuild it with :meth:`retry`.
        """
        try:
            return await self._http.get(self._path)
        except APIError as e:
            if e.status_code == 404:
                return None
            raise

    async def wait_for_ready(
        self, *, wait_secs: int | None = None
    ) -> dict[str, Any] | None:
        """Poll until the export stops building.

        Args:
            wait_secs: Maximum wait in seconds. None waits indefinitely.

        Returns:
            The export dict once ``status`` is ``ready``, ``failed`` or
            ``expired``; None if the export does not exist.

        Raises:
            TimeoutError: ``wait_secs`` elapsed while it was still building.
        """
        import asyncio

        start = time.monotonic()
        poll_interval = DEFAULT_POLL_INTERVAL

        while True:
            export = await self.get()
            if export is None or export.get("status") in EXPORT_TERMINAL_STATUSES:
                return export

            if wait_secs is not None and (time.monotonic() - start) >= wait_secs:
                raise TimeoutError(
                    f"Export {self._export_id} was still {export.get('status')} "
                    f"after {wait_secs}s.",
                    timeout_seconds=wait_secs,
                )

            await asyncio.sleep(poll_interval)
            poll_interval = _next_poll_interval(poll_interval)

    async def retry(self) -> dict[str, Any]:
        """Rebuild this export. Never a new batch, never a quote, never a charge.

        This is the only rebuild path: a plain re-``download()`` would be a new
        purchase the moment anything has been added since.

        Raises:
            DatasetConflictError: ``export_already_ready`` — the file is built,
                download it instead.
        """
        return await self._http.post(f"{self._path}retry/")

    async def download_to(self, path: str) -> str:
        """Stream the built file to ``path``. Returns ``path``.

        Raises:
            TimeoutError: The export is not ``ready``, or its link has gone —
                call :meth:`retry`, which is free.
        """
        export = await self.get() or {}
        url = export.get("url")
        if not url:
            raise _no_url(export)
        await _astream_to(url, path)
        return path
