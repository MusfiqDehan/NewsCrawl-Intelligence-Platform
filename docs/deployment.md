# Production Deployment

Production runs as a single Docker Compose stack (`docker-compose.prod.yml`)
behind the **central Traefik deployment** (the separate `traefik/` repo, which
owns TLS, the `traefik_proxy` network, and the monitoring stack).

## Topology

```
Cloudflare
   │
Central Traefik (traefik_proxy network, TLS, security/compress/ratelimit middlewares)
   │  Host: newscrawl.musfiqdehan.com          Host: newscrawl-api.musfiqdehan.com
   ▼
NewsCrawl Nginx  ←— the ONLY service on traefik_proxy
   │  (fan-out by Host header, buffering, body limits, asset caching)
   ├──► web  (Next.js :3000)          ┐
   ├──► api  (FastAPI  :8000)         │
   │    crawler (Scrapy+Playwright)   │  newscrawl_internal network
   │    processor-cleaning/llm/embed  │  (never exposed to the proxy)
   └──  postgres / redis / minio      ┘
```

- Traefik routes both hostnames to the same Nginx service (`newscrawl-gateway`);
  Nginx disambiguates by `Host` header (`infrastructure/nginx/nginx.conf`).
- Reused central middlewares: `security-headers@file`, `compress@file`, and
  `api-ratelimit@file` on the API router (labels on the nginx service).
- Databases and workers have **no** published ports and no proxy-network
  membership.

## Images

Built from the repo root (`make prod-build`):

| Image | Dockerfile | Contents |
| --- | --- | --- |
| `newscrawl-api` | `infrastructure/docker/Dockerfile.api` | uv-locked venv, uvicorn, non-root |
| `newscrawl-crawler` | `Dockerfile.crawler` | + Playwright Chromium with system deps |
| `newscrawl-processor` | `Dockerfile.processor` | one image, three entrypoints (cleaning/LLM/embedding) |
| `newscrawl-web` | `Dockerfile.web` | Next.js standalone build, `NEXT_PUBLIC_API_URL` baked at build time |

All Python images are two-stage: a `uv sync --frozen` builder layer keyed on
the lockfile, then a slim runtime copying the venv.

## Step-by-step

```bash
# On the server (central Traefik already running):
git clone <repo> /opt/newscrawl && cd /opt/newscrawl
cp env.prod.example env.prod        # fill in EVERY "REPLACE_WITH_*"
make prod-build
make prod-migrate                   # alembic upgrade head
make deploy-prod                    # compose up -d
docker compose --env-file env.prod -f docker-compose.prod.yml run --rm api \
  python -m newscrawl_api.seed      # first boot only: sources + admin user

# Survive reboots:
sudo cp infrastructure/systemd/newscrawl.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now newscrawl
```

DNS: point both hostnames at the Traefik host (Cloudflare proxied entries work
with the origin-cert setup already in the traefik repo).

## Monitoring integration

Prod reuses the central Prometheus/Grafana/Loki:

1. Append `infrastructure/prometheus/newscrawl-scrape-config.yml` to
   `traefik/monitoring/prometheus/prometheus.yml`.
2. Attach central Prometheus to the app network:
   `docker network connect newscrawl_internal prometheus`.
3. Drop `infrastructure/grafana/dashboards/*.json` into the central Grafana's
   dashboard provisioning folder.
4. Logs: all services emit JSON to stdout; the existing Promtail container
   pipeline ships them to Loki unchanged.

## State & durability

- **PostgreSQL** — source of truth (frontier, articles, jobs, embeddings).
  Nightly `pg_dump` via the `postgres-backup` sidecar, 14-day retention
  (`infrastructure/postgres/backup.sh`).
- **Redis** — queues and coordination only; AOF everysec + RDB snapshots
  (`infrastructure/redis/redis.conf`), `noeviction`.
- **MinIO** — raw HTML archive; loss is tolerable (articles keep extracted text).

See [runbook.md](runbook.md) for day-2 operations, scaling, and restores.
