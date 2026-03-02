"""
E2E batch tests — 25 inputs per platform with optional date filtering.

Tests the real-world pattern of sending many inputs in a single API call.
Supports both URL-based platforms (Instagram, TikTok, YouTube) and
query-based platforms (Reddit, Google News).

Each platform runs in its own xdist group for parallel execution.

Usage:
    # All batch tests in parallel (5 workers)
    pytest tests/e2e/test_batch.py -n 5 --dist loadgroup -v

    # Single platform
    pytest tests/e2e/test_batch.py -k instagram -v
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from gofetch import GoFetchClient

from .config import (
    BATCH_PLATFORMS,
    PLATFORM_TIMESTAMP_FIELDS,
    extract_username_from_url,
)

logger = logging.getLogger("e2e.batch")

# Mark all tests in this module
pytestmark = [pytest.mark.e2e, pytest.mark.batch]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_result_identifiers(results: list[dict], platform: str) -> set[str]:
    """Extract unique identifiers from results for coverage checking.

    For URL-based platforms: extracts creator usernames.
    For Reddit: extracts subreddit names (not post authors).
    """
    identifiers: set[str] = set()
    for r in results:
        if platform == "reddit":
            # Reddit: extract subreddit names, not post authors
            for field in ("subreddit", "communityName"):
                val = r.get(field)
                if isinstance(val, str) and val:
                    identifiers.add(val.strip().lower())
        else:
            # URL-based platforms: try common username fields
            for field in ("ownerUsername", "author", "channelName", "authorMeta"):
                val = r.get(field)
                if isinstance(val, str) and val:
                    identifiers.add(val.strip().lstrip("@").lower())
                elif isinstance(val, dict):
                    # TikTok authorMeta has a 'name' sub-field
                    name = val.get("name", val.get("nickname", ""))
                    if name:
                        identifiers.add(str(name).strip().lstrip("@").lower())

        # URL-based extraction (works for all platforms with parseable URLs)
        result_url = r.get("url", "") or r.get("webVideoUrl", "")
        if result_url:
            uname = extract_username_from_url(result_url, platform)
            if uname:
                identifiers.add(uname)

    return identifiers


def _parse_result_date(result: dict, platform: str) -> datetime | None:
    """Try to parse a posted-at timestamp from a result item."""
    timestamp_fields = PLATFORM_TIMESTAMP_FIELDS.get(platform, [])

    for field in timestamp_fields:
        val = result.get(field)
        if val is None:
            continue

        # Unix timestamp (int or string)
        if isinstance(val, (int, float)):
            try:
                return datetime.fromtimestamp(val, tz=timezone.utc)
            except (ValueError, OSError):
                continue

        if isinstance(val, str):
            # Try ISO 8601
            for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
                try:
                    return datetime.strptime(val, fmt).replace(tzinfo=timezone.utc)
                except ValueError:
                    continue

            # Try unix timestamp as string
            try:
                ts = float(val)
                return datetime.fromtimestamp(ts, tz=timezone.utc)
            except (ValueError, OSError):
                continue

    return None


# ---------------------------------------------------------------------------
# Test parametrisation
# ---------------------------------------------------------------------------


def _make_batch_params() -> list:
    params = []
    for platform_name, batch_config in BATCH_PLATFORMS.items():
        params.append(
            pytest.param(
                platform_name,
                batch_config,
                id=f"batch-{platform_name}",
                marks=[pytest.mark.xdist_group(f"batch_{platform_name}")],
            )
        )
    return params


@pytest.mark.parametrize("platform_name,batch_config", _make_batch_params())
def test_batch_multi_input(
    client: GoFetchClient,
    platform_name: str,
    batch_config: dict,
) -> None:
    """
    Send 25 inputs + optional date filter in a single API call.

    Supports URL-based platforms (Instagram, TikTok, YouTube) and
    query-based platforms (Reddit, Google News).

    Validates:
    1. Job completes with SUCCEEDED status
    2. Results are non-empty
    3. Results come from multiple sources (not collapsed to one)
    4. Source coverage meets minimum threshold (when applicable)
    5. Posted-at dates within range (when date filter applied, <=10% tolerance)
    6. Result URLs are valid
    """
    limit_key = batch_config["limit_key"]
    limit_value = batch_config.get("limit_value", 100)
    min_coverage = batch_config.get("min_coverage", 0)
    date_param = batch_config.get("date_param")
    batch_timeout = batch_config["batch_timeout"]

    # Build run_input — URL-based or query-based
    is_url_based = "url_key" in batch_config
    run_input: dict = {}

    if is_url_based:
        urls = batch_config["urls"]
        run_input[batch_config["url_key"]] = urls
        input_count = len(urls)
    else:
        queries = batch_config["queries"]
        run_input["queries"] = queries
        input_count = len(queries)

    run_input[limit_key] = limit_value

    # Date filter (only for platforms that support it)
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=7)
    cutoff_str = cutoff.strftime("%Y-%m-%d")
    if date_param:
        run_input[date_param] = cutoff_str

    logger.info(
        "Starting batch: platform=%s inputs=%d date_filter=%s timeout=%ds",
        platform_name,
        input_count,
        cutoff_str if date_param else "none",
        batch_timeout,
    )
    t_start = time.monotonic()

    # --- 1. Create and run job ---
    actor = client.actor(platform_name)
    run = actor.call(run_input=run_input, wait_secs=batch_timeout)

    elapsed = time.monotonic() - t_start
    logger.info(
        "Batch finished: id=%s status=%s elapsed=%.1fs",
        run.get("id"),
        run.get("status"),
        elapsed,
    )

    # Validation 1: Job SUCCEEDED
    status = run.get("status", "")
    assert status == "SUCCEEDED", (
        f"Batch job {run.get('id')} finished with status '{status}' "
        f"instead of SUCCEEDED after {elapsed:.0f}s.\n"
        f"GoFetch job data: {run.get('_gofetch_job', {})}"
    )

    # --- Fetch results ---
    dataset = client.dataset(run["defaultDatasetId"])
    results = dataset.list_items()

    # Validation 2: Non-empty
    assert len(results) > 0, (
        f"Batch job for {platform_name} returned zero results from {input_count} inputs."
    )

    logger.info("Batch %s: %d results from %d inputs", platform_name, len(results), input_count)

    # Validation 3: Results from multiple sources
    result_identifiers = _extract_result_identifiers(results, platform_name)
    assert len(result_identifiers) > 1, (
        f"Batch results appear to come from only {len(result_identifiers)} source(s): "
        f"{result_identifiers}. Expected results from multiple sources."
    )

    # Validation 4: Source coverage (when min_coverage > 0 and input URLs available)
    matched_count = 0
    if min_coverage > 0 and "urls" in batch_config:
        input_identifiers: set[str] = set()
        for url in batch_config["urls"]:
            uname = extract_username_from_url(url, platform_name)
            if uname:
                input_identifiers.add(uname)

        matched = input_identifiers & result_identifiers
        matched_count = len(matched)
        assert matched_count >= min_coverage, (
            f"Source coverage too low: {matched_count}/{len(input_identifiers)} "
            f"(need at least {min_coverage}). "
            f"Matched: {sorted(matched)[:10]}... "
            f"Missing: {sorted(input_identifiers - result_identifiers)[:10]}..."
        )

        logger.info(
            "Coverage: %d/%d sources matched (%d required)",
            matched_count,
            len(input_identifiers),
            min_coverage,
        )

    # Validation 5: Date range check (only when date filter was applied)
    if date_param:
        parseable = 0
        out_of_range = 0
        for r in results:
            dt = _parse_result_date(r, platform_name)
            if dt is not None:
                parseable += 1
                if dt < cutoff:
                    out_of_range += 1

        if parseable > 0:
            oor_ratio = out_of_range / parseable
            logger.info(
                "Date check: %d parseable, %d out-of-range (%.1f%%)",
                parseable,
                out_of_range,
                oor_ratio * 100,
            )
            assert oor_ratio <= 0.10, (
                f"DATE RANGE: {out_of_range}/{parseable} results ({oor_ratio:.0%}) are older "
                f"than cutoff {cutoff_str}. Tolerance is 10%."
            )
        else:
            logger.warning(
                "No parseable dates found in %d results — skipping date range validation",
                len(results),
            )

    # Validation 6: URL validity
    result_urls = [r.get("url", "") for r in results if r.get("url")]
    if result_urls:
        invalid = [
            u for u in result_urls
            if not (isinstance(u, str) and u.startswith("http") and len(u) > 10)
        ]
        invalid_ratio = len(invalid) / len(result_urls) if result_urls else 0
        assert invalid_ratio <= 0.20, (
            f"INVALID URLS: {len(invalid)}/{len(result_urls)} result URLs are invalid "
            f"({invalid_ratio:.0%}). Threshold is 20%."
        )

    logger.info(
        "PASS: batch-%s → %d results, %d sources, %.1fs",
        platform_name,
        len(results),
        matched_count if min_coverage > 0 else len(result_identifiers),
        elapsed,
    )
