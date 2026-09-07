"""Tests for type definitions."""

from __future__ import annotations

import warnings

from gofetch import (
    BatchState,
    DatasetKind,
    ExportStatus,
    JobStatus,
    ListPage,
    PullStatus,
    QuoteKind,
    RunStatus,
    ScraperType,
)
from gofetch.types import (
    ACTOR_URL_MAPPING,
    DatasetBatch,
    DatasetDownloadAccepted,
    DatasetExportRow,
    DatasetListRow,
    DatasetOverview,
    DatasetQuote,
    resolve_actor_url,
)


class TestScraperType:

    def test_instagram_type(self) -> None:
        assert ScraperType.INSTAGRAM == "instagram"
        assert ScraperType.INSTAGRAM_PROFILE == "instagram_profile"
        assert ScraperType.INSTAGRAM_POSTS == "instagram_posts"

    def test_tiktok_type(self) -> None:
        assert ScraperType.TIKTOK == "tiktok"

    def test_youtube_type(self) -> None:
        assert ScraperType.YOUTUBE == "youtube"

    def test_reddit_type(self) -> None:
        assert ScraperType.REDDIT == "reddit"

    def test_google_news_type(self) -> None:
        assert ScraperType.GOOGLE_NEWS == "google_news"

    def test_google_serp_type(self) -> None:
        assert ScraperType.GOOGLE_SERP == "google_serp"

    def test_facebook_types(self) -> None:
        assert ScraperType.FACEBOOK == "facebook"
        assert ScraperType.FACEBOOK_POSTS == "facebook_posts"
        assert ScraperType.FACEBOOK_PROFILE == "facebook_profile"

    def test_comment_types(self) -> None:
        assert ScraperType.INSTAGRAM_COMMENTS == "instagram_comments"
        assert ScraperType.TIKTOK_COMMENTS == "tiktok_comments"

    def test_identity_types(self) -> None:
        assert ScraperType.PROFILE_PROBE == "profile_probe"
        assert ScraperType.TIKTOK_IDENTITY_RESOLVE == "tiktok_identity_resolve"


class TestJobStatus:

    def test_all_statuses(self) -> None:
        assert JobStatus.PENDING == "pending"
        assert JobStatus.RUNNING == "running"
        assert JobStatus.COMPLETED == "completed"
        assert JobStatus.FAILED == "failed"
        assert JobStatus.CANCELLED == "cancelled"

    def test_to_apify_status(self) -> None:
        assert JobStatus.PENDING.to_apify_status() == "READY"
        assert JobStatus.RUNNING.to_apify_status() == "RUNNING"
        assert JobStatus.COMPLETED.to_apify_status() == "SUCCEEDED"
        assert JobStatus.FAILED.to_apify_status() == "FAILED"
        assert JobStatus.CANCELLED.to_apify_status() == "ABORTED"


class TestRunStatus:

    def test_creation(self) -> None:
        status = RunStatus(data={"id": "123"}, is_ready=True)
        assert status.data == {"id": "123"}
        assert status.is_ready is True

    def test_unpacking(self) -> None:
        status = RunStatus(data={"id": "123"}, is_ready=False)
        data, is_ready = status
        assert data == {"id": "123"}
        assert is_ready is False


class TestResolveActorUrl:

    def test_apify_instagram_scraper(self) -> None:
        assert resolve_actor_url("apify/instagram-scraper") == "instagram"

    def test_apify_instagram_profile(self) -> None:
        assert resolve_actor_url("apify/instagram-profile-scraper") == "instagram_profile"

    def test_clockworks_tiktok(self) -> None:
        assert resolve_actor_url("clockworks/tiktok-profile-scraper") == "tiktok"

    def test_streamers_youtube(self) -> None:
        assert resolve_actor_url("streamers/youtube-scraper") == "youtube"

    def test_xmolodtsov_reddit(self) -> None:
        assert resolve_actor_url("xmolodtsov/reddit-scraper") == "reddit"

    def test_xmolodtsov_google_news(self) -> None:
        assert resolve_actor_url("xmolodtsov/google-news-scraper") == "google_news"

    def test_direct_type(self) -> None:
        assert resolve_actor_url("instagram") == "instagram"
        assert resolve_actor_url("instagram_profile") == "instagram_profile"
        assert resolve_actor_url("instagram_posts") == "instagram_posts"
        assert resolve_actor_url("instagram_comments") == "instagram_comments"
        assert resolve_actor_url("tiktok") == "tiktok"
        assert resolve_actor_url("tiktok_comments") == "tiktok_comments"
        assert resolve_actor_url("youtube") == "youtube"
        assert resolve_actor_url("facebook") == "facebook"
        assert resolve_actor_url("facebook_posts") == "facebook_posts"
        assert resolve_actor_url("facebook_profile") == "facebook_profile"
        assert resolve_actor_url("reddit") == "reddit"
        assert resolve_actor_url("google_news") == "google_news"
        assert resolve_actor_url("google_serp") == "google_serp"
        assert resolve_actor_url("profile_probe") == "profile_probe"
        assert resolve_actor_url("tiktok_identity_resolve") == "tiktok_identity_resolve"

    def test_every_scraper_type_resolves_silently(self) -> None:
        # A ScraperType missing from ACTOR_URL_MAPPING still works (the value
        # passes through) but warns on every legitimate call — the 0.3.0 bug
        # for the comment scrapers. Pin the invariant so it can't drift again.
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            for scraper_type in ScraperType:
                assert resolve_actor_url(scraper_type.value) == scraper_type.value

    def test_mapping_targets_are_known_types(self) -> None:
        assert set(ACTOR_URL_MAPPING.values()) == {t.value for t in ScraperType}

    def test_unknown_type(self) -> None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            assert resolve_actor_url("unknown/actor") == "unknown/actor"
        assert len(caught) == 1


class TestListPage:

    def test_is_a_list_and_a_page(self) -> None:
        page = ListPage([{"a": 1}, {"a": 2}], offset=0, limit=None, total=5)
        assert isinstance(page, list)
        assert len(page) == 2
        assert page[0] == {"a": 1}
        assert list(page) == [{"a": 1}, {"a": 2}]
        assert page.items == [{"a": 1}, {"a": 2}]
        assert page.count({"a": 1}) == 1  # list.count() is untouched
        assert page.total == 5
        assert page.offset == 0
        assert page.limit is None
        assert page.desc is False

    def test_total_defaults_to_count(self) -> None:
        page = ListPage([{"a": 1}])
        assert page.total == 1


class TestDatasetTypes:
    """The enums and the documentation models, against real dev payloads."""

    def test_pull_statuses(self) -> None:
        assert PullStatus.OK == "ok"
        assert PullStatus.OPEN_BATCH_EXISTS == "open_batch_exists"
        assert PullStatus.QUOTA_EXHAUSTED == "quota_exhausted"
        assert PullStatus.NOTHING_AVAILABLE == "nothing_available"
        assert PullStatus.UNAVAILABLE == "unavailable"

    def test_other_enums(self) -> None:
        assert BatchState.ACKED == "acked"
        assert ExportStatus.READY == "ready"
        assert DatasetKind.POOL == "pool"
        assert QuoteKind.MOVING == "moving"

    def test_list_row_model(self) -> None:
        from tests.test_datasets import MOCK_LIST_ROW

        row = DatasetListRow(**MOCK_LIST_ROW)
        assert row.slug == "creator-feed"
        assert row.is_active is False
        assert row.price_per_1000 == "15.0000"

    def test_overview_model_is_a_different_shape_from_the_list_row(self) -> None:
        from tests.test_datasets import MOCK_OVERVIEW

        overview = DatasetOverview(**MOCK_OVERVIEW)
        assert overview.max_batch_size == 2500
        assert overview.download is not None
        assert overview.download.balance == "4690.3253"
        assert not hasattr(overview, "kind")

    def test_quote_model(self) -> None:
        from tests.test_datasets import MOCK_QUOTE

        quote = DatasetQuote(**MOCK_QUOTE)
        assert quote.items["new"] == 1000
        assert quote.quote_kind == "moving"

    def test_batch_model(self) -> None:
        from tests.test_datasets import MOCK_ACKED

        batch = DatasetBatch(**MOCK_ACKED["batch"])
        assert batch.billed_rows == 990
        assert batch.billed_amount == "14.8500"

    def test_accepted_and_export_models(self) -> None:
        from tests.test_datasets import MOCK_ACCEPTED, MOCK_EXPORT_READY

        accepted = DatasetDownloadAccepted(**MOCK_ACCEPTED)
        assert accepted.billed_amount == "15.0000"
        export = DatasetExportRow(**MOCK_EXPORT_READY)
        assert export.status == "ready"
        assert export.url is not None

    def test_accepted_export_allows_a_zero_billed_purchase(self) -> None:
        """The upload `nothing_new` path has no batch behind it."""
        accepted = DatasetDownloadAccepted(
            export_id="3f2b7c40-0000-4000-8000-000000000002",
            status="pending",
            format="jsonl",
            batch_id=None,
            billed_items=0,
            billed_amount="0.0000",
            constraints=[{"code": "nothing_new", "message": "Nothing new to buy."}],
        )
        assert accepted.billed_items == 0
        assert accepted.billed_amount == "0.0000"
        assert accepted.batch_id is None

    def test_money_is_typed_str_not_float(self) -> None:
        """A float round-trip is how a sub-cent charge stops matching the ledger."""
        for model, field in (
            (DatasetListRow, "price_per_1000"),
            (DatasetQuote, "amount"),
            (DatasetQuote, "balance"),
            (DatasetBatch, "price_per_1000_at_open"),
            (DatasetDownloadAccepted, "billed_amount"),
        ):
            assert model.model_fields[field].annotation is str, f"{model.__name__}.{field}"
