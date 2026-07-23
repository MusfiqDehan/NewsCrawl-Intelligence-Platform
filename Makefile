# ─────────────────────────────────────────────────────────────────────────────
# NewsCrawl Intelligence Platform
# ─────────────────────────────────────────────────────────────────────────────
SHELL := /bin/bash
COMPOSE_LOCAL := docker compose --env-file env.local -f docker-compose.local.yml
COMPOSE_PROD  := docker compose --env-file env.prod -f docker-compose.prod.yml

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ── Setup ─────────────────────────────────────────────────────────────────────
.PHONY: install
install: ## Install Python workspace + web dependencies
	uv sync --all-packages
	@if [ -f apps/web/package.json ]; then cd apps/web && pnpm install; fi

env.local:
	cp env.local.example env.local

# ── Local development ─────────────────────────────────────────────────────────
.PHONY: dev
dev: env.local ## Start local infrastructure (postgres, redis, minio, prometheus, grafana)
	$(COMPOSE_LOCAL) up -d

.PHONY: dev-down
dev-down: ## Stop local infrastructure
	$(COMPOSE_LOCAL) down

.PHONY: dev-logs
dev-logs: ## Tail local infrastructure logs
	$(COMPOSE_LOCAL) logs -f

.PHONY: dev-clean
dev-clean: ## Stop local infrastructure and remove volumes (DESTRUCTIVE)
	$(COMPOSE_LOCAL) down -v

.PHONY: api
api: ## Run FastAPI dev server on the host
	set -a && source env.local && set +a && \
	uv run uvicorn newscrawl_api.main:app --reload --host 0.0.0.0 --port 8000

.PHONY: web
web: ## Run Next.js dev server on the host
	cd apps/web && pnpm dev

.PHONY: crawl
crawl: ## Run a crawl worker on the host (SOURCE=<slug> optional)
	set -a && source env.local && set +a && \
	uv run python -m newscrawl_crawler.run_worker $(if $(SOURCE),--source $(SOURCE),)

.PHONY: worker
worker: ## Run a processing worker on the host (STAGE=cleaning|llm|embedding|all)
	set -a && source env.local && set +a && \
	uv run python -m newscrawl_processor.main --stage $(or $(STAGE),all)

.PHONY: seed
seed: ## Seed database with sources and the initial admin user
	set -a && source env.local && set +a && \
	uv run python -m newscrawl_api.seed

# ── Database ──────────────────────────────────────────────────────────────────
.PHONY: migrate
migrate: ## Apply Alembic migrations
	set -a && source env.local && set +a && \
	uv run alembic -c apps/api/alembic.ini upgrade head

.PHONY: migration
migration: ## Autogenerate a migration (MSG="description")
	set -a && source env.local && set +a && \
	uv run alembic -c apps/api/alembic.ini revision --autogenerate -m "$(MSG)"

# ── Quality gates ─────────────────────────────────────────────────────────────
.PHONY: lint
lint: ## Ruff lint + format check (Python) and ESLint (web)
	uv run ruff check .
	uv run ruff format --check .
	@if [ -d apps/web/node_modules ]; then cd apps/web && pnpm lint; fi

.PHONY: format
format: ## Auto-format Python code
	uv run ruff check --fix .
	uv run ruff format .

.PHONY: typecheck
typecheck: ## mypy (Python) and tsc (web)
	uv run mypy apps/api/newscrawl_api apps/crawler/newscrawl_crawler apps/processor/newscrawl_processor packages/contracts/newscrawl_contracts packages/crawler-utils/newscrawl_crawler_utils
	@if [ -d apps/web/node_modules ]; then cd apps/web && pnpm typecheck; fi

.PHONY: test
test: ## Run unit tests (fast, no external services)
	uv run pytest -m "not integration and not e2e" -q

.PHONY: test-integration
test-integration: ## Run integration tests (needs Docker for testcontainers)
	uv run pytest -m integration -q

.PHONY: test-e2e
test-e2e: ## Run the end-to-end pipeline test (needs local Postgres + Redis)
	set -a && source env.local && set +a && uv run pytest -m e2e -q

.PHONY: test-all
test-all: ## Run every test
	uv run pytest -q

.PHONY: check
check: lint typecheck test ## Full local quality gate

# ── Production ────────────────────────────────────────────────────────────────
.PHONY: prod-build
prod-build: ## Build production images
	$(COMPOSE_PROD) build

.PHONY: deploy-prod
deploy-prod: ## Deploy the production stack (requires env.prod + central Traefik running)
	$(COMPOSE_PROD) up -d

.PHONY: prod-down
prod-down: ## Stop the production stack
	$(COMPOSE_PROD) down

.PHONY: prod-migrate
prod-migrate: ## Run migrations inside the prod api container
	$(COMPOSE_PROD) run --rm api alembic -c /app/apps/api/alembic.ini upgrade head
