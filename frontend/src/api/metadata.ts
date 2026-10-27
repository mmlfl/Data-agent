export type SyncTarget = "sqlite" | "milvus";

export interface CachedTable {
  table_name: string;
  schema_name: string;
  table_comment: string;
  column_count: number;
  synced_at: string | null;
}

export interface CacheTables {
  available: boolean;
  cache_file: string;
  dialect: string;
  total_tables: number;
  total_columns: number;
  last_synced_at: string | null;
  schemas: string[];
  matched_tables: number;
  offset: number;
  limit: number;
  tables: CachedTable[];
}

export interface CachedColumn {
  column_name: string;
  data_type: string | null;
  column_comment: string | null;
  is_nullable: string | null;
  data_length: number | null;
}

export interface CacheTable {
  table_name: string;
  schema_name: string;
  table_comment: string;
  synced_at: string | null;
  columns: CachedColumn[];
}

export async function readCache<T>(path: string, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, { signal, cache: "no-store", headers: { Accept: "application/json" } });
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new Error("无法连接缓存服务，请确认后端已启动后重试。");
  }
  let body;
  try {
    body = await response.json();
    if (!body || typeof body !== "object" || Array.isArray(body)) throw new Error();
  } catch {
    throw new Error("缓存接口未返回有效数据，请确认后端已更新并重启。");
  }
  if (!response.ok) {
    if (response.status === 404 && body.detail === "Not Found") {
      throw new Error("缓存浏览接口尚未加载，请更新并重启后端。");
    }
    throw new Error(typeof body.detail === "string" ? body.detail : "读取缓存失败，请稍后刷新。");
  }
  return body as T;
}

export function getCachedTables(options: { q: string; schema: string | null; offset: number }, signal?: AbortSignal) {
  const query = new URLSearchParams({ q: options.q, offset: String(options.offset), limit: "30" });
  if (options.schema !== null) query.set("schema_name", options.schema);
  return readCache<CacheTables>(`/api/cache/tables?${query}`, signal);
}

export function getCachedTable(table: Pick<CachedTable, "table_name" | "schema_name">, signal?: AbortSignal) {
  const query = new URLSearchParams({ table_name: table.table_name, schema_name: table.schema_name });
  return readCache<CacheTable>(`/api/cache/table?${query}`, signal);
}

export interface SyncReport {
  status?: string;
  message: string;
  tableCount?: number;
  written?: number;
  skipped?: number;
  collection?: string;
}

const SQLITE_SYNC_URL = "/api/cache/sync";
const MILVUS_SYNC_URL = "/api/milvus/sync";

function numeric(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) && value >= 0
    ? value
    : undefined;
}

export async function runMetadataSync(target: SyncTarget): Promise<SyncReport> {
  const path = target === "sqlite" ? SQLITE_SYNC_URL : MILVUS_SYNC_URL;
  const headers: Record<string, string> = {
    "X-Requested-With": "SQL-Insight-Workbench",
    Accept: "application/json",
  };

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
      `Milvus 同步接口尚未接通（${response.status}）。请确认后端已更新并重启。`,
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
