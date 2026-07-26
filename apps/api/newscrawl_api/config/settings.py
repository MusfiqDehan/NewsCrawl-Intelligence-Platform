"""Environment-driven application settings (pydantic-settings)."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    newscrawl_env: str = "local"

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://newscrawl:newscrawl-local-dev@localhost:5433/newscrawl",
    )
    database_pool_size: int = 10
    database_max_overflow: int = 10

    # ── Redis ────────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6380/0"

    # ── Object storage ───────────────────────────────────────────────────────
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "newscrawl"
    s3_secret_key: str = "newscrawl-local-dev"  # noqa: S105 - dev default, overridden by env
    s3_bucket_raw_html: str = "newscrawl-raw-html"
    s3_region: str = "us-east-1"

    # ── API / auth ───────────────────────────────────────────────────────────
    api_host: str = "0.0.0.0"  # noqa: S104
    api_port: int = 8000
    jwt_secret_key: str = "local-dev-secret-change-me"  # noqa: S105 - dev default
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 14
    cors_allowed_origins: str = "http://localhost:3000"

    admin_email: str = "admin@newscrawl.dev"
    admin_password: str = "admin-local-dev"  # noqa: S105 - dev default

    # ── LLM ──────────────────────────────────────────────────────────────────
    llm_provider: str = "gemini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    openai_api_key: str = ""
    openai_model: str = "gpt-5.2-mini"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5"
    # DeepSeek (OpenAI-compatible): https://api.deepseek.com
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com"
    ollama_base_url: str = "http://localhost:11434"
    # 1.5b is the practical CPU default under load; use 3b+ when RAM/GPU allow.
    ollama_model: str = "qwen2.5:1.5b"
    llm_fallback_providers: str = "deepseek,ollama"
    llm_timeout_seconds: float = 60.0
    llm_max_retries: int = 3

    # ── Embeddings ───────────────────────────────────────────────────────────
    embedding_model: str = "BAAI/bge-m3"
    embedding_dimension: int = 1024
    embedding_device: str = "cpu"
    embedding_version: int = 1
    # When set (prod), API query encode goes to the embedding worker HTTP server
    # instead of loading sentence-transformers in the API process.
    embedding_service_url: str = ""
    embedding_service_port: int = 8081

    # ── Crawler ──────────────────────────────────────────────────────────────
    crawler_user_agent: str = "NewsCrawlBot/0.1 (+https://newscrawl.musfiqdehan.com/bot)"
    crawler_max_concurrency: int = 8
    frontier_lease_seconds: int = 300
    frontier_max_retries: int = 5

    # ── Observability ────────────────────────────────────────────────────────
    log_level: str = "INFO"
    metrics_port: int = 9100

    # ── Article retention ────────────────────────────────────────────────────
    # Delete articles older than this age; scheduler wakes this often.
    # Short wake interval keeps the live corpus inside the 24h window.
    article_retention_hours: int = 24
    article_retention_interval_minutes: int = 5
    # Legacy alias (hours). Used only when minutes is unset/zero.
    article_retention_interval_hours: float = 0

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @property
    def sync_database_url(self) -> str:
        """psycopg/synchronous URL (used by Alembic offline mode and scripts)."""
        return self.database_url.replace("+asyncpg", "")


@lru_cache
def get_settings() -> Settings:
    return Settings()
