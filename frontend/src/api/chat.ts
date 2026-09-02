import type { AgentEvent, CacheSyncResponse, HealthResponse } from "../types";

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch("/health");
  if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
  return res.json();
}

export async function syncCache(): Promise<CacheSyncResponse> {
  const headers: Record<string, string> = {
    "X-Requested-With": "SQL-Insight-Workbench",
  };
  const token = import.meta.env.VITE_CACHE_SYNC_TOKEN;
  if (typeof token === "string" && token) {
    headers["X-Cache-Sync-Token"] = token;
  }

  const res = await fetch("/api/cache/sync", { method: "POST", headers });
  if (!res.ok) {
    let detail = `同步失败: ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json();
}

export interface StreamChatOptions {
  message: string;
  conversationId?: string;
  onEvent: (event: AgentEvent) => void;
  signal?: AbortSignal;
}

export async function streamChat({
  message,
  conversationId,
  onEvent,
  signal,
}: StreamChatOptions): Promise<void> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      conversation_id: conversationId ?? null,
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

  const consumeLine = (line: string): boolean => {
    const trimmed = line.trim();
    if (!trimmed.startsWith("data:")) return false;
    const data = trimmed.slice(5).trim();
    if (data === "[DONE]") return true;
    if (!data) return false;
    try {
      const parsed = JSON.parse(data) as unknown;
      if (
        parsed &&
        typeof parsed === "object" &&
        typeof (parsed as { type?: unknown }).type === "string"
      ) {
        onEvent(parsed as AgentEvent);
      }
    } catch {
      // Ignore a malformed event while keeping the remaining stream usable.
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
}
