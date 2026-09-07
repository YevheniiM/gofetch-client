"""E2E for the Datasets product against a real environment.

The delivery loop is one stateful conversation with the server — a pull opens a
batch, the ack bills it, a download buys what is left — so these run in file
order and share `STATE`. Running one alone will skip or fail on purpose.

Money is checked the only way that proves anything: the org's credit balance is
read before and after every step that could charge, and the deltas are asserted
against what the receipt claimed.

    source .env.dev && pytest tests/e2e/test_datasets_e2e.py -v --log-cli-level=INFO

`E2E_DATASET_SLUG` picks the dataset (default `creator-feed`). The dataset must
be active and have sellable rows; a paused one is a legitimate state that these
tests report rather than work around.

The run BUYS: one batch-sized pull and then everything the pool has left, so
re-running it against the same dataset needs the supply topped up first.
"""

from __future__ import annotations

import logging
import os
import tempfile
import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pytest

from gofetch.exceptions import APIError, DatasetConflictError

if TYPE_CHECKING:
    from gofetch import GoFetchClient

logger = logging.getLogger("e2e.datasets")

pytestmark = [pytest.mark.e2e, pytest.mark.datasets]

SLUG = os.environ.get("E2E_DATASET_SLUG", "creator-feed")

STATE: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _feed(client: GoFetchClient):
    return client.datasets().feed(SLUG)


def _balance(client: GoFetchClient) -> Decimal:
    """The org's credit balance, read off the free quote.

    `Decimal` and never `float`: the contract keeps money as quantized strings
    precisely so a sub-cent charge still reconciles (P0 §5).
    """
    return Decimal(_feed(client).quote()["balance"])


# httpx logs the full URL of every request it makes, and two of them here are
# presigned S3 links. Redacting only our own payloads would leave the credential
# in the run log anyway, so the filter sits on httpx's logger.
_SIGNED = ("AWSAccessKeyId", "X-Amz-Signature", "X-Amz-Credential", "x-amz-security-token")


class _StripSignedQuery(logging.Filter):
    """httpx passes an ``httpx.URL``, not a ``str`` — match on ``str(arg)``."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.args:
            record.args = tuple(_strip(a) for a in record.args)
        return True


def _strip(arg: object) -> object:
    text = str(arg)
    if not any(s in text for s in _SIGNED):
        return arg
    return text.split("?")[0] + "?<presigned>"


@pytest.fixture(scope="module", autouse=True)
def _redact_httpx_urls():
    log_filter = _StripSignedQuery()
    logging.getLogger("httpx").addFilter(log_filter)
    yield
    logging.getLogger("httpx").removeFilter(log_filter)


def _redacted(payload: Any) -> Any:
    """Payloads minus the presigned URL.

    A presigned link carries an access key id, a signature and a session token.
    It is short-lived, but a run log is not, so it never goes to the logger.
    """
    if isinstance(payload, dict) and payload.get("url"):
        return {**payload, "url": "<presigned>"}
    return payload


def _log(label: str, payload: Any) -> None:
    logger.info("%s: %s", label, _redacted(payload))


def _need(key: str) -> Any:
    if key not in STATE:
        pytest.skip(f"earlier step did not produce {key}")
    return STATE[key]


# ---------------------------------------------------------------------------
# 1. Read surface
# ---------------------------------------------------------------------------

def test_list_and_get(client: GoFetchClient) -> None:
    page = client.datasets().list()
    _log("datasets().list()", {"total": page.total, "items": page.items})
    row = next((r for r in page.items if r["slug"] == SLUG), None)
    assert row is not None, f"{SLUG} not visible to this API key"
    # The list and the detail are two different shapes (P0 §3) — the list row
    # carries `items`/`open_batch_id`, the detail carries `config`/`pool`.
    assert {"slug", "name", "kind", "price_per_1000", "is_active"} <= set(row)

    detail = _feed(client).get()
    _log("feed.get()", detail)
    assert detail["slug"] == SLUG and "name" in detail
    assert {"config", "pool", "delivered", "owned_index", "download"} <= set(detail)
    assert isinstance(detail["price_per_1000"], str), "money must stay a string"

    STATE["detail"] = detail
    STATE["kind"] = row["kind"]
    if not detail["config"]["is_active"]:
        pytest.skip(f"{SLUG} is paused — activate it before running the money path")


def test_quote_is_free_and_priced(client: GoFetchClient) -> None:
    before = _balance(client)
    quote = _feed(client).quote()
    _log("feed.quote()", quote)
    assert quote["items"]["new"] >= 0
    for key in ("price_per_1000", "amount", "balance"):
        assert isinstance(quote[key], str), f"{key} must stay a string"
    assert _balance(client) == before, "quoting must not move money"
    STATE["quote"] = quote


# ---------------------------------------------------------------------------
# 2. Pull -> rows -> ack, and the ledger
# ---------------------------------------------------------------------------

def test_pull_opens_a_batch(client: GoFetchClient) -> None:
    _need("quote")
    STATE["balance_before_pull"] = _balance(client)
    response = _feed(client).pull()
    _log("feed.pull()", response)
    if response["status"] not in ("ok", "open_batch_exists"):
        pytest.skip(f"pull has no batch to give: {response['status']} "
                    f"{response.get('constraints')}")
    batch = response["batch"]
    assert batch["row_count"] > 0
    assert isinstance(batch["price_per_1000_at_open"], str)
    STATE["batch_id"] = batch["batch_id"]
    STATE["batch"] = batch


def test_pull_is_idempotent_while_the_batch_is_open(client: GoFetchClient) -> None:
    batch_id = _need("batch_id")
    again = _feed(client).pull()
    _log("feed.pull() re-pull", again)
    assert again["status"] == "open_batch_exists"
    assert again["batch"]["batch_id"] == batch_id
    # Re-served, not topped up: the row count must not have grown.
    assert again["batch"]["row_count"] == STATE["batch"]["row_count"]


def test_rows_are_readable_and_paginate(client: GoFetchClient) -> None:
    batch_id = _need("batch_id")
    batch = _feed(client).batch(batch_id)
    page = batch.rows(limit=2)
    _log("batch.rows(limit=2)", {"total": page.total, "on_page": len(page),
                                 "first": page.items[:1]})
    assert page.total == STATE["batch"]["row_count"]
    rows = list(batch.iterate_rows())
    assert len(rows) == page.total
    STATE["rows"] = rows


def test_ack_settles_and_bills(client: GoFetchClient) -> None:
    batch_id = _need("batch_id")
    _need("rows")
    before = _balance(client)
    envelope = _feed(client).batch(batch_id).ack()
    _log("batch.ack()", envelope)
    after = _balance(client)

    # The ack answers with pull's envelope, not a bare batch.
    ack = envelope["batch"]
    assert ack["state"] == "acked"
    assert isinstance(ack["billed_amount"], str)
    charged = before - after
    assert charged == Decimal(ack["billed_amount"]), (
        f"balance moved {charged} but the receipt says {ack['billed_amount']}")
    expected = (Decimal(STATE["batch"]["price_per_1000_at_open"])
                * Decimal(ack["billed_rows"]) / Decimal(1000))
    assert charged == expected, f"charged {charged}, price x rows says {expected}"
    STATE["ack"] = ack
    STATE["balance_after_ack"] = after
    logger.info("LEDGER pull->ack: balance %s -> %s (-%s) for %s rows on batch %s",
                before, after, charged, ack["billed_rows"], batch_id)


def test_ack_is_idempotent(client: GoFetchClient) -> None:
    batch_id = _need("batch_id")
    before = _balance(client)
    again = _feed(client).batch(batch_id).ack()
    _log("batch.ack() replay", again)
    assert again["batch"]["state"] == "acked"
    assert _balance(client) == before, "a second ack must not bill again"


# ---------------------------------------------------------------------------
# 3. Export of the acked batch
# ---------------------------------------------------------------------------

def test_batch_export_builds_a_file(client: GoFetchClient) -> None:
    batch_id = _need("batch_id")
    _need("ack")
    before = _balance(client)
    export = _feed(client).batch(batch_id).export()
    _log("batch.export()", export)
    assert export.get("export_id")
    ready = _feed(client).export(export["export_id"]).wait_for_ready(wait_secs=180)
    _log("export.wait_for_ready()", ready)
    assert ready and ready["status"] == "ready", f"export never became ready: {ready}"
    assert _balance(client) == before, "re-exporting what was bought must be free"

    with tempfile.TemporaryDirectory() as d:
        path = _feed(client).export(export["export_id"]).download_to(
            os.path.join(d, "batch.jsonl"))
        size = os.path.getsize(path)
        logger.info("export file %s bytes", size)
        assert size > 0
    STATE["batch_export_id"] = export["export_id"]


# ---------------------------------------------------------------------------
# 4. Download — the money path, and its idempotency
# ---------------------------------------------------------------------------

def test_config_sizes_the_purchase(client: GoFetchClient) -> None:
    """A download buys min(batch_size, quota left, available) — not the pool.

    Proven by moving the one knob that bounds it and re-reading the free quote.
    """
    _need("ack")
    feed = _feed(client)
    before = feed.get()["config"]
    STATE["config_before"] = before
    # update_config answers with the whole overview, not a config object.
    # The quota is widened too so that `batch_size` is the constraint the next
    # assertion is actually measuring.
    detail = feed.update_config(batch_size=20, daily_quota=10000)
    _log("feed.update_config(batch_size=20, daily_quota=10000)", detail["config"])
    assert detail["config"] == before | {"batch_size": 20, "daily_quota": 10000}

    quote = feed.quote()
    _log("feed.quote() after widening", quote)
    detail = feed.get()
    ceiling = min(detail["config"]["batch_size"],
                  detail["delivered"]["quota_remaining"],
                  detail["pool"]["available"])
    assert quote["items"]["new"] == ceiling, (
        f"quote offers {quote['items']['new']}, but min(batch_size, quota, pool) "
        f"is {ceiling}")


def test_download_buys_a_batch(client: GoFetchClient) -> None:
    _need("ack")
    feed = _feed(client)
    quote = feed.quote()
    if quote["items"]["new"] == 0:
        pytest.skip("nothing new to buy — the pool is empty after the pull")
    key = uuid.uuid4().hex
    ceiling = quote["items"]["new"]
    before = _balance(client)
    receipt = feed.download(expected_items=ceiling, idempotency_key=key)
    _log("feed.download()", receipt)
    after = _balance(client)

    assert receipt["status"] in ("queued", "pending", "building", "ready")
    assert isinstance(receipt["billed_amount"], str)
    charged = before - after
    assert charged == Decimal(receipt["billed_amount"]), (
        f"balance moved {charged}, receipt says {receipt['billed_amount']}")
    assert receipt["billed_items"] == ceiling, (
        f"asked for {ceiling}, bought {receipt['billed_items']}")
    logger.info("LEDGER download: balance %s -> %s (-%s) for %s items, export %s",
                before, after, charged, receipt["billed_items"], receipt["export_id"])
    STATE.update(dl_key=key, dl_ceiling=ceiling, dl_receipt=receipt,
                 balance_after_download=after)


def test_download_replay_returns_the_receipt_and_bills_nothing(
        client: GoFetchClient) -> None:
    key, ceiling = _need("dl_key"), _need("dl_ceiling")
    first = _need("dl_receipt")
    before = _balance(client)
    # Both halves of the fingerprint, which is the only honest replay: the key
    # alone re-quotes a ceiling of 0 and reads as a different purchase.
    replay = _feed(client).download(expected_items=ceiling, idempotency_key=key)
    _log("feed.download() replay", replay)
    assert replay["export_id"] == first["export_id"], "replay must return the receipt"
    assert replay["billed_amount"] == first["billed_amount"]
    assert _balance(client) == before, "a replay must not charge again"


def test_download_same_key_different_ceiling_is_refused(client: GoFetchClient) -> None:
    key = _need("dl_key")
    ceiling = _need("dl_ceiling")
    before = _balance(client)
    with pytest.raises(APIError) as excinfo:
        _feed(client).download(expected_items=ceiling + 1, idempotency_key=key)
    err = excinfo.value
    _log("feed.download() same key, different ceiling",
         {"status": err.status_code, "code": err.error_code, "message": err.message})
    assert err.status_code == 400
    assert err.error_code == "idempotency_key_reused"
    assert _balance(client) == before, "a refusal must not charge"


def test_unsupported_format_names_the_supported_ones(client: GoFetchClient) -> None:
    with pytest.raises(APIError) as excinfo:
        _feed(client).download(expected_items=0, format="xml",
                               idempotency_key=uuid.uuid4().hex)
    err = excinfo.value
    _log("unsupported format",
         {"status": err.status_code, "code": err.error_code, "details": err.details})
    assert err.error_code == "unsupported_format"
    # P0 §4: the accepted values are a top-level sibling, not `errors.<field>`.
    assert err.details.get("supported_formats")


def test_download_drains_then_refuses_pool_empty(client: GoFetchClient) -> None:
    """Keep buying — one fresh key per purchase — until there is nothing left.

    The last call is the one that matters. A drained pool does NOT answer with
    a free zero-item receipt; it refuses ``409 pool_empty`` and bills nothing,
    so a drain loop has to be driven off the quote.
    """
    _need("dl_receipt")
    feed = _feed(client)
    detail = feed.get()
    budget = 12
    if detail["pool"]["available"] > budget * detail["config"]["batch_size"]:
        pytest.skip(f"pool holds {detail['pool']['available']} rows — draining it "
                    f"would cost more than this check is worth; raise batch_size "
                    f"or run against a smaller dataset")
    for _ in range(budget):
        if feed.quote()["items"]["new"] == 0:
            break
        _log("feed.download() draining", feed.download(idempotency_key=uuid.uuid4().hex))
    else:
        pytest.fail(f"pool did not drain in {budget} downloads")

    before = _balance(client)
    with pytest.raises(DatasetConflictError) as excinfo:
        feed.download(idempotency_key=uuid.uuid4().hex)
    err = excinfo.value
    _log("feed.download() with nothing left",
         {"status": err.status_code, "code": err.code, "quote": err.quote})
    assert err.code in ("pool_empty", "quota_exhausted", "nothing_available")
    assert err.quote is not None, "a come-back-later refusal must carry the quote"
    assert _balance(client) == before, "a refusal must not charge"


def test_download_export_becomes_ready(client: GoFetchClient) -> None:
    receipt = _need("dl_receipt")
    export = _feed(client).export(receipt["export_id"]).wait_for_ready(wait_secs=300)
    _log("download export.wait_for_ready()", export)
    assert export and export["status"] == "ready"
    with tempfile.TemporaryDirectory() as d:
        path = _feed(client).export(receipt["export_id"]).download_to(
            os.path.join(d, "download.jsonl"))
        logger.info("download export file %s bytes", os.path.getsize(path))
        assert os.path.getsize(path) > 0


# ---------------------------------------------------------------------------
# 5. Refusals the SDK must survive
# ---------------------------------------------------------------------------

def test_unknown_slug_is_a_404_that_names_no_reason(client: GoFetchClient) -> None:
    with pytest.raises(APIError) as excinfo:
        client.datasets().feed(f"no-such-dataset-{uuid.uuid4().hex[:8]}").get()
    err = excinfo.value
    _log("unknown slug", {"status": err.status_code, "message": err.message})
    assert err.status_code == 404
    assert "paused" not in err.message.lower()


def test_batches_and_exports_list(client: GoFetchClient) -> None:
    feed = _feed(client)
    batches = feed.batches(limit=5)
    _log("feed.batches()", {"total": batches.total, "items": batches.items[:2]})
    assert batches.total >= 1
    exports = feed.exports(limit=5)
    _log("feed.exports()", {"total": exports.total, "items": exports.items[:2]})
    assert exports.total >= 1
    # P0 §3: only the detail route mints a presigned link.
    assert all("url" not in row for row in exports.items)


def test_owned_index_upload_url_is_a_presigned_put(client: GoFetchClient) -> None:
    upload = _feed(client).owned_index_upload_url(filename="index_handles.txt")
    _log("owned_index_upload_url()", upload)
    assert upload["method"] == "PUT"
    assert upload["key"].endswith("index_handles.txt")
    assert upload["url"].startswith("https://")


def test_owned_index_load_rejects_a_key_it_did_not_issue(client: GoFetchClient) -> None:
    with pytest.raises(APIError) as excinfo:
        _feed(client).owned_index_load("owned-index/../../etc/passwd")
    err = excinfo.value
    _log("owned_index_load() foreign key",
         {"status": err.status_code, "message": err.message})
    assert err.status_code == 400
