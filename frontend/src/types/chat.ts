import type {
  DataFrameComponent,
  FinalResultComponent,
  UiComponent,
} from "./components";

export type TurnPhase =
  | "idle"
  | "streaming"
  | "summarizing"
  | "complete"
  | "cancelled"
  | "error";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  phase?: TurnPhase;
  statusText?: string | null;
  toolCallIds?: string[];
  finalResult?: FinalResultComponent | null;
  error?: string | null;
}

export type ToolCallStatus = "running" | "success" | "error";

export interface ToolCallRecord {
  id: string;
  turnId: string;
  name: string;
  status: ToolCallStatus;
  arguments?: Record<string, unknown>;
  content?: string | null;
  component?: UiComponent | null;
  error?: string | null;
  executionTimeMs?: number | null;
  startedAt: number;
  completedAt?: number;
}

export interface ResultArtifact {
  id: string;
  turnId: string;
  data: DataFrameComponent;
  finalResult?: FinalResultComponent | null;
  createdAt: number;
}

export interface ChatState {
  conversationId: string;
  activeAssistantId: string | null;
  messages: ChatMessage[];
  toolCalls: Record<string, ToolCallRecord>;
  results: Record<string, ResultArtifact>;
  resultOrder: string[];
  activeResultId: string | null;
  phase: TurnPhase;
}
