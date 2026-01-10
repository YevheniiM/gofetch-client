# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2025-01-10

### Added

- Initial release of `gofetch-client`
- `GoFetchClient` - main client class (drop-in replacement for `ApifyClient`)
- `ActorClient` - job management with `call()` and `start()` methods
- `DatasetClient` - result fetching with `iterate_items()` and `list_items()`
- Async support via `AsyncGoFetchClient`, `AsyncActorClient`, `AsyncDatasetClient`
- Webhook utilities:
  - `verify_webhook_signature()` - HMAC-SHA256 signature verification
  - `transform_webhook_payload()` - GoFetch → Apify payload transformation
  - `generate_webhook_config()` - VWD-compatible webhook URL generation
  - `WebhookEventType` enum (compatible with `apify_shared.consts`)
- Exception classes:
  - `GoFetchError` - base exception
  - `APIError` - HTTP error responses
  - `AuthenticationError` - 401 errors
  - `RateLimitError` - 429 errors with retry_after
  - `JobError` - job failures
  - `TimeoutError` - operation timeouts
  - `ValidationError` - input validation errors
- Type definitions:
  - `ScraperType` enum
  - `JobStatus` enum with `to_apify_status()` method
  - `RunStatus` named tuple
- Apify actor URL resolution
- Full type hints (py.typed marker included)
- Automatic retries with exponential backoff
- Rate limit handling with retry_after support
