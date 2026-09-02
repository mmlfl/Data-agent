import type { UiComponent } from "./components";

export const SUPPORTED_PROTOCOL_VERSION = "1" as const;

export type AgentEventType =
  | "status"
  | "text_delta"
  | "text"
  | "tool_start"
  | "tool_result"
  | "final_result"
  | "error"
  | "done";

export interface AgentEvent {
  protocol_version: typeof SUPPORTED_PROTOCOL_VERSION;
  type: AgentEventType | (string & {});
  content?: string | null;
  tool_name?: string | null;
  tool_call_id?: string | null;
  ui_component?: UiComponent | null;
  metadata?: Record<string, unknown>;
}

export function isUiComponent(value: unknown): value is UiComponent {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const type = (value as { type?: unknown }).type;
  return (
    type === "dataframe" ||
    type === "table_list" ||
    type === "table_schema" ||
    type === "final_result"
  );
}
