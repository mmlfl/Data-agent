import { useEffect, useRef, useState } from "react";
import { type SyncReport, type SyncTarget } from "../api/metadata";
import { listJobs, submitJob, type MetadataJob } from "../api/jobs";

export interface SyncExecution {
  id: string; target: SyncTarget; status: "running" | "success" | "error";
  startedAt: number; finishedAt?: number; message: string; report?: SyncReport;
}

export function useMetadataSync(onCacheSynced: () => Promise<unknown>) {
  const [executions, setExecutions] = useState<SyncExecution[]>([]);
  const [submitting, setSubmitting] = useState<SyncTarget | null>(null);
  const [submissionError, setSubmissionError] = useState<SyncExecution | null>(null);
  const lock = useRef(false), lastSuccess = useRef("");
  const refreshHealth = useRef(onCacheSynced); refreshHealth.current = onCacheSynced;
  const update = (jobs: MetadataJob[]) => {
    const rows: SyncExecution[] = jobs.filter(job => job.target === "sqlite" || job.target === "milvus").map(job => ({
      id: job.id, target: job.target as SyncTarget,
      status: job.status === "success" ? "success" : ["queued", "running"].includes(job.status) ? "running" : "error",
      startedAt: job.created_at * 1000, finishedAt: ["queued", "running"].includes(job.status) ? undefined : job.updated_at * 1000,
      message: job.error || String(job.report?.message ?? job.stage), report: job.report ? {
        message: String(job.report.message ?? job.stage), tableCount: job.report.table_count as number | undefined,
        written: job.report.written as number | undefined, skipped: job.report.skipped as number | undefined,
        collection: job.report.collection as string | undefined,
      } : undefined,
    }));
    setExecutions(rows);
    const success = rows.find(job => job.target === "sqlite" && job.status === "success");
    if (success && success.id !== lastSuccess.current) {
      lastSuccess.current = success.id; void refreshHealth.current().catch(() => {});
    }
  };
  useEffect(() => {
    const controller = new AbortController(); let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try { const result = await listJobs(controller.signal); if (!controller.signal.aborted) update(result.jobs); }
      catch { /* Recover on the next poll after a disconnect. */ }
      finally { if (!controller.signal.aborted) timer = setTimeout(() => void poll(), 1500); }
    };
    void poll(); return () => { controller.abort(); clearTimeout(timer); };
  }, []);
  const sync = async (target: SyncTarget) => {
    if (lock.current) return;
    lock.current = true; setSubmitting(target); setSubmissionError(null);
    try { await submitJob(target); update((await listJobs()).jobs); }
    catch (error) { setSubmissionError({ id: crypto.randomUUID(), target, status: "error", startedAt: Date.now(),
      finishedAt: Date.now(), message: error instanceof Error ? error.message : "任务提交失败，请重试" }); }
    finally { lock.current = false; setSubmitting(null); }
  };
  return { executions: submissionError ? [submissionError, ...executions] : executions,
    activeTarget: submitting ?? executions.find(job => job.status === "running")?.target ?? null, sync };
}
