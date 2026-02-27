# GoFetch Client

[![PyPI version](https://badge.fury.io/py/gofetch-client.svg)](https://badge.fury.io/py/gofetch-client)
[![Python versions](https://img.shields.io/pypi/pyversions/gofetch-client.svg)](https://pypi.org/project/gofetch-client/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Python client for [GoFetch.io](https://go-fetch.io) social media scraping API.**

A drop-in replacement for `apify-client` that uses the GoFetch.io infrastructure.

## Features

- **Drop-in replacement** for `apify-client` - minimal code changes required
- **Multiple platforms**: Instagram, TikTok, YouTube, Reddit, Google News
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
- `xmolodtsov/reddit-scraper` → `reddit`
- `xmolodtsov/google-news-scraper` → `google_news`

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

### Reddit

```python
# Using Apify-style actor URL
run = client.actor("xmolodtsov/reddit-scraper").call(input={"query": "python"})
# Or using GoFetch scraper type directly
run = client.actor("reddit").call(input={"query": "python"})
```

### Google News

```python
# Using Apify-style actor URL
run = client.actor("xmolodtsov/google-news-scraper").call(input={"query": "technology"})
# Or using GoFetch scraper type directly
run = client.actor("google_news").call(input={"query": "technology"})
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

---

## Agentic Development Infrastructure

This project ships with a complete [Claude Code](https://claude.ai/claude-code) agentic infrastructure — specialized agents, one-command skills, safety hooks, and a regression test framework. Everything lives under `.claude/` and activates automatically when you open a Claude Code session.

```
.claude/
├── settings.local.json        # Permissions + hook wiring
├── hooks/                     # 6 safety & automation hooks
├── agents/                    # 7 specialized agent definitions
└── skills/                    # 8 invocable skill workflows
docs/
└── REGRESSION_TESTING.md      # 90 test cases across 8 modules
```

### Hooks

Hooks run automatically — you never call them directly. They intercept operations in real-time.

#### Safety hooks

| Hook | Trigger | Behavior |
|------|---------|----------|
| `no-ai-attribution.sh` | Before `git commit` | Blocks commits containing `Co-Authored-By` AI references |
| `destructive-command-confirm.sh` | Before any shell command | Blocks `git push --force`, `reset --hard`, `rm -rf /`, `clean -f`, `branch -D`, `checkout .` |
| `protect-sensitive-files.sh` | Before editing a file | Blocks edits to `.env`, `.pem`, `.key`, `credentials.*`, `secrets.*` |

#### Automation hooks

| Hook | Trigger | Behavior |
|------|---------|----------|
| `test-before-commit.sh` | Before `git commit` | Non-blocking reminder listing staged `.py` files |
| `auto-lint.sh` | After editing a `.py` file | Runs `ruff check --fix` silently on the file |
| `session-context.sh` | Session start | Prints version, branch, working tree, recent commits, available skills/agents |

Hooks work invisibly during normal development. For example, editing `src/gofetch/http.py` will trigger `protect-sensitive-files.sh` (passes — not a secret file), then after the edit `auto-lint.sh` fixes import ordering automatically. Committing triggers `no-ai-attribution.sh`, `destructive-command-confirm.sh`, and `test-before-commit.sh` in sequence.

### Agents

Seven role-specific experts, each with deep knowledge of their domain and strict boundaries on what they should and shouldn't touch.

| Agent | Role | When to Use |
|-------|------|-------------|
| **sdk-developer** | Core development | Features, bugs, refactoring across all modules |
| **api-compatibility-specialist** | Apify interface guardian | Verifying/fixing `apify-client` compatibility |
| **qa-engineer** | Manual QA (reporter only) | Hands-on testing — produces reports, never modifies code |
| **test-engineer** | Automated test writer | Writing pytest suites, closing coverage gaps |
| **async-specialist** | Async/await expert | Async implementations, sync/async parity |
| **docs-writer** | Documentation | README, CHANGELOG, docstrings, migration guides |
| **release-manager** | Version + publishing | Version bumps, changelog, tagging, PyPI releases |

**The `qa-engineer` is special** — it has strict reporter-only rules. It NEVER modifies source or test files, NEVER suggests patches, and NEVER commits. It runs 12 structured testing phases and produces a severity-rated report. This separation is intentional: QA finds problems, developers fix them.

#### Agent selection

```
Writing/fixing code?
├── Async-specific?  → async-specialist
├── Apify compat?    → api-compatibility-specialist
└── General          → sdk-developer

Testing?
├── Writing tests    → test-engineer
└── Manual QA        → qa-engineer

Documentation?       → docs-writer
Releasing?           → release-manager
```

### Skills

Skills are one-command workflows invoked with `/skill-name` in Claude Code.

| Skill | Purpose | Duration |
|-------|---------|----------|
| `/self-test` | Lint + types + targeted tests on changed files | ~30 sec |
| `/regression-lite` | ~50 core tests from every module | ~15-20 min |
| `/regression-full` | All 90+ tests with parametrized variants (150+ effective) | ~45-60 min |
| `/review-changes` | Pre-commit review: security, types, compatibility, style, coverage | ~2-5 min |
| `/debug` | Hypothesis-driven debugging: reproduce, hypothesize, investigate, isolate | varies |
| `/fix-from-qa` | Parse a QA report, triage, fix by severity | varies |
| `/manual-qa [scope]` | Launch qa-engineer with scope: `client`, `http`, `webhook`, `async`, `compat`, `all` | ~20-30 min |
| `/release [major\|minor\|patch]` | Full release: validate, version, changelog, tag, publish | ~10-15 min |

### Real-World Workflows

#### Adding a new feature

```
1. Implement in src/gofetch/ (maintain sync/async parity)
2. /self-test              → quick validation
3. /review-changes         → pre-commit check (catches compat issues, missing tests)
4. Write tests             → use test-engineer agent
5. Commit
```

**Example — adding a new scraper type (e.g., Twitter/X):**

The `sdk-developer` agent plans changes across `types.py`, `constants.py`, and actor URL resolution. After implementation, `/self-test` catches type errors from the new enum. `/review-changes` flags the missing test coverage. The `test-engineer` agent writes parametrized tests. `/manual-qa compat` verifies the new actor URL resolves correctly through the Apify compatibility layer. On commit, `no-ai-attribution.sh` checks the message and `test-before-commit.sh` lists the staged Python files.

#### Debugging a production issue

```
1. /debug <description>    → structured investigation
2. Fix the root cause
3. /self-test              → verify fix + no regressions
4. /regression-lite        → broader regression check
5. Commit
```

**Example — "Jobs time out even though the API shows them as completed":**

`/debug` reproduces the issue with mock HTTP, generates 3-5 hypotheses ranked by likelihood, and investigates each one. It might find that the polling loop compares raw GoFetch status `"completed"` against Apify status `"SUCCEEDED"` — a mapping issue in `actor.py:_wait_for_completion()`. After fixing, `/self-test` confirms the fix and `/regression-lite` runs all actor polling tests (ACT-04 through ACT-06).

#### Full QA cycle before a release

```
1. /manual-qa all          → 12-phase QA, produces severity-rated report
2. /fix-from-qa            → parse report, fix SEV-1 first, then SEV-2, SEV-3
3. /manual-qa all          → re-run to verify all fixes
4. /regression-full        → 150+ tests, coverage threshold check (80%)
5. /release minor          → validate, bump, changelog, tag, push
```

**Example — shipping v0.2.0:**

`/manual-qa all` runs through environment verification, unit smoke tests, client instantiation, actor testing, dataset pagination, HTTP retries with mock transports, webhook signatures, exception hierarchy, async clients, edge cases, mypy, and ruff. It produces a report finding 5 issues. `/fix-from-qa` processes the report, fixing the SEV-1 (async client not raising `AuthenticationError`) first, then SEV-2s and SEV-3s — each fix includes a test. Re-running `/manual-qa all` comes back clean. `/regression-full` confirms 150+ tests pass at 83% coverage. `/release minor` bumps `0.1.0 → 0.2.0`, updates both version locations, prepares the changelog, commits, tags, and pauses for confirmation before pushing.

#### Maintaining sync/async parity

```
1. Change a sync method (e.g., HTTPClient.get)
2. /review-changes         → flags that AsyncHTTPClient.get wasn't updated
3. Mirror the change in the async counterpart
4. /manual-qa async        → verifies both behave identically
```

The `async-specialist` agent knows every sync/async class pair and common pitfalls — like accidentally using `time.sleep()` instead of `asyncio.sleep()` in async code, or forgetting to `await` a coroutine.

### Regression Testing

The full specification lives at [`docs/REGRESSION_TESTING.md`](docs/REGRESSION_TESTING.md) — 90 test cases with unique IDs:

| Module | IDs | Count | Priority |
|--------|-----|-------|----------|
| Client | CLI-01..10 | 10 | Medium |
| Actor | ACT-01..15 | 15 | High |
| Dataset | DAT-01..10 | 10 | High |
| HTTP | HTTP-01..12 | 12 | Highest |
| Webhook | WHK-01..10 | 10 | Medium |
| Async | ASY-01..15 | 15 | High |
| Compatibility | CMP-01..10 | 10 | Medium |
| Exceptions | EXC-01..08 | 8 | Low |

Each test specifies preconditions, steps, and expected results. Many use `@pytest.mark.parametrize` — effective count exceeds 150.

Reference test IDs in PRs and bug reports: *"This PR fixes the issue exposed by ACT-06 (polling backoff timing)"* or *"Blocked on HTTP-08 — need backoff timing test before shipping retry changes."*

### Customizing the Infrastructure

**Add a hook:** Create a script in `.claude/hooks/`, `chmod +x` it, wire it in `settings.local.json` under `PreToolUse`, `PostToolUse`, or `SessionStart`. Exit `0` to allow, `2` to block.

**Add an agent:** Create a markdown file in `.claude/agents/` with sections: Identity, Codebase Knowledge, Responsibilities, Boundaries.

**Add a skill:** Create `.claude/skills/<name>/SKILL.md` with YAML frontmatter (`name`, `description`, `user_invocable: true`) and step-by-step procedure.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Links

- **Documentation**: https://github.com/YevheniiM/gofetch-client#readme
- **Issues**: https://github.com/YevheniiM/gofetch-client/issues
- **GoFetch.io**: https://go-fetch.io
