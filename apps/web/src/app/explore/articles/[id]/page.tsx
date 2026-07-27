"use client";

import { format } from "date-fns";
import { ArrowLeft, ExternalLink } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import {
  Badge,
  Card,
  CardTitle,
  ErrorState,
  Spinner,
  StatusBadge,
} from "@/components/ui";
import { usePublicArticle, usePublicSimilarArticles } from "@/lib/hooks";
import { formatNumber } from "@/lib/utils";

export default function PublicArticleDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { data: article, isLoading, error } = usePublicArticle(id);
  const similar = usePublicSimilarArticles(id);

  if (isLoading) return <Spinner />;
  if (error) return <ErrorState message={(error as Error).message} />;
  if (!article) return null;

  return (
    <div className="space-y-6">
      <Link
        href="/explore/articles"
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
      >
        <ArrowLeft className="h-4 w-4" /> Back to browse
      </Link>

      <div className="nc-fade-in grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <div>
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <StatusBadge status={article.language} />
              {article.sentiment && (
                <Badge color="yellow">{article.sentiment}</Badge>
              )}
              {article.event_type && (
                <Badge color="blue">{article.event_type}</Badge>
              )}
              {article.political_category && (
                <Badge color="purple">{article.political_category}</Badge>
              )}
            </div>
            <h1 className="font-[family-name:var(--font-display)] text-2xl font-semibold leading-snug text-slate-900 dark:text-white">
              {article.title}
            </h1>
            {article.subtitle && (
              <p className="mt-2 text-lg text-slate-500 dark:text-slate-400">
                {article.subtitle}
              </p>
            )}
            <div className="mt-3 flex flex-wrap items-center gap-2 text-sm text-slate-500">
              {article.author && <span>{article.author}</span>}
              {article.published_at && (
                <span>· {format(new Date(article.published_at), "PPp")}</span>
              )}
              <a
                href={article.canonical_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-sky-600 hover:text-sky-500 dark:text-sky-400 dark:hover:text-sky-300"
              >
                · original <ExternalLink className="h-3 w-3" />
              </a>
            </div>
          </div>

          {article.summary && (
            <Card>
              <CardTitle>Summary</CardTitle>
              <p className="text-sm leading-relaxed text-slate-700 dark:text-slate-300">
                {article.summary}
              </p>
            </Card>
          )}

          <Card>
            <CardTitle>Article</CardTitle>
            <div className="max-h-[40rem] space-y-4 overflow-y-auto whitespace-pre-line text-sm leading-relaxed text-slate-700 dark:text-slate-300">
              {article.body}
            </div>
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <CardTitle>Details</CardTitle>
            <dl className="space-y-2 text-sm">
              {[
                ["Category", article.category ?? "—"],
                ["Words", formatNumber(article.word_count)],
                ["Published", article.published_at
                  ? format(new Date(article.published_at), "PP")
                  : "—"],
              ].map(([label, value]) => (
                <div key={label} className="flex justify-between gap-2">
                  <dt className="text-slate-500">{label}</dt>
                  <dd className="text-right text-slate-700 dark:text-slate-300">
                    {value}
                  </dd>
                </div>
              ))}
            </dl>
            {article.tags.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {article.tags.map((tag) => (
                  <Badge key={tag} color="gray">
                    {tag}
                  </Badge>
                ))}
              </div>
            )}
          </Card>

          <Card>
            <CardTitle>Similar articles</CardTitle>
            {similar.isLoading && <Spinner />}
            {similar.isError && (
              <p className="text-sm text-slate-500">Not available yet</p>
            )}
            {similar.data && similar.data.length === 0 && (
              <p className="text-sm text-slate-500">No similar articles</p>
            )}
            <div className="space-y-3">
              {similar.data?.map(({ article: a, similarity }) => (
                <Link
                  key={a.id}
                  href={`/explore/articles/${a.id}`}
                  className="block rounded-lg border border-slate-200 p-3 transition-all duration-150 hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-sm dark:border-slate-800 dark:hover:border-slate-700"
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="line-clamp-2 text-sm text-slate-700 dark:text-slate-300">
                      {a.title}
                    </span>
                    <Badge color="blue">{(similarity * 100).toFixed(0)}%</Badge>
                  </div>
                </Link>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
