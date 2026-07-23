# Operations Runbook

Day-2 operations for the NewsCrawl production stack
(`docker-compose.prod.yml` behind the central Traefik).

## Deploy / upgrade

```bash
cd /opt/newscrawl
git pull
make prod-build          # build images
make prod-migrate        # alembic upgrade head (run BEFORE rolling app services)
make deploy-prod         # docker compose up -d
```

First-time setup:

```bash
cp env.prod.example env.prod   # fill in every REPLACE_WITH_* value
sudo cp infrastructure/systemd/newscrawl.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now newscrawl
docker compose --env-file env.prod -f docker-compose.prod.yml run --rm api \
  python -m newscrawl_api.seed    # seed sources + admin user
```

Traefik: no changes needed — the Nginx service carries labels for both
hostnames; make sure DNS for `newscrawl.musfiqdehan.com` and
`newscrawl-api.musfiqdehan.com` points at the Traefik host and the
`traefik_proxy` network exists.

## Health checks

| Check | Command |
| --- | --- |
| API liveness | `curl -s https://newscrawl-api.musfiqdehan.com/api/v1/health` |
| API readiness (PG+Redis) | `curl -s https://newscrawl-api.musfiqdehan.com/api/v1/ready` |
| Container state | `docker compose --env-file env.prod -f docker-compose.prod.yml ps` |
| Worker heartbeats | dashboard → System page, or `GET /api/v1/workers` |
| Queue backlog | dashboard → System page, or `GET /api/v1/queues` |

## Common incidents

### Queue backlog grows, articles stall

1. Check worker liveness (`/api/v1/workers`): a dead consumer leaves pending
   entries; the stale-claim logic re-delivers them after the idle timeout.
2. Check the failing worker's logs:
   `docker logs newscrawl-processor-cleaning-1 --since 15m`
3. Dead-lettered messages appear in the `processing:dead_letter` stream with
   the original payload and last error — inspect with:
   `docker exec newscrawl-redis redis-cli XRANGE processing:dead_letter - + COUNT 10`
4. After fixing the cause, re-publish dead letters to their origin stream (the
   payload carries `origin_stream`).

### A source stops producing articles

1. Dashboard → Sources: is `urls_failed` rising or `last article` stale?
2. Frontier state for that source:
   `SELECT status, failure_category, count(*) FROM crawl_urls WHERE source_id='…' GROUP BY 1,2;`
3. `blocked` + `robots_restricted` → the site changed its robots policy;
   review before overriding anything.
4. `browser_failure` → Playwright/Chromium issue; check crawler memory and the
   `newscrawl_crawler_browser_pages_total` panel.
5. Repeated `parse_error` → site layout changed; update that source's selector
   set and its fixture contract test.

### LLM spend spike

- Grafana → Processing & LLM → token burn-down, or `GET /api/v1/stats/llm/daily`.
- Set `LLM_PROVIDER=ollama` (self-hosted) or pause LLM enrichment by scaling
  the worker to zero: `docker compose … up -d --scale processor-llm=0`.
  Cleaning and embeddings continue; articles keep flowing without enrichment.

### Postgres disk pressure

- Old partitions of `crawl_attempts` / `crawl_events` can be detached and
  dropped by month.
- Raw HTML lives in MinIO, never Postgres; check `minio_data` volume growth
  separately and prune old raw pages if needed (articles keep extracted text).

## Backup and restore

- `postgres-backup` container runs `pg_dump --format=custom` daily into the
  `postgres_backups` volume, retention 14 days (`BACKUP_RETENTION_DAYS`).
- Copy off-host (cron on the host):
  `docker cp newscrawl-postgres-backup:/backups/. /srv/backups/newscrawl/`
- Restore:

```bash
docker compose --env-file env.prod -f docker-compose.prod.yml stop api crawler \
  processor-cleaning processor-llm processor-embedding
docker exec -i newscrawl-postgres pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  --clean --if-exists < newscrawl-<stamp>.dump
docker compose --env-file env.prod -f docker-compose.prod.yml up -d
```

- Redis runs AOF (`appendfsync everysec`) + RDB snapshots (see
  `infrastructure/redis/redis.conf`); loss on crash is ≤1 s of queue state,
  and Postgres remains the source of truth for everything durable.
- MinIO raw HTML: replicate the `minio_data` volume or configure `mc mirror`
  to another target if raw-page retention matters to you.

## Scaling

- More crawl throughput: `docker compose … up -d --scale crawler=2` (each
  worker leases disjoint URL batches via `FOR UPDATE SKIP LOCKED`), or run
  host-level workers with `newscrawl-crawler@.service`.
- Processing: scale `processor-cleaning` / `processor-embedding` the same way;
  Redis consumer groups distribute messages automatically.
- Politeness is enforced globally per domain via the shared Redis token
  bucket, so adding workers never increases per-site request rates.

## Secrets rotation

- `JWT_SECRET_KEY`: rotate in `env.prod`, `docker compose up -d api` — active
  sessions are invalidated.
- DB password: change in Postgres, update `env.prod` (`POSTGRES_PASSWORD` and
  `DATABASE_URL`), restart dependents.
