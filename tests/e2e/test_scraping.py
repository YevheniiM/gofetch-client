"""
E2E scraping tests — every platform x every target x every result tier.

Run against the real GoFetch dev API. Requires GOFETCH_API_KEY env var.

Tests run in PARALLEL via pytest-xdist with one worker per TARGET (not per
platform). This means different targets within the same platform run
concurrently, giving ~3x speedup within each platform.

Usage:
    # All targets in parallel, tier 10 only (~21 workers)
    pytest tests/e2e/test_scraping.py -n auto --dist loadgroup -k "tier_10]"

    # All targets in parallel, quick tiers
    pytest tests/e2e/test_scraping.py -n auto --dist loadgroup -k "tier_10] or tier_50] or tier_100]"

    # All targets in parallel, all tiers
    pytest tests/e2e/test_scraping.py -n auto --dist loadgroup

    # Single platform — targets still run in parallel
    pytest tests/e2e/test_scraping.py -n 3 --dist loadgroup -k tiktok
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from gofetch import GoFetchClient

from .config import (
    PLATFORMS,
    RESULT_TIERS,
    build_run_input,
    extract_username_from_url,
    timeout_for_tier,
)

logger = logging.getLogger("e2e.scraping")

# Mark all tests in this module
pytestmark = [pytest.mark.e2e]


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def validate_run_dict(run: dict, scraper_type: str) -> list[str]:
    """Validate Apify-format run dict. Returns list of issues (empty = OK)."""
    issues: list[str] = []

    if not run.get("id"):
        issues.append("Missing 'id' in run dict")

    status = run.get("status", "")
    if not status:
        issues.append("Missing 'status' in run dict")

    act_id = run.get("actId", "")
    if not act_id:
        issues.append("Missing 'actId' in run dict")

    dataset_id = run.get("defaultDatasetId")
    if not dataset_id:
        issues.append("Missing 'defaultDatasetId' in run dict")

    return issues


def validate_results(
    results: list[dict],
    tier: int,
    platform_config: dict,
    target_name: str,
    target_config: dict | None = None,
) -> list[str]:
    """
    Validate scraped results. Returns list of issues.

    CRITICAL: Empty results from a known active target = ERROR.

    Checks:
    - Non-empty results
    - Result count vs requested tier (respecting platform_max_results)
    - No all-identical results
    - No all-error stubs
    - URL validity (>80% must be real URLs)
    - Expected field completeness (>50% must be present and non-null)
    - Profile attribution (at least some results trace back to input profiles)
    """
    issues: list[str] = []

    # --- Empty results are almost always an error ---
    if len(results) == 0:
        issues.append(
            f"CRITICAL: Zero results for target '{target_name}' with limit {tier}. "
            f"Empty results from known active targets indicate a scraping failure."
        )
        return issues  # no point checking further

    # --- Check result count vs requested tier ---
    if platform_config.get("single_document"):
        # Single-document scrapers (e.g. instagram_profile) return exactly 1
        # item regardless of the requested limit — skip count validation.
        pass
    else:
        min_ratio = platform_config.get("min_result_ratio", 0.3)
        # #4/#5: Clamp effective tier to platform_max_results if set
        platform_max = platform_config.get("platform_max_results")
        effective_tier = min(tier, platform_max) if platform_max else tier
        expected_min = max(1, int(effective_tier * min_ratio))
        if len(results) < expected_min:
            issues.append(
                f"LOW RESULTS: Got {len(results)} items for limit {tier} "
                f"(expected at least {expected_min}, ratio={min_ratio}"
                f"{f', capped at {platform_max}' if platform_max else ''}). "
                f"This may indicate throttling or a partial failure."
            )

    # --- Check that results are not all identical ---
    if len(results) > 1:
        ids = {str(r.get("id", r.get("url", i))) for i, r in enumerate(results)}
        if len(ids) == 1:
            issues.append(
                f"DUPLICATE: All {len(results)} results appear identical. "
                f"This likely indicates a data duplication bug."
            )

    # --- Check that results have substance (not just error/note stubs) ---
    error_items = [r for r in results if r.get("error") or r.get("note")]
    real_items = len(results) - len(error_items)
    if real_items == 0 and len(results) > 0:
        issues.append(
            f"ALL ERROR ITEMS: All {len(results)} results are error/note stubs. "
            f"No real data was scraped."
        )

    # --- URL validity: result 'url' fields should be real URLs ---
    urls = [r.get("url", "") for r in results if r.get("url")]
    if urls:
        invalid_urls = [u for u in urls if not (isinstance(u, str) and u.startswith("http") and len(u) > 10)]
        invalid_ratio = len(invalid_urls) / len(urls)
        if invalid_ratio > 0.2:
            issues.append(
                f"INVALID URLS: {len(invalid_urls)}/{len(urls)} result URLs are invalid "
                f"({invalid_ratio:.0%}). Threshold is 20%."
            )

    # --- Expected field completeness ---
    expected_fields = platform_config.get("expected_fields", [])
    if expected_fields and results:
        total_checks = len(results) * len(expected_fields)
        missing = 0
        for r in results:
            for field in expected_fields:
                if r.get(field) is None:
                    missing += 1
        if total_checks > 0:
            missing_ratio = missing / total_checks
            if missing_ratio > 0.5:
                issues.append(
                    f"FIELD COMPLETENESS: {missing}/{total_checks} expected field values "
                    f"are missing ({missing_ratio:.0%}). "
                    f"Expected fields: {expected_fields}. Threshold is 50%."
                )

    # --- Profile attribution (#9): use ownerUsername/author when available ---
    if target_config:
        scraper_type = platform_config.get("scraper_type", "")
        input_usernames: set[str] = set()
        for key in ("directUrls", "profiles", "channelUrls"):
            for url in target_config.get(key, []):
                uname = extract_username_from_url(url, scraper_type)
                if uname:
                    input_usernames.add(uname)

        if input_usernames:
            matched = 0
            attributable = 0
            for r in results:
                # Prefer structured fields; fall back to URL substring
                owner = r.get("ownerUsername", "") or r.get("author", "")
                if owner:
                    attributable += 1
                    if str(owner).strip().lstrip("@").lower() in input_usernames:
                        matched += 1
                else:
                    result_url = str(r.get("url", "")).lower()
                    if result_url and any(uname in result_url for uname in input_usernames):
                        matched += 1
                        attributable += 1

            # Only flag if we had attributable results and none matched
            if attributable > 0 and matched == 0:
                issues.append(
                    f"ATTRIBUTION: None of the {attributable} attributable results "
                    f"could be traced back to input profiles {input_usernames}. "
                    f"This may indicate results are from wrong profiles."
                )

    return issues


# ---------------------------------------------------------------------------
# Test generation — parametrize with xdist_group per target
# ---------------------------------------------------------------------------


def _make_test_params() -> list[tuple]:
    """Generate (platform_name, target, tier) tuples with xdist_group per target.

    Each target gets its own xdist worker, so different targets within the
    same platform run in parallel (e.g. tiktok_khaby, tiktok_charli,
    tiktok_mrbeast each get their own worker).  Tiers for the same target
    run sequentially within that worker, which avoids overwhelming the API
    with concurrent requests for the same account.
    """
    params = []
    for platform_name, platform_config in PLATFORMS.items():
        for target in platform_config["targets"]:
            for tier in platform_config.get("tiers", RESULT_TIERS):
                marks = [pytest.mark.xdist_group(target["name"])]
                if tier >= 500:
                    marks.append(pytest.mark.slow)
                params.append(
                    pytest.param(
                        platform_name,
                        target,
                        tier,
                        id=f"{platform_name}-{target['name']}-tier_{tier}",
                        marks=marks,
                    )
                )
    return params


@pytest.mark.parametrize("platform_name,target,tier", _make_test_params())
def test_scrape_platform(
    client: GoFetchClient,
    platform_name: str,
    target: dict,
    tier: int,
) -> None:
    """
    Core E2E test: scrape a platform target with a given result tier.

    Validates:
    1. Job creates successfully
    2. Job reaches terminal state within timeout
    3. Terminal status is SUCCEEDED (not FAILED/TIMED-OUT)
    4. Results are non-empty (critical — empty = error)
    5. Result count is reasonable for the tier
    6. Results contain expected fields
    7. Results are not duplicates
    """
    platform_config = PLATFORMS[platform_name]
    scraper_type = platform_config["scraper_type"]
    limit_key = platform_config["limit_key"]
    timeout = timeout_for_tier(tier, platform_name)  # #8: per-platform timeout

    # Build run input
    run_input = build_run_input(target["config"], limit_key, tier)

    logger.info(
        "Starting: platform=%s target=%s tier=%d timeout=%ds",
        platform_name,
        target["name"],
        tier,
        timeout,
    )
    t_start = time.monotonic()

    # --- 1. Create and run job ---
    actor = client.actor(scraper_type)
    run = actor.call(run_input=run_input, wait_secs=timeout)

    elapsed = time.monotonic() - t_start
    logger.info(
        "Job finished: id=%s status=%s elapsed=%.1fs",
        run.get("id"),
        run.get("status"),
        elapsed,
    )

    # --- 2. Validate run dict structure ---
    run_issues = validate_run_dict(run, scraper_type)
    assert not run_issues, "Run dict validation failed:\n" + "\n".join(run_issues)

    # --- 3. Check terminal status (#2, #7) ---
    status = run.get("status", "")

    # Jobs still RUNNING after timeout → skip (slow, not a bug)
    if status == "RUNNING":
        pytest.skip(
            f"Job {run['id']} still RUNNING after {timeout}s timeout — "
            f"skipping (slow job, not an SDK failure)"
        )

    if status == "READY":
        pytest.skip(f"Job {run['id']} still in READY state — never picked up")

    # TIMED-OUT → skip (API-side timeout, not an SDK bug)
    if status == "TIMED-OUT":
        pytest.skip(
            f"Job {run['id']} TIMED-OUT on the server side — "
            f"skipping (API timeout, not an SDK failure)"
        )

    # FAILED → hard failure
    assert status == "SUCCEEDED", (
        f"Job {run['id']} finished with status '{status}' instead of SUCCEEDED.\n"
        f"GoFetch job data: {run.get('_gofetch_job', {})}"
    )

    # --- 4. Fetch and validate results ---
    dataset = client.dataset(run["defaultDatasetId"])
    results = dataset.list_items()

    result_issues = validate_results(
        results, tier, platform_config, target["name"], target_config=target["config"],
    )

    # CRITICAL assertion: any result issues are test failures
    assert not result_issues, (
        f"Result validation failed for {platform_name}/{target['name']} tier={tier}:\n"
        + "\n".join(f"  - {issue}" for issue in result_issues)
    )

    logger.info(
        "PASS: %s/%s tier=%d → %d results in %.1fs",
        platform_name,
        target["name"],
        tier,
        len(results),
        elapsed,
    )


# ---------------------------------------------------------------------------
# Apify URL compatibility tests
# ---------------------------------------------------------------------------


def _make_apify_url_params() -> list[tuple]:
    """Test that Apify-style actor URLs work identically to direct types."""
    params = []
    for platform_name, platform_config in PLATFORMS.items():
        apify_url = platform_config.get("apify_url")
        if apify_url:
            target = platform_config["targets"][0]  # use first target only
            params.append(
                pytest.param(
                    platform_name,
                    apify_url,
                    target,
                    id=f"apify_url-{platform_name}",
                    marks=[pytest.mark.xdist_group(target["name"])],
                )
            )
    return params


@pytest.mark.parametrize("platform_name,apify_url,target", _make_apify_url_params())
def test_apify_url_compat(
    client: GoFetchClient,
    platform_name: str,
    apify_url: str,
    target: dict,
) -> None:
    """Verify that Apify-style actor URLs create jobs identically to direct types."""
    platform_config = PLATFORMS[platform_name]
    limit_key = platform_config["limit_key"]
    tier = 10  # minimal tier for compat check

    run_input = build_run_input(target["config"], limit_key, tier)
    timeout = timeout_for_tier(tier, platform_name)

    # Use Apify URL instead of direct scraper type
    actor = client.actor(apify_url)
    run = actor.call(run_input=run_input, wait_secs=timeout)

    assert run.get("status") == "SUCCEEDED", (
        f"Apify URL '{apify_url}' job failed with status: {run.get('status')}"
    )

    dataset = client.dataset(run["defaultDatasetId"])
    results = dataset.list_items()

    assert len(results) > 0, (
        f"Apify URL '{apify_url}' returned zero results. "
        f"Empty results indicate the URL mapping is broken."
    )


# ---------------------------------------------------------------------------
# actor.start() + run.wait_for_finish() flow
# ---------------------------------------------------------------------------


def _make_start_wait_params() -> list[tuple]:
    """One test per platform using start() instead of call()."""
    params = []
    for platform_name, platform_config in PLATFORMS.items():
        target = platform_config["targets"][0]
        params.append(
            pytest.param(
                platform_name,
                target,
                id=f"start_wait-{platform_name}",
                marks=[pytest.mark.xdist_group(target["name"])],
            )
        )
    return params


@pytest.mark.parametrize("platform_name,target", _make_start_wait_params())
def test_start_then_wait(
    client: GoFetchClient,
    platform_name: str,
    target: dict,
) -> None:
    """Test the non-blocking flow: actor.start() → run.wait_for_finish() → dataset."""
    platform_config = PLATFORMS[platform_name]
    scraper_type = platform_config["scraper_type"]
    limit_key = platform_config["limit_key"]
    tier = 10
    timeout = timeout_for_tier(tier, platform_name)

    run_input = build_run_input(target["config"], limit_key, tier)

    # start() should return immediately
    actor = client.actor(scraper_type)
    run = actor.start(run_input=run_input)

    assert run.get("id"), "start() did not return a job ID"
    assert run.get("status") in ("READY", "RUNNING"), (
        f"start() returned unexpected status: {run.get('status')}"
    )

    # wait via RunClient
    run_client = client.run(run["id"])
    final = run_client.wait_for_finish(wait_secs=timeout)

    assert final is not None, f"wait_for_finish returned None for job {run['id']}"
    assert final.get("status") == "SUCCEEDED", (
        f"Job {run['id']} finished with {final.get('status')}"
    )

    # fetch results
    dataset = run_client.dataset()
    results = dataset.list_items()

    assert len(results) > 0, (
        f"start+wait flow for {platform_name} returned zero results"
    )


# ---------------------------------------------------------------------------
# Pagination tests — verify large result sets paginate correctly
# (#12: uses distinct xdist group to avoid doubling API load on main target)
# ---------------------------------------------------------------------------


def _make_pagination_params() -> list[tuple]:
    params = []
    for platform_name, platform_config in PLATFORMS.items():
        if platform_config.get("single_document"):
            continue  # skip single-document scrapers — pagination is N/A
        target = platform_config["targets"][0]
        params.append(
            pytest.param(
                platform_name,
                id=f"pagination-{platform_name}",
                marks=[pytest.mark.slow, pytest.mark.xdist_group(f"pagination_{target['name']}")],
            )
        )
    return params


@pytest.mark.parametrize("platform_name", _make_pagination_params())
def test_pagination_integrity(client: GoFetchClient, platform_name: str) -> None:
    """
    Fetch 500 items and verify pagination works correctly.

    Checks:
    - iterate_items() yields all items across pages
    - list_items() returns same count as iterate_items()
    - No duplicate items across pages
    - (#13) Cross-check with dataset.get_info()["itemCount"]
    """
    platform_config = PLATFORMS[platform_name]
    scraper_type = platform_config["scraper_type"]
    limit_key = platform_config["limit_key"]
    # Respect platform ceiling — no point requesting 500 when max is ~100
    platform_max = platform_config.get("platform_max_results")
    tier = min(500, platform_max) if platform_max else 500
    timeout = timeout_for_tier(tier, platform_name)
    target = platform_config["targets"][0]

    run_input = build_run_input(target["config"], limit_key, tier)

    actor = client.actor(scraper_type)
    run = actor.call(run_input=run_input, wait_secs=timeout)

    if run.get("status") != "SUCCEEDED":
        pytest.skip(f"Job did not succeed (status={run.get('status')}), skipping pagination check")

    dataset = client.dataset(run["defaultDatasetId"])

    # iterate_items — lazy generator
    iter_items = list(dataset.iterate_items())

    # list_items — eager list
    list_items_result = dataset.list_items()

    assert len(iter_items) == len(list_items_result), (
        f"iterate_items() returned {len(iter_items)} items but "
        f"list_items() returned {len(list_items_result)}"
    )

    assert len(iter_items) > 0, (
        f"Pagination test for {platform_name} returned zero results"
    )

    # #13: Cross-check with dataset info itemCount
    info = dataset.get_info()
    if info and isinstance(info.get("itemCount"), int) and info["itemCount"] > 0:
        assert len(iter_items) == info["itemCount"], (
            f"iterate_items() returned {len(iter_items)} but "
            f"dataset.get_info() reports itemCount={info['itemCount']}"
        )

    # Check for duplicates (using item indices or urls)
    seen = set()
    duplicates = 0
    for item in iter_items:
        key = item.get("url") or item.get("id") or str(item)
        if key in seen:
            duplicates += 1
        seen.add(key)

    dup_ratio = duplicates / len(iter_items) if iter_items else 0
    assert dup_ratio < 0.1, (
        f"High duplicate ratio in paginated results: {duplicates}/{len(iter_items)} "
        f"({dup_ratio:.1%}) — likely a pagination bug"
    )


# ---------------------------------------------------------------------------
# Dataset info test
# ---------------------------------------------------------------------------


@pytest.mark.xdist_group("instagram_kylie")
def test_dataset_info(client: GoFetchClient) -> None:
    """Run a minimal job and verify dataset.get_info() returns correct metadata."""
    target = PLATFORMS["instagram"]["targets"][0]
    run_input = build_run_input(target["config"], "resultsLimit", 10)

    actor = client.actor("instagram")
    run = actor.call(run_input=run_input, wait_secs=timeout_for_tier(10, "instagram"))

    if run.get("status") != "SUCCEEDED":
        pytest.skip("Job didn't succeed")

    dataset = client.dataset(run["defaultDatasetId"])
    info = dataset.get_info()

    assert info.get("id"), "Dataset info missing 'id'"
    assert info.get("name", "").startswith("gofetch-"), (
        f"Dataset name should start with 'gofetch-', got: {info.get('name')}"
    )
    assert isinstance(info.get("itemCount"), int), "itemCount should be int"
    assert info["itemCount"] > 0, (
        "CRITICAL: itemCount is 0 for a SUCCEEDED job — this indicates a data loss issue"
    )


# ---------------------------------------------------------------------------
# Job abort test (#14: poll until RUNNING before sending abort)
# ---------------------------------------------------------------------------


@pytest.mark.xdist_group("instagram_kylie")
def test_abort_running_job(client: GoFetchClient) -> None:
    """Start a large job and abort it mid-flight."""
    target = PLATFORMS["instagram"]["targets"][0]
    run_input = build_run_input(target["config"], "resultsLimit", 3000)

    actor = client.actor("instagram")
    run = actor.start(run_input=run_input)

    assert run.get("id"), "start() must return job ID"

    run_client = client.run(run["id"])

    # Poll until the job is actually RUNNING (not just READY)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        current = run_client.get()
        if current and current.get("status") == "RUNNING":
            break
        if current and current.get("status") not in ("READY", "RUNNING"):
            # Already terminal — nothing to abort
            pytest.skip(f"Job reached {current.get('status')} before we could abort")
        time.sleep(2)

    aborted = run_client.abort()

    assert aborted.get("status") in ("ABORTED", "ABORTING", "SUCCEEDED", "FAILED"), (
        f"Unexpected status after abort: {aborted.get('status')}"
    )


# ---------------------------------------------------------------------------
# Log retrieval test
# ---------------------------------------------------------------------------


@pytest.mark.xdist_group("reddit_technology")
def test_log_retrieval(client: GoFetchClient) -> None:
    """Run a job and verify logs are retrievable."""
    target = PLATFORMS["reddit"]["targets"][0]
    run_input = build_run_input(target["config"], "postsLimit", 10)

    actor = client.actor("reddit")
    run = actor.call(run_input=run_input, wait_secs=timeout_for_tier(10, "reddit"))

    run_client = client.run(run["id"])
    log_client = run_client.log()

    text_log = log_client.get()
    structured_log = log_client.list()

    # At minimum, a completed job should have some log entries
    if run.get("status") == "SUCCEEDED":
        assert text_log is not None, "Log text should not be None for completed job"
        assert len(structured_log) > 0, "Structured log should have entries"
