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
| `src/gofetch/client.py` | Main GoFetchClient class |
| `src/gofetch/actor.py` | ActorClient for job management |
| `src/gofetch/dataset.py` | DatasetClient for results |
| `src/gofetch/webhook.py` | Webhook utilities |
| `src/gofetch/http.py` | HTTP client with retries |

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
