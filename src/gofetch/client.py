"""
Main GoFetch client.

Provides the primary entry point for interacting with the GoFetch API.
Designed as a drop-in replacement for ApifyClient.
"""

from __future__ import annotations

from typing import NoReturn

from gofetch.actor import ActorClient, AsyncActorClient
from gofetch.constants import DEFAULT_BASE_URL, DEFAULT_TIMEOUT
from gofetch.dataset import AsyncDatasetClient, DatasetClient
from gofetch.http import AsyncHTTPClient, HTTPClient
from gofetch.run import AsyncRunClient, RunClient
from gofetch.types import resolve_actor_url
from gofetch.webhook_client import (
    AsyncWebhookClient,
    AsyncWebhookCollectionClient,
    WebhookClient,
    WebhookCollectionClient,
)


class GoFetchClient:
    """
    GoFetch API client - drop-in replacement for ApifyClient.

    This client provides the same interface as Apify's SDK, allowing
    you to switch from Apify to GoFetch with minimal code changes.

    Usage:
        # Initialize client
        client = GoFetchClient(api_key="sk_scr_myorg_xxxx")

        # Get actor client (same as Apify)
        actor = client.actor("apify/instagram-scraper")  # Apify URL works!
        # Or use GoFetch scraper type directly
        actor = client.actor("instagram")

        # Run synchronously (blocking)
        run = actor.call(run_input={"directUrls": ["https://instagram.com/nike"]})
        print(f"Job completed: {run['id']}")

        # Fetch results
        dataset = client.dataset(run["defaultDatasetId"])
        for item in dataset.iterate_items():
            print(item)

        # Run asynchronously (with webhooks)
        run = actor.start(
            run_input={"directUrls": ["https://instagram.com/nike"]},
            webhooks=[{
                "request_url": "https://myapp.com/webhook",
                "event_types": ["ACTOR.RUN.SUCCEEDED"]
            }]
        )
        print(f"Job started: {run['id']}")

    Attributes:
        base_url: The API base URL
        timeout: Request timeout in seconds
    """

    def __init__(
        self,
        api_key: str | None = None,
        token: str | None = None,  # Alias for api_key (Apify compat)
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = 3,
    ) -> None:
        """
        Initialize the GoFetch client.

        Args:
            api_key: GoFetch API key (format: sk_scr_...)
            token: Alias for api_key (for Apify compatibility)
            base_url: API base URL (default: https://api.go-fetch.io)
            timeout: Request timeout in seconds (default: 30)
            max_retries: Maximum retries for failed requests (default: 3)

        Raises:
            ValueError: If neither api_key nor token is provided
        """
        # Support both api_key and token for Apify compatibility
        self._api_key = api_key or token
        if not self._api_key:
            raise ValueError("Either 'api_key' or 'token' must be provided")

        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries

        self._http = HTTPClient(
            api_key=self._api_key,
            base_url=self._base_url,
            timeout=self._timeout,
            max_retries=self._max_retries,
        )

    @property
    def base_url(self) -> str:
        """Get the API base URL."""
        return self._base_url

    @property
    def timeout(self) -> float:
        """Get the request timeout."""
        return self._timeout

    def actor(self, actor_url: str) -> ActorClient:
        """
        Get an actor client for a specific scraper.

        Args:
            actor_url: Apify-style actor URL or GoFetch scraper type.
                Supported values:
                - "apify/instagram-scraper" -> instagram
                - "apify/instagram-profile-scraper" -> instagram_profile
                - "clockworks/tiktok-profile-scraper" -> tiktok
                - "streamers/youtube-scraper" -> youtube
                - Or direct: "instagram", "tiktok", "youtube"

        Returns:
            ActorClient instance for the specified scraper

        Raises:
            ValueError: If actor_url is empty

        Example:
            # Using Apify URL (for compatibility)
            actor = client.actor("apify/instagram-scraper")

            # Using GoFetch type directly
            actor = client.actor("instagram")
        """
        if not actor_url:
            raise ValueError("actor_id must not be empty")
        scraper_type = resolve_actor_url(actor_url)
        return ActorClient(
            http=self._http,
            scraper_type=scraper_type,
        )

    def dataset(self, dataset_id: str) -> DatasetClient:
        """
        Get a dataset client to fetch results.

        Args:
            dataset_id: Dataset/Job ID. In GoFetch, the job ID serves
                as the dataset ID (they are equivalent).

        Returns:
            DatasetClient instance for fetching results

        Example:
            run = actor.call(run_input={...})
            dataset = client.dataset(run["defaultDatasetId"])
            items = list(dataset.iterate_items())
        """
        return DatasetClient(
            http=self._http,
            job_id=dataset_id,
        )

    def run(self, run_id: str) -> RunClient:
        """Get a run client for a specific job."""
        return RunClient(http=self._http, run_id=run_id)

    def webhook(self, webhook_id: str) -> WebhookClient:
        """Get a webhook client for a specific webhook."""
        return WebhookClient(http=self._http, webhook_id=webhook_id)

    def webhooks(self) -> WebhookCollectionClient:
        """Get webhook collection client for listing/creating webhooks."""
        return WebhookCollectionClient(http=self._http)

    def key_value_store(self, store_id: str) -> NoReturn:
        """Not supported in GoFetch.

        Apify's key-value store has no GoFetch equivalent.
        """
        raise NotImplementedError(
            f"GoFetch does not have a key-value store. "
            f"key_value_store('{store_id}') cannot be used. "
            f"Media uploaded by GoFetch scrapers is accessible via direct URLs "
            f"and does not require manual cleanup."
        )

    def close(self) -> None:
        """Close the client and release resources."""
        self._http.close()

    def __enter__(self) -> GoFetchClient:
        """Context manager entry."""
        return self

    def __exit__(self, *args: object) -> None:
        """Context manager exit."""
        self.close()


class AsyncGoFetchClient:
    """
    Async GoFetch API client.

    Same interface as GoFetchClient but uses async/await.

    Usage:
        async with AsyncGoFetchClient(api_key="...") as client:
            actor = client.actor("instagram")
            run = await actor.call(run_input={...})
            dataset = client.dataset(run["defaultDatasetId"])
            items = await dataset.list_items()
    """

    def __init__(
        self,
        api_key: str | None = None,
        token: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = 3,
    ) -> None:
        """Initialize the async GoFetch client."""
        self._api_key = api_key or token
        if not self._api_key:
            raise ValueError("Either 'api_key' or 'token' must be provided")

        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries

        self._http = AsyncHTTPClient(
            api_key=self._api_key,
            base_url=self._base_url,
            timeout=self._timeout,
            max_retries=self._max_retries,
        )

    @property
    def base_url(self) -> str:
        """Get the API base URL."""
        return self._base_url

    @property
    def timeout(self) -> float:
        """Get the request timeout."""
        return self._timeout

    def actor(self, actor_url: str) -> AsyncActorClient:
        """Get an async actor client for a specific scraper."""
        if not actor_url:
            raise ValueError("actor_id must not be empty")
        scraper_type = resolve_actor_url(actor_url)
        return AsyncActorClient(
            http=self._http,
            scraper_type=scraper_type,
        )

    def dataset(self, dataset_id: str) -> AsyncDatasetClient:
        """Get an async dataset client to fetch results."""
        return AsyncDatasetClient(
            http=self._http,
            job_id=dataset_id,
        )

    def run(self, run_id: str) -> AsyncRunClient:
        """Get an async run client for a specific job."""
        return AsyncRunClient(http=self._http, run_id=run_id)

    def webhook(self, webhook_id: str) -> AsyncWebhookClient:
        """Get an async webhook client for a specific webhook."""
        return AsyncWebhookClient(http=self._http, webhook_id=webhook_id)

    def webhooks(self) -> AsyncWebhookCollectionClient:
        """Get async webhook collection client for listing/creating webhooks."""
        return AsyncWebhookCollectionClient(http=self._http)

    def key_value_store(self, store_id: str) -> NoReturn:
        """Not supported in GoFetch."""
        raise NotImplementedError(
            f"GoFetch does not have a key-value store. "
            f"key_value_store('{store_id}') cannot be used. "
            f"Media uploaded by GoFetch scrapers is accessible via direct URLs "
            f"and does not require manual cleanup."
        )

    async def close(self) -> None:
        """Close the client and release resources."""
        await self._http.close()

    async def __aenter__(self) -> AsyncGoFetchClient:
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: object) -> None:
        """Async context manager exit."""
        await self.close()


# Alias for Apify compatibility
ApifyClient = GoFetchClient
