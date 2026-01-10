"""
Constants used throughout the GoFetch client.
"""

from __future__ import annotations

# API Configuration
DEFAULT_BASE_URL = "https://api.go-fetch.io"
DEFAULT_TIMEOUT = 30.0  # seconds
DEFAULT_POLL_INTERVAL = 2.0  # seconds
MAX_POLL_INTERVAL = 30.0  # seconds
POLL_BACKOFF_FACTOR = 1.5

# Pagination
DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 1000

# Retry configuration
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 1.0  # seconds
RETRY_BACKOFF_FACTOR = 2.0
RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}

# API Headers
API_KEY_HEADER = "X-API-Key"
WEBHOOK_SIGNATURE_HEADER = "X-Webhook-Signature"

# Webhook event types (matching Apify format)
WEBHOOK_EVENT_SUCCEEDED = "ACTOR.RUN.SUCCEEDED"
WEBHOOK_EVENT_FAILED = "ACTOR.RUN.FAILED"
WEBHOOK_EVENT_TIMED_OUT = "ACTOR.RUN.TIMED_OUT"

# GoFetch native event types
GOFETCH_EVENT_COMPLETED = "job.completed"
GOFETCH_EVENT_FAILED = "job.failed"
GOFETCH_EVENT_PROGRESS = "job.progress"
GOFETCH_EVENT_STARTED = "job.started"
GOFETCH_EVENT_CREATED = "job.created"

# Status mappings
GOFETCH_TO_APIFY_STATUS = {
    "pending": "READY",
    "running": "RUNNING",
    "completed": "SUCCEEDED",
    "failed": "FAILED",
    "cancelled": "ABORTED",
}

APIFY_TO_GOFETCH_STATUS = {v: k for k, v in GOFETCH_TO_APIFY_STATUS.items()}

# Scraper type mappings (Apify actor URL -> GoFetch type)
ACTOR_URL_TO_SCRAPER_TYPE = {
    "apify/instagram-scraper": "instagram",
    "apify/instagram-profile-scraper": "instagram_profile",
    "clockworks/tiktok-profile-scraper": "tiktok",
    "streamers/youtube-scraper": "youtube",
}

# Ignored errors per platform (items with these errors are not raised as exceptions)
INSTAGRAM_IGNORED_ERRORS = [
    "not_found",
    "no_items",
    "Page not found",
    "Restricted profile",
    "restricted_page",
]

TIKTOK_IGNORED_ERRORS = [
    "This profile/hashtag does not exist.",
]

TIKTOK_IGNORED_NOTES = [
    "No videos found to match the date filter",
    "Profile has no videos",
    "Profile has no videos (or is behind a login wall)",
    "Profile is private",
    "No videos found to match the filter",
]

YOUTUBE_IGNORED_ERRORS = [
    "NO_VIDEOS",
    "VIDEO_UNAVAILABLE",
    "CHANNEL_HAS_NO_LIVE_VIDEOS",
    "DATE_FILTER_TOO_STRICT",
    "CHANNEL_HAS_NO_SHORTS",
    "CHANNEL_DOES_NOT_EXIST",
]

YOUTUBE_IGNORED_NOTES = [
    "The channel has no live videos.",
    "The channel has no shorts.",
    "The channel has no streams.",
    "No videos found on the page.",
    "No videos were collected due to date filtering.",
    "Channel does not exist",
    "Channel is empty",
    "This video is not available",
    "No results were collected during scrape - make sure video limits are set above 0",
]
