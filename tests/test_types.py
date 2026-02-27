"""Tests for type definitions."""

from __future__ import annotations

from gofetch import JobStatus, RunStatus, ScraperType
from gofetch.types import resolve_actor_url


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
        assert resolve_actor_url("tiktok") == "tiktok"
        assert resolve_actor_url("youtube") == "youtube"
        assert resolve_actor_url("reddit") == "reddit"
        assert resolve_actor_url("google_news") == "google_news"

    def test_unknown_type(self) -> None:
        assert resolve_actor_url("unknown/actor") == "unknown/actor"
