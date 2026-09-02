import { describe, expect, it } from "vitest";
import type {
  AgentEvent,
  ChatMessage,
  DataFrameComponent,
  FinalResultComponent,
} from "../types";
import { chatReducer, createInitialChatState } from "./chatReducer";

const user: ChatMessage = { id: "u1", role: "user", content: "查询订单" };
const assistant: ChatMessage = {
  id: "a1",
  role: "assistant",
  content: "",
  phase: "streaming",
  toolCallIds: [],
};

const dataframe: DataFrameComponent = {
  type: "dataframe",
  title: "查询结果",
  columns: [
    { name: "month", data_type: "string" },
    { name: "amount", data_type: "number" },
  ],
  rows: [{ month: "2026-01", amount: 12 }],
  row_count: 1,
  row_count_is_exact: true,
  displayed_row_count: 1,
  truncated: false,
  sql: "SELECT month, amount FROM orders",
};

const finalResult: FinalResultComponent = {
  type: "final_result",
  source_tool_call_id: "sql-1",
  title: "月度订单",
  summary: "一月订单金额为 12。",
  insights: ["金额为 12"],
  chart: {
    type: "bar",
    x_field: "month",
    y_fields: ["amount"],
  },
  warnings: [],
};

function evt(event: Omit<AgentEvent, "protocol_version">): AgentEvent {
  return { protocol_version: "1", ...event };
}

function startedState() {
  return chatReducer(createInitialChatState("local"), {
    type: "start_turn",
    userMessage: user,
    assistantMessage: assistant,
  });
}

describe("chatReducer", () => {
  it("keeps repeated calls to the same tool as separate runway steps", () => {
    let state = startedState();
    for (const [id, receivedAt] of [
      ["describe-1", 1],
      ["describe-2", 2],
    ] as const) {
      state = chatReducer(state, {
        type: "event",
        assistantId: "a1",
        receivedAt,
        event: evt({
          type: "tool_start",
          tool_name: "describe_table",
          tool_call_id: id,
          metadata: { arguments: { table_name: id } },
        }),
      });
    }

    expect(Object.keys(state.toolCalls)).toEqual(["describe-1", "describe-2"]);
    expect(state.messages[1].toolCallIds).toEqual(["describe-1", "describe-2"]);
  });

  it("links final result to its dataframe artifact and consumes done metadata", () => {
    let state = startedState();
    state = chatReducer(state, {
      type: "event",
      assistantId: "a1",
      receivedAt: 1,
      event: evt({
        type: "tool_result",
        tool_name: "run_sql",
        tool_call_id: "sql-1",
        ui_component: dataframe,
        metadata: { success: true, execution_time_ms: 14 },
      }),
    });
    state = chatReducer(state, {
      type: "event",
      assistantId: "a1",
      receivedAt: 2,
      event: evt({
        type: "final_result",
        tool_name: "finalize_result",
        tool_call_id: "final-1",
        ui_component: finalResult,
        metadata: { success: true },
      }),
    });
    state = chatReducer(state, {
      type: "event",
      assistantId: "a1",
      receivedAt: 3,
      event: evt({
        type: "done",
        metadata: { conversation_id: "server-id", finalized: true },
      }),
    });

    expect(state.results["sql-1"].finalResult?.title).toBe("月度订单");
    expect(state.activeResultId).toBe("sql-1");
    expect(state.conversationId).toBe("server-id");
    expect(state.phase).toBe("complete");
    expect(state.toolCalls["sql-1"].executionTimeMs).toBe(14);
  });

  it("associates an out-of-order final result when dataframe arrives later", () => {
    let state = startedState();
    state = chatReducer(state, {
      type: "event",
      assistantId: "a1",
      receivedAt: 1,
      event: evt({
        type: "final_result",
        tool_name: "finalize_result",
        tool_call_id: "final-1",
        ui_component: finalResult,
        metadata: { success: true },
      }),
    });
    state = chatReducer(state, {
      type: "event",
      assistantId: "a1",
      receivedAt: 2,
      event: evt({
        type: "tool_result",
        tool_name: "run_sql",
        tool_call_id: "sql-1",
        ui_component: dataframe,
        metadata: { success: true },
      }),
    });

    expect(state.results["sql-1"].finalResult?.summary).toBe(
      "一月订单金额为 12。",
    );
  });

  it("does not turn a cancelled request back into complete", () => {
    let state = startedState();
    state = chatReducer(state, { type: "cancel", assistantId: "a1" });
    state = chatReducer(state, { type: "stream_finished", assistantId: "a1" });
    expect(state.phase).toBe("cancelled");
  });

  it("keeps late cancelled events from stealing the active result canvas", () => {
    let state = startedState();
    state = chatReducer(state, {
      type: "event",
      assistantId: "a1",
      receivedAt: 1,
      event: evt({
        type: "tool_result",
        tool_name: "run_sql",
        tool_call_id: "sql-old",
        ui_component: dataframe,
        metadata: { success: true },
      }),
    });
    expect(state.activeResultId).toBe("sql-old");

    state = chatReducer(state, { type: "cancel", assistantId: "a1" });

    const nextUser: ChatMessage = {
      id: "u2",
      role: "user",
      content: "下一问",
    };
    const nextAssistant: ChatMessage = {
      id: "a2",
      role: "assistant",
      content: "",
      phase: "streaming",
      toolCallIds: [],
    };
    state = chatReducer(state, {
      type: "start_turn",
      userMessage: nextUser,
      assistantMessage: nextAssistant,
    });

    const newerFrame: DataFrameComponent = {
      ...dataframe,
      sql: "SELECT 2",
      rows: [{ month: "2026-02", amount: 20 }],
    };
    state = chatReducer(state, {
      type: "event",
      assistantId: "a2",
      receivedAt: 2,
      event: evt({
        type: "tool_result",
        tool_name: "run_sql",
        tool_call_id: "sql-new",
        ui_component: newerFrame,
        metadata: { success: true },
      }),
    });
    expect(state.activeResultId).toBe("sql-new");

    state = chatReducer(state, {
      type: "event",
      assistantId: "a1",
      receivedAt: 3,
      event: evt({
        type: "tool_result",
        tool_name: "run_sql",
        tool_call_id: "sql-late",
        ui_component: {
          ...dataframe,
          sql: "SELECT late",
        },
        metadata: { success: true },
      }),
    });

    expect(state.results["sql-late"]).toBeTruthy();
    expect(state.activeResultId).toBe("sql-new");
    expect(state.activeAssistantId).toBe("a2");
  });
});
