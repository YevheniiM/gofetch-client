# GoFetch Client

[![PyPI version](https://badge.fury.io/py/gofetch-client.svg)](https://badge.fury.io/py/gofetch-client)
[![Python versions](https://img.shields.io/pypi/pyversions/gofetch-client.svg)](https://pypi.org/project/gofetch-client/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Python client for [GoFetch.io](https://go-fetch.io) social media scraping API.**

A drop-in replacement for `apify-client` that uses the GoFetch.io infrastructure.

## Features

- **Drop-in replacement** for `apify-client` - minimal code changes required
- **13 scrapers**: Instagram (posts, profiles, comments), TikTok (videos, comments, identity resolve), YouTube, Facebook (posts, pages), Google SERP, cross-platform Profile Probe
- **Sync and async** execution modes
- **Webhook support** for asynchronous job notifications
- **[Datasets](#datasets)**: pull/ack subscription feeds and paid downloads
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
- `apify/facebook-scraper` → `facebook`
- `apify/facebook-posts-scraper` → `facebook_posts`
- `apify/facebook-pages-scraper` → `facebook_profile`
- `scraperlink/google-search-results-serp-scraper` → `google_serp`

Input is passed to the API as-is (`run_input` → `config`); the platform accepts the
common Apify key spellings (`directUrls`, `resultsLimit`, `startUrls`, `onlyPostsNewerThan`, …).

## Supported Platforms

Every scraper is a `scraper_type` you pass to `client.actor(...)`. `run_input` goes to the API
unchanged, so the keys below are the API's own. Billing is per returned item (post, comment,
SERP query, probe row); rates are on your dashboard.

| `scraper_type` | Returns | Key inputs |
|---|---|---|
| `instagram` / `instagram_posts` | posts and reels for accounts | `directUrls` or `usernames`, `maxPosts` (default 50, `0` = all), `onlyPostsNewerThan` |
| `instagram_profile` | one profile row per account | `usernames` or `directUrls` |
| `instagram_comments` | comments (+ replies) on posts/reels | `directUrls` or `handles`, `maxComments`, `includeReplies` |
| `tiktok` | videos for profiles / hashtags / searches | `profiles` or `directUrls` / `hashtags` / `searchQueries`, `maxVideosPerProfile`, `onlyPostsNewerThan` |
| `tiktok_comments` | comments (+ replies) on videos | same as `instagram_comments` |
| `tiktok_identity_resolve` | a creator's other social handles, with evidence | `creators` |
| `youtube` | videos, shorts and streams for channels | `channelUrls` or `directUrls`, `maxVideos`, `onlyPostsNewerThan` |
| `facebook` / `facebook_posts` | posts for pages | `pageUrls` or `directUrls`, `resultsLimit` (default 50), `onlyPostsNewerThan` |
| `facebook_profile` | one page-info row per page | `pageUrls` or `directUrls` |
| `google_serp` | first-page organic results per query | `queries`, `country` (US), `hl` (en), `limit` (≤ 10) |
| `profile_probe` | one resolved-profile row per (creator, platform, candidate) across IG / YT / FB / X | `creators` |

Dates are `YYYY-MM-DD`.

### Instagram

```python
# Posts (and reels) for accounts
run = client.actor("instagram").call(run_input={
    "directUrls": ["https://www.instagram.com/nike/"],   # or "usernames": ["nike"]
    "onlyPostsNewerThan": "2026-01-01",
    "maxPosts": 50,
})

# Profile info only
run = client.actor("instagram_profile").call(run_input={"usernames": ["nike"]})
```

### Instagram / TikTok comments

Identical inputs and an identical output schema for both platforms — one parser handles both.

```python
run = client.actor("instagram_comments").call(run_input={   # or "tiktok_comments"
    "handles": ["nasa"],            # or "directUrls": [post/video URLs]
    "maxPosts": 10,                 # posts per handle (ignored with directUrls)
    "maxComments": 5000,            # global cap — this is your cost ceiling, always set it
    "maxCommentsPerPost": 500,
    "includeReplies": True,         # replies are separate billable items
    "maxRepliesPerComment": 50,
    "onlyCommentsNewerThan": "2026-01-01",
})
comments = client.dataset(run["defaultDatasetId"]).list_items()
```

Replies are top-level items with `isReply: true` and `parentCommentId` pointing at the parent.
`repliesCount` is `null` when replies were not checked — `null` is not `0`. Read the job's
`coverage` (Instagram) / `completeness` (TikTok) block to tell a capped job from a degraded one —
see [Completeness](#results-completeness-and-polling).

### TikTok

```python
run = client.actor("tiktok").call(run_input={
    "profiles": ["khaby.lame", "charlidamelio"],
    "onlyPostsNewerThan": "2026-01-01",
    "maxVideosPerProfile": 50,
})
```

### TikTok identity resolve

Given TikTok creators, returns their handles on other platforms with the evidence used. Each
creator settles one `row_type: "seed"` row plus up to 25 link rows.

```python
run = client.actor("tiktok_identity_resolve").call(run_input={
    "creators": [
        {"ref": "1", "handle": "@thekoreanvegan"},
        {"ref": "2", "url": "https://www.tiktok.com/@nasa"},
        "bare_handle_also_works",
    ],
    "options": {"surfaces": ["seed", "hub", "counterpart"], "enrich": False},
})
```

### YouTube

```python
run = client.actor("youtube").call(run_input={
    "channelUrls": ["https://www.youtube.com/@MrBeast"],   # startUrls: [{"url": ...}] also works
    "onlyPostsNewerThan": "2026-01-01",
    "maxVideos": 100,
})
```

### Facebook

```python
# Posts for pages
run = client.actor("facebook").call(run_input={
    "pageUrls": ["https://www.facebook.com/nike"],
    "onlyPostsNewerThan": "2026-01-01",
    "resultsLimit": 50,
})

# Page info only
run = client.actor("facebook_profile").call(run_input={"pageUrls": ["https://www.facebook.com/nike"]})
```

### Google SERP

One output item per query, holding the top organic results. Search operators are honoured verbatim.

```python
run = client.actor("google_serp").call(run_input={
    "queries": ['"go-fetch.io" reviews', "social media scraping api"],
    "country": "US",
    "hl": "en",
    "limit": 10,   # first page only; capped at 10
})
for item in client.dataset(run["defaultDatasetId"]).iterate_items():
    print(item["search_term"], [r["url"] for r in item["results"]])
```

### Profile Probe

Resolve a batch of creators across Instagram, YouTube, Facebook and X in one call. Give each
creator a `ref` (your join key) and candidate handles per platform; you get one row per
(ref, platform, candidate) with `status`, the resolved `profile` and cross-resolve links.

```python
run = client.actor("profile_probe").call(run_input={
    "creators": [
        {"ref": "123", "platforms": {"instagram": ["nike"], "youtube": ["@nike"], "x": ["Nike"]}},
        {"ref": "456", "platforms": {"facebook": ["nike"]}},
    ],
    "options": {"tryVariants": False, "maxCacheAgeDays": 30},
})
```

Supported platform keys: `instagram`, `youtube`, `facebook`, `x`. Up to 1,000 creators per call.

## Results, completeness and polling

### Poll on `isTerminal`, not on `status`

A job that fails an attempt while the platform still has automatic retries left reports
`status: "FAILED"` with `isTerminal: false` — it is about to run again. `call()` and
`wait_for_finish()` already honour this; if you poll `start()`ed runs yourself, do the same:

```python
run = client.actor("instagram").start(run_input={...})
run = client.run(run["id"]).wait_for_finish()      # returns when isTerminal is true
if run["status"] != "SUCCEEDED":
    print(run["attemptHistory"])                    # per-attempt failure reasons
```

### Completeness signals

The run dict carries the job's `scraper_metadata`. Comment jobs report how much of what the
platform says exists was actually returned, so you can tell a cap from a failure:

```python
meta = run["scraper_metadata"] or {}
coverage = meta.get("coverage")          # Instagram comments: ratio vs the post's comment count
completeness = meta.get("completeness")  # TikTok comments: per-post accounting; read posts_complete
```

### `list_items()` returns a page that is still a list

```python
page = client.dataset(run["defaultDatasetId"]).list_items()
len(page), page[0]         # plain list behaviour
page.items, page.total     # apify-client's ListPage attributes (also offset, limit, desc)
```

## Datasets

A **dataset** here is the subscription product — a feed of rows you pull, read and ack, plus a
paid one-shot download of everything new. It is **not** `client.dataset(job_id)`, which fetches
one scraper job's results and is unchanged.

| You want | Use |
|---|---|
| One scraper job's results | `client.dataset(job_id)` — the Apify-compatible client |
| The Datasets product | `client.datasets()` and `client.dataset_feed(slug)` |

There are no dataset webhooks. Polling is the only delivery mechanism.

### The delivery loop

```python
feed = client.dataset_feed("creator-feed")

for row in feed.pull_and_iterate():
    store(row)          # persist durably — see below
```

`pull_and_iterate()` pulls a batch, pages every row, and acks. **The ack is what charges you**,
and it runs only after the last row has been yielded, so:

- persist each row durably before the generator ends;
- if you break out of the loop, or an exception escapes it, **nothing is acked and nothing is
  charged** — the batch stays open and a later pull re-serves it byte-identically;
- if your process is down longer than `config.ack_ttl_hours` (48 by default) the batch expires,
  the rows go back to the pool, and they are re-offered on a later pull. Losing an unacked batch
  costs data latency, not money.

If the dataset is **paused** mid-flight, `pull()` raises `409 dataset_paused` — the pause is
checked before an open batch is re-served, so a batch you already hold goes invisible to `pull()`.
It is still yours, and still ackable:

```python
open_batch = feed.get()["open_batch"]
if open_batch:
    batch = feed.batch(open_batch["batch_id"])
    rows = list(batch.iterate_rows())
    batch.ack()
```

The steps are available on their own if you want to drive them yourself:

```python
pull = feed.pull()
if pull["status"] in ("ok", "open_batch_exists"):
    batch = feed.batch(pull["batch"]["batch_id"])
    rows = list(batch.iterate_rows())
    result = batch.ack()
    result["batch"]["billed_rows"]     # bill from this, never from row_count
    result["constraints"]              # why fewer rows were billed, when they were
```

The other pull statuses — `unavailable`, `quota_exhausted`, `nothing_available` — are data, not
errors: they simply carry no batch.

### Buying everything new as a file

```python
receipt = feed.download()                       # quotes, then buys. This moves money.
                                                # for a recoverable purchase see below
export = feed.export(receipt["export_id"]).wait_for_ready()
feed.export(receipt["export_id"]).download_to("creators.jsonl")
```

`download()` always sends an `Idempotency-Key` — the API rejects a request without one — and
reuses that key for its single automatic `quote_stale` retry, so a retried purchase cannot buy
twice.

### Surviving a restart: the key AND its ceiling

The generated key dies with your process, so pass your own if the purchase must survive a
restart. **The key on its own is not enough.** The server fingerprints it together with
`expected_items`, and `download()` re-quotes that ceiling on every call — so once the first
purchase has landed, `items.new` is `0`, and a bare same-key retry arrives as
`expected_items: 0`, which reads as a *different* purchase and is refused
`400 idempotency_key_reused`.

Record both, and replay both:

```python
import uuid

key = uuid.uuid4().hex                 # one key per purchase — see below
ceiling = feed.quote()["items"]["new"]
persist(key, ceiling)                  # BEFORE the call, so a crash mid-purchase is recoverable

receipt = feed.download(idempotency_key=key, expected_items=ceiling)
```

```python
key, ceiling = load()                  # after the restart
receipt = feed.download(idempotency_key=key, expected_items=ceiling)
```

That returns the original receipt verbatim and bills nothing further. `download()` raises with
the re-quoted ceiling named in the message if you replay a key without its `expected_items`.

**Use a uuid per purchase, not a naming scheme.** Keys are scoped `(dataset, key)` per
*organization*, so two of your services sharing a scheme like `nightly-<date>` will replay each
other's receipts and hand back an export the other one bought.

### After a failure

| After | Key |
|---|---|
| Network error, timeout, any 5xx, `409 download_in_progress` | **Reuse the same key**, with the same `expected_items` — money may have moved, and only that pair replays the receipt |
| A 4xx refusal *before* any purchase landed | A fresh key is safe — nothing was billed |

`400 idempotency_key_reused` is **not** "try again", and is **not** a reason to mint a fresh key
— a fresh key buys the export a second time and abandons the one already paid for. It means the
key was sent with a different `expected_items` or `format` than the purchase it belongs to;
replay it with the original ceiling. It also fires while the first request is still in flight.

`billed_items: 0` with `billed_amount: "0.0000"` is a **successful free download** — there was
nothing new to buy. Do not read it as a failure.

`feed.quote()` tells you what it would cost, for free. `expected_items` is a ceiling, not an
equality: a claim larger than it is refused, a smaller one proceeds and says `fewer_than_quoted`
in `constraints`.

A built export lives 4 days. Treat `expires_at` as authoritative rather than `status` — nothing
marks an aged export expired, so a stale `ready` one signs a dead link. `retry()` rebuilds a
failed or expired export for free; a plain re-`download()` would be a new purchase.

### Money is strings

`price_per_1000`, `amount`, `balance`, `billed_amount` and `price_per_1000_at_open` come back as
quantized decimal strings and are returned **verbatim**. Do not `float()` them: you reconcile
them against the credit ledger, and a float round-trip is how a sub-cent charge stops matching.
(This is deliberately the opposite call from `usageTotalUsd`, which is a float.)

### Your owned index

A pool-backed dataset only delivers creators you do not already have, which it works out from an
index you upload.

```python
feed.upload_owned_index("index_handles.txt")     # presigned PUT, then queues the load
feed.get()["owned_index"]["latest_load"]         # the only place the outcome shows up
```

A refused load **replaces the live index anyway** — `index_missing`, `index_too_small`,
`index_skip_rate` and `index_shrunk` all mean the same thing: re-upload.

### Pace

```python
feed.update_config(daily_quota=2500, batch_size=1000)
```

Only those two are writable. `band`, `ack_ttl_hours` and `is_active` are read-only and the server
drops them silently, so passing one raises `ValidationError` here rather than answering 200
having changed nothing.

`feed.get()` returns the overview — config, pool depth, quota, open batch, quote. It is **not a
free status poll**: the server settles a batch that is due on the way past, which can move money.

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

HTTP-level problems raise; a job that fails does **not** — like Apify, `call()` returns the run
dict with `status: "FAILED"` (see [polling](#poll-on-isterminal-not-on-status)).

```python
from gofetch import (
    GoFetchClient,
    GoFetchError,
    AuthenticationError,
    RateLimitError,
    APIError,
)

try:
    client = GoFetchClient(api_key="sk_scr_xxx")
    run = client.actor("instagram").call(run_input={...})

except AuthenticationError:
    print("Invalid API key")

except RateLimitError as e:
    print(f"Rate limited. Retry after {e.retry_after} seconds")

except APIError as e:
    print(f"API rejected the request: {e.status_code} {e.message}")   # e.g. 400 on bad config

except GoFetchError as e:
    print(f"GoFetch error: {e.message}")

if run["status"] != "SUCCEEDED":
    print("Job did not succeed:", run["_gofetch_job"].get("error_message"))
```

### Dataset errors

Three `APIError` subclasses carry the structured data the datasets API sends with a refusal, so
`except APIError` still catches all of them.

```python
from gofetch import BatchExpiredError, DatasetConflictError, InsufficientCreditsError

try:
    receipt = feed.download()

except InsufficientCreditsError as e:          # 402 — nothing was billed
    print(e.constraints)                       # [{"code": "insufficient_credits", "message": …}]

except DatasetConflictError as e:              # 409
    if e.code == "dataset_paused":
        ...                                    # un-pause, then retry under the same key
    elif e.code == "download_in_progress":
        ...                                    # do NOT retry: the purchase may have landed

except BatchExpiredError:                      # 410 on rows() — nothing was billed
    ...                                        # pull again
```

`e.code` is the API's `errors.code`, and is `None` on the 409s that do not send one — branch on
the status first and treat the code as enrichment. `e.quote` carries the fresh quote on
`quote_stale`; it is deliberately absent on `download_in_progress`, `ledger_conflict`,
`idempotency_key_reused` and `unsupported_format`, so never assume it is there. `e.details`
carries `constraints`, `quote` and `supported_formats` when the response had them.

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
