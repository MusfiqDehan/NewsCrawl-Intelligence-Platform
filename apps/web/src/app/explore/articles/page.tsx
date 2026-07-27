"use client";

import { formatDistanceToNow } from "date-fns";
import { ChevronLeft, ChevronRight } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import {
  Button,
  EmptyState,
  ErrorState,
  Input,
  Select,
  Spinner,
  StatusBadge,
} from "@/components/ui";
import { usePublicArticles } from "@/lib/hooks";
import type { ArticleSummary } from "@/lib/types";
import { formatNumber } from "@/lib/utils";

function ArticleRow({ article }: { article: ArticleSummary }) {
  return (
    <Link
      href={`/explore/articles/${article.id}`}
      className="block rounded-xl border border-slate-200 bg-white p-4 transition-all duration-150 hover:-translate-y-0.5 hover:border-slate-300 hover:bg-slate-50 hover:shadow-sm dark:border-slate-800 dark:bg-slate-900/60 dark:hover:border-slate-700 dark:hover:bg-slate-900"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h3 className="truncate font-medium text-slate-900 dark:text-white">
            {article.title}
          </h3>
          {article.summary && (
            <p className="mt-1 line-clamp-2 text-sm text-slate-500 dark:text-slate-400">
              {article.summary}
            </p>
          )}
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-500">
            {article.author && <span>{article.author}</span>}
            {article.category && <span>· {article.category}</span>}
            <span>· {formatNumber(article.word_count)} words</span>
            {article.published_at && (
              <span>
                ·{" "}
                {formatDistanceToNow(new Date(article.published_at), {
                  addSuffix: true,
                })}
              </span>
            )}
          </div>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1.5">
          <StatusBadge status={article.language} />
          {article.sentiment && (
            <span className="text-xs text-slate-500">{article.sentiment}</span>
          )}
        </div>
      </div>
    </Link>
  );
}

export default function PublicArticlesPage() {
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [language, setLanguage] = useState("");
  const [page, setPage] = useState(1);

  const { data, isLoading, error } = usePublicArticles({
    q: search || undefined,
    language: language || undefined,
    page,
  });

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div className="space-y-4">
      <div className="nc-rise">
        <h1 className="font-[family-name:var(--font-display)] text-2xl font-bold text-slate-900 dark:text-white">
          Browse articles
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Recent Bangla and English coverage from the NewsCrawl corpus.
        </p>
      </div>

      <form
        className="flex flex-wrap gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          setPage(1);
          setSearch(q);
        }}
      >
        <Input
          placeholder="Filter by title…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="w-full sm:w-64"
        />
        <Select
          value={language}
          onChange={(e) => {
            setLanguage(e.target.value);
            setPage(1);
          }}
        >
          <option value="">All languages</option>
          <option value="bn">Bangla</option>
          <option value="en">English</option>
        </Select>
        <Button type="submit" variant="outline">
          Filter
        </Button>
      </form>

      {error && <ErrorState message={(error as Error).message} />}
      {isLoading && <Spinner />}
      {data && data.items.length === 0 && (
        <EmptyState message="No articles found" />
      )}

      {data && data.items.length > 0 && (
        <>
          <div className="text-sm text-slate-500">
            {formatNumber(data.total)} articles
          </div>
          <div className="nc-stagger space-y-3">
            {data.items.map((a) => (
              <ArticleRow key={a.id} article={a} />
            ))}
          </div>
          <div className="flex items-center justify-between pt-2">
            <Button
              variant="outline"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
            >
              <ChevronLeft className="h-4 w-4" /> Previous
            </Button>
            <span className="text-sm text-slate-500">
              Page {page} of {totalPages}
            </span>
            <Button
              variant="outline"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              Next <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
