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

import { Card, CardTitle, Spinner, StatusBadge } from "@/components/ui";
import { useOverview, useQueues } from "@/lib/hooks";
import { formatNumber } from "@/lib/utils";

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Card>
      <div className="text-sm text-slate-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-white">{value}</div>
      {sub && <div className="mt-1 text-xs text-slate-500">{sub}</div>}
    </Card>
  );
}

export default function OverviewPage() {
  const { data: overview, isLoading } = useOverview();
  const { data: queues } = useQueues();

  if (isLoading || !overview) return <Spinner />;

  const languages = Object.entries(overview.articles_by_language);
  const frontier = Object.entries(overview.frontier).sort((a, b) => b[1] - a[1]);

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-white">Overview</h1>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        <Stat
          label="Total articles"
          value={formatNumber(overview.total_articles)}
          sub={`+${formatNumber(overview.articles_last_24h)} last 24h`}
        />
        <Stat
          label="Sources"
          value={`${overview.enabled_sources}/${overview.total_sources}`}
          sub="enabled / total"
        />
        <Stat label="Active jobs" value={formatNumber(overview.active_jobs)} />
        <Stat
          label="LLM tokens"
          value={formatNumber(overview.llm_tokens_total)}
          sub={`$${overview.llm_cost_usd_total.toFixed(4)} total cost`}
        />
        <Stat
          label="Queue backlog"
          value={
            queues
              ? formatNumber(
                  Object.values(queues.streams).reduce((a, b) => a + b, 0) + queues.delayed,
                )
              : "—"
          }
          sub={queues ? `${queues.dead_letter} dead-lettered` : undefined}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardTitle>Articles per day (7 days)</CardTitle>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={overview.articles_per_day}>
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
                <Bar dataKey="count" fill="#0284c7" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardTitle>Articles by language</CardTitle>
            <div className="space-y-2">
              {languages.length === 0 && (
                <div className="text-sm text-slate-500">No articles yet</div>
              )}
              {languages.map(([lang, count]) => (
                <div key={lang} className="flex items-center justify-between">
                  <StatusBadge status={lang} />
                  <span className="text-sm text-slate-300">{formatNumber(count)}</span>
                </div>
              ))}
            </div>
          </Card>

          <Card>
            <CardTitle>URL frontier</CardTitle>
            <div className="space-y-2">
              {frontier.length === 0 && (
                <div className="text-sm text-slate-500">Frontier is empty</div>
              )}
              {frontier.map(([status, count]) => (
                <div key={status} className="flex items-center justify-between">
                  <StatusBadge status={status} />
                  <span className="text-sm text-slate-300">{formatNumber(count)}</span>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
