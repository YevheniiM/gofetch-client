"""Tests for GoFetchClient."""

from __future__ import annotations

import pytest

from gofetch import ApifyClient, GoFetchClient
from gofetch.actor import ActorClient
from gofetch.dataset import DatasetClient


class TestGoFetchClient:

    def test_init_with_api_key(self) -> None:
        client = GoFetchClient(api_key="sk_scr_test_xxx")
        assert client._api_key == "sk_scr_test_xxx"
        client.close()

    def test_init_with_token(self) -> None:
        client = GoFetchClient(token="sk_scr_test_xxx")
        assert client._api_key == "sk_scr_test_xxx"
        client.close()

    def test_init_requires_api_key(self) -> None:
        with pytest.raises(ValueError, match="api_key.*token"):
            GoFetchClient()

    def test_apify_client_alias(self) -> None:
        assert ApifyClient is GoFetchClient

    def test_actor_method_returns_actor_client(self) -> None:
        client = GoFetchClient(api_key="test")
        actor = client.actor("instagram")
        assert isinstance(actor, ActorClient)
        client.close()

    def test_actor_resolves_apify_urls(self) -> None:
        client = GoFetchClient(api_key="test")
        actor = client.actor("apify/instagram-scraper")
        assert actor._scraper_type == "instagram"
        actor = client.actor("clockworks/tiktok-profile-scraper")
        assert actor._scraper_type == "tiktok"
        actor = client.actor("streamers/youtube-scraper")
        assert actor._scraper_type == "youtube"
        actor = client.actor("xmolodtsov/reddit-scraper")
        assert actor._scraper_type == "reddit"
        actor = client.actor("xmolodtsov/google-news-scraper")
        assert actor._scraper_type == "google_news"
        actor = client.actor("apify/facebook-scraper")
        assert actor._scraper_type == "facebook"
        actor = client.actor("apify/facebook-posts-scraper")
        assert actor._scraper_type == "facebook_posts"
        actor = client.actor("apify/facebook-pages-scraper")
        assert actor._scraper_type == "facebook_profile"
        actor = client.actor("scraperlink/google-search-results-serp-scraper")
        assert actor._scraper_type == "google_serp"
        client.close()

    def test_actor_accepts_direct_types(self) -> None:
        client = GoFetchClient(api_key="test")
        for scraper_type in (
            "instagram", "instagram_profile", "instagram_posts", "instagram_comments",
            "tiktok", "tiktok_comments", "tiktok_identity_resolve", "youtube",
            "facebook", "facebook_posts", "facebook_profile",
            "google_serp", "profile_probe", "reddit", "google_news",
        ):
            assert client.actor(scraper_type)._scraper_type == scraper_type
        client.close()

    def test_dataset_method_returns_dataset_client(self) -> None:
        client = GoFetchClient(api_key="test")
        dataset = client.dataset("job123")
        assert isinstance(dataset, DatasetClient)
        client.close()

    def test_context_manager(self) -> None:
        with GoFetchClient(api_key="test") as client:
            assert client._api_key == "test"

    def test_custom_base_url(self) -> None:
        client = GoFetchClient(api_key="test", base_url="https://custom.api.com/")
        assert client.base_url == "https://custom.api.com"
        client.close()

    def test_custom_timeout(self) -> None:
        client = GoFetchClient(api_key="test", timeout=60.0)
        assert client.timeout == 60.0
        client.close()
