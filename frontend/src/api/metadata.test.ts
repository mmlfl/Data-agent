import { afterEach, describe, expect, it, vi } from "vitest";
import { getCachedTable, getCachedTables, runMetadataSync } from "./metadata";

afterEach(() => {
  vi.unstubAllGlobals();
});

function respond(body: unknown, status = 200) {
  const fetch = vi
    .fn()
    .mockResolvedValue(
      new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
      }),
    );
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

describe("local cache browsing", () => {
  it("encodes literal searches and uses bounded read-only pagination", async () => {
    const fetch = respond({ tables: [], matched_tables: 0 });
    await getCachedTables({ q: "实付金额 %", schema: "biz", offset: 30 });
    const url = new URL(fetch.mock.calls[0][0], "http://localhost");
    expect(url.pathname).toBe("/api/cache/tables");
    expect(url.searchParams.get("q")).toBe("实付金额 %");
    expect(url.searchParams.get("schema_name")).toBe("biz");
    expect(url.searchParams.get("limit")).toBe("30");
    expect(fetch.mock.calls[0][1]).toMatchObject({ cache: "no-store" });
    expect(fetch.mock.calls[0][1].method).toBeUndefined();
  });

  it("keeps the schema and exact table identity when loading fields", async () => {
    const fetch = respond({ columns: [] });
    await getCachedTable({ table_name: "ORDER & 1", schema_name: "" });
    const url = new URL(fetch.mock.calls[0][0], "http://localhost");
    expect(url.searchParams.get("table_name")).toBe("ORDER & 1");
    expect(url.searchParams.has("schema_name")).toBe(true);
    expect(url.searchParams.get("schema_name")).toBe("");
  });

  it("explains an old server without the new browsing routes", async () => {
    respond({ detail: "Not Found" }, 404);
    await expect(getCachedTables({ q: "", schema: null, offset: 0 })).rejects.toThrow("重启后端");
  });
});

describe("metadata synchronization", () => {
  it("uses the existing SQLite route and required request headers", async () => {
    const fetch = respond({
      status: "synced",
      table_count: 17,
      message: "已重新同步 17 张表",
    });
    const result = await runMetadataSync("sqlite");
    expect(fetch).toHaveBeenCalledWith(
      "/api/cache/sync",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          "X-Requested-With": "SQL-Insight-Workbench",
        }),
      }),
    );
    expect(result.tableCount).toBe(17);
  });

  it("posts Milvus sync to the fixed backend route", async () => {
    const fetch = respond({
      total: 12,
      written: 8,
      skipped: 4,
      collection: "schema_meta",
    });
    const result = await runMetadataSync("milvus");
    expect(fetch).toHaveBeenCalledWith(
      "/api/milvus/sync",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          "X-Requested-With": "SQL-Insight-Workbench",
        }),
      }),
    );
    expect(result).toMatchObject({
      tableCount: 12,
      written: 8,
      skipped: 4,
      collection: "schema_meta",
    });
  });

  it.each([404, 405])(
    "explains the unavailable Milvus HTTP route (%s)",
    async (status) => {
      respond({ detail: "Not found" }, status);
      await expect(runMetadataSync("milvus")).rejects.toThrow("接口尚未接通");
    },
  );

  it.each(["running", "pending", "queued", "started", "processing"])(
    "does not report an asynchronous %s response as completed",
    async (status) => {
      respond({ status, total: 20 });
      await expect(runMetadataSync("milvus")).rejects.toThrow("异步任务");
    },
  );

  it("does not treat HTTP 202 as successful completion", async () => {
    respond({ status: "success", total: 20 }, 202);
    await expect(runMetadataSync("milvus")).rejects.toThrow("异步任务");
  });

  it("preserves server error messages and rejects failed HTTP-200 responses", async () => {
    respond({ success: false, message: "Collection 不可用" });
    await expect(runMetadataSync("milvus")).rejects.toThrow("Collection 不可用");
  });

  it("does not accept HTML or unknown response objects as a completed sync", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("<!doctype html><html></html>")),
    );
    await expect(runMetadataSync("milvus")).rejects.toThrow("有效的同步结果");
    respond({ message: "hello" });
    await expect(runMetadataSync("milvus")).rejects.toThrow("可确认的同步状态");
  });

  it("does not invent a result when the connection is lost", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("Failed to fetch")),
    );
    await expect(runMetadataSync("sqlite")).rejects.toThrow("无法确认同步结果");
  });

  it("accepts an empty completed sync", async () => {
    respond({ total: 0, written: 0, skipped: 0 });
    await expect(runMetadataSync("milvus")).resolves.toMatchObject({
      tableCount: 0,
      written: 0,
    });
  });
});
