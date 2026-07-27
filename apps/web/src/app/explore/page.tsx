"use client";

import { SearchIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import {
  Badge,
  Button,
  EmptyState,
  ErrorState,
  Input,
  Select,
  Spinner,
  StatusBadge,
} from "@/components/ui";
import { usePublicSemanticSearch } from "@/lib/hooks";
import { detectQueryLanguage } from "@/lib/language";

export default function PublicSearchPage() {
  const [input, setInput] = useState("");
  const [query, setQuery] = useState("");
  const [language, setLanguage] = useState("");
  const [languageTouched, setLanguageTouched] = useState(false);
  const [detectedInput, setDetectedInput] = useState(input);

  const { data, isFetching, error } = usePublicSemanticSearch(
    query,
    language || undefined,
  );

  // Adjust `language` in response to `input` changing — done during render (React's
  // sanctioned pattern for this) rather than in an effect, since it only needs to
  // re-run when input itself changes, not as a reaction requiring a commit.
  if (input !== detectedInput) {
    setDetectedInput(input);
    if (!languageTouched) {
      const detected = detectQueryLanguage(input);
      if (detected) setLanguage(detected);
    }
  }

  return (
    <div className="space-y-6">
      <div className="nc-rise">
        <h1 className="font-[family-name:var(--font-display)] text-2xl font-bold text-slate-900 dark:text-white">
          Semantic Search
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Search Bangla and English news by meaning — no account required. Bangla
          queries stay scoped to Bangla articles.
        </p>
      </div>

      <form
        className="flex flex-wrap gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (!languageTouched) {
            const detected = detectQueryLanguage(input);
            if (detected) setLanguage(detected);
          }
          setQuery(input.trim());
        }}
      >
        <Input
          placeholder="e.g. প্রশ্নফাঁস or flood relief…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          className="min-w-[16rem] flex-1"
        />
        <Select
          value={language}
          onChange={(e) => {
            setLanguageTouched(true);
            setLanguage(e.target.value);
          }}
        >
          <option value="">All languages</option>
          <option value="bn">Bangla</option>
          <option value="en">English</option>
        </Select>
        <Button type="submit" disabled={input.trim().length < 2}>
          <SearchIcon className="h-4 w-4" /> Search
        </Button>
      </form>

      {error && <ErrorState message={(error as Error).message} />}
      {isFetching && <Spinner />}

      {data && !isFetching && data.results.length === 0 && (
        <EmptyState message="No matching articles found" />
      )}

      {data && !isFetching && data.results.length > 0 && (
        <div className="nc-stagger space-y-3">
          {data.results.map(({ article, similarity }) => (
            <Link
              key={article.id}
              href={`/explore/articles/${article.id}`}
              className="block rounded-xl border border-slate-200 bg-white p-4 transition-all duration-150 hover:-translate-y-0.5 hover:border-slate-300 hover:bg-slate-50 hover:shadow-sm dark:border-slate-800 dark:bg-slate-900/60 dark:hover:border-slate-700 dark:hover:bg-slate-900"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <h3 className="font-medium text-slate-900 dark:text-white">
                    {article.title}
                  </h3>
                  {article.summary && (
                    <p className="mt-1 line-clamp-2 text-sm text-slate-500 dark:text-slate-400">
                      {article.summary}
                    </p>
                  )}
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1.5">
                  <Badge color="blue">{(similarity * 100).toFixed(1)}%</Badge>
                  <StatusBadge status={article.language} />
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
