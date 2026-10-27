import { afterEach, expect, it, vi } from "vitest";
import { checkMilvus, checkSqlite, getMilvusDocument, getMilvusDocuments } from "./inspection";

afterEach(() => vi.unstubAllGlobals());

it("uses read-only check endpoints without accepting a server or scope from the browser", async () => {
  const fetch = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ status: "ready" }))));
  vi.stubGlobal("fetch", fetch);
  await checkSqlite();
  await checkMilvus();
  expect(fetch.mock.calls.map((call) => call[0])).toEqual(["/api/cache/check", "/api/milvus/check"]);
  expect(fetch.mock.calls.every((call) => call[1].method === undefined && call[1].cache === "no-store")).toBe(true);
});

it("encodes document searches and exact record identifiers", async () => {
  const fetch = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ documents: [] }))));
  vi.stubGlobal("fetch", fetch);
  await getMilvusDocuments("AA_01%", 30);
  await getMilvusDocument("ddl:123&tenant=other");
  const page = new URL(fetch.mock.calls[0][0], "http://localhost");
  expect(page.searchParams.get("q")).toBe("AA_01%");
  expect(page.searchParams.get("offset")).toBe("30");
  expect(page.searchParams.get("limit")).toBe("30");
  const detail = new URL(fetch.mock.calls[1][0], "http://localhost");
  expect(detail.searchParams.get("record_id")).toBe("ddl:123&tenant=other");
  expect(detail.searchParams.has("tenant")).toBe(false);
});

it("preserves an unavailable service as unknown instead of an empty collection", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: "unavailable", document_count: null, can_browse: false }))));
  const report = await getMilvusDocuments("", 0);
  expect(report.status).toBe("unavailable");
  expect(report.document_count).toBeNull();
  expect(report.can_browse).toBe(false);
});
