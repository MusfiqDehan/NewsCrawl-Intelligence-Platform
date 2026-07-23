# NewsCrawl Intelligence Platform

A production-grade, distributed, multilingual (Bangla + English) news crawling and intelligence platform.

It crawls configured news sources (Prothom Alo, Kaler Kantho, Naya Diganta, BBC / BBC Bangla, Al Jazeera — extensible to more), stores raw content in S3-compatible object storage, processes articles through a queue-based pipeline (cleaning → language detection → deduplication → LLM extraction → embeddings), and serves everything through a FastAPI control/query plane and a Next.js operations dashboard with multilingual semantic search.

## Architecture at a glance

```
Next.js dashboard ──► FastAPI (control + query plane)
                          │
        ┌─────────────────┼──────────────────┐
        ▼                 ▼                  ▼
   PostgreSQL 17     Redis 8           MinIO (S3)
   + pgvector        Streams/locks     raw HTML
   frontier,         heartbeats,
   articles, jobs    rate limits
        ▲                 ▲
        │                 │
  Scrapy workers ──► Playwright fallback ──► news websites
        │
        ▼
  Processing workers: clean → langdetect → dedup → LLM (Gemini) → BGE-M3 embeddings
```

Five separated planes: **control** (API), **crawl** (Scrapy + Playwright workers), **processing** (Redis Streams consumers), **query** (API + pgvector search), **observability** (Prometheus + Grafana + structured JSON logs).

Design decisions are documented in [docs/architecture.md](docs/architecture.md) and the other documents under [docs/](docs/).

## Repository layout

```
apps/
  api/         FastAPI app, SQLAlchemy models, Alembic migrations, frontier services
  crawler/     Scrapy project: spiders, middlewares, pipelines, Playwright integration
  processor/   Queue consumers: cleaning, dedup, LLM extraction, embeddings
  web/         Next.js dashboard (App Router, Tailwind, shadcn/ui, TanStack)
packages/
  contracts/       Shared Pydantic contracts (queue messages, enums)
  crawler-utils/   URL normalization, content hashing, SimHash
  shared-types/    TypeScript types shared with the web app
infrastructure/  Docker, Postgres, Redis, Nginx, Prometheus, Grafana, systemd
docs/            Architecture, runbooks, ADRs
```

Python code is a single [uv workspace](https://docs.astral.sh/uv/concepts/workspaces/) — one lockfile, one virtualenv, distinct package names (`newscrawl_api`, `newscrawl_crawler`, `newscrawl_processor`, ...).

## Quick start (local)

Prerequisites: Docker, uv, Node 22+, pnpm.

```bash
cp env.local.example env.local   # adjust if needed (Gemini API key for LLM extraction)
make install                     # Python workspace + web dependencies
make dev                         # postgres, redis, minio, prometheus, grafana
make migrate                     # apply database migrations
make seed                        # seed sources + admin user
make api                         # FastAPI on :8000
make web                         # dashboard on :3000
make crawl                       # crawl worker
make worker                      # processing workers
```

Quality gates:

```bash
make lint
make typecheck
make test               # unit tests
make test-integration   # testcontainers-based integration tests
```

## Environments

| | Local | Production |
|---|---|---|
| Compose file | `docker-compose.local.yml` | `docker-compose.prod.yml` |
| Env file | `env.local` | `env.prod` |
| Edge | direct ports | central Traefik → internal Nginx |
| Domains | `localhost:3000` / `:8000` | `newscrawl.musfiqdehan.com` / `newscrawl-api.musfiqdehan.com` |
| Monitoring | bundled Prometheus + Grafana | central monitoring stack (Prometheus, Grafana, Loki) |

Production deployment details: [docs/deployment.md](docs/deployment.md).

## Documentation

- [docs/architecture.md](docs/architecture.md) — planes, components, design decisions (ADRs)
- [docs/crawl-lifecycle.md](docs/crawl-lifecycle.md) — job + URL state machines
- [docs/deduplication.md](docs/deduplication.md) — staged dedup strategy
- [docs/observability.md](docs/observability.md) — logging, metrics, dashboards, analytics API
- [docs/deployment.md](docs/deployment.md) — production deployment (Traefik + Nginx)
- [docs/runbook.md](docs/runbook.md) — day-2 operations, backup/restore, scaling
- [docs/benchmarks.md](docs/benchmarks.md) — performance notes and bottlenecks

## Legal & operational posture

The crawler respects robots.txt, applies per-domain rate limits, identifies itself with a descriptive User-Agent, and only crawls explicitly configured sources (SSRF-guarded). Designed for authorized data collection and research use.
