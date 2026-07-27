"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Card, CardTitle, Spinner, StatusBadge } from "@/components/ui";
import { useOverview, useQueues, useSentiment } from "@/lib/hooks";
import { useTheme } from "@/lib/theme";
import { formatNumber } from "@/lib/utils";

const SENTIMENT_COLORS: Record<string, string> = {
  positive: "#34d399",
  negative: "#f87171",
  neutral: "#94a3b8",
  "not available": "#38bdf8",
};

const SENTIMENT_LABELS: Record<string, string> = {
  positive: "Positive",
  negative: "Negative",
  neutral: "Neutral",
  "not available": "Not available",
};

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Card interactive>
      <div className="text-sm text-slate-500 dark:text-slate-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-slate-900 dark:text-white">{value}</div>
      {sub && <div className="mt-1 text-xs text-slate-500 dark:text-slate-500">{sub}</div>}
    </Card>
  );
}

export default function OverviewPage() {
  const { data: overview, isLoading } = useOverview();
  const { data: sentiment } = useSentiment();
  const { data: queues } = useQueues();
  const { resolvedTheme } = useTheme();
  const dark = resolvedTheme === "dark";
  const chart = {
    grid: dark ? "#1e293b" : "#e2e8f0",
    axis: dark ? "#64748b" : "#94a3b8",
    tooltipBg: dark ? "#0f172a" : "#ffffff",
    tooltipBorder: dark ? "#334155" : "#e2e8f0",
    tooltipText: dark ? "#e2e8f0" : "#0f172a",
    legendText: dark ? "#94a3b8" : "#64748b",
  };

  if (isLoading || !overview) return <Spinner />;

  const languages = Object.entries(overview.articles_by_language);
  const frontier = Object.entries(overview.frontier).sort((a, b) => b[1] - a[1]);
  const sentimentData =
    sentiment
      ?.filter((b) => b.count > 0)
      .map((b) => ({
        name: SENTIMENT_LABELS[b.sentiment] ?? b.sentiment,
        key: b.sentiment,
        value: b.count,
      })) ?? [];
  const sentimentTotal = sentiment?.reduce((sum, b) => sum + b.count, 0) ?? 0;

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-slate-900 dark:text-white">Overview</h1>

      <div className="nc-stagger grid grid-cols-2 gap-4 lg:grid-cols-5">
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
                  dataKey="count"
                  fill="#0284c7"
                  radius={[4, 4, 0, 0]}
                  animationDuration={600}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card>
          <CardTitle>Sentiment</CardTitle>
          {sentimentTotal === 0 || sentimentData.length === 0 ? (
            <div className="flex h-64 items-center justify-center text-sm text-slate-500">
              No articles yet
            </div>
          ) : (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={sentimentData}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="46%"
                    innerRadius={48}
                    outerRadius={78}
                    paddingAngle={2}
                    animationDuration={600}
                  >
                    {sentimentData.map((entry) => (
                      <Cell
                        key={entry.key}
                        fill={SENTIMENT_COLORS[entry.key] ?? "#64748b"}
                        stroke={chart.tooltipBg}
                      />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(value) => formatNumber(Number(value))}
                    contentStyle={{
                      backgroundColor: chart.tooltipBg,
                      border: `1px solid ${chart.tooltipBorder}`,
                      borderRadius: 8,
                    }}
                    labelStyle={{ color: chart.tooltipText }}
                  />
                  <Legend
                    verticalAlign="bottom"
                    height={36}
                    formatter={(value) => (
                      <span className="text-xs" style={{ color: chart.legendText }}>
                        {value}
                      </span>
                    )}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardTitle>Articles by language</CardTitle>
          <div className="space-y-2">
            {languages.length === 0 && (
              <div className="text-sm text-slate-500">No articles yet</div>
            )}
            {languages.map(([lang, count]) => (
              <div key={lang} className="flex items-center justify-between">
                <StatusBadge status={lang} />
                <span className="text-sm text-slate-600 dark:text-slate-300">
                  {formatNumber(count)}
                </span>
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
                <span className="text-sm text-slate-600 dark:text-slate-300">
                  {formatNumber(count)}
                </span>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
