"use client";

import { formatDistanceToNow } from "date-fns";
import { Globe, Monitor } from "lucide-react";

import {
  Badge,
  EmptyState,
  ErrorState,
  Spinner,
  StatusBadge,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { useSourceHealth } from "@/lib/hooks";
import { formatNumber } from "@/lib/utils";

export default function SourcesPage() {
  const { data, isLoading, error } = useSourceHealth();

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold text-white">Source Health</h1>

      {error && <ErrorState message={(error as Error).message} />}
      {isLoading && <Spinner />}
      {data && data.length === 0 && <EmptyState message="No sources configured" />}

      {data && data.length > 0 && (
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
              <tr key={s.source_id} className="hover:bg-slate-900/50">
                <Td>
                  <div className="font-medium text-white">{s.name}</div>
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
                    <span className="inline-flex items-center gap-1 text-xs text-slate-400">
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
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </div>
  );
}
