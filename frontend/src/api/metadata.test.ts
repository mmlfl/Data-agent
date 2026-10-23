import { afterEach, describe, expect, it, vi } from "vitest";
import { runMetadataSync, validateSyncPath } from "./metadata";

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

describe("metadata synchronization", () => {
  it("uses the existing SQLite route and required request headers", async () => {
    const fetch = respond({
      status: "synced",
      table_count: 17,
      message: "已重新同步 17 张表",
    });
    const result = await runMetadataSync(
      "sqlite",
      "/api/unused",
      "test-session-token",
    );
    expect(fetch).toHaveBeenCalledWith(
      "/api/cache/sync",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          "X-Requested-With": "SQL-Insight-Workbench",
          "X-Cache-Sync-Token": "test-session-token",
        }),
      }),
    );
    expect(result.tableCount).toBe(17);
  });

  it("accepts the metadata report and configured Milvus route", async () => {
    const fetch = respond({
      total: 12,
      written: 8,
      skipped: 4,
      collection: "schema_meta",
    });
    const result = await runMetadataSync(
      "milvus",
      "/api/schema/resync",
      "session-token",
    );
    expect(fetch).toHaveBeenCalledWith(
      "/api/schema/resync",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          "X-Milvus-Sync-Token": "session-token",
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
      await expect(
        runMetadataSync("milvus", "/api/milvus/sync"),
      ).rejects.toThrow("接口尚未接通");
    },
  );

  it.each(["running", "pending", "queued", "started", "processing"])(
    "does not report an asynchronous %s response as completed",
    async (status) => {
      respond({ status, total: 20 });
      await expect(
        runMetadataSync("milvus", "/api/milvus/sync"),
      ).rejects.toThrow("异步任务");
    },
  );

  it("does not treat HTTP 202 as successful completion", async () => {
    respond({ status: "success", total: 20 }, 202);
    await expect(runMetadataSync("milvus", "/api/milvus/sync")).rejects.toThrow(
      "异步任务",
    );
  });

  it("preserves server error messages and rejects failed HTTP-200 responses", async () => {
    respond({ success: false, message: "Collection 不可用" });
    await expect(runMetadataSync("milvus", "/api/milvus/sync")).rejects.toThrow(
      "Collection 不可用",
    );
  });

  it("does not accept HTML or unknown response objects as a completed sync", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("<!doctype html><html></html>")),
    );
    await expect(runMetadataSync("milvus", "/api/milvus/sync")).rejects.toThrow(
      "有效的同步结果",
    );
    respond({ message: "hello" });
    await expect(runMetadataSync("milvus", "/api/milvus/sync")).rejects.toThrow(
      "可确认的同步状态",
    );
  });

  it("does not invent a result when the connection is lost", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("Failed to fetch")),
    );
    await expect(runMetadataSync("sqlite", "")).rejects.toThrow(
      "无法确认同步结果",
    );
  });

  it.each([
    "https://other.example/api/sync",
    "//other.example/api/sync",
    "/api/../health",
    "/api/\\other.example/sync",
    "/health",
    "/api/sync#anything",
  ])("rejects unsafe or non-API paths: %s", (path) => {
    expect(() => validateSyncPath(path)).toThrow();
  });

  it("accepts an empty completed sync", async () => {
    respond({ total: 0, written: 0, skipped: 0 });
    await expect(
      runMetadataSync("milvus", "/api/milvus/sync"),
    ).resolves.toMatchObject({ tableCount: 0, written: 0 });
  });
});
