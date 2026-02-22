# Project Instructions

## Commit Guidelines

**IMPORTANT: Never include any AI attribution in commits.**

- Do NOT add `Co-Authored-By:` lines referencing any AI
- Do NOT mention AI assistance in commit messages
- Do NOT reference AI in code comments, documentation, or anywhere in the repository
- All commits should appear as if written entirely by the human developer

## Project Overview

Python SDK for GoFetch.io social media scraping API. Drop-in replacement for `apify-client`.

## Key Files

| File | Purpose |
|------|---------|
| `src/gofetch/client.py` | Main GoFetchClient class (sync + async), factory methods |
| `src/gofetch/actor.py` | ActorClient for job creation/polling, shared helpers |
| `src/gofetch/dataset.py` | DatasetClient for paginated results (sync + async) |
| `src/gofetch/run.py` | RunClient for job management (get, wait, abort) |
| `src/gofetch/log.py` | LogClient for job log retrieval (text + structured) |
| `src/gofetch/webhook_client.py` | WebhookClient + CollectionClient for webhook CRUD |
| `src/gofetch/webhook.py` | Webhook utilities, signature verification, event mappings |
| `src/gofetch/http.py` | HTTP client with retries (sync + async) |
| `src/gofetch/exceptions.py` | Exception hierarchy (7 classes) |
| `src/gofetch/types.py` | Enums, Pydantic models, URL resolution |
| `src/gofetch/constants.py` | Configuration values, status mappings |
| `src/gofetch/scrapers/base.py` | BaseScraper abstract class |

## Development Commands

```bash
pip install -e ".[dev]"  # Install in dev mode
pytest                    # Run tests
ruff check src/          # Lint
mypy src/                # Type check
```

## Publishing

1. Update version in `src/gofetch/__init__.py` and `pyproject.toml`
2. Update `CHANGELOG.md`
3. Create GitHub release - CI publishes to PyPI automatically

---

## Agent System

### Available Agents

| Agent | Role | When to Use |
|-------|------|-------------|
| **sdk-developer** | Core SDK development | Features, bugs, refactoring across all modules |
| **sdk-architect** | Architecture & design (plan mode) | New module design, pattern decisions, trade-off analysis |
| **api-compatibility-specialist** | Apify interface guardian | Verifying/fixing apify-client compatibility |
| **qa-engineer** | Manual QA (REPORTER ONLY) | Hands-on testing, produces reports, never modifies code |
| **test-engineer** | Automated test writer | Writing pytest suites, improving coverage |
| **integration-test-engineer** | E2E integration tests | Full request/response cycle testing with mock transports |
| **async-specialist** | Async/await expert | Async implementations, sync/async parity |
| **research-specialist** | API & SDK research (READ ONLY) | Investigating apify-client updates, API changes, patterns |
| **security-specialist** | Security auditing | Credential handling, webhook security, dependency audit |
| **docs-writer** | Documentation | README, CHANGELOG, docstrings, migration guides |
| **release-manager** | Version + publishing | Version bumps, changelog, tagging, PyPI releases |

### Agent Selection Decision Tree

```
Is it about writing/fixing code?
├── Yes → Is it async-specific?
│   ├── Yes → async-specialist
│   └── No → Is it about Apify compatibility?
│       ├── Yes → api-compatibility-specialist
│       └── No → sdk-developer
├── Is it about architecture/design?
│   └── Yes → sdk-architect
├── Is it about testing?
│   ├── Writing unit tests → test-engineer
│   ├── Writing integration/e2e tests → integration-test-engineer
│   └── Manual QA session → qa-engineer
├── Is it about research/investigation?
│   ├── API or SDK compatibility research → research-specialist
│   └── Security audit → security-specialist
├── Is it about documentation?
│   └── Yes → docs-writer
└── Is it about releasing?
    └── Yes → release-manager
```

## Skills

| Skill | Purpose | Duration |
|-------|---------|----------|
| `/self-test` | Quick lint + types + tests on changes | ~30 sec |
| `/regression-lite` | Core ~50 tests across all modules | ~15-20 min |
| `/regression-full` | All 90+ tests with parametrized variants | ~45-60 min |
| `/review-changes` | Pre-commit code review (security, types, compat) | ~2-5 min |
| `/debug` | Hypothesis-driven debugging workflow | Varies |
| `/fix-from-qa` | Process QA reports and fix issues by severity | Varies |
| `/manual-qa` | Launch qa-engineer for hands-on testing | ~20-30 min |
| `/release` | Full release workflow (validate → version → publish) | ~10-15 min |

## Development Lifecycle

### Feature Development
1. Plan the feature (identify affected modules)
2. Implement in `src/gofetch/` (maintain sync/async parity)
3. Write tests in `tests/`
4. Run `/self-test` to validate
5. Run `/review-changes` before committing

### Bug Fix
1. Run `/debug` to investigate
2. Fix the root cause
3. Add regression test
4. Run `/self-test`
5. Run `/review-changes`

### Pre-release
1. Run `/manual-qa` with scope `all`
2. Process findings with `/fix-from-qa`
3. Run `/regression-full`
4. Run `/release`

### QA Cycle
1. Run `/manual-qa` (produces report)
2. Review report findings
3. Run `/fix-from-qa` to address issues
4. Re-run `/manual-qa` to verify fixes

## Architecture Notes

### Sync/Async Parity
Every sync class has an async counterpart (7 pairs). Changes to sync code MUST be mirrored in async.

| Sync | Async | File |
|------|-------|------|
| `GoFetchClient` | `AsyncGoFetchClient` | `client.py` |
| `ActorClient` | `AsyncActorClient` | `actor.py` |
| `DatasetClient` | `AsyncDatasetClient` | `dataset.py` |
| `RunClient` | `AsyncRunClient` | `run.py` |
| `LogClient` | `AsyncLogClient` | `log.py` |
| `WebhookClient` | `AsyncWebhookClient` | `webhook_client.py` |
| `WebhookCollectionClient` | `AsyncWebhookCollectionClient` | `webhook_client.py` |
| `HTTPClient` | `AsyncHTTPClient` | `http.py` |

### Retry Logic (`http.py`)
- Retries on: `{408, 429, 500, 502, 503, 504}` and connection errors
- Backoff: `1.0s × 2.0^attempt` (1s, 2s, 4s)
- Default max retries: 3
- No retry on: 400, 401, 403, 404, 422

### Pagination (`dataset.py`)
- Page size: 100 items (default), max 1000
- Fetches pages sequentially with offset/limit
- Handles both `results` and `items` response keys

### Polling Backoff (`actor.py`)
- Initial interval: 2.0 seconds
- Backoff factor: 1.5× per poll
- Cap: 30.0 seconds maximum
- Pattern: 2.0, 3.0, 4.5, 6.75, 10.125, 15.1875, 22.78, 30.0, 30.0, ...

### Exception Hierarchy
```
GoFetchError
├── APIError
│   ├── AuthenticationError (401)
│   └── RateLimitError (429)
├── JobError
├── TimeoutError
└── ValidationError
```
