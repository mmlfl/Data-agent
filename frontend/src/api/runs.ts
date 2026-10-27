import type { AgentEvent, ChatState } from "../types";
import { chatReducer, createInitialChatState } from "../state/chatReducer";
import { readCache } from "./metadata";

export interface Run { id: string; question: string; status: string; events: AgentEvent[]; }
export const finished = (status: string) => ["success", "partial", "error", "cancelled", "interrupted"].includes(status);
export const getRun = (id: string, after = 0, signal?: AbortSignal) => readCache<Run>(`/api/runs/${encodeURIComponent(id)}?after=${after}`, signal);
export const getConversations = () => readCache<{ conversations: { id: string; title: string }[] }>("/api/conversations");
export async function restoreConversation(id: string): Promise<{state: ChatState; activeRun?: string; sequence: number}> {
  const { runs } = await readCache<{ runs: Run[] }>(`/api/conversations/${encodeURIComponent(id)}/runs`);
  let state = createInitialChatState(id), sequence = 0;
  for (const run of runs) {
    const assistantId = `answer:${run.id}`;
    state = chatReducer(state, { type: "start_turn", userMessage: { id: `user:${run.id}`, role: "user", content: run.question },
      assistantMessage: { id: assistantId, role: "assistant", content: "", phase: "streaming", toolCallIds: [] } });
    sequence = 0;
    let page: Run;
    do {
      page = await getRun(run.id, sequence);
      for (const event of page.events) {
        sequence = Number(event.metadata?.sequence ?? sequence);
        state = chatReducer(state, { type: "event", assistantId, event, receivedAt: Date.now() });
      }
    } while (page.events.length === 200);
    if (finished(page.status) && state.phase !== "complete" && state.phase !== "error" && state.phase !== "cancelled")
      state = chatReducer(state, { type: "request_error", assistantId, message: "该运行已中断，已保留收到的结果。" });
  }
  const last = runs.at(-1);
  return { state, activeRun: last && !finished(last.status) ? last.id : undefined, sequence };
}

export async function cancelRun(id: string) {
  const response = await fetch(`/api/runs/${encodeURIComponent(id)}/cancel`, { method: "POST", headers: { "X-Requested-With": "SQL-Insight-Workbench" } });
  if (!response.ok) throw new Error("取消请求未送达，请稍后重试。");
}

export async function followRun(id: string, after: number, onEvent: (event: AgentEvent) => void, signal: AbortSignal) {
  let sequence = after;
  while (!signal.aborted) {
    const run = await getRun(id, sequence, signal);
    for (const event of run.events) {
      sequence = Number(event.metadata?.sequence ?? sequence);
      onEvent(event);
    }
    if (finished(run.status) && run.events.length < 200) return;
    await new Promise<void>(resolve => {
      const complete = () => { clearTimeout(timer); signal.removeEventListener("abort", complete); resolve(); };
      const timer = setTimeout(complete, 700); signal.addEventListener("abort", complete, { once: true });
    });
  }
}
