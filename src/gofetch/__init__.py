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
    AuthenticationError,
    BatchExpiredError,
    DatasetConflictError,
    GoFetchError,
    InsufficientCreditsError,
    JobError,
    RateLimitError,
    TimeoutError,
    ValidationError,
)
from gofetch.log import AsyncLogClient, LogClient
from gofetch.run import AsyncRunClient, RunClient
from gofetch.types import (
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

__version__ = "0.7.0"

__all__ = [
    "APIError",
    "ActorClient",
    "ApifyClient",
    "AsyncActorClient",
    "AsyncDatasetBatchClient",
    "AsyncDatasetClient",
    "AsyncDatasetCollectionClient",
    "AsyncDatasetExportClient",
    "AsyncDatasetFeedClient",
    "AsyncGoFetchClient",
    "AsyncLogClient",
    "AsyncRunClient",
    "AsyncWebhookClient",
    "AsyncWebhookCollectionClient",
    "AuthenticationError",
    "BatchExpiredError",
    "BatchState",
    "DatasetBatchClient",
    "DatasetClient",
    "DatasetCollectionClient",
    "DatasetConflictError",
    "DatasetExportClient",
    "DatasetFeedClient",
    "DatasetKind",
    "ExportStatus",
    "GoFetchClient",
    "GoFetchError",
    "InsufficientCreditsError",
    "JobError",
    "JobStatus",
    "ListPage",
    "LogClient",
    "PullStatus",
    "QuoteKind",
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
