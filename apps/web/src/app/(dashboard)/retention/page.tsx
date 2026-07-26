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
} from "@/components/ui";
import { useRetentionStats } from "@/lib/hooks";
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
    <Card>
      <div className="text-sm text-slate-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-white">{value}</div>
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

  if (isLoading) return <Spinner />;
  if (error) return <ErrorState message={(error as Error).message} />;
  if (!data) return <EmptyState message="No retention data yet" />;

  const healthy =
    data.last_cycle_at != null &&
    Date.now() - new Date(data.last_cycle_at).getTime() <
      (data.interval_minutes + 2) * 60_000;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold text-white">
            <Trash2 className="h-5 w-5 text-slate-400" />
            Deleted Articles
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            Retention audit — articles older than {data.retention_hours}h are
            purged about every {data.interval_minutes} minutes.
          </p>
        </div>
        <Badge color={healthy ? "green" : "yellow"}>
          {healthy ? "Retention running" : "Waiting for next cycle"}
        </Badge>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
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
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis dataKey="day" stroke="#64748b" fontSize={12} />
                  <YAxis stroke="#64748b" fontSize={12} allowDecimals={false} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#0f172a",
                      border: "1px solid #334155",
                      borderRadius: 8,
                    }}
                    labelStyle={{ color: "#e2e8f0" }}
                  />
                  <Bar
                    dataKey="articles_deleted"
                    name="Deleted"
                    fill="#f87171"
                    radius={[4, 4, 0, 0]}
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
                  <span className="text-slate-300">{row.language}</span>
                  <span className="font-medium text-white">
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
                <tr key={row.source_id} className="border-t border-slate-800">
                  <Td>{row.source_name}</Td>
                  <Td className="text-slate-400">{row.source_slug}</Td>
                  <Td className="text-right font-medium text-white">
                    {formatNumber(row.articles_deleted)}
                  </Td>
                </tr>
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
                <tr key={cycle.id} className="border-t border-slate-800">
                  <Td className="whitespace-nowrap text-slate-300">
                    {formatTime(cycle.finished_at)}
                  </Td>
                  <Td>
                    <Badge color={cycle.status === "completed" ? "green" : "red"}>
                      {cycle.status}
                    </Badge>
                  </Td>
                  <Td className="text-right font-medium text-white">
                    {formatNumber(cycle.articles_deleted)}
                  </Td>
                  <Td className="text-right text-slate-400">
                    {formatNumber(cycle.batches)}
                  </Td>
                  <Td className="text-right text-slate-400">
                    {formatNumber(cycle.raw_html_deleted)}
                  </Td>
                  <Td className="text-right text-slate-400">
                    {cycle.duration_seconds.toFixed(1)}s
                  </Td>
                  <Td className="whitespace-nowrap text-xs text-slate-500">
                    {formatTime(cycle.cutoff_at)}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </div>
  );
}
