export interface AgentEvent {
  type: string;
  content?: string | null;
  tool_name?: string | null;
  tool_call_id?: string | null;
  metadata?: Record<string, unknown>;
}

export interface HealthResponse {
  status: string;
  service: string;
  with_db: boolean;
  db_dialect: string;
  tools: string[];
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  toolEvents?: AgentEvent[];
  error?: string | null;
}
