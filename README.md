# GoFetch Client

[![PyPI version](https://badge.fury.io/py/gofetch-client.svg)](https://badge.fury.io/py/gofetch-client)
[![Python versions](https://img.shields.io/pypi/pyversions/gofetch-client.svg)](https://pypi.org/project/gofetch-client/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Python client for [GoFetch.io](https://go-fetch.io) social media scraping API.**

A drop-in replacement for `apify-client` that uses the GoFetch.io infrastructure.

## Features

- **Drop-in replacement** for `apify-client` - minimal code changes required
- **Multiple platforms**: Instagram, TikTok, YouTube
- **Sync and async** execution modes
- **Webhook support** for asynchronous job notifications
- **Full type hints** for better IDE support
- **Automatic retries** with exponential backoff

## Installation

```bash
pip install gofetch-client
```

For async support with HTTP/2:
```bash
pip install gofetch-client[async]
```

## Quick Start

### Basic Usage

```python
from gofetch import GoFetchClient

# Initialize client
client = GoFetchClient(api_key="sk_scr_your_api_key")

# Create an actor for Instagram scraping
actor = client.actor("instagram")

# Run synchronously (blocks until complete)
run = actor.call(run_input={
    "directUrls": ["https://www.instagram.com/nike/"],
    "maxPosts": 10,
})

# Fetch results
dataset = client.dataset(run["defaultDatasetId"])
for item in dataset.iterate_items():
    print(item["id"], item.get("caption", "")[:50])
```

### Async Execution with Webhooks

```python
from gofetch import GoFetchClient

client = GoFetchClient(api_key="sk_scr_your_api_key")
actor = client.actor("instagram")

# Start async job with webhook notification
run = actor.start(
    run_input={
        "directUrls": ["https://www.instagram.com/nike/"],
        "maxPosts": 100,
    },
    webhooks=[{
        "request_url": "https://your-app.com/webhook",
        "event_types": ["ACTOR.RUN.SUCCEEDED", "ACTOR.RUN.FAILED"]
    }]
)

print(f"Job started: {run['id']}")
# Your webhook will be called when the job completes
```

## Migration from Apify

GoFetch Client is designed as a drop-in replacement for `apify-client`.

### Before (Apify)

```python
from apify_client import ApifyClient

client = ApifyClient(token="apify_api_xxx")
actor = client.actor("apify/instagram-scraper")
run = actor.call(run_input={"directUrls": [...]})
dataset = client.dataset(run["defaultDatasetId"])
items = list(dataset.iterate_items())
```

### After (GoFetch)

```python
from gofetch import GoFetchClient  # Only import changes!

client = GoFetchClient(api_key="sk_scr_xxx")  # Use GoFetch API key
actor = client.actor("apify/instagram-scraper")  # Same actor URL works!
run = actor.call(run_input={"directUrls": [...]})
dataset = client.dataset(run["defaultDatasetId"])
items = list(dataset.iterate_items())
```

The client automatically translates Apify actor URLs to GoFetch scrapers:
- `apify/instagram-scraper` → `instagram`
- `apify/instagram-profile-scraper` → `instagram_profile`
- `clockworks/tiktok-profile-scraper` → `tiktok`
- `streamers/youtube-scraper` → `youtube`

## Supported Platforms

### Instagram

```python
actor = client.actor("instagram")
run = actor.call(run_input={
    "directUrls": ["https://www.instagram.com/nike/"],
    "onlyPostsNewerThan": "2024-01-01",
    "maxPosts": 50,
})
```

### TikTok

```python
actor = client.actor("tiktok")
run = actor.call(run_input={
    "profiles": ["khaby.lame", "charlidamelio"],
    "oldestPostDate": "2024-01-01",
    "maxVideosPerProfile": 50,
})
```

### YouTube

```python
actor = client.actor("youtube")
run = actor.call(run_input={
    "startUrls": [{"url": "https://www.youtube.com/@MrBeast"}],
    "oldestPostDate": "2024-01-01",
})
```

## Webhook Handling

### Verifying Webhook Signatures

```python
from gofetch import verify_webhook_signature

def webhook_handler(request):
    payload = request.body
    signature = request.headers.get("X-Webhook-Signature", "")

    if not verify_webhook_signature(payload, signature, "your_webhook_secret"):
        return Response("Invalid signature", status=401)

    # Process webhook...
```

### Transforming Webhook Payloads

```python
from gofetch import transform_webhook_payload

def webhook_handler(request):
    gofetch_payload = json.loads(request.body)

    # Transform to Apify-compatible format
    apify_payload = transform_webhook_payload(gofetch_payload)

    if apify_payload["eventType"] == "ACTOR.RUN.SUCCEEDED":
        dataset_id = apify_payload["resource"]["defaultDatasetId"]
        # Fetch results...
```

## Error Handling

```python
from gofetch import (
    GoFetchClient,
    GoFetchError,
    AuthenticationError,
    RateLimitError,
    JobError,
    TimeoutError,
)

try:
    client = GoFetchClient(api_key="sk_scr_xxx")
    run = client.actor("instagram").call(run_input={...})

except AuthenticationError:
    print("Invalid API key")

except RateLimitError as e:
    print(f"Rate limited. Retry after {e.retry_after} seconds")

except TimeoutError as e:
    print(f"Job timed out: {e.job_id}")

except JobError as e:
    print(f"Job failed: {e.error_message}")

except GoFetchError as e:
    print(f"GoFetch error: {e.message}")
```

## Development

```bash
# Clone the repository
git clone https://github.com/YevheniiM/gofetch-client.git
cd gofetch-client

# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest

# Run linting
ruff check src/

# Run type checking
mypy src/
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Links

- **Documentation**: https://github.com/YevheniiM/gofetch-client#readme
- **Issues**: https://github.com/YevheniiM/gofetch-client/issues
- **GoFetch.io**: https://go-fetch.io
