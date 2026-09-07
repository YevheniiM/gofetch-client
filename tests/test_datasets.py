"""Tests for the Datasets product clients (collection, feed, batch, export).

Payloads are copied from real dev responses (2026-09-06, Go-Fetch QA org) and
from the shipped contract, not invented.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gofetch.constants import IDEMPOTENCY_KEY_HEADER
from gofetch.dataset_batch import AsyncDatasetBatchClient, DatasetBatchClient
from gofetch.dataset_export import AsyncDatasetExportClient, DatasetExportClient
from gofetch.datasets import (
    AsyncDatasetCollectionClient,
    AsyncDatasetFeedClient,
    DatasetCollectionClient,
    DatasetFeedClient,
)
from gofetch.exceptions import (
    APIError,
    BatchExpiredError,
    DatasetConflictError,
    TimeoutError,
    ValidationError,
)

# ---------------------------------------------------------------------------
# Fixtures / mock data
# ---------------------------------------------------------------------------

MOCK_LIST_ROW = {
    "slug": "creator-feed",
    "name": "Creator Feed",
    "description": "",
    "kind": "pool",
    "price_per_1000": "15.0000",
    "is_active": False,
    "updated_at": "2026-09-04T03:04:44.184349Z",
    "items": {"total": 0, "delivered": 0, "undelivered": 0},
    "open_batch_id": None,
    "degraded": [
        {
            "code": "pool_refused:index_missing",
            "message": "We do not have a copy of your creator index yet.",
        }
    ],
}

MOCK_LIST_PAGE = {"total": 1, "offset": 0, "limit": 25, "count": 1, "results": [MOCK_LIST_ROW]}

MOCK_QUOTE = {
    "items": {"new": 1000, "owned": 0, "total": 1000},
    "price_per_1000": "15.0000",
    "amount": "15.0000",
    "balance": "4690.3253",
    "affordable": True,
    "formats": ["jsonl"],
    "blocked": None,
    "quote_kind": "moving",
    "resuming": False,
}

MOCK_OVERVIEW = {
    "slug": "creator-feed",
    "name": "Creator Feed",
    "config": {
        "band": "nano",
        "daily_quota": 50,
        "batch_size": 5,
        "ack_ttl_hours": 48,
        "is_active": False,
    },
    "price_per_1000": "15.0000",
    "max_daily_quota": 10000,
    "max_batch_size": 2500,
    "pool": {
        "supported": True,
        "available": 0,
        "status": "refused",
        "refreshed_at": None,
        "stale": False,
        "refusal_code": "index_missing",
    },
    "delivered": {"today": 0, "total": 0, "quota_reserved": 0, "quota_remaining": 50},
    "open_batch": None,
    "owned_index": {
        "row_count": 0,
        "loaded_at": None,
        "source_file": None,
        "source_name": None,
        "skipped_count": 0,
        "latest_load": None,
    },
    "download": {**MOCK_QUOTE, "supported": True},
    "degraded": [],
}

MOCK_BATCH = {
    "batch_id": "api-2b1f-20260906-7",
    "state": "open",
    "row_count": 1000,
    "billed_rows": None,
    "billed_amount": None,
    "price_per_1000_at_open": "15.0000",
    "expires_at": "2026-09-08T13:00:00Z",
    "created_at": "2026-09-06T13:00:00Z",
    "acked_at": None,
    "expired_at": None,
}

MOCK_PULL_OK = {"status": "ok", "batch": MOCK_BATCH, "constraints": []}

MOCK_ACKED = {
    "status": "acked",
    "batch": {**MOCK_BATCH, "state": "acked", "billed_rows": 990, "billed_amount": "14.8500"},
    "constraints": [{"code": "index_drop", "message": "10 rows were already in your index."}],
}

MOCK_ACCEPTED = {
    "export_id": "3f2b7c40-0000-4000-8000-000000000001",
    "status": "pending",
    "format": "jsonl",
    "batch_id": "dl-2b1f-20260906-1",
    "billed_items": 1000,
    "billed_amount": "15.0000",
    "constraints": [],
}

MOCK_EXPORT_READY = {
    "id": "3f2b7c40-0000-4000-8000-000000000001",
    "status": "ready",
    "format": "jsonl",
    "item_count": 1000,
    "byte_size": 512000,
    "created_at": "2026-09-06T13:00:00Z",
    "ready_at": "2026-09-06T13:00:30Z",
    "expires_at": "2026-09-10T13:00:00Z",
    "error": "",
    "url": "https://s3.example.com/export.jsonl?X-Amz-Signature=abc",
}

EXPORT_ID = MOCK_EXPORT_READY["id"]


def _rows_page(rows, total, offset=0, limit=100):
    return {"total": total, "offset": offset, "limit": limit, "count": len(rows), "results": rows}


def _routed(routes):
    """A side_effect that answers by path, so one mock serves a whole flow."""

    def answer(path, *args, **kwargs):
        for suffix, response in routes.items():
            if path.endswith(suffix):
                return response(kwargs) if callable(response) else response
        raise AssertionError(f"unexpected path {path}")

    return answer


# ---------------------------------------------------------------------------
# DatasetCollectionClient
# ---------------------------------------------------------------------------


class TestDatasetCollectionClient:

    def test_list_returns_a_list_page(self):
        http = MagicMock()
        http.get.return_value = MOCK_LIST_PAGE

        page = DatasetCollectionClient(http).list()

        http.get.assert_called_once_with(
            "/api/v1/datasets/", params={"limit": 25, "offset": 0}
        )
        assert len(page) == 1
        assert page.total == 1
        assert page[0]["slug"] == "creator-feed"

    def test_a_paused_dataset_is_listed(self):
        """`is_active: false` is how a retired dataset shows up — not a 404."""
        http = MagicMock()
        http.get.return_value = MOCK_LIST_PAGE

        page = DatasetCollectionClient(http).list()

        assert page[0]["is_active"] is False

    def test_limit_is_clamped_to_the_server_max(self):
        """The server silently clamps above 100, so asking for 500 would lie."""
        http = MagicMock()
        http.get.return_value = MOCK_LIST_PAGE

        DatasetCollectionClient(http).list(limit=500)

        assert http.get.call_args[1]["params"]["limit"] == 100

    def test_iterate_pages_until_exhausted(self):
        http = MagicMock()
        http.get.side_effect = [
            _rows_page([{"slug": "a"}, {"slug": "b"}], total=3),
            _rows_page([{"slug": "c"}], total=3, offset=2),
        ]

        rows = list(DatasetCollectionClient(http).iterate())

        assert [r["slug"] for r in rows] == ["a", "b", "c"]
        assert http.get.call_count == 2

    def test_feed_returns_a_feed_client_without_hitting_the_api(self):
        http = MagicMock()

        feed = DatasetCollectionClient(http).feed("creator-feed")

        assert isinstance(feed, DatasetFeedClient)
        http.get.assert_not_called()


# ---------------------------------------------------------------------------
# DatasetFeedClient — reads and config
# ---------------------------------------------------------------------------


class TestDatasetFeedClient:

    def test_get_returns_the_overview(self):
        http = MagicMock()
        http.get.return_value = MOCK_OVERVIEW

        overview = DatasetFeedClient(http, "creator-feed").get()

        http.get.assert_called_once_with("/api/v1/datasets/creator-feed/")
        assert overview["config"]["daily_quota"] == 50

    def test_money_is_returned_as_the_exact_string(self):
        """Never floated: "15.00" and "15.0000" compared unequal once already."""
        http = MagicMock()
        http.get.return_value = MOCK_OVERVIEW

        overview = DatasetFeedClient(http, "creator-feed").get()

        assert overview["price_per_1000"] == "15.0000"
        assert overview["download"]["balance"] == "4690.3253"
        assert isinstance(overview["download"]["amount"], str)

    def test_update_config_sends_only_the_writable_fields(self):
        http = MagicMock()
        http.patch.return_value = MOCK_OVERVIEW

        DatasetFeedClient(http, "creator-feed").update_config(daily_quota=2500)

        http.patch.assert_called_once_with(
            "/api/v1/datasets/creator-feed/config/", json={"daily_quota": 2500}
        )

    @pytest.mark.parametrize("field", ["band", "ack_ttl_hours", "is_active"])
    def test_update_config_rejects_read_only_fields(self, field):
        """DRF drops these silently, so a 200 would look like it worked."""
        http = MagicMock()

        with pytest.raises(ValidationError, match=field):
            DatasetFeedClient(http, "creator-feed").update_config(**{field: 1})

        http.patch.assert_not_called()

    def test_update_config_rejects_an_empty_change(self):
        http = MagicMock()

        with pytest.raises(ValidationError):
            DatasetFeedClient(http, "creator-feed").update_config()

    def test_batches_and_exports_hit_their_own_routes(self):
        http = MagicMock()
        http.get.return_value = _rows_page([], 0)
        feed = DatasetFeedClient(http, "creator-feed")

        feed.batches()
        feed.exports()

        paths = [call[0][0] for call in http.get.call_args_list]
        assert paths == [
            "/api/v1/datasets/creator-feed/batches/",
            "/api/v1/datasets/creator-feed/exports/",
        ]


# ---------------------------------------------------------------------------
# pull_and_iterate — the loop that loses data if it is wrong
# ---------------------------------------------------------------------------


class TestPullAndIterate:

    def _http(self, pull=None, rows=None):
        http = MagicMock()
        http.post.side_effect = _routed({"/pull/": pull or MOCK_PULL_OK, "/ack/": MOCK_ACKED})
        http.get.side_effect = _routed({"/rows/": rows or _rows_page([{"h": "a"}, {"h": "b"}], 2)})
        return http

    def _acked(self, http):
        return any("/ack/" in call[0][0] for call in http.post.call_args_list)

    def test_full_consumption_acks(self):
        http = self._http()

        rows = list(DatasetFeedClient(http, "creator-feed").pull_and_iterate())

        assert [r["h"] for r in rows] == ["a", "b"]
        assert self._acked(http)

    def test_early_break_does_not_ack(self):
        """Ack is the charge. A consumer that stops early has not stored the rest."""
        http = self._http()

        for _row in DatasetFeedClient(http, "creator-feed").pull_and_iterate():
            break

        assert not self._acked(http)

    def test_exception_in_the_consumer_does_not_ack(self):
        http = self._http()

        with pytest.raises(RuntimeError):
            for _row in DatasetFeedClient(http, "creator-feed").pull_and_iterate():
                raise RuntimeError("consumer blew up")

        assert not self._acked(http)

    def test_exception_while_paging_does_not_ack(self):
        http = self._http()
        http.get.side_effect = APIError(message="boom", status_code=500)

        with pytest.raises(APIError):
            list(DatasetFeedClient(http, "creator-feed").pull_and_iterate())

        assert not self._acked(http)

    def test_auto_ack_false_never_acks(self):
        http = self._http()

        list(DatasetFeedClient(http, "creator-feed").pull_and_iterate(auto_ack=False))

        assert not self._acked(http)

    @pytest.mark.parametrize(
        "pull",
        [
            {"status": "quota_exhausted", "batch": None, "constraints": []},
            {"status": "nothing_available", "batch": None, "constraints": []},
            {"status": "unavailable", "batch": None, "constraints": []},
        ],
    )
    def test_a_pull_without_a_batch_yields_nothing(self, pull):
        http = self._http(pull=pull)

        assert list(DatasetFeedClient(http, "creator-feed").pull_and_iterate()) == []
        assert not self._acked(http)
        http.get.assert_not_called()

    def test_open_batch_exists_is_served_like_ok(self):
        """Re-pulling an open batch is the at-least-once contract, not an error."""
        http = self._http(pull={"status": "open_batch_exists", "batch": MOCK_BATCH,
                                "constraints": []})

        rows = list(DatasetFeedClient(http, "creator-feed").pull_and_iterate())

        assert len(rows) == 2
        assert self._acked(http)

    def test_a_page_without_a_total_is_not_read_as_the_last_page(self):
        """`_as_page` falls back to total=len(rows), which always equals the rows
        just read. Believing it would end iteration after page one and then ack
        — charging the customer for rows the SDK never handed them."""
        http = MagicMock()
        http.post.side_effect = _routed({"/pull/": MOCK_PULL_OK, "/ack/": MOCK_ACKED})
        http.get.side_effect = [
            {"results": [{"h": "a"}, {"h": "b"}]},   # full page, no `total`
            {"results": [{"h": "c"}]},               # short page, no `total`
        ]

        rows = list(
            DatasetFeedClient(http, "creator-feed").pull_and_iterate(page_size=2)
        )

        assert [r["h"] for r in rows] == ["a", "b", "c"]
        assert self._acked(http)

    def test_a_short_first_page_without_a_total_still_ends(self):
        http = MagicMock()
        http.post.side_effect = _routed({"/pull/": MOCK_PULL_OK, "/ack/": MOCK_ACKED})
        http.get.side_effect = [{"results": [{"h": "a"}]}]

        rows = list(
            DatasetFeedClient(http, "creator-feed").pull_and_iterate(page_size=2)
        )

        assert [r["h"] for r in rows] == ["a"]
        assert http.get.call_count == 1

    def test_a_reported_total_still_stops_on_the_last_full_page(self):
        """When the server does send a total it stays authoritative — no extra
        request just to see an empty page."""
        http = MagicMock()
        http.post.side_effect = _routed({"/pull/": MOCK_PULL_OK, "/ack/": MOCK_ACKED})
        http.get.side_effect = [_rows_page([{"h": "a"}, {"h": "b"}], total=2, limit=2)]

        rows = list(
            DatasetFeedClient(http, "creator-feed").pull_and_iterate(page_size=2)
        )

        assert len(rows) == 2
        assert http.get.call_count == 1

    def test_dataset_paused_propagates_and_never_acks(self):
        """The pause is checked BEFORE the open batch is re-served, so pull()
        cannot see a batch the customer still owns. Swallowing this 409 would
        look like "no rows today" while their batch quietly expires."""
        http = MagicMock()
        http.post.side_effect = DatasetConflictError(
            message="This dataset is paused.", error_code="dataset_paused"
        )

        with pytest.raises(DatasetConflictError) as exc_info:
            list(DatasetFeedClient(http, "creator-feed").pull_and_iterate())

        assert exc_info.value.code == "dataset_paused"
        assert not self._acked(http)

    def test_an_open_batch_is_still_readable_and_ackable_while_paused(self):
        """The documented recovery: get()["open_batch"] -> rows -> ack."""
        http = MagicMock()
        http.get.side_effect = _routed(
            {
                "/creator-feed/": {**MOCK_OVERVIEW, "open_batch": MOCK_BATCH},
                "/rows/": _rows_page([{"h": "a"}], 1),
            }
        )
        http.post.side_effect = _routed({"/ack/": MOCK_ACKED})
        feed = DatasetFeedClient(http, "creator-feed")

        open_batch = feed.get()["open_batch"]
        batch = feed.batch(open_batch["batch_id"])
        rows = list(batch.iterate_rows())
        result = batch.ack()

        assert [r["h"] for r in rows] == ["a"]
        assert result["batch"]["billed_amount"] == "14.8500"

    def test_expired_batch_surfaces_as_batch_expired_error(self):
        http = self._http()
        http.get.side_effect = BatchExpiredError(message="rows released back to the pool")

        with pytest.raises(BatchExpiredError):
            list(DatasetFeedClient(http, "creator-feed").pull_and_iterate())

        assert not self._acked(http)


# ---------------------------------------------------------------------------
# download — the money path
# ---------------------------------------------------------------------------


class TestDownload:

    def _http(self, post):
        http = MagicMock()
        http.get.return_value = MOCK_QUOTE
        http.post.side_effect = post
        return http

    def test_always_sends_an_idempotency_key(self):
        """Without one the API answers 400 idempotency_key_required."""
        http = self._http([MOCK_ACCEPTED])

        DatasetFeedClient(http, "creator-feed").download()

        headers = http.post.call_args[1]["headers"]
        assert headers[IDEMPOTENCY_KEY_HEADER]
        assert len(headers[IDEMPOTENCY_KEY_HEADER]) == 32

    def test_expected_items_defaults_to_the_quote(self):
        http = self._http([MOCK_ACCEPTED])

        DatasetFeedClient(http, "creator-feed").download()

        http.get.assert_called_once_with("/api/v1/datasets/creator-feed/download/")
        assert http.post.call_args[1]["json"] == {"expected_items": 1000}

    def test_an_explicit_ceiling_skips_the_quote(self):
        http = self._http([MOCK_ACCEPTED])

        DatasetFeedClient(http, "creator-feed").download(expected_items=500, format="csv")

        http.get.assert_not_called()
        assert http.post.call_args[1]["json"] == {"expected_items": 500, "format": "csv"}

    def test_a_caller_key_is_used_verbatim(self):
        """A generated key dies with the process; only the caller's survives one."""
        http = self._http([MOCK_ACCEPTED])

        DatasetFeedClient(http, "creator-feed").download(idempotency_key="nightly-2026-09-06")

        assert http.post.call_args[1]["headers"] == {
            IDEMPOTENCY_KEY_HEADER: "nightly-2026-09-06"
        }

    def test_reused_key_after_a_requote_names_the_ceiling_that_replays(self):
        """Live local proof (2026-09-06): the server fingerprints the key on
        `expected_items`, and download() re-quotes it. After the first purchase
        landed, items.new was 0, so POST {"expected_items": 0} with the same key
        answered 400 idempotency_key_reused while POST {"expected_items": 10}
        replayed the receipt verbatim. The server says "mint a fresh key", which
        abandons the export already paid for, so the SDK names the real fix."""
        reused = APIError(
            message=(
                "This Idempotency-Key was already used for a different download. "
                "A new purchase needs a new key; reuse a key only to retry the "
                "request it was issued for."
            ),
            status_code=400,
            error_code="idempotency_key_reused",
        )
        http = self._http(reused)
        http.get.return_value = {**MOCK_QUOTE, "items": {"new": 0, "owned": 10, "total": 10}}

        with pytest.raises(APIError) as exc_info:
            DatasetFeedClient(http, "creator-feed").download(idempotency_key="nightly")

        assert exc_info.value.error_code == "idempotency_key_reused"
        assert "re-quoted the ceiling to 0" in str(exc_info.value)
        assert "expected_items" in str(exc_info.value)

    def test_a_reused_key_on_an_explicit_ceiling_is_left_alone(self):
        """Nothing was re-quoted, so the server's own message is the whole truth."""
        reused = APIError(message="already used", status_code=400,
                          error_code="idempotency_key_reused")
        http = self._http(reused)

        with pytest.raises(APIError) as exc_info:
            DatasetFeedClient(http, "creator-feed").download(
                idempotency_key="nightly", expected_items=10
            )

        assert str(exc_info.value) == "[400:idempotency_key_reused] already used"

    def test_a_reused_key_from_the_quote_stale_retry_is_also_hinted(self):
        """The retry POST sits inside the 409 handler; it must be covered too,
        and it ships the server's fresh ceiling, so the caller's key is now
        mismatched against that number rather than the first one."""
        stale = DatasetConflictError(
            message="stale", error_code="quote_stale", quote={"items": {"new": 940}}
        )
        reused = APIError(
            message="already used", status_code=400, error_code="idempotency_key_reused"
        )
        http = self._http([stale, reused])

        with pytest.raises(APIError) as exc_info:
            DatasetFeedClient(http, "creator-feed").download()

        assert "re-quoted the ceiling to 940" in str(exc_info.value)

    def test_the_hint_keeps_the_exception_type_and_its_siblings(self):
        """Rebuilding it as a bare APIError would downgrade a subclass and drop
        whatever structured data the parser attached."""
        reused = DatasetConflictError(
            message="already used",
            error_code="idempotency_key_reused",
            details={"supported_formats": ["jsonl"]},
        )
        http = self._http([reused])
        http.get.return_value = {**MOCK_QUOTE, "items": {"new": 0, "owned": 10, "total": 10}}

        with pytest.raises(DatasetConflictError) as exc_info:
            DatasetFeedClient(http, "creator-feed").download(idempotency_key="k-1")

        assert "re-quoted the ceiling to 0" in str(exc_info.value)
        assert exc_info.value.details["supported_formats"] == ["jsonl"]

    def test_quote_stale_retries_once_with_the_same_key_and_the_fresh_ceiling(self):
        """A refusal releases the key, so the same key is the correct retry."""
        stale = DatasetConflictError(
            message="The number of new items changed since you were quoted.",
            error_code="quote_stale",
            quote={"items": {"new": 940, "owned": 0, "total": 940}},
        )
        http = self._http([stale, MOCK_ACCEPTED])

        result = DatasetFeedClient(http, "creator-feed").download()

        assert result == MOCK_ACCEPTED
        assert http.post.call_count == 2
        first, second = http.post.call_args_list
        assert first[1]["json"]["expected_items"] == 1000
        assert second[1]["json"]["expected_items"] == 940
        assert first[1]["headers"] == second[1]["headers"]

    def test_quote_stale_twice_raises(self):
        """Exactly one retry — a second refusal is the caller's to handle."""
        stale = DatasetConflictError(
            message="stale", error_code="quote_stale", quote={"items": {"new": 940}}
        )
        http = self._http([stale, stale])

        with pytest.raises(DatasetConflictError):
            DatasetFeedClient(http, "creator-feed").download()

        assert http.post.call_count == 2

    def test_download_in_progress_is_not_retried(self):
        """It is the answer that says your purchase may already have happened."""
        conflict = DatasetConflictError(
            message="A download for this key is already running.",
            error_code="download_in_progress",
        )
        http = self._http([conflict])

        with pytest.raises(DatasetConflictError) as exc_info:
            DatasetFeedClient(http, "creator-feed").download()

        assert exc_info.value.code == "download_in_progress"
        assert http.post.call_count == 1

    def test_dataset_paused_is_not_retried(self):
        conflict = DatasetConflictError(message="paused", error_code="dataset_paused")
        http = self._http([conflict])

        with pytest.raises(DatasetConflictError):
            DatasetFeedClient(http, "creator-feed").download()

        assert http.post.call_count == 1

    def test_a_zero_billed_download_is_a_success(self):
        """The upload `nothing_new` path accepts an export with no batch behind
        it. Zero is a free download, not a failure."""
        nothing_new = {
            "export_id": "3f2b7c40-0000-4000-8000-000000000002",
            "status": "pending",
            "format": "jsonl",
            "batch_id": None,
            "billed_items": 0,
            "billed_amount": "0.0000",
            "constraints": [{"code": "nothing_new", "message": "Nothing new to buy."}],
        }
        http = self._http([nothing_new])

        result = DatasetFeedClient(http, "creator-feed").download()

        assert result["billed_items"] == 0
        assert result["billed_amount"] == "0.0000"
        assert result["export_id"]

    def test_a_drained_pool_refuses_rather_than_billing_a_free_zero(self):
        """Measured on dev 2026-09-07: a POOL dataset with nothing left answers
        409 pool_empty, NOT the upload path's zero-item receipt. A drain loop
        driven off a zero receipt would never terminate."""
        http = MagicMock()
        http.get.return_value = {**MOCK_QUOTE, "items": {"new": 0, "owned": 100,
                                                         "total": 100}}
        http.post.side_effect = DatasetConflictError(
            message="No rows are available right now: everything is already "
                    "delivered, held by another batch, or in your own index.",
            error_code="pool_empty",
            quote={"items": {"new": 0, "owned": 100, "total": 100},
                   "amount": "0.0000", "balance": "4688.8125"})

        with pytest.raises(DatasetConflictError) as exc_info:
            DatasetFeedClient(http, "creator-feed").download()

        assert exc_info.value.code == "pool_empty"
        # A come-back-later refusal carries the quote; nothing was billed.
        assert exc_info.value.quote["items"]["new"] == 0

    def test_quote_stale_without_a_quote_is_re_raised_not_retried_blind(self):
        """`quote` is absent on download_in_progress, idempotency_key_reused,
        unsupported_format and ledger_conflict — never assume it is there."""
        stale = DatasetConflictError(message="stale", error_code="quote_stale", quote=None)
        http = self._http([stale])

        with pytest.raises(DatasetConflictError):
            DatasetFeedClient(http, "creator-feed").download()

        assert http.post.call_count == 1

    def test_idempotency_key_reused_is_not_retried(self):
        """400, and it means a different purchase — never "try again"."""
        http = self._http([APIError(
            message="This Idempotency-Key was already used for a different download.",
            status_code=400,
            error_code="idempotency_key_reused",
        )])

        with pytest.raises(APIError) as exc_info:
            DatasetFeedClient(http, "creator-feed").download(idempotency_key="k-1")

        assert exc_info.value.error_code == "idempotency_key_reused"
        assert http.post.call_count == 1

    def test_billed_amount_comes_back_as_the_exact_string(self):
        http = self._http([MOCK_ACCEPTED])

        result = DatasetFeedClient(http, "creator-feed").download()

        assert result["billed_amount"] == "15.0000"
        assert isinstance(result["billed_amount"], str)


# ---------------------------------------------------------------------------
# DatasetBatchClient
# ---------------------------------------------------------------------------


class TestDatasetBatchClient:

    def test_get_returns_none_on_404(self):
        http = MagicMock()
        http.get.side_effect = APIError(message="No batch", status_code=404)

        assert DatasetBatchClient(http, "creator-feed", "api-x").get() is None

    def test_rows_pages_through_the_batch(self):
        http = MagicMock()
        http.get.side_effect = [
            _rows_page([{"h": "a"}], total=2),
            _rows_page([{"h": "b"}], total=2, offset=1),
        ]

        rows = list(DatasetBatchClient(http, "creator-feed", "api-x").iterate_rows())

        assert [r["h"] for r in rows] == ["a", "b"]

    def test_rows_on_an_expired_batch_raises_batch_expired(self):
        http = MagicMock()
        http.get.side_effect = BatchExpiredError(message="rows released back to the pool")

        with pytest.raises(BatchExpiredError):
            DatasetBatchClient(http, "creator-feed", "api-x").rows()

    def test_ack_reports_what_was_actually_billed(self):
        http = MagicMock()
        http.post.return_value = MOCK_ACKED

        result = DatasetBatchClient(http, "creator-feed", "api-x").ack()

        http.post.assert_called_once_with("/api/v1/datasets/creator-feed/batches/api-x/ack/")
        assert result["batch"]["billed_rows"] == 990
        assert result["batch"]["billed_amount"] == "14.8500"
        assert result["constraints"][0]["code"] == "index_drop"

    def test_export_defaults_to_an_empty_body(self):
        http = MagicMock()
        http.post.return_value = MOCK_ACCEPTED

        DatasetBatchClient(http, "creator-feed", "api-x").export()

        http.post.assert_called_once_with(
            "/api/v1/datasets/creator-feed/batches/api-x/export/", json={}
        )

    def test_export_passes_the_format(self):
        http = MagicMock()
        http.post.return_value = MOCK_ACCEPTED

        DatasetBatchClient(http, "creator-feed", "api-x").export(format="csv")

        assert http.post.call_args[1]["json"] == {"format": "csv"}


# ---------------------------------------------------------------------------
# DatasetExportClient
# ---------------------------------------------------------------------------


class TestDatasetExportClient:

    def test_get_returns_none_on_404(self):
        http = MagicMock()
        http.get.side_effect = APIError(message="No export", status_code=404)

        assert DatasetExportClient(http, "creator-feed", EXPORT_ID).get() is None

    def test_wait_for_ready_polls_until_terminal(self):
        http = MagicMock()
        http.get.side_effect = [
            {**MOCK_EXPORT_READY, "status": "pending", "url": None},
            {**MOCK_EXPORT_READY, "status": "building", "url": None},
            MOCK_EXPORT_READY,
        ]

        with patch("gofetch.dataset_export.time.sleep"):
            export = DatasetExportClient(http, "creator-feed", EXPORT_ID).wait_for_ready()

        assert export["status"] == "ready"
        assert http.get.call_count == 3

    @pytest.mark.parametrize("status", ["failed", "expired"])
    def test_wait_for_ready_stops_on_a_recoverable_terminal(self, status):
        http = MagicMock()
        http.get.return_value = {**MOCK_EXPORT_READY, "status": status, "url": None}

        export = DatasetExportClient(http, "creator-feed", EXPORT_ID).wait_for_ready()

        assert export["status"] == status
        assert http.get.call_count == 1

    def test_wait_for_ready_times_out(self):
        http = MagicMock()
        http.get.return_value = {**MOCK_EXPORT_READY, "status": "building", "url": None}

        with pytest.raises(TimeoutError):
            DatasetExportClient(http, "creator-feed", EXPORT_ID).wait_for_ready(wait_secs=0)

    def test_retry_posts_to_the_retry_route(self):
        http = MagicMock()
        http.post.return_value = {**MOCK_EXPORT_READY, "status": "pending"}

        DatasetExportClient(http, "creator-feed", EXPORT_ID).retry()

        http.post.assert_called_once_with(
            f"/api/v1/datasets/creator-feed/exports/{EXPORT_ID}/retry/"
        )

    def test_download_to_writes_the_gzip_bytes_verbatim(self, tmp_path):
        """Measured on dev 2026-09-07: the object is `<id>.jsonl.gz` served as
        application/gzip with NO Content-Encoding, so nothing inflates it in
        transit. Inflating it here would break `byte_size` and surprise a caller
        who asked for the file the server built."""
        import gzip

        body = gzip.compress(b'{"tiktok_handle": "beautyvibe35"}\n')
        http = MagicMock()
        http.get.return_value = MOCK_EXPORT_READY
        target = tmp_path / "export.jsonl.gz"

        with patch("gofetch.dataset_export.httpx.Client") as client_cls:
            response = client_cls.return_value.__enter__.return_value.stream
            response.return_value.__enter__.return_value.status_code = 200
            response.return_value.__enter__.return_value.iter_bytes.return_value = [body]
            DatasetExportClient(http, "creator-feed", EXPORT_ID).download_to(str(target))

        assert target.read_bytes() == body
        assert target.read_bytes()[:2] == b"\x1f\x8b"

    def test_download_to_streams_without_the_api_key(self, tmp_path):
        """The presigned GET is signed bare — X-API-Key would break it."""
        http = MagicMock()
        http.get.return_value = MOCK_EXPORT_READY
        target = tmp_path / "export.jsonl"

        with patch("gofetch.dataset_export._stream_to") as stream:
            path = DatasetExportClient(http, "creator-feed", EXPORT_ID).download_to(str(target))

        stream.assert_called_once_with(MOCK_EXPORT_READY["url"], str(target))
        assert path == str(target)

    def test_download_to_refuses_an_export_with_no_url(self, tmp_path):
        """A `ready` export past expires_at presigns a dead key; retry() is free."""
        http = MagicMock()
        http.get.return_value = {**MOCK_EXPORT_READY, "url": None}

        with pytest.raises(TimeoutError, match="retry"):
            DatasetExportClient(http, "creator-feed", EXPORT_ID).download_to(
                str(tmp_path / "x.jsonl")
            )


# ---------------------------------------------------------------------------
# Owned index
# ---------------------------------------------------------------------------


class TestOwnedIndex:

    def test_upload_owned_index_puts_then_loads(self, tmp_path):
        index = tmp_path / "index_handles.txt"
        index.write_text("nike\nadidas\n")
        http = MagicMock()
        http.post.side_effect = _routed(
            {
                "/upload-url/": {
                    "url": "https://s3.example.com/put?sig=abc",
                    "key": "owned-index/org-1/uuid/index_handles.txt",
                    "bucket": "creator-discovery",
                    "expires_in": 3600,
                    "method": "PUT",
                },
                "/load/": {"status": "queued", "source": "s3://…", "message_id": "m-1"},
            }
        )

        with patch("gofetch.datasets._put_presigned") as put:
            result = DatasetFeedClient(http, "creator-feed").upload_owned_index(str(index))

        put.assert_called_once_with("https://s3.example.com/put?sig=abc", b"nike\nadidas\n")
        assert http.post.call_args_list[0][1]["json"] == {"filename": "index_handles.txt"}
        # The key goes back verbatim: the server only accepts one it issued.
        assert http.post.call_args_list[1][1]["json"] == {
            "key": "owned-index/org-1/uuid/index_handles.txt"
        }
        assert result["status"] == "queued"

    def test_upload_url_omits_an_absent_filename(self):
        http = MagicMock()
        http.post.return_value = {"url": "u", "key": "k"}

        DatasetFeedClient(http, "creator-feed").owned_index_upload_url()

        http.post.assert_called_once_with(
            "/api/v1/datasets/creator-feed/owned-index/upload-url/", json={}
        )


# ---------------------------------------------------------------------------
# Async twins
# ---------------------------------------------------------------------------


class TestAsyncDatasets:

    async def test_list(self):
        http = AsyncMock()
        http.get.return_value = MOCK_LIST_PAGE

        page = await AsyncDatasetCollectionClient(http).list()

        assert page[0]["slug"] == "creator-feed"

    async def test_iterate(self):
        http = AsyncMock()
        http.get.side_effect = [
            _rows_page([{"slug": "a"}], total=2),
            _rows_page([{"slug": "b"}], total=2, offset=1),
        ]

        rows = [r async for r in AsyncDatasetCollectionClient(http).iterate()]

        assert [r["slug"] for r in rows] == ["a", "b"]

    async def test_feed_returns_the_async_feed_client(self):
        feed = AsyncDatasetCollectionClient(AsyncMock()).feed("creator-feed")

        assert isinstance(feed, AsyncDatasetFeedClient)
        assert isinstance(feed.batch("api-x"), AsyncDatasetBatchClient)
        assert isinstance(feed.export(EXPORT_ID), AsyncDatasetExportClient)

    def _http(self):
        http = AsyncMock()
        http.post.side_effect = _routed({"/pull/": MOCK_PULL_OK, "/ack/": MOCK_ACKED})
        http.get.side_effect = _routed({"/rows/": _rows_page([{"h": "a"}, {"h": "b"}], 2)})
        return http

    async def test_pull_and_iterate_acks_on_full_consumption(self):
        http = self._http()

        rows = [r async for r in AsyncDatasetFeedClient(http, "creator-feed").pull_and_iterate()]

        assert len(rows) == 2
        assert any("/ack/" in call[0][0] for call in http.post.call_args_list)

    async def test_pull_and_iterate_does_not_ack_on_early_break(self):
        http = self._http()

        async for _row in AsyncDatasetFeedClient(http, "creator-feed").pull_and_iterate():
            break

        assert not any("/ack/" in call[0][0] for call in http.post.call_args_list)

    async def test_pull_and_iterate_does_not_ack_on_exception(self):
        http = self._http()

        with pytest.raises(RuntimeError):
            async for _row in AsyncDatasetFeedClient(http, "creator-feed").pull_and_iterate():
                raise RuntimeError("consumer blew up")

        assert not any("/ack/" in call[0][0] for call in http.post.call_args_list)

    async def test_a_page_without_a_total_is_not_read_as_the_last_page(self):
        """The async twin must not under-read and then ack either."""
        http = AsyncMock()
        http.post.side_effect = _routed({"/pull/": MOCK_PULL_OK, "/ack/": MOCK_ACKED})
        http.get.side_effect = [
            {"results": [{"h": "a"}, {"h": "b"}]},
            {"results": [{"h": "c"}]},
        ]

        rows = [
            r
            async for r in AsyncDatasetFeedClient(http, "creator-feed").pull_and_iterate(
                page_size=2
            )
        ]

        assert [r["h"] for r in rows] == ["a", "b", "c"]
        assert any("/ack/" in call[0][0] for call in http.post.call_args_list)

    async def test_download_sends_the_key_and_retries_quote_stale_once(self):
        stale = DatasetConflictError(
            message="stale", error_code="quote_stale", quote={"items": {"new": 940}}
        )
        http = AsyncMock()
        http.get.return_value = MOCK_QUOTE
        http.post.side_effect = [stale, MOCK_ACCEPTED]

        result = await AsyncDatasetFeedClient(http, "creator-feed").download()

        assert result["billed_amount"] == "15.0000"
        first, second = http.post.call_args_list
        assert first[1]["headers"] == second[1]["headers"]
        assert second[1]["json"]["expected_items"] == 940

    async def test_update_config_rejects_read_only_fields(self):
        http = AsyncMock()

        with pytest.raises(ValidationError, match="band"):
            await AsyncDatasetFeedClient(http, "creator-feed").update_config(band="micro")

    async def test_batch_get_returns_none_on_404(self):
        http = AsyncMock()
        http.get.side_effect = APIError(message="No batch", status_code=404)

        assert await AsyncDatasetBatchClient(http, "creator-feed", "api-x").get() is None

    async def test_wait_for_ready(self):
        http = AsyncMock()
        http.get.side_effect = [
            {**MOCK_EXPORT_READY, "status": "building", "url": None},
            MOCK_EXPORT_READY,
        ]

        with patch("asyncio.sleep", new=AsyncMock()):
            export = await AsyncDatasetExportClient(
                http, "creator-feed", EXPORT_ID
            ).wait_for_ready()

        assert export["status"] == "ready"

    async def test_download_to(self, tmp_path):
        http = AsyncMock()
        http.get.return_value = MOCK_EXPORT_READY
        target = str(tmp_path / "export.jsonl")

        with patch("gofetch.dataset_export._astream_to", new=AsyncMock()) as stream:
            path = await AsyncDatasetExportClient(
                http, "creator-feed", EXPORT_ID
            ).download_to(target)

        stream.assert_awaited_once_with(MOCK_EXPORT_READY["url"], target)
        assert path == target

    async def test_upload_owned_index(self, tmp_path):
        index = tmp_path / "index.txt"
        index.write_text("nike\n")
        http = AsyncMock()
        http.post.side_effect = _routed(
            {
                "/upload-url/": {"url": "https://s3.example.com/put", "key": "owned-index/o/u/i"},
                "/load/": {"status": "queued"},
            }
        )

        with patch("gofetch.datasets._aput_presigned", new=AsyncMock()) as put:
            result = await AsyncDatasetFeedClient(http, "creator-feed").upload_owned_index(
                str(index)
            )

        put.assert_awaited_once_with("https://s3.example.com/put", b"nike\n")
        assert result["status"] == "queued"


# ---------------------------------------------------------------------------
# Presigned transfers do not carry the API key
# ---------------------------------------------------------------------------


class TestPresignedTransfers:

    def test_put_uses_a_bare_client(self):
        """base_url, X-API-Key and a JSON content type would all break the signature."""
        from gofetch.datasets import _put_presigned

        with patch("gofetch.datasets.httpx.Client") as client_cls:
            client = client_cls.return_value.__enter__.return_value
            client.put.return_value = MagicMock(status_code=200)

            _put_presigned("https://s3.example.com/put", b"data")

        client_cls.assert_called_once_with(timeout=None)
        client.put.assert_called_once_with("https://s3.example.com/put", content=b"data")

    def test_put_failure_becomes_a_gofetch_error(self):
        from gofetch.datasets import _put_presigned

        failure = MagicMock(status_code=403, headers={})
        failure.json.side_effect = ValueError("xml")
        failure.text = "<Error><Code>AccessDenied</Code></Error>"

        with patch("gofetch.datasets.httpx.Client") as client_cls:
            client_cls.return_value.__enter__.return_value.put.return_value = failure

            with pytest.raises(APIError, match="AccessDenied"):
                _put_presigned("https://s3.example.com/put", b"data")

    def test_stream_writes_the_body_to_disk(self, tmp_path):
        from gofetch.dataset_export import _stream_to

        target = tmp_path / "out.jsonl"
        response = MagicMock(status_code=200)
        response.iter_bytes.return_value = [b'{"a": 1}\n', b'{"b": 2}\n']

        with patch("gofetch.dataset_export.httpx.Client") as client_cls:
            client = client_cls.return_value.__enter__.return_value
            client.stream.return_value.__enter__.return_value = response

            _stream_to("https://s3.example.com/get", str(target))

        assert target.read_bytes() == b'{"a": 1}\n{"b": 2}\n'
        client.stream.assert_called_once_with("GET", "https://s3.example.com/get")


# ---------------------------------------------------------------------------
# Batch ownership — a batch belongs to the API key that opened it
# ---------------------------------------------------------------------------

# Copied from the shipped refusal copy, not paraphrased.
BATCH_NOT_YOURS = {
    "detail": "Batch api-x-20260907-1: This batch belongs to a different API key on "
              "your organization. Its rows and its ack belong to the client that "
              "pulled it.",
    "errors": {"code": "batch_not_yours"},
}

PULL_OPEN_BATCH_NOT_YOURS = {
    "status": "unavailable",
    "batch": None,
    "constraints": [{
        "code": "open_batch_not_yours",
        "message": "Another API key on your organization holds this dataset's open "
                   "batch. One batch is open at a time — pull again once that client "
                   "acks it.",
    }],
}


def _forbidden(payload=BATCH_NOT_YOURS):
    """The exception `_handle_error_response` builds for a 403 carrying a code."""
    return APIError(message=payload["detail"], status_code=403,
                    error_code=payload["errors"]["code"])


class TestBatchOwnership:
    """A second key on the same org must be refused, not quietly served.

    The org is never crossed here — both keys belong to it — so the failure this
    guards is a misrouted paid delivery, not a tenancy leak. The SDK's job is to
    surface the refusal as a typed, terminal error and never retry it.
    """

    @pytest.mark.parametrize("call", [
        lambda c: c.rows(),
        lambda c: list(c.iterate_rows()),
        lambda c: c.ack(),
        lambda c: c.export(),
    ])
    def test_a_foreign_batch_is_a_403_naming_the_code(self, call):
        http = MagicMock()
        http.get.side_effect = _forbidden()
        http.post.side_effect = _forbidden()

        with pytest.raises(APIError) as exc_info:
            call(DatasetBatchClient(http, "creator-feed", "api-x-20260907-1"))

        assert exc_info.value.status_code == 403
        assert exc_info.value.error_code == "batch_not_yours"

    def test_batch_not_yours_is_never_retried(self):
        """403 is outside the retry set, so a misroute cannot be papered over."""
        from gofetch.constants import RETRYABLE_STATUS_CODES

        assert 403 not in RETRYABLE_STATUS_CODES

    def test_get_on_a_foreign_batch_raises_rather_than_returning_none(self):
        """Only a 404 means "no such batch". A 403 means it exists and is not yours."""
        http = MagicMock()
        http.get.side_effect = _forbidden()

        with pytest.raises(APIError) as exc_info:
            DatasetBatchClient(http, "creator-feed", "api-x-20260907-1").get()

        assert exc_info.value.error_code == "batch_not_yours"

    def test_a_pull_blocked_by_another_key_is_data_not_an_error(self):
        http = MagicMock()
        http.post.return_value = PULL_OPEN_BATCH_NOT_YOURS

        response = DatasetFeedClient(http, "creator-feed").pull()

        assert response["status"] == "unavailable"
        assert response["batch"] is None
        assert [c["code"] for c in response["constraints"]] == ["open_batch_not_yours"]

    def test_pull_and_iterate_yields_nothing_when_another_key_holds_the_batch(self):
        http = MagicMock()
        http.post.return_value = PULL_OPEN_BATCH_NOT_YOURS

        rows = list(DatasetFeedClient(http, "creator-feed").pull_and_iterate())

        assert rows == []
        http.get.assert_not_called()

    def test_a_download_blocked_by_a_foreign_batch_is_the_existing_409(self):
        http = MagicMock()
        http.get.return_value = MOCK_QUOTE
        http.post.side_effect = DatasetConflictError(
            message="Ack the open batch before buying the rest.",
            error_code="open_batch_blocks_download")

        with pytest.raises(DatasetConflictError) as exc_info:
            DatasetFeedClient(http, "creator-feed").download()

        assert exc_info.value.code == "open_batch_blocks_download"

    def test_a_foreign_export_is_a_404_and_reads_as_absent(self):
        """The export list is scoped too, so a foreign export simply is not there."""
        http = MagicMock()
        http.get.side_effect = APIError(message="No export", status_code=404)

        assert DatasetExportClient(http, "creator-feed", "e-1").get() is None
