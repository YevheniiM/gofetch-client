"""
E2E regression test configuration.

Defines platforms, test targets, parameter matrices, result tiers,
and validation rules for end-to-end testing against the real GoFetch API.
"""

from __future__ import annotations

import os
import re
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Result-count tiers (min → max)
# ---------------------------------------------------------------------------
# TIER_MODE env var selects which tier set to run:
#   quick  — smoke test (3 tiers)
#   medium — CI / standard (5 tiers)
#   full   — nightly / pre-release (6 tiers, default)

_TIER_MODE = os.environ.get("TIER_MODE", "full").lower()

_FULL_TIERS: list[int] = [10, 50, 250, 1000, 2000, 3000]
_MEDIUM_TIERS: list[int] = [10, 50, 250, 1000, 2000]
_QUICK_TIERS: list[int] = [10, 50, 250]

RESULT_TIERS: list[int] = {
    "quick": _QUICK_TIERS,
    "medium": _MEDIUM_TIERS,
    "full": _FULL_TIERS,
}.get(_TIER_MODE, _FULL_TIERS)

# Tiers above this threshold test volume scaling, not account diversity —
# only the first target per platform runs them.
HIGH_TIER_THRESHOLD = 250

# Per-platform tier overrides — skip tiers above platform ceiling
REDDIT_TIERS: list[int] = [10, 50, 250, 500]  # ceiling ~950
GOOGLE_NEWS_TIERS: list[int] = [10, 50, 100]  # ceiling ~100-219

# ---------------------------------------------------------------------------
# Timeouts (seconds) — scale with result tier
# ---------------------------------------------------------------------------
BASE_TIMEOUT = 600  # 10 min — containers scale to 0, cold start can take several minutes
DEFAULT_TIMEOUT_PER_100 = 30  # +30s per 100 items requested (default)
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
        "min_result_ratio": 0.5,
        "timeout_per_100": 30,
    },
    "instagram_profile": {
        "scraper_type": "instagram_profile",
        "apify_url": "apify/instagram-profile-scraper",
        "targets": INSTAGRAM_PROFILE_TARGETS,
        "limit_key": "resultsLimit",
        "expected_fields": ["url"],
        "single_document": True,  # returns exactly 1 profile doc regardless of limit
        "min_result_ratio": 0.0,
        "timeout_per_100": 30,
        "tiers": [10],  # single-document — every tier returns the same 1 doc
    },
    "instagram_posts": {
        "scraper_type": "instagram_posts",
        "apify_url": None,
        "targets": INSTAGRAM_POSTS_TARGETS,
        "limit_key": "resultsLimit",
        "expected_fields": ["url"],
        "min_result_ratio": 0.5,
        "timeout_per_100": 30,
    },
    "tiktok": {
        "scraper_type": "tiktok",
        "apify_url": "clockworks/tiktok-profile-scraper",
        "targets": TIKTOK_TARGETS,
        "limit_key": "videosLimit",
        "expected_fields": ["webVideoUrl"],
        "min_result_ratio": 0.3,
        "timeout_per_100": 60,  # #8: TikTok needs more time per 100 items
    },
    "youtube": {
        "scraper_type": "youtube",
        "apify_url": "streamers/youtube-scraper",
        "targets": YOUTUBE_TARGETS,
        "limit_key": "videosLimit",
        "expected_fields": ["url"],
        "min_result_ratio": 0.3,
        "timeout_per_100": 60,  # #8: YouTube needs more time per 100 items
    },
    "reddit": {
        "scraper_type": "reddit",
        "apify_url": "xmolodtsov/reddit-scraper",
        "targets": REDDIT_TARGETS,
        "limit_key": "postsLimit",
        "expected_fields": ["url"],
        "min_result_ratio": 0.5,
        "platform_max_results": 950,  # #4: Reddit caps at ~1000 posts per query
        "timeout_per_100": 30,
        "tiers": REDDIT_TIERS,
    },
    "google_news": {
        "scraper_type": "google_news",
        "apify_url": "xmolodtsov/google-news-scraper",
        "targets": GOOGLE_NEWS_TARGETS,
        "limit_key": "resultsLimit",
        "expected_fields": ["url"],
        "min_result_ratio": 0.3,
        "platform_max_results": 100,  # #5: RSS feeds cap at ~100-219 articles
        "timeout_per_100": 30,
        "tiers": GOOGLE_NEWS_TIERS,
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def timeout_for_tier(tier: int, platform_name: str | None = None) -> int:
    """Calculate appropriate timeout for a given result tier.

    Uses per-platform timeout_per_100 when platform_name is provided (#8).
    """
    per_100 = DEFAULT_TIMEOUT_PER_100
    if platform_name:
        config = PLATFORMS.get(platform_name, {})
        per_100 = config.get("timeout_per_100", DEFAULT_TIMEOUT_PER_100)
    timeout = BASE_TIMEOUT + (tier / 100) * per_100
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
    "reddit": ["createdAt", "timestamp"],
    "google_news": ["publishedAt", "date"],
}

# ---------------------------------------------------------------------------
# Batch test configuration — 25 URLs per platform
# ---------------------------------------------------------------------------

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

REDDIT_BATCH_QUERIES: list[dict[str, str]] = [
    {"profileUrl": "https://www.reddit.com/r/technology/", "searchQuery": "technology"},
    {"profileUrl": "https://www.reddit.com/r/science/", "searchQuery": "science"},
    {"profileUrl": "https://www.reddit.com/r/worldnews/", "searchQuery": "world news"},
    {"profileUrl": "https://www.reddit.com/r/programming/", "searchQuery": "programming"},
    {"profileUrl": "https://www.reddit.com/r/datascience/", "searchQuery": "data science"},
    {"profileUrl": "https://www.reddit.com/r/MachineLearning/", "searchQuery": "machine learning"},
    {"profileUrl": "https://www.reddit.com/r/artificial/", "searchQuery": "AI"},
    {"profileUrl": "https://www.reddit.com/r/gaming/", "searchQuery": "gaming"},
    {"profileUrl": "https://www.reddit.com/r/movies/", "searchQuery": "movies"},
    {"profileUrl": "https://www.reddit.com/r/music/", "searchQuery": "music"},
    {"profileUrl": "https://www.reddit.com/r/sports/", "searchQuery": "sports"},
    {"profileUrl": "https://www.reddit.com/r/news/", "searchQuery": "news"},
    {"profileUrl": "https://www.reddit.com/r/space/", "searchQuery": "space"},
    {"profileUrl": "https://www.reddit.com/r/gadgets/", "searchQuery": "gadgets"},
    {"profileUrl": "https://www.reddit.com/r/Futurology/", "searchQuery": "future"},
    {"profileUrl": "https://www.reddit.com/r/Documentaries/", "searchQuery": "documentaries"},
    {"profileUrl": "https://www.reddit.com/r/books/", "searchQuery": "books"},
    {"profileUrl": "https://www.reddit.com/r/Fitness/", "searchQuery": "fitness"},
    {"profileUrl": "https://www.reddit.com/r/food/", "searchQuery": "food"},
    {"profileUrl": "https://www.reddit.com/r/travel/", "searchQuery": "travel"},
    {"profileUrl": "https://www.reddit.com/r/photography/", "searchQuery": "photography"},
    {"profileUrl": "https://www.reddit.com/r/Art/", "searchQuery": "art"},
    {"profileUrl": "https://www.reddit.com/r/DIY/", "searchQuery": "DIY"},
    {"profileUrl": "https://www.reddit.com/r/EarthPorn/", "searchQuery": "nature"},
    {"profileUrl": "https://www.reddit.com/r/history/", "searchQuery": "history"},
]

GOOGLE_NEWS_BATCH_QUERIES: list[str] = [
    "technology",
    "artificial intelligence",
    "sports",
    "politics",
    "health",
    "entertainment",
    "business",
    "climate change",
    "cryptocurrency",
    "space exploration",
    "education",
    "cybersecurity",
    "electric vehicles",
    "renewable energy",
    "stock market",
    "real estate",
    "travel",
    "food safety",
    "mental health",
    "robotics",
    "quantum computing",
    "social media",
    "startup funding",
    "video games",
    "science",
]

BATCH_PLATFORMS: dict[str, dict] = {
    "instagram": {
        "urls": INSTAGRAM_BATCH_URLS,
        "url_key": "directUrls",
        "date_param": "onlyPostsNewerThan",
        "limit_key": "resultsLimit",
        "limit_value": 10,  # 25 URLs x 10 = 250 items (tests multi-input, not volume)
        "min_coverage": 12,  # #6: relaxed from 15 — infrequent posters may have 0 results
        "batch_timeout": 1800,
    },
    "tiktok": {
        "urls": TIKTOK_BATCH_URLS,
        "url_key": "profiles",
        "date_param": "oldestPostDate",
        "limit_key": "videosLimit",
        "limit_value": 10,  # 25 URLs x 10 = 250 items
        "min_coverage": 12,  # #6: relaxed from 15
        "batch_timeout": 1800,
    },
    "youtube": {
        "urls": YOUTUBE_BATCH_URLS,
        "url_key": "channelUrls",
        "date_param": "oldestPostDate",
        "limit_key": "videosLimit",
        "limit_value": 10,  # 25 URLs x 10 = 250 items
        "min_coverage": 12,  # #6: relaxed from 15
        "batch_timeout": 3600,  # #10: YouTube batch needs more time (25 channels)
    },
    "reddit": {
        "queries": REDDIT_BATCH_QUERIES,
        # URLs derived from queries — used for coverage checking
        "urls": [q["profileUrl"] for q in REDDIT_BATCH_QUERIES],
        "limit_key": "postsLimit",
        "limit_value": 10,  # 25 queries x 10 posts = 250 total
        "date_param": None,
        "min_coverage": 15,
        "batch_timeout": 1800,
    },
    "google_news": {
        "queries": GOOGLE_NEWS_BATCH_QUERIES,
        "limit_key": "resultsLimit",
        "limit_value": 25,  # 25 queries x 25 results = 625 total
        "date_param": None,
        "min_coverage": 0,  # can't reliably match query terms to article URLs
        "batch_timeout": 1200,
    },
}

# Instagram path segments that are NOT usernames
_INSTAGRAM_NON_USER_SEGMENTS = {"p", "reel", "reels", "stories", "tv", "explore", "accounts"}


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
        # Guard against post URLs: /p/shortcode/, /reel/..., /stories/...  (#3)
        parts = path.split("/")
        if parts and parts[0] and parts[0].lower() not in _INSTAGRAM_NON_USER_SEGMENTS:
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
