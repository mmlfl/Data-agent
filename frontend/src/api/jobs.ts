import { readCache, type SyncTarget } from "./metadata";
export interface MetadataJob {
  id: string; target: string; status: string; stage: string; created_at: number;
  updated_at: number; error?: string | null; report?: Record<string, unknown> | null;
}
export const listJobs = (signal?: AbortSignal) => readCache<{ jobs: MetadataJob[] }>("/api/metadata/jobs", signal);
export async function submitJob(target: SyncTarget | "knowledge") {
  const response = await fetch("/api/metadata/jobs", { method: "POST", headers: {
    "Content-Type": "application/json", "X-Requested-With": "SQL-Insight-Workbench",
  }, body: JSON.stringify({ target }) });
  if (!response.ok) { const error = await response.json().catch(() => ({})); throw new Error(error.detail || "任务未提交，请重试"); }
  return response.json() as Promise<MetadataJob>;
}
