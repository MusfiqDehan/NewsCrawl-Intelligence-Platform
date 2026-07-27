"use client";

import { Badge, Card, CardTitle, EmptyState, Spinner, Table, Td, Th, Tr } from "@/components/ui";
import { useQueues, useWorkers } from "@/lib/hooks";
import { formatNumber } from "@/lib/utils";

const STREAM_LABELS: Record<string, string> = {
  "processing:cleaning": "Cleaning",
  "processing:llm": "LLM extraction",
  "processing:embedding": "Embeddings",
};

export default function SystemPage() {
  const workers = useWorkers();
  const queues = useQueues();

  return (
    <div className="space-y-6">
      <h1 className="nc-rise text-xl font-semibold text-slate-900 dark:text-white">
        System Operations
      </h1>

      <div className="nc-stagger grid gap-4 lg:grid-cols-3">
        {queues.data &&
          Object.entries(queues.data.streams).map(([stream, depth]) => (
            <Card key={stream} interactive>
              <div className="text-sm text-slate-500">
                {STREAM_LABELS[stream] ?? stream}
              </div>
              <div className="mt-1 text-2xl font-semibold text-slate-900 dark:text-white">
                {formatNumber(depth)}
              </div>
              <div className="mt-1 text-xs text-slate-500">messages pending</div>
            </Card>
          ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardTitle>Retry / dead-letter</CardTitle>
          {queues.isLoading && <Spinner />}
          {queues.data && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-500 dark:text-slate-400">Delayed (retry) jobs</span>
                <Badge color={queues.data.delayed > 0 ? "yellow" : "gray"}>
                  {formatNumber(queues.data.delayed)}
                </Badge>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-500 dark:text-slate-400">Dead-lettered messages</span>
                <Badge color={queues.data.dead_letter > 0 ? "red" : "gray"}>
                  {formatNumber(queues.data.dead_letter)}
                </Badge>
              </div>
            </div>
          )}
        </Card>

        <Card>
          <CardTitle>Live workers</CardTitle>
          {workers.isLoading && <Spinner />}
          {workers.data && workers.data.length === 0 && (
            <EmptyState message="No workers registered" />
          )}
          {workers.data && workers.data.length > 0 && (
            <div className="text-sm text-slate-500 dark:text-slate-400">
              {workers.data.filter((w) => w.alive).length} of {workers.data.length} alive
            </div>
          )}
        </Card>
      </div>

      {workers.data && workers.data.length > 0 && (
        <Table>
          <thead>
            <tr>
              <Th>Worker</Th>
              <Th>Type</Th>
              <Th>Status</Th>
              <Th>Host</Th>
              <Th className="text-right">PID</Th>
              <Th className="text-right">Last beat</Th>
              <Th>Liveness</Th>
            </tr>
          </thead>
          <tbody>
            {workers.data.map((w) => (
              <Tr key={w.worker_id}>
                <Td className="font-mono text-xs text-slate-900 dark:text-white">{w.worker_id}</Td>
                <Td>{w.worker_type}</Td>
                <Td>{w.status}</Td>
                <Td className="text-slate-500">{w.hostname}</Td>
                <Td className="text-right text-slate-500">{w.pid}</Td>
                <Td className="text-right">{w.last_beat_age_seconds}s ago</Td>
                <Td>
                  <Badge color={w.alive ? "green" : "red"}>
                    {w.alive ? "alive" : "stale"}
                  </Badge>
                </Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      )}
    </div>
  );
}
