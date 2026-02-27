"""
E2E test fixtures — real GoFetch client, ngrok tunnel, webhook receiver.

Environment variables (loaded from `.env` in project root):
  GOFETCH_API_KEY    — API key for the GoFetch dev environment
  GOFETCH_BASE_URL   — (optional) API base URL, defaults to https://api.go-fetch.io
  E2E_WEBHOOK_PORT   — (optional) local port for webhook receiver (default: 8765)

Load them before running:
  source .env && pytest tests/e2e/ -v
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import httpx
import pytest

from gofetch import GoFetchClient
from gofetch.webhook import verify_webhook_signature

logger = logging.getLogger("e2e")

# ---------------------------------------------------------------------------
# Markers
# ---------------------------------------------------------------------------

def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "e2e: end-to-end tests against real GoFetch API")
    config.addinivalue_line("markers", "webhook: tests requiring ngrok webhook tunnel")
    config.addinivalue_line("markers", "slow: long-running tests (tier >= 500)")
    config.addinivalue_line("markers", "batch: batch multi-URL tests (25 URLs per call)")


# ---------------------------------------------------------------------------
# Environment guard
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def api_key() -> str:
    key = os.environ.get("GOFETCH_API_KEY", "")
    if not key:
        pytest.skip("GOFETCH_API_KEY not set — skipping E2E tests")
    return key


@pytest.fixture(scope="session")
def base_url() -> str:
    return os.environ.get("GOFETCH_BASE_URL", "https://api.go-fetch.io")


# ---------------------------------------------------------------------------
# GoFetch client (session-scoped, real HTTP)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def client(api_key: str, base_url: str) -> GoFetchClient:
    c = GoFetchClient(api_key=api_key, base_url=base_url, timeout=60.0)
    yield c
    c.close()


# ---------------------------------------------------------------------------
# Webhook receiver — lightweight HTTP server
# ---------------------------------------------------------------------------

class WebhookStore:
    """Thread-safe store for received webhook events."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: list[dict[str, Any]] = []

    def add(self, event: dict[str, Any]) -> None:
        with self._lock:
            self._events.append(event)

    def get_events(self, job_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            if job_id is None:
                return list(self._events)
            return [e for e in self._events if e.get("job_id") == job_id]

    def wait_for_event(
        self,
        job_id: str,
        event_type: str,
        timeout: float = 120.0,
    ) -> dict[str, Any] | None:
        """Block until a specific event arrives or timeout."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for ev in self.get_events(job_id):
                if ev.get("event") == event_type:
                    return ev
            time.sleep(1.0)
        return None

    def wait_for_terminal(
        self,
        job_id: str,
        timeout: float = 120.0,
    ) -> dict[str, Any] | None:
        """Wait for a terminal webhook event (completed/failed/timed_out/cancelled)."""
        terminal = {"job.completed", "job.failed", "job.timed_out", "job.cancelled"}
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for ev in self.get_events(job_id):
                if ev.get("event") in terminal:
                    return ev
            time.sleep(1.0)
        return None

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


# Global store shared between the HTTP handler and fixtures
_webhook_store = WebhookStore()


class _WebhookHandler(BaseHTTPRequestHandler):
    """Handles incoming webhook POST requests."""

    signing_secret: str = ""

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        signature = self.headers.get("X-Webhook-Signature", "")

        # Parse payload
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            logger.warning("Webhook received non-JSON body: %s", body[:200])
            self.send_response(400)
            self.end_headers()
            return

        # Extract job_id from nested data
        data = payload.get("data", {})
        job_id = data.get("job_id", "")

        # Verify signature if secret is configured
        sig_valid = True
        if self.signing_secret and signature:
            sig_valid = verify_webhook_signature(body, signature, self.signing_secret)

        event_record = {
            "event": payload.get("event", "unknown"),
            "job_id": job_id,
            "payload": payload,
            "signature": signature,
            "signature_valid": sig_valid,
            "received_at": time.time(),
            "path": self.path,
        }

        _webhook_store.add(event_record)
        logger.info(
            "Webhook received: event=%s job=%s sig_valid=%s",
            event_record["event"],
            job_id,
            sig_valid,
        )

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress default stderr logging; we use our own logger
        pass


@pytest.fixture(scope="session")
def webhook_port() -> int:
    return int(os.environ.get("E2E_WEBHOOK_PORT", "8765"))


@pytest.fixture(scope="session")
def webhook_server(webhook_port: int) -> WebhookStore:
    """Start the webhook receiver HTTP server in a background thread."""
    server = HTTPServer(("0.0.0.0", webhook_port), _WebhookHandler)
    server.timeout = 1.0
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Webhook receiver started on port %d", webhook_port)
    yield _webhook_store
    server.shutdown()
    _webhook_store.clear()


# ---------------------------------------------------------------------------
# ngrok tunnel (uses ngrok CLI — no pyngrok dependency)
# ---------------------------------------------------------------------------

def _get_ngrok_public_url(timeout: float = 10.0) -> str:
    """Poll the ngrok local API until a tunnel URL is available."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = httpx.get("http://127.0.0.1:4040/api/tunnels", timeout=2.0)
            tunnels = resp.json().get("tunnels", [])
            for t in tunnels:
                pub = t.get("public_url", "")
                if pub.startswith("https://"):
                    return pub
        except (httpx.ConnectError, httpx.ReadError):
            pass
        time.sleep(0.5)
    raise RuntimeError("ngrok tunnel URL not available after {timeout}s")


@pytest.fixture(scope="session")
def ngrok_url(webhook_server: WebhookStore, webhook_port: int) -> str:
    """Start `ngrok http <port>` and return the public HTTPS URL."""
    if not shutil.which("ngrok"):
        pytest.skip("ngrok CLI not found on PATH")

    proc = subprocess.Popen(
        ["ngrok", "http", str(webhook_port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        public_url = _get_ngrok_public_url()
    except RuntimeError:
        proc.terminate()
        pytest.skip("Could not start ngrok tunnel")

    logger.info("ngrok tunnel active: %s → localhost:%d", public_url, webhook_port)
    yield public_url
    proc.terminate()
    proc.wait(timeout=5)


# ---------------------------------------------------------------------------
# Helpers available to tests
# ---------------------------------------------------------------------------

@pytest.fixture
def fresh_webhook_store(webhook_server: WebhookStore) -> WebhookStore:
    """Provide a clean webhook store for each test."""
    webhook_server.clear()
    return webhook_server
