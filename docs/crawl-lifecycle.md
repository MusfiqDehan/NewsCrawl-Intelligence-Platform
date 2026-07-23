# Crawl Lifecycle

Two state machines drive the crawl plane: **crawl jobs** (operator-facing
units of work) and **frontier URLs** (individual pages).

## Crawl job state machine

```
created ──► queued ──► running ──► completed
               │          │  ▲
               │          ▼  │
               │        paused
               │          │
               └──────────┴──► cancelled          running ──► failed
```

- Transitions are enforced by `CrawlJobService.transition` — illegal moves
  raise `InvalidTransitionError` and nothing is written.
- `pause`/`resume`/`cancel` are API endpoints; workers observe them via Redis
  pub/sub control signals (no polling of the jobs table mid-pass).
- Every job carries live counters (`pages_discovered/requested/successful/
  failed/skipped/changed/unchanged`, `error_count`, `last_error`) incremented
  atomically by pipelines as items flow.

Job types: `full_crawl`, `incremental_crawl`, `section_crawl`, `url_crawl`,
`retry_failed`, `backfill`.

## Frontier URL state machine

The frontier is the `crawl_urls` table (PostgreSQL — ADR #1). Every URL is
normalized (per-source rules) and hashed; `url_hash` is unique, so a URL can
exist only once regardless of how many times it is discovered.

```
discovered ─► queued ─► leased ─► crawling ─► success
                ▲          │                     │
                │          │ lease expires       │ content change detected later
                │          ▼ (reaper)            ▼ (update detection re-queues)
                └────── queued              queued (recrawl at next_crawl_at)

crawling ─► retry_pending ─(backoff elapsed)─► queued      (transient failures)
crawling ─► failed                                          (attempts exhausted)
crawling ─► blocked                                         (robots / 403-hard)
queued   ─► skipped                                         (filtered before fetch)
```

- **Leasing:** workers claim batches with
  `UPDATE … WHERE id IN (SELECT … FOR UPDATE SKIP LOCKED)` setting
  `lease_owner` + `lease_expires_at`; concurrent workers never collide. A
  reaper returns expired leases to `queued` (crash recovery).
- **Retry backoff:** exponential with jitter, per failure category;
  categories (`network`, `http_4xx`, `http_5xx`, `parse_error`,
  `robots_restricted`, `browser_failure`, …) decide retryability and budget.
- **Priority:** score computed from URL type (article > section > sitemap),
  freshness boost, and depth penalty; claims are ordered by
  `(priority DESC, next_crawl_at)`.
- **Incremental recrawl:** `etag` / `last_modified` stored per URL and sent as
  conditional headers — a 304 short-circuits the whole pipeline; otherwise the
  content hash gates reprocessing and `next_crawl_at` follows an adaptive
  schedule per source.

## One page, end to end

1. Discovery (sitemap/RSS/section parse) inserts the normalized URL —
   `discovered/queued`.
2. A crawl worker leases it, fetches (HTTP first; Playwright when
   `requires_browser` or runtime detection demands), extracts with the
   source's selector set.
3. Pipelines write raw HTML to MinIO, update the frontier row
   (`success` + scheduling metadata), and publish a `RawPageMessage` to
   `processing:cleaning`.
4. The processing plane takes over — see
   [deduplication.md](deduplication.md) and the processor docs.
