import type {
  AgentEvent,
  ChatMessage,
  ChatState,
  FinalResultComponent,
  ToolCallRecord,
  TurnPhase,
} from "../types";
import { isUiComponent } from "../types/events";

export type ChatAction =
  | { type: "restore"; state: ChatState }
  | {
      type: "start_turn";
      userMessage: ChatMessage;
      assistantMessage: ChatMessage;
    }
  | {
      type: "event";
      assistantId: string;
      event: AgentEvent;
      receivedAt: number;
    }
  | { type: "request_error"; assistantId: string; message: string }
  | { type: "cancel"; assistantId: string }
  | { type: "stream_finished"; assistantId: string }
  | { type: "set_active_result"; resultId: string };

export function createInitialChatState(conversationId: string): ChatState {
  return {
    conversationId,
    activeAssistantId: null,
    messages: [],
    toolCalls: {},
    results: {},
    resultOrder: [],
    activeResultId: null,
    phase: "idle",
    contextTokens: 0,
    contextWindowTokens: 256_000,
    contextNotice: null,
  };
}

function updateMessage(
  messages: ChatMessage[],
  id: string,
  update: (message: ChatMessage) => ChatMessage,
): ChatMessage[] {
  return messages.map((message) =>
    message.id === id ? update(message) : message,
  );
}

function phaseAfterFinish(current: TurnPhase): TurnPhase {
  return current === "cancelled" || current === "error" ? current : "complete";
}

function asArguments(value: unknown): Record<string, unknown> | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value))
    return undefined;
  return value as Record<string, unknown>;
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function findPendingFinal(
  messages: ChatMessage[],
  sourceId: string,
): FinalResultComponent | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const result = messages[index].finalResult;
    if (result?.source_tool_call_id === sourceId) return result;
  }
  return null;
}

export function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case "restore":
      return action.state;
    case "start_turn":
      return {
        ...state,
        messages: [
          ...state.messages,
          action.userMessage,
          action.assistantMessage,
        ],
        activeAssistantId: action.assistantMessage.id,
        phase: "streaming",
        contextNotice: null,
      };

    case "set_active_result":
      return state.results[action.resultId]
        ? { ...state, activeResultId: action.resultId }
        : state;

    case "request_error": {
      const messages = updateMessage(
        state.messages,
        action.assistantId,
        (message) => ({
          ...message,
          phase: "error",
          error: message.error ?? action.message,
        }),
      );
      const isActive = state.activeAssistantId === action.assistantId;
      return {
        ...state,
        messages,
        activeAssistantId: isActive ? null : state.activeAssistantId,
        phase: isActive ? "error" : state.phase,
      };
    }

    case "cancel": {
      const messages = updateMessage(
        state.messages,
        action.assistantId,
        (message) => ({
          ...message,
          phase: "cancelled",
          statusText: "已停止生成",
        }),
      );
      const isActive = state.activeAssistantId === action.assistantId;
      return {
        ...state,
        messages,
        activeAssistantId: isActive ? null : state.activeAssistantId,
        phase: isActive ? "cancelled" : state.phase,
      };
    }

    case "stream_finished": {
      const isActive = state.activeAssistantId === action.assistantId;
      const phase = isActive ? phaseAfterFinish(state.phase) : state.phase;
      const messages = updateMessage(
        state.messages,
        action.assistantId,
        (message) => ({
          ...message,
          phase: phaseAfterFinish(message.phase ?? "streaming"),
        }),
      );
      return {
        ...state,
        messages,
        activeAssistantId: isActive ? null : state.activeAssistantId,
        phase,
      };
    }

    case "event":
      break;
  }

  const { event, assistantId, receivedAt } = action;
  const metadata = event.metadata ?? {};
  let messages = state.messages;
  let toolCalls = state.toolCalls;
  let results = state.results;
  let resultOrder = state.resultOrder;
  let activeResultId = state.activeResultId;
  let phase = state.phase;
  let conversationId = state.conversationId;
  let activeAssistantId = state.activeAssistantId;
  let contextTokens = state.contextTokens;
  let contextWindowTokens = state.contextWindowTokens;
  let contextNotice = state.contextNotice;
  const isActiveTurn = activeAssistantId === assistantId;

  const nextTokens = asNumber(metadata.context_tokens);
  const nextWindow = asNumber(metadata.context_window_tokens);
  if (isActiveTurn && nextTokens != null && nextTokens >= 0)
    contextTokens = nextTokens;
  if (isActiveTurn && nextWindow != null && nextWindow > 0)
    contextWindowTokens = nextWindow;

  if (event.type === "status") {
    const statusText = event.content ?? null;
    if (statusText === "summarizing" && isActiveTurn) phase = "summarizing";
    if (statusText === "context_refreshed" && isActiveTurn) {
      const notice =
        typeof metadata.message === "string"
          ? metadata.message
          : "模型上下文已刷新，保留当前任务继续执行。聊天记录仍可查看。";
      contextNotice = notice;
    }
    if (
      statusText === "context_refreshed" ||
      statusText === "context_usage" ||
      statusText === "context_overflow" ||
      statusText === "context_tool_truncated"
    ) {
      // Don't overwrite assistant statusText with internal context markers.
    } else {
      messages = updateMessage(messages, assistantId, (message) => ({
        ...message,
        phase: statusText === "summarizing" ? "summarizing" : message.phase,
        statusText,
      }));
    }
    if (
      isActiveTurn &&
      (statusText === "context_overflow" ||
        statusText === "context_tool_truncated") &&
      typeof metadata.message === "string"
    ) {
      contextNotice = metadata.message;
    }
  } else if (event.type === "text_delta" && event.content) {
    messages = updateMessage(messages, assistantId, (message) => ({
      ...message,
      content: message.content + event.content,
    }));
  } else if (event.type === "text" && event.content) {
    messages = updateMessage(messages, assistantId, (message) => ({
      ...message,
      content: event.content ?? message.content,
    }));
  } else if (event.type === "error") {
    if (isActiveTurn) {
      phase = "error";
      activeAssistantId = null;
    }
    messages = updateMessage(messages, assistantId, (message) => ({
      ...message,
      phase: "error",
      error: event.content ?? "请求处理失败",
    }));
  }

  const isToolTerminal =
    event.type === "tool_result" || event.type === "final_result";
  if ((event.type === "tool_start" || isToolTerminal) && event.tool_call_id) {
    const id = event.tool_call_id;
    const existing = toolCalls[id];
    const success = metadata.success !== false;
    const component = isUiComponent(event.ui_component)
      ? event.ui_component
      : existing?.component;
    const record: ToolCallRecord = {
      id,
      turnId: assistantId,
      name: event.tool_name ?? existing?.name ?? "unknown",
      status:
        event.type === "tool_start" ? "running" : success ? "success" : "error",
      arguments:
        event.type === "tool_start"
          ? asArguments(metadata.arguments)
          : existing?.arguments,
      content: event.content ?? existing?.content,
      component,
      error:
        typeof metadata.error === "string"
          ? metadata.error
          : (existing?.error ?? null),
      executionTimeMs:
        asNumber(metadata.execution_time_ms) ??
        existing?.executionTimeMs ??
        null,
      startedAt: existing?.startedAt ?? receivedAt,
      completedAt: isToolTerminal ? receivedAt : existing?.completedAt,
    };
    toolCalls = { ...toolCalls, [id]: record };
    messages = updateMessage(messages, assistantId, (message) => ({
      ...message,
      toolCallIds: message.toolCallIds?.includes(id)
        ? message.toolCallIds
        : [...(message.toolCallIds ?? []), id],
    }));

    if (component?.type === "dataframe") {
      const pendingFinal = findPendingFinal(messages, id);
      results = {
        ...results,
        [id]: {
          id,
          turnId: assistantId,
          data: component,
          finalResult: results[id]?.finalResult ?? pendingFinal,
          createdAt: results[id]?.createdAt ?? receivedAt,
        },
      };
      if (!resultOrder.includes(id)) resultOrder = [...resultOrder, id];
      // 取消/切换会话后的迟到事件可写入历史，但不得抢当前洞察画布焦点
      if (isActiveTurn) activeResultId = id;
    }

    if (component?.type === "final_result") {
      const sourceId = component.source_tool_call_id;
      if (results[sourceId]) {
        results = {
          ...results,
          [sourceId]: { ...results[sourceId], finalResult: component },
        };
        if (isActiveTurn) activeResultId = sourceId;
      }
      messages = updateMessage(messages, assistantId, (message) => ({
        ...message,
        finalResult: component,
        statusText: null,
      }));
    }
  }

  if (event.type === "done") {
    if (isActiveTurn) {
      phase = phaseAfterFinish(phase);
      activeAssistantId = null;
    }
    const nextConversationId = metadata.conversation_id;
    if (typeof nextConversationId === "string" && nextConversationId) {
      conversationId = nextConversationId;
    }
    if (isActiveTurn && metadata.context_refreshed === true && !contextNotice) {
      contextNotice = "模型上下文已刷新，聊天记录仍可查看。";
    }
    messages = updateMessage(messages, assistantId, (message) => ({
      ...message,
      phase: phaseAfterFinish(message.phase ?? "streaming"),
      statusText: null,
      queryId:
        message.phase !== "cancelled" &&
        message.phase !== "error" &&
        typeof metadata.query_id === "string"
          ? metadata.query_id
          : null,
      confirmedQuestion:
        typeof metadata.confirmed_question === "string"
          ? metadata.confirmed_question
          : null,
    }));
  }

  return {
    ...state,
    conversationId,
    activeAssistantId,
    messages,
    toolCalls,
    results,
    resultOrder,
    activeResultId,
    phase,
    contextTokens,
    contextWindowTokens,
    contextNotice,
  };
}
