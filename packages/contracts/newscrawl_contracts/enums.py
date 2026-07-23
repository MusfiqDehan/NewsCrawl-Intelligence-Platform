"""Shared enums used across the control, crawl, and processing planes.

These are stored as plain varchar in PostgreSQL (native_enum=False) so adding
members never requires an ALTER TYPE migration.
"""

from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "admin"
    VIEWER = "viewer"


class CrawlJobStatus(StrEnum):
    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CrawlJobType(StrEnum):
    FULL_CRAWL = "full_crawl"
    INCREMENTAL_CRAWL = "incremental_crawl"
    SECTION_CRAWL = "section_crawl"
    URL_CRAWL = "url_crawl"
    RETRY_FAILED = "retry_failed"
    BACKFILL = "backfill"


class UrlStatus(StrEnum):
    DISCOVERED = "discovered"
    QUEUED = "queued"
    LEASED = "leased"
    CRAWLING = "crawling"
    SUCCESS = "success"
    FAILED = "failed"
    RETRY_PENDING = "retry_pending"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class UrlType(StrEnum):
    HOMEPAGE = "homepage"
    SECTION = "section"
    ARTICLE = "article"
    SITEMAP = "sitemap"
    RSS = "rss"
    OTHER = "other"


class FetchMethod(StrEnum):
    HTTP = "http"
    BROWSER = "browser"


class AttemptOutcome(StrEnum):
    SUCCESS = "success"
    NOT_MODIFIED = "not_modified"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class FailureCategory(StrEnum):
    DNS_FAILURE = "dns_failure"
    CONNECTION_TIMEOUT = "connection_timeout"
    HTTP_403 = "http_403"
    HTTP_429 = "http_429"
    HTTP_5XX = "http_5xx"
    HTTP_OTHER = "http_other"
    ROBOTS_RESTRICTED = "robots_restricted"
    PARSER_FAILURE = "parser_failure"
    BROWSER_FAILURE = "browser_failure"
    DATABASE_FAILURE = "database_failure"
    LLM_FAILURE = "llm_failure"
    EMBEDDING_FAILURE = "embedding_failure"
    UNKNOWN = "unknown"


class WorkerType(StrEnum):
    CRAWLER = "crawler"
    PROCESSOR = "processor"


class WorkerStatus(StrEnum):
    STARTING = "starting"
    RUNNING = "running"
    DRAINING = "draining"
    STOPPED = "stopped"


class ProcessingStage(StrEnum):
    CLEANING = "cleaning"
    LLM_EXTRACTION = "llm_extraction"
    EMBEDDING = "embedding"


class ProcessingStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


class ExtractionMethod(StrEnum):
    SELECTORS = "selectors"
    JSON_LD = "json_ld"
    OPENGRAPH = "opengraph"
    READABILITY = "readability"
    LLM = "llm"


class EntityType(StrEnum):
    PERSON = "person"
    ORGANIZATION = "organization"
    LOCATION = "location"
    EVENT = "event"
    OTHER = "other"


class EmbeddingKind(StrEnum):
    TITLE = "title"
    SUMMARY = "summary"
    BODY = "body"
    ENTITY = "entity"


class Language(StrEnum):
    BANGLA = "bn"
    ENGLISH = "en"
    UNKNOWN = "unknown"
