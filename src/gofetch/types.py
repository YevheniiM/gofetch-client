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


class DatasetKind(str, Enum):
    """How a Datasets-product dataset is supplied."""

    POOL = "pool"
    UPLOAD = "upload"


class PullStatus(str, Enum):
    """The discriminator on a ``POST /datasets/{slug}/pull/`` response.

    Only ``OK`` and ``OPEN_BATCH_EXISTS`` come with a batch. The other three are
    data, not errors: the source refused, the daily quota is spent, or there is
    nothing undelivered left.
    """

    OK = "ok"
    OPEN_BATCH_EXISTS = "open_batch_exists"
    UNAVAILABLE = "unavailable"
    QUOTA_EXHAUSTED = "quota_exhausted"
    NOTHING_AVAILABLE = "nothing_available"


class BatchState(str, Enum):
    """A batch's lifecycle. ``EXPIRED`` means the rows went back to the pool and
    nothing was billed."""

    OPEN = "open"
    ACKED = "acked"
    EXPIRED = "expired"


class ExportStatus(str, Enum):
    """An export build's state. ``FAILED`` and ``EXPIRED`` are rebuilt for free
    by ``retry()``."""

    PENDING = "pending"
    BUILDING = "building"
    READY = "ready"
    FAILED = "failed"
    EXPIRED = "expired"


class QuoteKind(str, Enum):
    """Whether the inventory behind a quote moves. Copy only — never a billing
    input: both kinds treat ``expected_items`` as a ceiling."""

    FIXED = "fixed"
    MOVING = "moving"


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


# Datasets product. Money is `str` on every one of these on purpose: the values
# are quantized decimal strings that the caller reconciles against the credit
# ledger, and a float round-trip is exactly how a sub-cent charge stops matching
# ("15.00" and "15.0000" compared unequal for the same number once already).
# This is deliberately the opposite call from `usageTotalUsd`, which is floated.


class DatasetListRow(BaseModel):
    """One row of ``GET /api/v1/datasets/``.

    A different shape from :class:`DatasetOverview` — the list is not a subset
    of the detail. A paused dataset is listed with ``is_active: false``.
    """

    slug: str
    name: str
    description: str = ""
    kind: str
    price_per_1000: str
    is_active: bool
    updated_at: str
    items: dict[str, int] = Field(default_factory=dict)
    open_batch_id: str | None = None
    degraded: list[dict[str, Any]] = Field(default_factory=list)

    model_config = {"extra": "allow"}


class DatasetQuote(BaseModel):
    """``GET /api/v1/datasets/{slug}/download/``, and the ``download`` block of
    :class:`DatasetOverview`.

    ``blocked`` is a ``{"code", "message"}`` refusal, or None. It is a *quote*,
    not a purchase: reading it bills nothing.
    """

    items: dict[str, int] = Field(default_factory=dict)
    price_per_1000: str
    amount: str
    balance: str
    affordable: bool
    formats: list[str] = Field(default_factory=list)
    blocked: dict[str, Any] | None = None
    quote_kind: str
    resuming: bool = False

    model_config = {"extra": "allow"}


class DatasetOverview(BaseModel):
    """``GET /api/v1/datasets/{slug}/`` and the response to a config PATCH.

    Fetching this settles a batch that is due, so it can move money — it is not
    a free status poll.
    """

    slug: str
    name: str
    config: dict[str, Any] = Field(default_factory=dict)
    price_per_1000: str
    max_daily_quota: int
    max_batch_size: int
    pool: dict[str, Any] = Field(default_factory=dict)
    delivered: dict[str, int] = Field(default_factory=dict)
    open_batch: dict[str, Any] | None = None
    owned_index: dict[str, Any] = Field(default_factory=dict)
    download: DatasetQuote | None = None
    degraded: list[dict[str, Any]] = Field(default_factory=list)

    model_config = {"extra": "allow"}


class DatasetBatch(BaseModel):
    """A pulled batch. ``batch_id`` is a prefixed string (``api-…``/``dl-…``),
    not a UUID — unlike an export id.

    Bill from ``billed_rows``, never from ``row_count``: an ack can settle fewer
    rows than the batch advertises and says why in ``constraints``.
    """

    batch_id: str
    state: str
    row_count: int
    billed_rows: int | None = None
    billed_amount: str | None = None
    price_per_1000_at_open: str
    expires_at: str | None = None
    created_at: str
    acked_at: str | None = None
    expired_at: str | None = None

    model_config = {"extra": "allow"}


class DatasetDownloadAccepted(BaseModel):
    """The 202 receipt from a download or a batch re-export.

    ``billed_items`` and ``billed_amount`` come from the *batch*, not the
    export, and are 0/"0.0000" when there is no batch behind it.
    """

    export_id: str
    status: str
    format: str
    batch_id: str | None = None
    billed_items: int = 0
    billed_amount: str
    constraints: list[dict[str, Any]] = Field(default_factory=list)

    model_config = {"extra": "allow"}


class DatasetExportRow(BaseModel):
    """One export. ``url`` is present only on the detail route — a presigned GET
    minted per request, ``None`` unless ``status`` is ``ready``.

    ``expires_at`` is authoritative over ``status``: nothing marks an aged
    export expired, so a stale ``ready`` one presigns a dead key.
    """

    id: str
    status: str
    format: str
    item_count: int | None = None
    byte_size: int | None = None
    created_at: str
    ready_at: str | None = None
    expires_at: str | None = None
    error: str = ""
    url: str | None = None

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
