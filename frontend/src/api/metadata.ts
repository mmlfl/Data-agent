export type SyncTarget = "sqlite" | "milvus";

export interface SyncReport {
  status?: string;
  message: string;
  tableCount?: number;
  written?: number;
  skipped?: number;
  collection?: string;
}

export const DEFAULT_MILVUS_SYNC_URL =
  import.meta.env.VITE_MILVUS_SYNC_URL || "/api/milvus/sync";

/** Keep sync credentials on the application's own API origin. */
export function validateSyncPath(path: string): string {
  const value = path.trim();
  if (
    !value.startsWith("/api/") ||
    value.includes("\\") ||
    value.includes("#")
  ) {
    throw new Error(
      "请填写以 /api/ 开头的本站接口路径，例如 /api/milvus/sync。",
    );
  }
  const url = new URL(value, "http://workspace.local");
  if (
    url.origin !== "http://workspace.local" ||
    !url.pathname.startsWith("/api/")
  ) {
    throw new Error("同步接口必须是本站 /api/ 下的路径。");
  }
  return value;
}

function numeric(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) && value >= 0
    ? value
    : undefined;
}

export async function runMetadataSync(
  target: SyncTarget,
  milvusPath: string,
  token = "",
): Promise<SyncReport> {
  const path =
    target === "sqlite" ? "/api/cache/sync" : validateSyncPath(milvusPath);
  const headers: Record<string, string> = {
    "X-Requested-With": "SQL-Insight-Workbench",
    Accept: "application/json",
  };
  const credential =
    token ||
    (target === "sqlite"
      ? import.meta.env.VITE_CACHE_SYNC_TOKEN
      : import.meta.env.VITE_MILVUS_SYNC_TOKEN);
  if (credential)
    headers[
      target === "sqlite" ? "X-Cache-Sync-Token" : "X-Milvus-Sync-Token"
    ] = credential;

  let response: Response;
  try {
    // No timeout: a sync can continue server-side even after the browser gives up.
    response = await fetch(path, {
      method: "POST",
      headers,
      redirect: "error",
    });
  } catch {
    throw new Error(
      "连接中断，无法确认同步结果。请检查服务状态；重新执行前请先确认上一次任务是否已完成。",
    );
  }
  if (target === "milvus" && [404, 405].includes(response.status)) {
    throw new Error(
      `Milvus 同步接口尚未接通（${response.status}）。请在「接口设置」填写后端实际提供的 HTTP 同步路径。`,
    );
  }
  let body: Record<string, unknown>;
  try {
    const json: unknown = await response.json();
    if (!json || typeof json !== "object" || Array.isArray(json))
      throw new Error();
    body = json as Record<string, unknown>;
  } catch {
    throw new Error(
      response.ok
        ? "接口未返回有效的同步结果，请检查同步接口地址。"
        : `同步请求失败（${response.status}），请检查服务状态。`,
    );
  }
  const detail =
    typeof body.detail === "string"
      ? body.detail
      : typeof body.message === "string"
        ? body.message
        : undefined;
  if (
    !response.ok ||
    body.success === false ||
    ["error", "failed", "failure"].includes(String(body.status).toLowerCase())
  ) {
    throw new Error(detail || `同步请求失败（${response.status}）。`);
  }
  const status =
    typeof body.status === "string" ? body.status.toLowerCase() : undefined;
  if (
    response.status === 202 ||
    (status &&
      ["pending", "running", "queued", "started", "processing"].includes(
        status,
      ))
  ) {
    throw new Error(
      "后端已接收异步任务，但未返回最终结果。请在后端确认完成情况；当前页面不会将任务标记为同步成功。",
    );
  }
  const tableCount = numeric(body.table_count) ?? numeric(body.total);
  const written = numeric(body.written);
  if (!(
    ["success", "ok", "synced", "completed", "ready", "cached"].includes(
      status ?? "",
    ) ||
    body.success === true ||
    (!status && (tableCount !== undefined || written !== undefined))
  )) {
    throw new Error("接口没有返回可确认的同步状态或数量，请核对接口响应。");
  }
  return {
    status,
    message:
      detail ||
      (target === "sqlite"
        ? `已重新同步 ${tableCount ?? 0} 张表的元数据`
        : "Milvus 单表元数据同步完成"),
    tableCount,
    written,
    skipped: numeric(body.skipped),
    collection:
      typeof body.collection === "string" ? body.collection : undefined,
  };
}
