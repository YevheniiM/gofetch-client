"""
Type definitions for GoFetch client.

Includes enums, data classes, and Pydantic models for API responses.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, NamedTuple

from pydantic import BaseModel, Field


class ScraperType(str, Enum):
    """
    Supported scraper types.

    These map to Apify actor URLs for compatibility:
    - INSTAGRAM -> apify/instagram-scraper
    - INSTAGRAM_PROFILE -> apify/instagram-profile-scraper
    - TIKTOK -> clockworks/tiktok-profile-scraper
    - YOUTUBE -> streamers/youtube-scraper
    """

    INSTAGRAM = "instagram"
    INSTAGRAM_PROFILE = "instagram_profile"
    INSTAGRAM_POSTS = "instagram_posts"
    TIKTOK = "tiktok"
    YOUTUBE = "youtube"


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
    # Direct mappings (already GoFetch types)
    "instagram": "instagram",
    "instagram_profile": "instagram_profile",
    "instagram_posts": "instagram_posts",
    "tiktok": "tiktok",
    "youtube": "youtube",
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
    return ACTOR_URL_MAPPING.get(actor_url, actor_url)
