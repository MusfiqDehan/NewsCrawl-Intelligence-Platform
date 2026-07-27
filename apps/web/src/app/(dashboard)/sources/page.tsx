"use client";

import { formatDistanceToNow } from "date-fns";
import { Globe, Monitor, Pencil, Plus } from "lucide-react";
import { useState } from "react";

import {
  Badge,
  Button,
  EmptyState,
  ErrorState,
  Spinner,
  StatusBadge,
  Table,
  Td,
  Th,
  Tr,
} from "@/components/ui";
import { useSourceHealth, useSources } from "@/lib/hooks";
import type { Source } from "@/lib/types";
import { formatNumber } from "@/lib/utils";

import { SourceForm } from "./source-form";

function ManageSources() {
  const { data: sources, isLoading, error } = useSources();
  const [editing, setEditing] = useState<Source | "new" | null>(null);

  return (
    <div className="space-y-4">
      <div className="nc-rise flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Manage sources</h2>
        {editing === null && (
          <Button onClick={() => setEditing("new")}>
            <Plus className="h-4 w-4" /> New source
          </Button>
        )}
      </div>

      {editing !== null && (
        <SourceForm
          source={editing === "new" ? undefined : editing}
          onClose={() => setEditing(null)}
        />
      )}

      {error && <ErrorState message={(error as Error).message} />}
      {isLoading && <Spinner />}
      {sources && sources.length > 0 && (
        <div className="nc-fade-in">
          <Table>
            <thead>
              <tr>
                <Th>Source</Th>
                <Th>Base URL</Th>
                <Th>Frequency</Th>
                <Th>Status</Th>
                <Th>Actions</Th>
              </tr>
            </thead>
            <tbody>
              {sources.map((s) => (
                <Tr key={s.id}>
                  <Td>
                    <div className="font-medium text-slate-900 dark:text-white">{s.name}</div>
                    <div className="text-xs text-slate-500">{s.slug}</div>
                  </Td>
                  <Td className="text-slate-500 dark:text-slate-400">{s.base_url}</Td>
                  <Td className="text-slate-500 dark:text-slate-400">
                    every {s.crawl_frequency_minutes}m
                  </Td>
                  <Td>
                    <Badge color={s.crawl_enabled ? "green" : "gray"}>
                      {s.crawl_enabled ? "crawling" : "paused"}
                    </Badge>
                  </Td>
                  <Td>
                    <Button variant="ghost" title="Edit" onClick={() => setEditing(s)}>
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </div>
      )}
    </div>
  );
}

export default function SourcesPage() {
  const { data, isLoading, error } = useSourceHealth();

  return (
    <div className="space-y-8">
      <ManageSources />

      <h1 className="nc-rise text-xl font-semibold text-slate-900 dark:text-white">
        Source Health
      </h1>

      {error && <ErrorState message={(error as Error).message} />}
      {isLoading && <Spinner />}
      {data && data.length === 0 && <EmptyState message="No sources configured" />}

      {data && data.length > 0 && (
        <div className="nc-fade-in">
          <Table>
            <thead>
              <tr>
                <Th>Source</Th>
                <Th>Language</Th>
                <Th>Fetch</Th>
                <Th>Status</Th>
                <Th className="text-right">Articles</Th>
                <Th className="text-right">Last 24h</Th>
                <Th className="text-right">Queued</Th>
                <Th className="text-right">Crawled OK</Th>
                <Th className="text-right">Failed</Th>
                <Th>Last article</Th>
              </tr>
            </thead>
            <tbody>
              {data.map((s) => (
                <Tr key={s.source_id}>
                  <Td>
                    <div className="font-medium text-slate-900 dark:text-white">{s.name}</div>
                    <div className="text-xs text-slate-500">{s.slug}</div>
                  </Td>
                  <Td>
                    <StatusBadge status={s.language} />
                  </Td>
                  <Td>
                    {s.requires_browser ? (
                      <span className="inline-flex items-center gap-1 text-xs text-violet-400">
                        <Monitor className="h-3.5 w-3.5" /> Browser
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400">
                        <Globe className="h-3.5 w-3.5" /> HTTP
                      </span>
                    )}
                  </Td>
                  <Td>
                    <Badge color={s.enabled ? "green" : "gray"}>
                      {s.enabled ? "enabled" : "disabled"}
                    </Badge>
                  </Td>
                  <Td className="text-right">{formatNumber(s.articles_total)}</Td>
                  <Td className="text-right">
                    {s.articles_last_24h > 0 ? (
                      <span className="text-emerald-400">
                        +{formatNumber(s.articles_last_24h)}
                      </span>
                    ) : (
                      <span className="text-slate-600">0</span>
                    )}
                  </Td>
                  <Td className="text-right">{formatNumber(s.urls_queued)}</Td>
                  <Td className="text-right text-emerald-400">
                    {formatNumber(s.urls_success)}
                  </Td>
                  <Td className="text-right text-rose-400">{formatNumber(s.urls_failed)}</Td>
                  <Td className="text-slate-500">
                    {s.last_article_at
                      ? formatDistanceToNow(new Date(s.last_article_at), { addSuffix: true })
                      : "—"}
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </div>
      )}
    </div>
  );
}
