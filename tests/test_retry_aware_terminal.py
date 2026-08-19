"""Tests for retry-aware terminality.

The server made ``failed`` conditionally terminal: a job that fails an attempt
while automatic retries remain reports ``status="failed"`` with
``is_terminal=False``, because the platform is about to run it again. A wait loop
that decides terminality from the status string alone returns on that job and
abandons a run that is still in progress — the retry's results are produced with
nobody polling, and re-submitting duplicates the spend.

These tests pin both halves of the contract: trust the server when it answers,
fall back to the status map when it does not.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from gofetch.actor import (
    ActorClient,
    AsyncActorClient,
    _format_job_as_apify_run,
    _is_terminal,
    _job_is_terminal,
)


def _job(**overrides) -> dict:
    job = {
        "id": "job-123",
        "status": "failed",
        "scraper_type": "tiktok_comments",
        "started_at": "2026-08-05T12:08:00Z",
        "completed_at": "2026-08-05T12:12:37Z",
    }
    job.update(overrides)
    return job


class TestJobIsTerminal:
    def test_failed_with_retry_pending_is_not_terminal(self) -> None:
        assert _job_is_terminal(_job(is_terminal=False, will_auto_retry=True)) is False

    def test_failed_with_retries_exhausted_is_terminal(self) -> None:
        assert _job_is_terminal(_job(is_terminal=True, will_auto_retry=False)) is True

    def test_completed_is_terminal(self) -> None:
        assert _job_is_terminal(_job(status="completed", is_terminal=True)) is True

    def test_running_is_not_terminal(self) -> None:
        assert _job_is_terminal(_job(status="running", is_terminal=False)) is False

    def test_server_verdict_wins_over_status_string(self) -> None:
        """The whole point: `failed` no longer implies terminal."""
        job = _job(status="failed", is_terminal=False)
        assert _is_terminal(job["status"]) is True      # old logic said "done"
        assert _job_is_terminal(job) is False           # new logic asks the server

    # -- backward compatibility with servers that don't send the field --

    def test_falls_back_to_status_map_when_field_absent(self) -> None:
        assert _job_is_terminal(_job()) is True
        assert _job_is_terminal(_job(status="running")) is False
        assert _job_is_terminal(_job(status="completed")) is True

    def test_falls_back_when_field_is_not_a_bool(self) -> None:
        """A null or string value must not be read as truthy/falsy."""
        for bad in (None, "false", "true", 0, 1, ""):
            assert _job_is_terminal(_job(is_terminal=bad)) is True

    def test_missing_status_and_field_is_not_terminal(self) -> None:
        assert _job_is_terminal({"id": "x"}) is False


class TestRunDictFields:
    def test_promotes_retry_fields_to_top_level(self) -> None:
        run = _format_job_as_apify_run(
            _job(is_terminal=False, will_auto_retry=True,
                 attempt_history=[{"attempt": 0, "error_message": "boom"}]),
        )
        assert run["isTerminal"] is False
        assert run["willAutoRetry"] is True
        assert run["attemptHistory"] == [{"attempt": 0, "error_message": "boom"}]

    def test_apify_status_still_says_failed(self) -> None:
        """Apify-shaped status is unchanged; isTerminal is what disambiguates it."""
        run = _format_job_as_apify_run(_job(is_terminal=False, will_auto_retry=True))
        assert run["status"] == "FAILED"
        assert run["isTerminal"] is False

    def test_attempt_history_defaults_to_empty_list(self) -> None:
        run = _format_job_as_apify_run(_job())
        assert run["attemptHistory"] == []

    def test_job_still_reachable_under_gofetch_job(self) -> None:
        run = _format_job_as_apify_run(_job(is_terminal=False))
        assert run["_gofetch_job"]["is_terminal"] is False

    def test_promotes_scraper_metadata_to_top_level(self) -> None:
        # coverage / completeness live here; the 0.3.0 dict dropped them, so the
        # only path was run["_gofetch_job"]["scraper_metadata"].
        metadata = {"coverage": {"mean": 0.2, "posts_failed": 0}}
        run = _format_job_as_apify_run(_job(scraper_metadata=metadata))
        assert run["scraper_metadata"] == metadata

    def test_scraper_metadata_none_when_server_omits_it(self) -> None:
        assert _format_job_as_apify_run(_job())["scraper_metadata"] is None


class TestWaitLoopsHonourServerVerdict:
    """All four wait loops must block through a pending retry, not return on it."""

    def test_sync_call_blocks_through_retry(self) -> None:
        http = MagicMock()
        http.post.return_value = _job(status="pending", is_terminal=False)
        http.get.side_effect = [
            _job(status="failed", is_terminal=False, will_auto_retry=True),  # retry pending
            _job(status="running", is_terminal=False),                       # retry started
            _job(status="completed", is_terminal=True),                      # real outcome
        ]

        actor = ActorClient(http=http, scraper_type="tiktok_comments")
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("time.sleep", lambda _s: None)
            run = actor.call(run_input={})

        assert run["status"] == "SUCCEEDED"
        assert run["isTerminal"] is True
        assert http.get.call_count == 3, "returned early on the failed-with-retry poll"

    @pytest.mark.asyncio
    async def test_async_call_blocks_through_retry(self) -> None:
        http = AsyncMock()
        http.post.return_value = _job(status="pending", is_terminal=False)
        http.get.side_effect = [
            _job(status="failed", is_terminal=False, will_auto_retry=True),
            _job(status="completed", is_terminal=True),
        ]

        actor = AsyncActorClient(http=http, scraper_type="tiktok_comments")
        with pytest.MonkeyPatch.context() as mp:
            async def _no_sleep(_s):
                return None
            mp.setattr("asyncio.sleep", _no_sleep)
            run = await actor.call(run_input={})

        assert run["status"] == "SUCCEEDED"
        assert http.get.call_count == 2

    def test_sync_call_still_returns_on_exhausted_failure(self) -> None:
        """Must not hang when the failure really is final."""
        http = MagicMock()
        http.post.return_value = _job(status="pending", is_terminal=False)
        http.get.side_effect = [_job(status="failed", is_terminal=True, will_auto_retry=False)]

        actor = ActorClient(http=http, scraper_type="tiktok_comments")
        run = actor.call(run_input={})

        assert run["status"] == "FAILED"
        assert run["isTerminal"] is True
        assert http.get.call_count == 1

    def test_sync_call_against_old_server_unchanged(self) -> None:
        """No is_terminal field: behave exactly as 0.3.0 did."""
        http = MagicMock()
        http.post.return_value = _job(status="pending")
        http.get.side_effect = [_job(status="failed")]  # no is_terminal key

        actor = ActorClient(http=http, scraper_type="tiktok_comments")
        run = actor.call(run_input={})

        assert run["status"] == "FAILED"
        assert http.get.call_count == 1
