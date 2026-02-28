"""
GoFetch Python Client - Social Media Scraping API

A drop-in replacement for apify-client that uses the GoFetch.io API.

Usage:
    from gofetch import GoFetchClient

    client = GoFetchClient(api_key="sk_scr_...")

    # Sync execution (blocks until complete)
    actor = client.actor("instagram")
    run = actor.call(run_input={"directUrls": ["https://instagram.com/nike"]})

    # Fetch results
    dataset = client.dataset(run["defaultDatasetId"])
    items = list(dataset.iterate_items())

    # Async execution (returns immediately, uses webhooks)
    run = actor.start(
        run_input={"directUrls": ["https://instagram.com/nike"]},
        webhooks=[{"request_url": "https://...", "event_types": ["ACTOR.RUN.SUCCEEDED"]}]
    )
"""

from gofetch.actor import ActorClient, AsyncActorClient
from gofetch.client import AsyncGoFetchClient, GoFetchClient
from gofetch.dataset import AsyncDatasetClient, DatasetClient
from gofetch.exceptions import (
    APIError,
    AuthenticationError,
    GoFetchError,
    JobError,
    RateLimitError,
    TimeoutError,
    ValidationError,
)
from gofetch.log import AsyncLogClient, LogClient
from gofetch.run import AsyncRunClient, RunClient
from gofetch.types import (
    JobStatus,
    RunStatus,
    ScraperType,
)
from gofetch.webhook import (
    WebhookEventType,
    generate_webhook_config,
    transform_webhook_payload,
    verify_webhook_signature,
)
from gofetch.webhook_client import (
    AsyncWebhookClient,
    AsyncWebhookCollectionClient,
    WebhookClient,
    WebhookCollectionClient,
)

# Apify compatibility alias
ApifyClient = GoFetchClient

__version__ = "0.2.0"

__all__ = [
    "APIError",
    "ActorClient",
    "ApifyClient",
    "AsyncActorClient",
    "AsyncDatasetClient",
    "AsyncGoFetchClient",
    "AsyncLogClient",
    "AsyncRunClient",
    "AsyncWebhookClient",
    "AsyncWebhookCollectionClient",
    "AuthenticationError",
    "DatasetClient",
    "GoFetchClient",
    "GoFetchError",
    "JobError",
    "JobStatus",
    "LogClient",
    "RateLimitError",
    "RunClient",
    "RunStatus",
    "ScraperType",
    "TimeoutError",
    "ValidationError",
    "WebhookClient",
    "WebhookCollectionClient",
    "WebhookEventType",
    "__version__",
    "generate_webhook_config",
    "transform_webhook_payload",
    "verify_webhook_signature",
]
