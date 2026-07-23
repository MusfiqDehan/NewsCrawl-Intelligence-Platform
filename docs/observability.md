# Observability

Three pillars: structured JSON logs, Prometheus metrics, Grafana dashboards.

## Structured logging

All planes (API, crawler, processor) share one structlog configuration
(`newscrawl_api.observability.configure_logging`):

- **JSON to stderr** when not attached to a TTY (containers, systemd) — pretty
  console rendering during local development.
- Every line carries `timestamp` (ISO, UTC), `level`, `service`, `event`, plus
  bound context (`worker_id`, `source`, `crawl_job_id`, `url`, `error`, …).
- In production, Promtail tails container JSON logs into Loki; no extra log
  shipping code is needed.

Example line:

```json
{"event": "page_processed", "url": "https://…", "action": "created", "service": "processor", "level": "info", "timestamp": "2026-07-23T09:00:00Z"}
```

## Prometheus metrics

| Plane | Exposure | Port |
| --- | --- | --- |
| API | `GET /api/v1/metrics` | 8000 |
| Crawler worker | exporter started by the `PrometheusStatsExtension` Scrapy extension | 9101 (`CRAWLER_METRICS_PORT`) |
| Cleaning worker | exporter started at worker boot | 9102 (`PROCESSOR_METRICS_PORT`) |
| LLM worker | 〃 | 9103 |
| Embedding worker | 〃 | 9104 |

### API plane

- `newscrawl_http_requests_total{method,path,status}` / `newscrawl_http_request_duration_seconds{method,path}` —
  recorded by a pure-ASGI middleware; `path` is the route template so
  cardinality stays bounded.
- Platform gauges refreshed every 15 s by a lifespan background task:
  `newscrawl_queue_depth{stream}`, `newscrawl_delayed_jobs`,
  `newscrawl_dead_letter_messages`, `newscrawl_frontier_urls{status}`,
  `newscrawl_workers_alive{worker_type}`, `newscrawl_articles_total`.

### Crawl plane (`newscrawl_crawler.extensions.PrometheusStatsExtension`)

- `newscrawl_crawler_responses_total{source,status}`
- `newscrawl_crawler_items_total{source}` — pages that produced an item
- `newscrawl_crawler_errors_total{source}` — spider callback errors
- `newscrawl_crawler_browser_pages_total{source}` — Playwright fetches
- `newscrawl_crawler_spider_passes_total{source,reason}`
- `newscrawl_crawler_last_pass{source,stat}` — snapshot of key Scrapy stats
  (requests, responses, items, log_errors, browser_retries, elapsed_seconds)

### Processing plane (`newscrawl_processor.metrics`)

- `newscrawl_processor_messages_total{worker,outcome}` — outcomes:
  `created|updated|unchanged|duplicate|unusable|malformed|retried|dead_letter|analyzed|failed|embedded|missing`
- `newscrawl_processor_duration_seconds{worker}` — per-message latency histogram
- `newscrawl_llm_tokens_total{provider,kind}` / `newscrawl_llm_cost_usd_total{provider}`
- `newscrawl_embeddings_total{kind}` / `newscrawl_duplicates_total{method}`

## Grafana

Two provisioned dashboards in `infrastructure/grafana/dashboards/`:

- **NewsCrawl — Crawl Operations** (`newscrawl-crawl-ops`): article/frontier
  stats, response codes, per-source throughput, browser usage, API traffic and
  p95 latency.
- **NewsCrawl — Processing & LLM** (`newscrawl-processing`): queue depths,
  message outcomes, processing latency, embedding/dup rates, token and cost
  burn-down.

Local: `make dev` runs Prometheus (`:9090`) + Grafana (`:3001`, admin/admin)
with these dashboards auto-provisioned. Production: add the scrape snippet in
`infrastructure/prometheus/` to the central monitoring stack.

## Analytics API

Aggregates computed in PostgreSQL, served under `/api/v1/stats/*` (auth
required) — these back the Next.js dashboard:

- `GET /stats/overview` — articles, sources, jobs, frontier, per-day counts, LLM spend
- `GET /stats/sources` — per-source health (articles, frontier state, last article)
- `GET /stats/timeseries?days=N` — per-day per-source article counts
- `GET /stats/entities/top` / `GET /stats/topics/top` — most-mentioned entities/topics
- `GET /stats/sentiment` — sentiment distribution
- `GET /stats/llm/daily?days=N` — daily LLM extractions/tokens/cost per provider
