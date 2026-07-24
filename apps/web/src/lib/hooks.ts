"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./api";
import type {
  ArticleDetail,
  ArticleList,
  CrawlJob,
  CrawlJobList,
  Overview,
  QueueDepths,
  ScoredArticle,
  SemanticSearchResult,
  Source,
  SourceHealth,
  Worker,
} from "./types";

export function useOverview() {
  return useQuery({
    queryKey: ["overview"],
    queryFn: () => api<Overview>("/stats/overview"),
    refetchInterval: 15_000,
  });
}

export function useSourceHealth() {
  return useQuery({
    queryKey: ["source-health"],
    queryFn: () => api<SourceHealth[]>("/stats/sources"),
    refetchInterval: 30_000,
  });
}

export function useSources() {
  return useQuery({
    queryKey: ["sources"],
    queryFn: () => api<Source[]>("/sources"),
  });
}

export function useJobs(status?: string) {
  return useQuery({
    queryKey: ["jobs", status],
    queryFn: () =>
      api<CrawlJobList>("/crawl-jobs", { params: { status, limit: 50 } }),
    refetchInterval: 10_000,
  });
}

export function useJobAction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, action }: { id: string; action: "pause" | "resume" | "cancel" }) =>
      api<CrawlJob>(`/crawl-jobs/${id}/${action}`, { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["jobs"] }),
  });
}

export function useCreateJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { source_id: string; job_type: string; priority?: number }) =>
      api<CrawlJob>("/crawl-jobs", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["jobs"] }),
  });
}

export function useArticles(params: {
  source_id?: string;
  language?: string;
  q?: string;
  page: number;
}) {
  return useQuery({
    queryKey: ["articles", params],
    queryFn: () => api<ArticleList>("/articles", { params: { ...params, page_size: 20 } }),
    placeholderData: (prev) => prev,
  });
}

export function useArticle(id: string) {
  return useQuery({
    queryKey: ["article", id],
    queryFn: () => api<ArticleDetail>(`/articles/${id}`),
  });
}

export function useSimilarArticles(id: string) {
  return useQuery({
    queryKey: ["similar", id],
    queryFn: () => api<ScoredArticle[]>(`/articles/${id}/similar`),
    retry: false,
  });
}

export function useSemanticSearch(q: string, language?: string) {
  return useQuery({
    queryKey: ["semantic-search", q, language],
    queryFn: () => api<SemanticSearchResult>("/search/semantic", { params: { q, language } }),
    enabled: q.trim().length >= 2,
    staleTime: 60_000,
  });
}

/** Unauthenticated explore surface — never attaches a bearer token. */
export function usePublicSemanticSearch(q: string, language?: string) {
  return useQuery({
    queryKey: ["public-semantic-search", q, language],
    queryFn: () =>
      api<SemanticSearchResult>("/public/search/semantic", {
        params: { q, language },
        skipAuth: true,
      }),
    enabled: q.trim().length >= 2,
    staleTime: 60_000,
  });
}

export function usePublicArticles(params: {
  language?: string;
  q?: string;
  page: number;
}) {
  return useQuery({
    queryKey: ["public-articles", params],
    queryFn: () =>
      api<ArticleList>("/public/articles", {
        params: { ...params, page_size: 20 },
        skipAuth: true,
      }),
    placeholderData: (prev) => prev,
  });
}

export function usePublicArticle(id: string) {
  return useQuery({
    queryKey: ["public-article", id],
    queryFn: () =>
      api<ArticleDetail>(`/public/articles/${id}`, { skipAuth: true }),
    enabled: Boolean(id),
  });
}

export function usePublicSimilarArticles(id: string) {
  return useQuery({
    queryKey: ["public-similar", id],
    queryFn: () =>
      api<ScoredArticle[]>(`/public/articles/${id}/similar`, { skipAuth: true }),
    enabled: Boolean(id),
    retry: false,
  });
}

export function useWorkers() {
  return useQuery({
    queryKey: ["workers"],
    queryFn: () => api<Worker[]>("/workers"),
    refetchInterval: 10_000,
  });
}

export function useQueues() {
  return useQuery({
    queryKey: ["queues"],
    queryFn: () => api<QueueDepths>("/queues"),
    refetchInterval: 10_000,
  });
}
