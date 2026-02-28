"""
E2E regression test configuration.

Defines platforms, test targets, parameter matrices, result tiers,
and validation rules for end-to-end testing against the real GoFetch API.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Result-count tiers (min → max)
# ---------------------------------------------------------------------------
RESULT_TIERS: list[int] = [10, 25, 50, 100, 250, 500, 1000, 2000, 3000]

QUICK_TIERS: list[int] = [10, 50, 100]
MEDIUM_TIERS: list[int] = [10, 50, 100, 500, 1000]

# ---------------------------------------------------------------------------
# Timeouts (seconds) — scale with result tier
# ---------------------------------------------------------------------------
BASE_TIMEOUT = 600  # 10 min — containers scale to 0, cold start can take several minutes
TIMEOUT_PER_100_ITEMS = 30  # +30s per 100 items requested
MAX_TIMEOUT = 1800  # 30 min hard cap
WEBHOOK_RECEIVE_TIMEOUT = 120  # 2 min to receive webhook after job completes

# ---------------------------------------------------------------------------
# Platform configurations
# ---------------------------------------------------------------------------

INSTAGRAM_TARGETS = [
    {
        "name": "instagram_kylie",
        "config": {"directUrls": ["https://www.instagram.com/kyliejenner/"]},
    },
    {
        "name": "instagram_cristiano",
        "config": {"directUrls": ["https://www.instagram.com/cristiano/"]},
    },
    {
        "name": "instagram_leomessi",
        "config": {"directUrls": ["https://www.instagram.com/leomessi/"]},
    },
]

INSTAGRAM_PROFILE_TARGETS = [
    {
        "name": "profile_cristiano",
        "config": {"directUrls": ["https://www.instagram.com/cristiano/"]},
    },
    {
        "name": "profile_leomessi",
        "config": {"directUrls": ["https://www.instagram.com/leomessi/"]},
    },
    {
        "name": "profile_selenagomez",
        "config": {"directUrls": ["https://www.instagram.com/selenagomez/"]},
    },
]

INSTAGRAM_POSTS_TARGETS = [
    {
        "name": "posts_cristiano",
        "config": {"directUrls": ["https://www.instagram.com/cristiano/"]},
    },
    {
        "name": "posts_kyliejenner",
        "config": {"directUrls": ["https://www.instagram.com/kyliejenner/"]},
    },
]

TIKTOK_TARGETS = [
    {
        "name": "tiktok_khaby",
        "config": {"profiles": ["https://www.tiktok.com/@khaby.lame"]},
    },
    {
        "name": "tiktok_charli",
        "config": {"profiles": ["https://www.tiktok.com/@charlidamelio"]},
    },
    {
        "name": "tiktok_mrbeast",
        "config": {"profiles": ["https://www.tiktok.com/@mrbeast"]},
    },
]

YOUTUBE_TARGETS = [
    {
        "name": "youtube_mrbeast",
        "config": {"channelUrls": ["https://www.youtube.com/@MrBeast"]},
    },
    {
        "name": "youtube_tseries",
        "config": {"channelUrls": ["https://www.youtube.com/@tseries"]},
    },
    {
        "name": "youtube_cocomelon",
        "config": {"channelUrls": ["https://www.youtube.com/@cocomelon"]},
    },
]

REDDIT_TARGETS = [
    {
        "name": "reddit_technology",
        "config": {
            "queries": [
                {"profileUrl": "https://www.reddit.com/r/technology/", "searchQuery": "technology"},
            ],
        },
    },
    {
        "name": "reddit_science",
        "config": {
            "queries": [
                {"profileUrl": "https://www.reddit.com/r/science/", "searchQuery": "science"},
            ],
        },
    },
    {
        "name": "reddit_worldnews",
        "config": {
            "queries": [
                {"profileUrl": "https://www.reddit.com/r/worldnews/", "searchQuery": "world news"},
            ],
        },
    },
]

GOOGLE_NEWS_TARGETS = [
    {
        "name": "news_technology",
        "config": {"queries": ["technology"]},
    },
    {
        "name": "news_ai",
        "config": {"queries": ["artificial intelligence"]},
    },
    {
        "name": "news_sports",
        "config": {"queries": ["sports"], "language": "en", "country": "US"},
    },
]

# ---------------------------------------------------------------------------
# Master platform registry
# ---------------------------------------------------------------------------

PLATFORMS: dict[str, dict] = {
    "instagram": {
        "scraper_type": "instagram",
        "apify_url": "apify/instagram-scraper",
        "targets": INSTAGRAM_TARGETS,
        "limit_key": "resultsLimit",
        "expected_fields": ["url", "type"],
        "min_result_ratio": 0.5,  # expect at least 50% of requested limit
    },
    "instagram_profile": {
        "scraper_type": "instagram_profile",
        "apify_url": "apify/instagram-profile-scraper",
        "targets": INSTAGRAM_PROFILE_TARGETS,
        "limit_key": "resultsLimit",
        "expected_fields": ["url"],
        "min_result_ratio": 0.1,  # profiles return fewer items
    },
    "instagram_posts": {
        "scraper_type": "instagram_posts",
        "apify_url": None,  # no Apify URL mapping
        "targets": INSTAGRAM_POSTS_TARGETS,
        "limit_key": "resultsLimit",
        "expected_fields": ["url"],
        "min_result_ratio": 0.5,
    },
    "tiktok": {
        "scraper_type": "tiktok",
        "apify_url": "clockworks/tiktok-profile-scraper",
        "targets": TIKTOK_TARGETS,
        "limit_key": "videosLimit",
        "expected_fields": ["webVideoUrl"],
        "min_result_ratio": 0.3,
    },
    "youtube": {
        "scraper_type": "youtube",
        "apify_url": "streamers/youtube-scraper",
        "targets": YOUTUBE_TARGETS,
        "limit_key": "videosLimit",
        "expected_fields": ["url"],
        "min_result_ratio": 0.3,
    },
    "reddit": {
        "scraper_type": "reddit",
        "apify_url": "xmolodtsov/reddit-scraper",
        "targets": REDDIT_TARGETS,
        "limit_key": "postsLimit",
        "expected_fields": ["url"],
        "min_result_ratio": 0.5,
    },
    "google_news": {
        "scraper_type": "google_news",
        "apify_url": "xmolodtsov/google-news-scraper",
        "targets": GOOGLE_NEWS_TARGETS,
        "limit_key": "resultsLimit",
        "expected_fields": ["url"],
        "min_result_ratio": 0.3,
    },
}


# ---------------------------------------------------------------------------
# Webhook event expectations per terminal status
# ---------------------------------------------------------------------------

EXPECTED_WEBHOOK_EVENTS = {
    "SUCCEEDED": ["job.created", "job.started", "job.completed"],
    "FAILED": ["job.created", "job.started", "job.failed"],
    "TIMED-OUT": ["job.created", "job.started", "job.timed_out"],
    "ABORTED": ["job.created", "job.cancelled"],
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def timeout_for_tier(tier: int) -> int:
    """Calculate appropriate timeout for a given result tier."""
    timeout = BASE_TIMEOUT + (tier / 100) * TIMEOUT_PER_100_ITEMS
    return min(int(timeout), MAX_TIMEOUT)


def build_run_input(target_config: dict, limit_key: str, tier: int) -> dict:
    """Build run_input dict from target config with the result limit applied."""
    run_input = dict(target_config)
    run_input[limit_key] = tier
    return run_input


# ---------------------------------------------------------------------------
# Date parameter mappings (per-platform)
# ---------------------------------------------------------------------------

PLATFORM_DATE_PARAMS: dict[str, str] = {
    "instagram": "onlyPostsNewerThan",
    "tiktok": "oldestPostDate",
    "youtube": "oldestPostDate",
}

PLATFORM_TIMESTAMP_FIELDS: dict[str, list[str]] = {
    "instagram": ["timestamp", "postedAt"],
    "tiktok": ["createTime", "postedAt"],
    "youtube": ["date", "postedAt", "uploadDate"],
}

# ---------------------------------------------------------------------------
# Batch test configuration — 25 URLs per platform
# ---------------------------------------------------------------------------

BATCH_TIMEOUT = 1800  # 30 min for batch jobs (25 URLs can take a while)

INSTAGRAM_BATCH_URLS: list[str] = [
    "https://www.instagram.com/kyliejenner/",
    "https://www.instagram.com/cristiano/",
    "https://www.instagram.com/leomessi/",
    "https://www.instagram.com/selenagomez/",
    "https://www.instagram.com/therock/",
    "https://www.instagram.com/kimkardashian/",
    "https://www.instagram.com/beyonce/",
    "https://www.instagram.com/justinbieber/",
    "https://www.instagram.com/kendalljenner/",
    "https://www.instagram.com/natgeo/",
    "https://www.instagram.com/taylorswift/",
    "https://www.instagram.com/vifrfrfrfrfrfrvikfrfrfrfrviral/",  # intentionally obscure — tests resilience
    "https://www.instagram.com/neymarjr/",
    "https://www.instagram.com/nickiminaj/",
    "https://www.instagram.com/khloekardashian/",
    "https://www.instagram.com/nike/",
    "https://www.instagram.com/mileycyrus/",
    "https://www.instagram.com/jlo/",
    "https://www.instagram.com/kolofrfrfrfrviral2/",  # intentionally obscure
    "https://www.instagram.com/katyperry/",
    "https://www.instagram.com/kevinhart4real/",
    "https://www.instagram.com/zendaya/",
    "https://www.instagram.com/badgalriri/",
    "https://www.instagram.com/ddlovato/",
    "https://www.instagram.com/shakira/",
]

TIKTOK_BATCH_URLS: list[str] = [
    "https://www.tiktok.com/@khaby.lame",
    "https://www.tiktok.com/@charlidamelio",
    "https://www.tiktok.com/@mrbeast",
    "https://www.tiktok.com/@bellapoarch",
    "https://www.tiktok.com/@addisonre",
    "https://www.tiktok.com/@zachking",
    "https://www.tiktok.com/@bfrfrfrfrviral1",  # intentionally obscure
    "https://www.tiktok.com/@willsmith",
    "https://www.tiktok.com/@therock",
    "https://www.tiktok.com/@selenagomez",
    "https://www.tiktok.com/@gordonramsayofficial",
    "https://www.tiktok.com/@jfrfrfrfrviral2",  # intentionally obscure
    "https://www.tiktok.com/@justinbieber",
    "https://www.tiktok.com/@lizzo",
    "https://www.tiktok.com/@dojacat",
    "https://www.tiktok.com/@tfrfrfrfrviral3",  # intentionally obscure
    "https://www.tiktok.com/@dixiedamelio",
    "https://www.tiktok.com/@spencerx",
    "https://www.tiktok.com/@kfrfrfrfrviral4",  # intentionally obscure
    "https://www.tiktok.com/@jasonderulo",
    "https://www.tiktok.com/@bfrfrfrfrviral5",  # intentionally obscure
    "https://www.tiktok.com/@lorfrfrfrviral6",  # intentionally obscure
    "https://www.tiktok.com/@cristiano",
    "https://www.tiktok.com/@mfrfrfrfrviral7",  # intentionally obscure
    "https://www.tiktok.com/@arianagrande",
]

YOUTUBE_BATCH_URLS: list[str] = [
    "https://www.youtube.com/@MrBeast",
    "https://www.youtube.com/@tseries",
    "https://www.youtube.com/@cocomelon",
    "https://www.youtube.com/@SET_India",
    "https://www.youtube.com/@PewDiePie",
    "https://www.youtube.com/@KidsDianaShow",
    "https://www.youtube.com/@LikeNastya",
    "https://www.youtube.com/@Vlad-and-Niki",
    "https://www.youtube.com/@ZeeMusic",
    "https://www.youtube.com/@WWE",
    "https://www.youtube.com/@5MinuteCrafts",
    "https://www.youtube.com/@TaylorSwift",
    "https://www.youtube.com/@Dude_Perfect",
    "https://www.youtube.com/@JustinBieber",
    "https://www.youtube.com/@Marshmello",
    "https://www.youtube.com/@EminemMusic",
    "https://www.youtube.com/@EdSheeran",
    "https://www.youtube.com/@ArianaGrande",
    "https://www.youtube.com/@BillieEilish",
    "https://www.youtube.com/@BLACKPINK",
    "https://www.youtube.com/@BTS",
    "https://www.youtube.com/@MarkRober",
    "https://www.youtube.com/@veritasium",
    "https://www.youtube.com/@mkbhd",
    "https://www.youtube.com/@LinusTechTips",
]

BATCH_PLATFORMS: dict[str, dict] = {
    "instagram": {
        "urls": INSTAGRAM_BATCH_URLS,
        "url_key": "directUrls",
        "date_param": "onlyPostsNewerThan",
        "limit_key": "resultsLimit",
        "min_coverage": 15,  # at least 15/25 creators should have results
    },
    "tiktok": {
        "urls": TIKTOK_BATCH_URLS,
        "url_key": "profiles",
        "date_param": "oldestPostDate",
        "limit_key": "videosLimit",
        "min_coverage": 15,
    },
    "youtube": {
        "urls": YOUTUBE_BATCH_URLS,
        "url_key": "channelUrls",
        "date_param": "oldestPostDate",
        "limit_key": "videosLimit",
        "min_coverage": 15,
    },
}


def extract_username_from_url(url: str, platform: str) -> str | None:
    """
    Extract a normalised username/handle from a platform URL.

    Returns lowercase username without leading '@' or trailing '/'.
    Returns None if the URL cannot be parsed for the given platform.
    """
    parsed = urlparse(url)
    path = parsed.path.strip("/")

    if platform in ("instagram", "instagram_profile", "instagram_posts"):
        # https://www.instagram.com/kyliejenner/ → kyliejenner
        parts = path.split("/")
        if parts and parts[0]:
            return parts[0].lower()

    elif platform == "tiktok":
        # https://www.tiktok.com/@khaby.lame → khaby.lame
        parts = path.split("/")
        if parts and parts[0]:
            return parts[0].lstrip("@").lower()

    elif platform == "youtube":
        # https://www.youtube.com/@MrBeast → mrbeast
        parts = path.split("/")
        if parts and parts[0]:
            return parts[0].lstrip("@").lower()

    elif platform == "reddit":
        # https://www.reddit.com/r/technology/ → technology
        match = re.match(r"r/([^/]+)", path)
        if match:
            return match.group(1).lower()

    return None
