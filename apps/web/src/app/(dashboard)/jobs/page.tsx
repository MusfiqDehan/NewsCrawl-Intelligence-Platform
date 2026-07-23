"use client";

import { formatDistanceToNow } from "date-fns";
import { Ban, Pause, Play, Plus } from "lucide-react";
import { useState } from "react";

import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  Select,
  Spinner,
  StatusBadge,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { useCreateJob, useJobAction, useJobs, useSources } from "@/lib/hooks";
import type { CrawlJob } from "@/lib/types";
import { formatNumber } from "@/lib/utils";

const JOB_TYPES = [
  "incremental_crawl",
  "full_crawl",
  "section_crawl",
  "retry_failed",
  "backfill",
];

function CreateJobForm({ onClose }: { onClose: () => void }) {
  const { data: sources } = useSources();
  const createJob = useCreateJob();
  const [sourceId, setSourceId] = useState("");
  const [jobType, setJobType] = useState("incremental_crawl");

  return (
    <Card className="mb-4">
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={async (e) => {
          e.preventDefault();
          await createJob.mutateAsync({ source_id: sourceId, job_type: jobType });
          onClose();
        }}
      >
        <div>
          <label className="mb-1 block text-xs text-slate-500">Source</label>
          <Select value={sourceId} onChange={(e) => setSourceId(e.target.value)} required>
            <option value="">Select source…</option>
            {sources?.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <label className="mb-1 block text-xs text-slate-500">Job type</label>
          <Select value={jobType} onChange={(e) => setJobType(e.target.value)}>
            {JOB_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </Select>
        </div>
        <Button type="submit" disabled={createJob.isPending || !sourceId}>
          {createJob.isPending ? "Creating…" : "Create job"}
        </Button>
        <Button type="button" variant="ghost" onClick={onClose}>
          Cancel
        </Button>
        {createJob.isError && (
          <ErrorState message={(createJob.error as Error).message} />
        )}
      </form>
    </Card>
  );
}

function JobActions({ job }: { job: CrawlJob }) {
  const action = useJobAction();
  const act = (a: "pause" | "resume" | "cancel") =>
    action.mutate({ id: job.id, action: a });

  return (
    <div className="flex gap-1">
      {(job.status === "running" || job.status === "queued") && (
        <Button variant="ghost" title="Pause" onClick={() => act("pause")}>
          <Pause className="h-3.5 w-3.5" />
        </Button>
      )}
      {job.status === "paused" && (
        <Button variant="ghost" title="Resume" onClick={() => act("resume")}>
          <Play className="h-3.5 w-3.5" />
        </Button>
      )}
      {["created", "queued", "running", "paused"].includes(job.status) && (
        <Button variant="ghost" title="Cancel" onClick={() => act("cancel")}>
          <Ban className="h-3.5 w-3.5 text-rose-400" />
        </Button>
      )}
    </div>
  );
}

export default function JobsPage() {
  const [statusFilter, setStatusFilter] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const { data, isLoading, error } = useJobs(statusFilter || undefined);
  const { data: sources } = useSources();
  const sourceName = (id: string) =>
    sources?.find((s) => s.id === id)?.name ?? id.slice(0, 8);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-white">Crawl Jobs</h1>
        <div className="flex gap-3">
          <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">All statuses</option>
            {["queued", "running", "paused", "completed", "failed", "cancelled"].map(
              (s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ),
            )}
          </Select>
          <Button onClick={() => setShowCreate((v) => !v)}>
            <Plus className="h-4 w-4" /> New job
          </Button>
        </div>
      </div>

      {showCreate && <CreateJobForm onClose={() => setShowCreate(false)} />}
      {error && <ErrorState message={(error as Error).message} />}
      {isLoading && <Spinner />}

      {data && data.items.length === 0 && <EmptyState message="No crawl jobs found" />}
      {data && data.items.length > 0 && (
        <Table>
          <thead>
            <tr>
              <Th>Source</Th>
              <Th>Type</Th>
              <Th>Status</Th>
              <Th className="text-right">Discovered</Th>
              <Th className="text-right">Success</Th>
              <Th className="text-right">Failed</Th>
              <Th className="text-right">Changed</Th>
              <Th>Created</Th>
              <Th>Actions</Th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((job) => (
              <tr key={job.id} className="hover:bg-slate-900/50">
                <Td className="font-medium text-white">{sourceName(job.source_id)}</Td>
                <Td className="text-slate-400">{job.job_type}</Td>
                <Td>
                  <StatusBadge status={job.status} />
                </Td>
                <Td className="text-right">{formatNumber(job.pages_discovered)}</Td>
                <Td className="text-right text-emerald-400">
                  {formatNumber(job.pages_successful)}
                </Td>
                <Td className="text-right text-rose-400">
                  {formatNumber(job.pages_failed)}
                </Td>
                <Td className="text-right">{formatNumber(job.pages_changed)}</Td>
                <Td className="text-slate-500">
                  {formatDistanceToNow(new Date(job.created_at), { addSuffix: true })}
                </Td>
                <Td>
                  <JobActions job={job} />
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </div>
  );
}
