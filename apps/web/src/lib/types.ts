export interface TokenResponse {
  access_token: string;
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

export interface Source {
  id: string;
  name: string;
  slug: string;
  base_url: string;
  language: string;
  enabled: boolean;
  crawl_enabled: boolean;
  requires_browser: boolean;
  crawl_frequency_minutes: number;
}

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
