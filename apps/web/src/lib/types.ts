export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in_minutes: number;
}

export interface User {
  id: string;
  email: string;
  role: "admin" | "operator" | "viewer";
  is_active: boolean;
  created_at: string;
}

export interface SelectorSet {
  title: string[];
  subtitle: string[];
  author: string[];
  published_at: string[];
  category: string[];
  body: string[];
  images: string[];
  tags: string[];
  body_probe: string | null;
}

export interface Source {
  id: string;
  name: string;
  slug: string;
  base_url: string;
  language: string;
  country: string;
  enabled: boolean;
  crawl_enabled: boolean;
  allowed_domains: string[];
  article_url_patterns: string[];
  section_urls: string[];
  sitemap_urls: string[];
  rss_urls: string[];
  crawl_frequency_minutes: number;
  rate_limit_delay_seconds: number;
  max_concurrency: number;
  requires_browser: boolean;
  extraction_strategy: string;
  robots_policy: string;
  source_weight: number;
  url_normalization: Record<string, unknown>;
  selectors: SelectorSet | null;
}

/** POST /sources payload — mirrors the backend's SourceCreate schema. */
export type SourceCreatePayload = Omit<
  Source,
  "id" | "url_normalization"
> & {
  url_normalization?: Record<string, unknown>;
};

/** PATCH /sources/{id} payload — every field optional. */
export type SourceUpdatePayload = Partial<SourceCreatePayload>;

export type CrawlJobStatus =
  | "created"
  | "queued"
  | "running"
  | "paused"
  | "completed"
  | "failed"
  | "cancelled";

export type CrawlJobType =
  | "full_crawl"
  | "incremental_crawl"
  | "section_crawl"
  | "url_crawl"
  | "retry_failed"
  | "backfill";

export interface CrawlJob {
  id: string;
  source_id: string;
  job_type: CrawlJobType;
  status: CrawlJobStatus;
  priority: number;
  params: Record<string, unknown>;
  created_by: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  pages_discovered: number;
  pages_requested: number;
  pages_successful: number;
  pages_failed: number;
  pages_skipped: number;
  pages_changed: number;
  pages_unchanged: number;
  error_count: number;
  last_error: string | null;
}

export interface CrawlJobList {
  items: CrawlJob[];
  total: number;
  limit: number;
  offset: number;
}

export interface ArticleSummary {
  id: string;
  source_id: string;
  canonical_url: string;
  title: string;
  subtitle: string | null;
  author: string | null;
  category: string | null;
  language: string;
  published_at: string | null;
  summary: string | null;
  word_count: number;
  sentiment: string | null;
  event_type: string | null;
  political_category: string | null;
  duplicate_of: string | null;
  current_version: number;
  created_at: string;
}

export interface ArticleDetail extends ArticleSummary {
  body: string;
  image_urls: string[];
  tags: string[];
  content_hash: string;
  extraction_confidence: number;
  updated_at_source: string | null;
}

export interface ArticleList {
  items: ArticleSummary[];
  total: number;
  page: number;
  page_size: number;
}

export interface ScoredArticle {
  article: ArticleSummary;
  similarity: number;
}

export interface SemanticSearchResult {
  query: string;
  results: ScoredArticle[];
}

export interface Overview {
  total_articles: number;
  articles_last_24h: number;
  total_sources: number;
  enabled_sources: number;
  active_jobs: number;
  frontier: Record<string, number>;
  articles_by_language: Record<string, number>;
  articles_per_day: { day: string; count: number }[];
  llm_cost_usd_total: number;
  llm_tokens_total: number;
}

export interface SentimentBucket {
  sentiment: string;
  count: number;
}

export interface SourceHealth {
  source_id: string;
  name: string;
  slug: string;
  language: string;
  enabled: boolean;
  requires_browser: boolean;
  articles_total: number;
  articles_last_24h: number;
  urls_queued: number;
  urls_success: number;
  urls_failed: number;
  last_article_at: string | null;
}

export interface Worker {
  worker_id: string;
  worker_type: string;
  status: string;
  hostname: string;
  pid: number;
  last_beat_age_seconds: number;
  alive: boolean;
  meta: Record<string, unknown>;
}

export interface QueueDepths {
  streams: Record<string, number>;
  delayed: number;
  dead_letter: number;
}

export interface RetentionDayPoint {
  day: string;
  articles_deleted: number;
  cycles: number;
  raw_html_deleted: number;
}

export interface RetentionCycle {
  id: number;
  started_at: string;
  finished_at: string;
  cutoff_at: string;
  retention_hours: number;
  articles_deleted: number;
  batches: number;
  raw_html_deleted: number;
  by_language: Record<string, number>;
  by_source: Record<string, number>;
  status: string;
  error_message: string | null;
  duration_seconds: number;
}

export interface RetentionStats {
  retention_hours: number;
  interval_minutes: number;
  total_deleted: number;
  deleted_last_24h: number;
  deleted_today: number;
  cycles_today: number;
  live_articles: number;
  overdue_live_articles: number;
  last_cycle_at: string | null;
  last_cycle_deleted: number;
  estimated_deleted_before_tracking: number;
  deleted_per_day: RetentionDayPoint[];
  by_language: { language: string; articles_deleted: number }[];
  by_source: {
    source_id: string;
    source_name: string;
    source_slug: string;
    articles_deleted: number;
  }[];
  recent_cycles: RetentionCycle[];
}
