from __future__ import annotations

from typing import TYPE_CHECKING, Any

from gofetch.exceptions import APIError

if TYPE_CHECKING:
    from gofetch.http import AsyncHTTPClient, HTTPClient


class LogClient:
    def __init__(self, http: HTTPClient, job_id: str) -> None:
        self._http = http
        self._job_id = job_id

    def get(self) -> str | None:
        """Get logs as a newline-separated text string. Returns None on 404."""
        try:
            data = self._http.get(f"/api/v1/jobs/{self._job_id}/logs/")
        except APIError as e:
            if e.status_code == 404:
                return None
            raise
        entries = data.get("results", [])
        lines = [
            f"{entry['timestamp']} [{entry['level']}] {entry['message']}"
            for entry in entries
        ]
        return "\n".join(lines)

    def list(self) -> list[dict[str, Any]]:
        """Get structured log entries. Returns empty list on 404."""
        try:
            data = self._http.get(f"/api/v1/jobs/{self._job_id}/logs/")
        except APIError as e:
            if e.status_code == 404:
                return []
            raise
        results: list[dict[str, Any]] = data.get("results", [])
        return results


class AsyncLogClient:
    def __init__(self, http: AsyncHTTPClient, job_id: str) -> None:
        self._http = http
        self._job_id = job_id

    async def get(self) -> str | None:
        """Get logs as a newline-separated text string. Returns None on 404."""
        try:
            data = await self._http.get(f"/api/v1/jobs/{self._job_id}/logs/")
        except APIError as e:
            if e.status_code == 404:
                return None
            raise
        entries = data.get("results", [])
        lines = [
            f"{entry['timestamp']} [{entry['level']}] {entry['message']}"
            for entry in entries
        ]
        return "\n".join(lines)

    async def list(self) -> list[dict[str, Any]]:
        """Get structured log entries. Returns empty list on 404."""
        try:
            data = await self._http.get(f"/api/v1/jobs/{self._job_id}/logs/")
        except APIError as e:
            if e.status_code == 404:
                return []
            raise
        results: list[dict[str, Any]] = data.get("results", [])
        return results
