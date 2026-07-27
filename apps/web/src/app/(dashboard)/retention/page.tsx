"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Trash2 } from "lucide-react";

import {
  Badge,
  Card,
  CardTitle,
  EmptyState,
  ErrorState,
  Spinner,
  Table,
  Td,
  Th,
  Tr,
} from "@/components/ui";
import { useRetentionStats } from "@/lib/hooks";
import { useTheme } from "@/lib/theme";
import { formatNumber } from "@/lib/utils";

function Stat({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <Card interactive>
      <div className="text-sm text-slate-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-slate-900 dark:text-white">{value}</div>
      {sub && <div className="mt-1 text-xs text-slate-500">{sub}</div>}
    </Card>
  );
}

function formatTime(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

export default function RetentionPage() {
  const { data, isLoading, error } = useRetentionStats();
  const { resolvedTheme } = useTheme();
  const dark = resolvedTheme === "dark";
  const chart = {
    grid: dark ? "#1e293b" : "#e2e8f0",
    axis: dark ? "#64748b" : "#94a3b8",
    tooltipBg: dark ? "#0f172a" : "#ffffff",
    tooltipBorder: dark ? "#334155" : "#e2e8f0",
    tooltipText: dark ? "#e2e8f0" : "#0f172a",
  };

  if (isLoading) return <Spinner />;
  if (error) return <ErrorState message={(error as Error).message} />;
  if (!data) return <EmptyState message="No retention data yet" />;

  // Reading the wall clock to check staleness is inherently impure; a stale-by-one-render
  // value here has no correctness impact (it's a display badge only), so it's suppressed
  // rather than routed through an effect (which previously caused an infinite render loop).
  const healthy =
    data.last_cycle_at != null &&
    // eslint-disable-next-line react-hooks/purity
    Date.now() - new Date(data.last_cycle_at).getTime() <
      (data.interval_minutes + 2) * 60_000;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold text-slate-900 dark:text-white">
            <Trash2 className="h-5 w-5 text-slate-500 dark:text-slate-400" />
            Deleted Articles
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            Retention audit — articles older than {data.retention_hours}h are
            purged about every {data.interval_minutes} minutes.
          </p>
        </div>
        <Badge color={healthy ? "green" : "yellow"} dot pulse={healthy}>
          {healthy ? "Retention running" : "Waiting for next cycle"}
        </Badge>
      </div>

      <div className="nc-stagger grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat
          label="Total deleted"
          value={formatNumber(data.total_deleted)}
          sub={
            data.estimated_deleted_before_tracking > 0
              ? `+${formatNumber(data.estimated_deleted_before_tracking)} estimated pre-tracking`
              : "tracked purge cycles"
          }
        />
        <Stat
          label="Deleted last 24h"
          value={formatNumber(data.deleted_last_24h)}
          sub={`${formatNumber(data.deleted_today)} today`}
        />
        <Stat
          label="Purge cycles today"
          value={formatNumber(data.cycles_today)}
          sub={
            data.last_cycle_at
              ? `Last: ${formatTime(data.last_cycle_at)} (−${formatNumber(data.last_cycle_deleted)})`
              : "No cycles yet"
          }
        />
        <Stat
          label="Live articles"
          value={formatNumber(data.live_articles)}
          sub={
            data.overdue_live_articles > 0
              ? `${formatNumber(data.overdue_live_articles)} overdue (>${data.retention_hours}h)`
              : `All within ${data.retention_hours}h window`
          }
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardTitle>Deleted per day</CardTitle>
          {data.deleted_per_day.length === 0 ? (
            <EmptyState message="No deletions recorded yet" />
          ) : (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data.deleted_per_day}>
                  <CartesianGrid strokeDasharray="3 3" stroke={chart.grid} />
                  <XAxis dataKey="day" stroke={chart.axis} fontSize={12} />
                  <YAxis stroke={chart.axis} fontSize={12} allowDecimals={false} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: chart.tooltipBg,
                      border: `1px solid ${chart.tooltipBorder}`,
                      borderRadius: 8,
                    }}
                    labelStyle={{ color: chart.tooltipText }}
                    cursor={{ fill: dark ? "rgba(148,163,184,0.06)" : "rgba(100,116,139,0.06)" }}
                  />
                  <Bar
                    dataKey="articles_deleted"
                    name="Deleted"
                    fill="#f87171"
                    radius={[4, 4, 0, 0]}
                    animationDuration={600}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>

        <Card>
          <CardTitle>By language</CardTitle>
          {data.by_language.length === 0 ? (
            <EmptyState message="No language breakdown yet" />
          ) : (
            <div className="space-y-3">
              {data.by_language.map((row) => (
                <div
                  key={row.language}
                  className="flex items-center justify-between text-sm"
                >
                  <span className="text-slate-600 dark:text-slate-300">{row.language}</span>
                  <span className="font-medium text-slate-900 dark:text-white">
                    {formatNumber(row.articles_deleted)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <Card>
        <CardTitle>By source</CardTitle>
        {data.by_source.length === 0 ? (
          <EmptyState message="No source breakdown yet" />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Source</Th>
                <Th>Slug</Th>
                <Th className="text-right">Deleted</Th>
              </tr>
            </thead>
            <tbody>
              {data.by_source.map((row) => (
                <Tr key={row.source_id}>
                  <Td>{row.source_name}</Td>
                  <Td className="text-slate-500 dark:text-slate-400">{row.source_slug}</Td>
                  <Td className="text-right font-medium text-slate-900 dark:text-white">
                    {formatNumber(row.articles_deleted)}
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      <Card>
        <CardTitle>Recent purge cycles</CardTitle>
        {data.recent_cycles.length === 0 ? (
          <EmptyState message="No purge cycles recorded yet" />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Finished</Th>
                <Th>Status</Th>
                <Th className="text-right">Deleted</Th>
                <Th className="text-right">Batches</Th>
                <Th className="text-right">S3 objects</Th>
                <Th className="text-right">Duration</Th>
                <Th>Cutoff</Th>
              </tr>
            </thead>
            <tbody>
              {data.recent_cycles.map((cycle) => (
                <Tr key={cycle.id}>
                  <Td className="whitespace-nowrap text-slate-600 dark:text-slate-300">
                    {formatTime(cycle.finished_at)}
                  </Td>
                  <Td>
                    <Badge color={cycle.status === "completed" ? "green" : "red"}>
                      {cycle.status}
                    </Badge>
                  </Td>
                  <Td className="text-right font-medium text-slate-900 dark:text-white">
                    {formatNumber(cycle.articles_deleted)}
                  </Td>
                  <Td className="text-right text-slate-500 dark:text-slate-400">
                    {formatNumber(cycle.batches)}
                  </Td>
                  <Td className="text-right text-slate-500 dark:text-slate-400">
                    {formatNumber(cycle.raw_html_deleted)}
                  </Td>
                  <Td className="text-right text-slate-500 dark:text-slate-400">
                    {cycle.duration_seconds.toFixed(1)}s
                  </Td>
                  <Td className="whitespace-nowrap text-xs text-slate-500">
                    {formatTime(cycle.cutoff_at)}
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </div>
  );
}
