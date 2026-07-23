# Performance Notes & Benchmarks

Measured on local development hardware (Linux, 8 vCPU, 16 GB RAM, all services
in Docker on one host) against the live pipeline in July 2026. Numbers are
indicative, not a load-test report; methodology is included so they can be
reproduced with `make dev` + the commands shown.

## Crawl plane

| Metric | Value | Notes |
| --- | --- | --- |
| Frontier claim (batch of 20) | ~5–15 ms | single `UPDATE … SKIP LOCKED` round-trip |
| HTTP article fetch + parse | dominated by politeness delay | 0.5 req/s/domain default token bucket |
| Playwright article fetch | 3–8 s per page | Kaler Kantho (Cloudflare) requires it; images/fonts/ads blocked |
| Spider pass over 5 sources (~100 URLs) | ~4–6 min | bounded by per-domain rate limits, not CPU |

The crawl plane is intentionally politeness-bound: throughput scales with the
number of *sources*, not workers. Adding a second crawl worker halves lease
latency but never exceeds per-domain budgets (shared Redis token bucket).

## Processing plane

Measured over the 62-article seed corpus:

| Stage | Throughput (single worker) | Notes |
| --- | --- | --- |
| Cleaning + persistence | 30–60 msg/s | dominated by Postgres round-trips |
| SimHash dedup lookup | <5 ms/article | 4 banded expression indexes on `articles.simhash` |
| BGE-M3 embedding (CPU) | ~1.5–3 articles/s | batch encode; first call pays ~10 s model load |
| Semantic search query | 30–80 ms warm | pgvector HNSW, 1024-dim, cosine |
| LLM extraction (Gemini Flash) | 2–5 s/article | network-bound; cost ≈ $0.0002–0.0005/article |

## API plane

`newscrawl_http_request_duration_seconds` p95 on the dev box (unloaded):

| Endpoint | p95 |
| --- | --- |
| `/articles` list (filtered, paginated) | <30 ms |
| `/articles/{id}/similar` | <60 ms |
| `/search/semantic` (warm model) | <900 ms (embed query + HNSW scan) |
| `/stats/overview` | <50 ms |

## Reproducing

```bash
make dev && make migrate && make seed
uv run python -m newscrawl_crawler.run_worker --once --max-pages 50
uv run python -m newscrawl_processor.run_worker --once
uv run python -m newscrawl_processor.run_embedding_worker --once
# then read the Grafana dashboards at :3001 or /api/v1/metrics
```

## Known bottlenecks / future work

- **Embedding on CPU** is the processing ceiling; set `EMBEDDING_DEVICE=cuda`
  on GPU hosts (~20× faster for BGE-M3).
- **Playwright memory**: each Chromium context costs ~150–300 MB; the crawler
  container is capped at 2 GB which covers 4 contexts comfortably.
- **HNSW index build** happens per insert (no batch rebuild needed), but bulk
  backfills are faster if the index is created after loading.
