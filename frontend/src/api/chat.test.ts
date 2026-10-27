import { afterEach, expect, it, vi } from "vitest";
import { streamChat } from "./chat";
afterEach(() => vi.unstubAllGlobals());
it("rejects EOF without a business terminal event", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response('data: {"type":"status","content":"thinking"}\n\n')));
  await expect(streamChat({ message: "question", onEvent: vi.fn() })).rejects.toThrow("完成状态");
});
it("accepts done and preserves ordered events", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response('data: {"type":"text_delta","content":"中文"}\n\ndata: {"type":"done"}\n\ndata: [DONE]\n\n')));
  const received: string[] = [];
  await streamChat({ message: "question", runId: "run-one", onEvent: event => received.push(event.type) });
  expect(received).toEqual(["text_delta", "done"]);
});
