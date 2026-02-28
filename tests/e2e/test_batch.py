"""
E2E batch tests — 25 creator URLs per platform with date filtering.

Tests the real-world pattern of sending many URLs in a single API call.
Each platform runs in its own xdist group for parallel execution.

Usage:
    # All batch tests in parallel (3 workers)
    pytest tests/e2e/test_batch.py -n 3 --dist loadgroup -v

    # Single platform
    pytest tests/e2e/test_batch.py -k instagram -v
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

import pytest

from gofetch import GoFetchClient

from .config import (
    BATCH_PLATFORMS,
    BATCH_TIMEOUT,
    PLATFORM_TIMESTAMP_FIELDS,
    extract_username_from_url,
)

logger = logging.getLogger("e2e.batch")

# Mark all tests in this module
pytestmark = [pytest.mark.e2e, pytest.mark.batch]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_result_usernames(results: list[dict], platform: str) -> set[str]:
    """Extract unique usernames/creators found in results."""
    usernames: set[str] = set()
    for r in results:
        # Try common username fields
        for field in ("ownerUsername", "author", "channelName", "authorMeta"):
            val = r.get(field)
            if isinstance(val, str) and val:
                usernames.add(val.strip().lstrip("@").lower())
            elif isinstance(val, dict):
                # TikTok authorMeta has a 'name' sub-field
                name = val.get("name", val.get("nickname", ""))
                if name:
                    usernames.add(str(name).strip().lstrip("@").lower())

        # Fall back to extracting from result URL
        result_url = r.get("url", "") or r.get("webVideoUrl", "")
        if result_url:
            uname = extract_username_from_url(result_url, platform)
            if uname:
                usernames.add(uname)

    return usernames


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
def test_batch_multi_url(
    client: GoFetchClient,
    platform_name: str,
    batch_config: dict,
) -> None:
    """
    Send 25 creator URLs + date filter in a single API call.

    Validates:
    1. Job completes with SUCCEEDED status
    2. Results are non-empty
    3. Results come from multiple creators (not collapsed to one)
    4. At least 15/25 creators have results (60% coverage)
    5. Posted-at dates are within the date range (<=10% out-of-range tolerance)
    6. Result URLs are valid
    """
    urls = batch_config["urls"]
    url_key = batch_config["url_key"]
    date_param = batch_config["date_param"]
    limit_key = batch_config["limit_key"]
    min_coverage = batch_config["min_coverage"]

    # Date filter: 2 days ago
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=2)
    cutoff_str = cutoff.strftime("%Y-%m-%d")

    run_input = {
        url_key: urls,
        limit_key: 100,  # modest per-creator limit
        date_param: cutoff_str,
    }

    logger.info(
        "Starting batch: platform=%s urls=%d date_filter=%s timeout=%ds",
        platform_name,
        len(urls),
        cutoff_str,
        BATCH_TIMEOUT,
    )
    t_start = time.monotonic()

    # --- 1. Create and run job ---
    actor = client.actor(platform_name)
    run = actor.call(run_input=run_input, wait_secs=BATCH_TIMEOUT)

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
        f"Batch job for {platform_name} returned zero results from {len(urls)} URLs."
    )

    logger.info("Batch %s: %d results from %d URLs", platform_name, len(results), len(urls))

    # Validation 3: Results from multiple creators
    result_usernames = _extract_result_usernames(results, platform_name)
    assert len(result_usernames) > 1, (
        f"Batch results appear to come from only {len(result_usernames)} creator(s): "
        f"{result_usernames}. Expected results from multiple creators."
    )

    # Validation 4: Creator coverage — at least min_coverage of 25 input URLs returned results
    input_usernames = set()
    for url in urls:
        uname = extract_username_from_url(url, platform_name)
        if uname:
            input_usernames.add(uname)

    matched_creators = input_usernames & result_usernames
    assert len(matched_creators) >= min_coverage, (
        f"Creator coverage too low: {len(matched_creators)}/{len(input_usernames)} "
        f"(need at least {min_coverage}). "
        f"Matched: {sorted(matched_creators)[:10]}... "
        f"Missing: {sorted(input_usernames - result_usernames)[:10]}..."
    )

    logger.info(
        "Coverage: %d/%d creators matched (%d required)",
        len(matched_creators),
        len(input_usernames),
        min_coverage,
    )

    # Validation 5: Date range check (<=10% out-of-range tolerance)
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
            f"DATE RANGE: {out_of_range}/{parseable} results ({oor_ratio:.0%}) are older than "
            f"cutoff {cutoff_str}. Tolerance is 10%."
        )
    else:
        logger.warning(
            "No parseable dates found in %d results — skipping date range validation",
            len(results),
        )

    # Validation 6: URL validity
    result_urls = [r.get("url", "") for r in results if r.get("url")]
    if result_urls:
        invalid = [u for u in result_urls if not (isinstance(u, str) and u.startswith("http") and len(u) > 10)]
        invalid_ratio = len(invalid) / len(result_urls) if result_urls else 0
        assert invalid_ratio <= 0.20, (
            f"INVALID URLS: {len(invalid)}/{len(result_urls)} result URLs are invalid "
            f"({invalid_ratio:.0%}). Threshold is 20%."
        )

    logger.info(
        "PASS: batch-%s → %d results, %d creators, %.1fs",
        platform_name,
        len(results),
        len(matched_creators),
        elapsed,
    )
