import type { AgentEvent, HealthResponse } from "../types";

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch("/health", { signal: AbortSignal.timeout(10_000) });
  if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
  return res.json();
}

export interface StreamChatOptions {
  message: string;
  conversationId?: string;
  onEvent: (event: AgentEvent) => void;
  signal?: AbortSignal;
  runId?: string;
}

export async function streamChat({
  message,
  conversationId,
  onEvent,
  signal,
  runId,
}: StreamChatOptions): Promise<void> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      conversation_id: conversationId ?? null,
      run_id: runId,
    }),
    signal,
  });

  if (!res.ok) {
    const text = await res.text();
    try {
      const body = JSON.parse(text) as { detail?: string };
      throw new Error(body.detail || `请求失败: ${res.status}`);
    } catch (error) {
      if (error instanceof SyntaxError) {
        throw new Error(text || `请求失败: ${res.status}`);
      }
      throw error;
    }
  }

  const reader = res.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";
  let terminal = false;

  const consumeLine = (line: string): boolean => {
    const trimmed = line.trim();
    if (!trimmed.startsWith("data:")) return false;
    const data = trimmed.slice(5).trim();
    if (data === "[DONE]") {
      if (!terminal) throw new Error("连接已结束，但分析没有返回完成状态，请核对本轮运行记录。");
      return true;
    }
    if (!data) return false;
    let parsed: unknown;
    try { parsed = JSON.parse(data) as unknown; }
    catch { throw new Error("分析事件格式异常，已保留收到的内容，请核对运行记录。"); }
      if (
        parsed &&
        typeof parsed === "object" &&
        typeof (parsed as { type?: unknown }).type === "string"
      ) {
        if ((parsed as AgentEvent).type === "done") terminal = true;
        onEvent(parsed as AgentEvent);
      }
    return false;
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      buffer += decoder.decode();
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split(/\r?\n/);
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (consumeLine(line)) return;
    }
  }

  if (buffer && consumeLine(buffer)) return;
  if (!terminal) throw new Error("分析连接中断，尚未收到完成状态。已收到的内容已保留。");
}
