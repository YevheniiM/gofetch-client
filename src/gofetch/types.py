"""
Type definitions for GoFetch client.

Includes enums, data classes, and Pydantic models for API responses.
"""

from __future__ import annotations

import warnings
from enum import Enum
from typing import TYPE_CHECKING, Any, NamedTuple

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from collections.abc import Iterable


class ScraperType(str, Enum):
    """
    Supported scraper types — the ``scraper_type`` values the GoFetch API accepts.

    Pass the value directly to ``client.actor(...)``. For migrations, these Apify
    actor URLs are also accepted and resolve to the type on the right:
    - apify/instagram-scraper -> INSTAGRAM
    - apify/instagram-profile-scraper -> INSTAGRAM_PROFILE
    - clockworks/tiktok-profile-scraper -> TIKTOK
    - streamers/youtube-scraper -> YOUTUBE
    - apify/facebook-scraper -> FACEBOOK
    - apify/facebook-posts-scraper -> FACEBOOK_POSTS
    - apify/facebook-pages-scraper -> FACEBOOK_PROFILE
    - scraperlink/google-search-results-serp-scraper -> GOOGLE_SERP
    - xmolodtsov/reddit-scraper -> REDDIT
    - xmolodtsov/google-news-scraper -> GOOGLE_NEWS

    INSTAGRAM_COMMENTS, TIKTOK_COMMENTS, PROFILE_PROBE and TIKTOK_IDENTITY_RESOLVE
    are GoFetch-native and have no Apify equivalent.

    REDDIT and GOOGLE_NEWS are kept for import compatibility only: the API does
    not currently accept them for job creation (it answers 400).
    """

    INSTAGRAM = "instagram"
    INSTAGRAM_PROFILE = "instagram_profile"
    INSTAGRAM_POSTS = "instagram_posts"
    INSTAGRAM_COMMENTS = "instagram_comments"
    TIKTOK = "tiktok"
    TIKTOK_COMMENTS = "tiktok_comments"
    TIKTOK_IDENTITY_RESOLVE = "tiktok_identity_resolve"
    YOUTUBE = "youtube"
    FACEBOOK = "facebook"
    FACEBOOK_POSTS = "facebook_posts"
    FACEBOOK_PROFILE = "facebook_profile"
    GOOGLE_SERP = "google_serp"
    PROFILE_PROBE = "profile_probe"
    # Not accepted by the API for job creation right now (400); see docstring.
    REDDIT = "reddit"
    GOOGLE_NEWS = "google_news"


class JobStatus(str, Enum):
    """Job status values from GoFetch API."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"

    def to_apify_status(self) -> str:
        """Convert to Apify-compatible status string."""
        status_map = {
            "pending": "READY",
            "running": "RUNNING",
            "completed": "SUCCEEDED",
            "failed": "FAILED",
            "cancelled": "ABORTED",
            "timed_out": "TIMED-OUT",
        }
        return status_map.get(self.value, "RUNNING")


class RunStatus(NamedTuple):
    """
    Compatible with VWD's RunStatus namedtuple.

    Used for return values from scraper run methods.
    """

    data: dict[str, Any]
    is_ready: bool


class ListPage(list[dict[str, Any]]):
    """
    A page of dataset items, shaped like apify-client's ``ListPage``.

    It is still a plain ``list`` — ``len()``, iteration, indexing and JSON
    serialisation behave exactly as before — but also carries the Apify page
    attributes ``items``, ``offset``, ``limit``, ``total`` and ``desc``, so
    ``dataset.list_items().items`` works when porting code. ``count`` is not
    provided because it would shadow ``list.count()``; use ``len(page)``.
    """

    def __init__(
        self,
        items: Iterable[dict[str, Any]] = (),
        *,
        offset: int = 0,
        limit: int | None = None,
        total: int | None = None,
        desc: bool = False,
    ) -> None:
        super().__init__(items)
        self.offset = offset
        self.limit = limit
        self.total = len(self) if total is None else total
        self.desc = desc

    @property
    def items(self) -> list[dict[str, Any]]:
        return self


# Pydantic models for API response validation


class JobResponse(BaseModel):
    """Response from GET /api/v1/jobs/{id}/"""

    id: str
    status: str
    scraper_type: str
    items_scraped: int = 0
    created_at: str
    updated_at: str
    started_at: str | None = None
    completed_at: str | None = None
    error_message: str | None = None
    output_dataset_url: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


class JobCreateResponse(BaseModel):
    """Response from POST /api/v1/jobs/create/"""

    id: str
    status: str
    items_scraped: int = 0
    created_at: str
    updated_at: str

    model_config = {"extra": "allow"}


class ResultsResponse(BaseModel):
    """Response from GET /api/v1/jobs/{id}/results/"""

    job_id: str
    status: str
    scraper_type: str
    results: list[dict[str, Any]]
    total: int | None = None
    offset: int | None = None
    limit: int | None = None

    model_config = {"extra": "allow"}


class JobLogEntry(BaseModel):
    """Individual log entry from job logs."""

    id: int
    timestamp: str
    level: str
    message: str


class ApifyRunFormat(BaseModel):
    """
    Apify-compatible run format.

    This is what ActorClient.call() and ActorClient.start() return
    to maintain compatibility with code expecting Apify responses.
    """

    id: str
    actId: str  # noqa: N815
    status: str
    defaultDatasetId: str  # noqa: N815
    startedAt: str | None = None  # noqa: N815
    finishedAt: str | None = None  # noqa: N815
    buildId: str | None = None  # noqa: N815
    buildNumber: str | None = None  # noqa: N815
    exitCode: int | None = None  # noqa: N815
    defaultKeyValueStoreId: str | None = None  # noqa: N815
    defaultRequestQueueId: str | None = None  # noqa: N815
    # Original GoFetch data for reference
    _gofetch_job: dict[str, Any] | None = None

    model_config = {"extra": "allow"}


# Actor URL mapping constants

ACTOR_URL_MAPPING: dict[str, str] = {
    # Apify actor URLs -> GoFetch scraper types
    "apify/instagram-scraper": "instagram",
    "apify/instagram-profile-scraper": "instagram_profile",
    "clockworks/tiktok-profile-scraper": "tiktok",
    "streamers/youtube-scraper": "youtube",
    "apify/facebook-scraper": "facebook",
    "apify/facebook-posts-scraper": "facebook_posts",
    "apify/facebook-pages-scraper": "facebook_profile",
    "scraperlink/google-search-results-serp-scraper": "google_serp",
    "xmolodtsov/reddit-scraper": "reddit",
    "xmolodtsov/google-news-scraper": "google_news",
    # Direct mappings (already GoFetch types)
    **{t.value: t.value for t in ScraperType},
    "google-serp": "google_serp",
}


def resolve_actor_url(actor_url: str) -> str:
    """
    Resolve an Apify actor URL to a GoFetch scraper type.

    Args:
        actor_url: Apify-style actor URL or GoFetch scraper type

    Returns:
        GoFetch scraper type string

    Examples:
        >>> resolve_actor_url("apify/instagram-scraper")
        'instagram'
        >>> resolve_actor_url("instagram")
        'instagram'
    """
    result = ACTOR_URL_MAPPING.get(actor_url)
    if result is None:
        warnings.warn(
            f"Unknown actor URL '{actor_url}', passing through as scraper type",
            stacklevel=2,
        )
        return actor_url
    return result
