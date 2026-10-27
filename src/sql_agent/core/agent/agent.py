"""Agent orchestrator with Vanna-style extension points."""

from __future__ import annotations

import asyncio
import logging
import time
import traceback
import uuid
from typing import Any, AsyncGenerator, List, Optional

from sql_agent.core.agent.config import AgentConfig
from sql_agent.core.audit import AuditLogger
from sql_agent.core.context.tokens import (
    estimate_request_tokens,
    estimate_message_tokens,
    estimate_text_tokens,
    is_context_overflow,
    truncate_tool_text,
    TRUNCATION_NOTICE,
)
from sql_agent.core.enhancer import LlmContextEnhancer, NoOpLlmContextEnhancer
from sql_agent.core.enricher import ToolContextEnricher
from sql_agent.core.errors import AgentError
from sql_agent.core.events import AgentEvent
from sql_agent.core.filter import ConversationFilter
from sql_agent.core.lifecycle import LifecycleHook
from sql_agent.core.llm import LlmMessage, LlmRequest, LlmResponse, LlmService
from sql_agent.capabilities.agent_memory import AgentMemory
from sql_agent.components import DataFrameComponent, FinalResultComponent
from sql_agent.core.middleware import LlmMiddleware
from sql_agent.core.observability import ObservabilityProvider
from sql_agent.core.system_prompt import DefaultSystemPromptBuilder, SystemPromptBuilder
from sql_agent.integrations.db import InMemoryAgentMemory
from sql_agent.core.recovery import ErrorRecoveryStrategy
from sql_agent.core.registry import ToolRegistry
from sql_agent.core.storage import (
    Conversation,
    ConversationStore,
    MemoryConversationStore,
    Message,
)
from sql_agent.core.tool import ToolCall, ToolContext, ToolSchema, ToolResult
from sql_agent.core.user import RequestContext, User, UserResolver
from sql_agent.core.workflow import NoOpWorkflowHandler, WorkflowHandler
from sql_agent.core.context.window import ContextWindowBudget
from sql_agent.services.finalization import finalization_call, systematic_sample as _systematic_sample

logger = logging.getLogger(__name__)


class Agent:
    """Compose LLM + tools + memory with pluggable extension points.

    Extension points (aligned with Vanna):
      - lifecycle_hooks
      - llm_middlewares
      - conversation_filters
      - context_enrichers
      - llm_context_enhancer
      - workflow_handler
      - error_recovery_strategy (stored; optional use on failures)
      - observability_provider
      - audit_logger
    """

    def __init__(
        self,
        llm_service: LlmService,
        tool_registry: ToolRegistry,
        user_resolver: UserResolver,
        agent_memory: Optional[AgentMemory] = None,
        conversation_store: Optional[ConversationStore] = None,
        config: Optional[AgentConfig] = None,
        system_prompt_builder: Optional[SystemPromptBuilder] = None,
        lifecycle_hooks: Optional[List[LifecycleHook]] = None,
        llm_middlewares: Optional[List[LlmMiddleware]] = None,
        conversation_filters: Optional[List[ConversationFilter]] = None,
        context_enrichers: Optional[List[ToolContextEnricher]] = None,
        llm_context_enhancer: Optional[LlmContextEnhancer] = None,
        workflow_handler: Optional[WorkflowHandler] = None,
        error_recovery_strategy: Optional[ErrorRecoveryStrategy] = None,
        observability_provider: Optional[ObservabilityProvider] = None,
        audit_logger: Optional[AuditLogger] = None,
        knowledge_service: Any = None,
    ) -> None:
        self.llm_service = llm_service
        self.tool_registry = tool_registry
        self.user_resolver = user_resolver
        self.agent_memory = agent_memory or InMemoryAgentMemory()
        self.conversation_store = conversation_store or MemoryConversationStore()
        self.config = config or AgentConfig()
        self.system_prompt_builder = (
            system_prompt_builder or DefaultSystemPromptBuilder()
        )
        self.lifecycle_hooks = lifecycle_hooks or []
        self.llm_middlewares = llm_middlewares or []
        self.conversation_filters = conversation_filters or []
        self.context_enrichers = context_enrichers or []
        self.llm_context_enhancer = llm_context_enhancer or NoOpLlmContextEnhancer()
        self.workflow_handler = workflow_handler or NoOpWorkflowHandler()
        self.error_recovery_strategy = error_recovery_strategy
        self.observability_provider = observability_provider
        self.audit_logger = audit_logger
        self.knowledge_service = knowledge_service

        if self.audit_logger and self.config.audit_config.enabled:
            self.tool_registry.audit_logger = self.audit_logger
            self.tool_registry.audit_config = self.config.audit_config

    async def send_message(
        self,
        request_context: RequestContext,
        message: str,
        *,
        conversation_id: Optional[str] = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        try:
            async for event in self._send_message(
                request_context, message, conversation_id=conversation_id
            ):
                yield event
        except AgentError as e:
            logger.error("AgentError in send_message: %s", e)
            yield AgentEvent(
                type="error",
                content="请求处理失败，请检查输入或稍后重试。",
                metadata={"error_code": "agent_error"},
            )
            yield AgentEvent(type="done")
        except Exception as e:
            logger.error(
                "Error in send_message (conversation_id=%s): %s\n%s",
                conversation_id,
                e,
                traceback.format_exc(),
            )
            yield AgentEvent(
                type="error",
                content="服务暂时无法完成分析，请稍后重试。",
                metadata={"error_code": "agent_unexpected_error"},
            )
            yield AgentEvent(type="done")

    async def _send_message(
        self,
        request_context: RequestContext,
        message: str,
        *,
        conversation_id: Optional[str] = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        if not message.strip():
            return

        user = await self.user_resolver.resolve_user(request_context)
        request_id = str(uuid.uuid4())

        # lifecycle: before_message (may rewrite text)
        working_message = message
        for hook in self.lifecycle_hooks:
            rewritten = await hook.before_message(user, working_message)
            if rewritten is not None:
                working_message = rewritten

        if conversation_id is None:
            conversation_id = str(uuid.uuid4())

        conversation = await self.conversation_store.get_conversation(
            conversation_id, user
        )
        if conversation is None:
            conversation = Conversation(id=conversation_id, user=user, messages=[])

        # workflow short-circuit (before appending user message to history)
        workflow_result = await self.workflow_handler.try_handle(
            self, user, conversation, working_message
        )
        if workflow_result.should_skip_llm:
            if workflow_result.conversation_mutation:
                await workflow_result.conversation_mutation(conversation)
            for event in workflow_result.events:
                yield event
            if self.config.auto_save_conversations:
                await self.conversation_store.update_conversation(conversation)
            yield AgentEvent(type="done", metadata={"conversation_id": conversation.id})
            return

        # Stores may return live objects. Work on a copy until input is accepted.
        conversation = conversation.model_copy(deep=True)
        conversation.add_message(Message(role="user", content=working_message))

        if self.config.include_thinking_indicators:
            yield AgentEvent(type="status", content="thinking")

        tool_schemas = await self.tool_registry.get_schemas(user)
        errors = await self.llm_service.validate_tools(tool_schemas)
        if errors:
            logger.warning("Tool schema validation warnings: %s", errors)

        system_prompt = await self.system_prompt_builder.build_system_prompt(
            user, tool_schemas
        )
        if system_prompt is not None:
            system_prompt = await self.llm_context_enhancer.enhance_system_prompt(
                system_prompt, working_message, user
            )

        window_budget = ContextWindowBudget.from_config(self.config)
        context_window = window_budget.total
        context_refreshed = False
        context_refresh_count = 0
        provider_retries = 0
        force_refresh = False
        safety_tokens = window_budget.safety
        input_budget = window_budget.input

        tool_context = ToolContext(
            user=user,
            conversation_id=conversation.id,
            request_id=request_id,
            agent_memory=self.agent_memory,
        )
        for enricher in self.context_enrichers:
            tool_context = await enricher.enrich_context(tool_context)
        tool_context.metadata["context_window_tokens"] = context_window
        tool_context.metadata["context_safety_tokens"] = safety_tokens
        deadline = time.monotonic() + self.config.max_request_seconds
        tool_context.metadata.update(request_deadline=deadline,
                                     max_sql_attempts=self.config.max_sql_attempts,
                                     max_sql_repairs=self.config.max_sql_repairs)

        tool_iterations = 0
        last_sql_result: Optional[tuple[str, DataFrameComponent]] = None
        query_ids: dict[str, str] = {}
        query_questions: dict[str, str] = {}
        finalize_draft: Optional[str] = None
        context_overflow_stopped = False
        request_budget_stopped = False
        request_message_count = len(conversation.messages)
        input_accepted = False
        truncated_tool_ids: set[str] = set()
        while tool_iterations < self.config.max_tool_iterations:
            request = await self._build_llm_request(
                conversation, tool_schemas, user, system_prompt
            )
            request = await self._apply_middlewares_before(request)
            context_tokens = estimate_request_tokens(request)
            if time.monotonic() >= deadline:
                request_budget_stopped = True
                yield AgentEvent(type="error", content="本轮处理时间预算已耗尽，请缩小问题范围或补充业务条件后重试。",
                                 metadata={"error_code": "request_budget_exhausted"})
                break
            budget = min(input_budget, context_window - safety_tokens - (request.max_tokens or 0))
            if not input_accepted:
                if context_tokens > budget:
                    # Validate the irreducible new request before touching old history.
                    minimal = conversation.model_copy(deep=True)
                    minimal.messages = [conversation.messages[-1]]
                    minimal_request = await self._build_llm_request(minimal, tool_schemas, user, system_prompt)
                    minimal_request = await self._apply_middlewares_before(minimal_request)
                    minimum_tokens = estimate_request_tokens(minimal_request)
                    minimum_budget = min(input_budget, context_window - safety_tokens - (minimal_request.max_tokens or 0))
                    if minimum_tokens > minimum_budget:
                        yield AgentEvent(type="error", content=(
                            f"本次输入连同系统提示和工具定义约 {minimum_tokens:,} tokens，"
                            f"可用输入预算为 {minimum_budget:,} tokens（总窗口 {context_window:,}）。"
                            "请缩短问题或拆成可独立处理的任务；原会话未改变，输入未截断。"
                        ), metadata={"error_code": "context_input_too_large", "input_rejected": True,
                                     "rejected_context_tokens": minimum_tokens,
                                     "context_input_budget": minimum_budget,
                                     "context_window_tokens": context_window})
                        yield AgentEvent(type="done", metadata={"conversation_id": conversation.id})
                        return
                input_accepted = True
                if self.config.auto_save_conversations:
                    await self.conversation_store.update_conversation(conversation.model_copy(deep=True))

            refreshed = False
            if force_refresh or context_tokens > budget:
                latest_user_index = max(
                    i for i, msg in enumerate(conversation.messages) if msg.role == "user"
                )
                current = conversation.messages[latest_user_index:]
                latest_batch = next((
                    i for i in range(len(current) - 1, 0, -1)
                    if current[i].role == "assistant" and current[i].tool_calls
                ), None)
                candidate = conversation.model_copy(deep=True)
                candidate.messages = [current[0].model_copy(deep=True)]
                if latest_batch is not None:
                    candidate.messages.extend(msg.model_copy(deep=True) for msg in current[latest_batch:])
                # Each pass shrinks one result to a fixed notice at worst.
                # Never edit call arguments or lose call/result pairs.
                candidates = [m for m in candidate.messages if m.role == "tool"]
                for _ in range(len(candidates) + 1):
                    request = await self._build_llm_request(candidate, tool_schemas, user, system_prompt)
                    request = await self._apply_middlewares_before(request)
                    context_tokens = estimate_request_tokens(request)
                    budget = min(input_budget, context_window - safety_tokens - (request.max_tokens or 0))
                    if context_tokens <= budget or not candidates:
                        break
                    largest = max(candidates, key=lambda m: estimate_text_tokens(m.content))
                    candidates.remove(largest)
                    target = max(estimate_text_tokens(TRUNCATION_NOTICE),
                                 estimate_text_tokens(largest.content) - (context_tokens - budget) - 16)
                    clipped = truncate_tool_text(largest.content, target)
                    if clipped != largest.content:
                        largest.content = clipped
                        truncated_tool_ids.add(largest.tool_call_id or "unknown")
                force_refresh = False
                if context_tokens <= budget:
                    conversation = candidate
                    tool_context.metadata.pop("known_schema", None)
                    tool_context.metadata.pop("schema_searches", None)
                    context_refreshed = refreshed = True
                    context_refresh_count += 1
                    if self.config.auto_save_conversations:
                        await self.conversation_store.update_conversation(conversation.model_copy(deep=True))

            usage_metadata = {
                "context_tokens": context_tokens,
                "context_window_tokens": context_window,
                "context_input_budget": budget,
                "context_safety_tokens": safety_tokens,
                "context_truncated_tool_count": len(truncated_tool_ids),
                "context_tokens_estimated": True,
                "context_refreshed": context_refreshed,
                "context_refresh_count": context_refresh_count,
            }
            if refreshed:
                yield AgentEvent(type="status", content="context_refreshed", metadata={
                    **usage_metadata,
                    "message": "模型上下文已刷新（不做摘要压缩）；保留当前问题和最近工具结果，继续执行。聊天记录仍可查看。",
                })
            yield AgentEvent(type="status", content="context_usage", metadata=usage_metadata)
            if context_tokens > budget:
                context_overflow_stopped = True
                yield AgentEvent(type="error", content=(
                    "保留当前任务所需的工具调用参数、系统提示或工具定义仍超过可用上下文。"
                    "无法安全自动续跑，请缩小任务范围或减少工具/提示内容后重试。"
                ), metadata={"error_code": "context_input_too_large", **usage_metadata})
                break
            # Explicitly bound generation to the reserved output budget.
            if request.max_tokens is None:
                request.max_tokens = self.config.max_tokens or self.config.context_output_reserve_tokens
            tool_context.metadata["visible_tool_ids"] = {
                msg.tool_call_id for msg in request.messages if msg.role == "tool"
            }
            request_message_count = len(conversation.messages)
            streamed_text = False
            buffer_response_text = (
                self.config.auto_finalize_results and last_sql_result is not None
            )

            try:
                if self.config.stream_responses:
                    content_parts: List[str] = []
                    reasoning_parts: List[str] = []
                    streamed_chars = 0
                    reported_chars = 0
                    pending_usage_text: List[str] = []
                    generated_tokens = 0
                    tool_calls = None
                    finish_reason = None
                    async for chunk in self._stream_with_deadline(request, deadline):
                        if chunk.reasoning_content:
                            reasoning_parts.append(chunk.reasoning_content)
                        if chunk.content:
                            content_parts.append(chunk.content)
                            streamed_text = True
                            if not buffer_response_text:
                                yield AgentEvent(
                                    type="text_delta", content=chunk.content
                                )
                        protocol_text = (chunk.reasoning_content or "") + (chunk.content or "")
                        if protocol_text:
                            streamed_chars += len(protocol_text)
                            pending_usage_text.append(protocol_text)
                            if streamed_chars - reported_chars >= 512:
                                reported_chars = streamed_chars
                                generated_tokens += estimate_text_tokens("".join(pending_usage_text))
                                pending_usage_text.clear()
                                yield AgentEvent(type="status", content="context_usage", metadata={
                                    **usage_metadata,
                                    "context_tokens": context_tokens + generated_tokens,
                                })
                        if chunk.tool_calls:
                            tool_calls = chunk.tool_calls
                        if chunk.finish_reason:
                            finish_reason = chunk.finish_reason
                    response = LlmResponse(
                        content="".join(content_parts) or None,
                        reasoning_content="".join(reasoning_parts) or None,
                        tool_calls=tool_calls,
                        finish_reason=finish_reason,
                    )
                else:
                    response = await asyncio.wait_for(self.llm_service.send_request(request),
                                                      max(0.001, deadline - time.monotonic()))
            except Exception as e:
                if isinstance(e, TimeoutError) and time.monotonic() >= deadline:
                    request_budget_stopped = True
                    yield AgentEvent(type="error", content="本轮处理时间预算已耗尽，已停止等待模型响应。",
                                     metadata={"error_code": "request_budget_exhausted"})
                    break
                if is_context_overflow(e) and not streamed_text and provider_retries < 2:
                    provider_retries += 1
                    # The provider tokenizer/limit can differ from our estimate.
                    input_budget = min(input_budget, int(context_tokens * 0.7))
                    force_refresh = True
                    continue
                if is_context_overflow(e):
                    context_overflow_stopped = True
                    yield AgentEvent(type="error", content="模型服务仍拒绝当前上下文，请缩短问题或检查模型窗口配置。",
                                     metadata={"error_code": "provider_context_overflow"})
                    break
                if self.error_recovery_strategy:
                    action = await self.error_recovery_strategy.handle_llm_error(
                        e, request
                    )
                    yield AgentEvent(
                        type="error",
                        content="模型服务暂时不可用，请稍后重试。",
                        metadata={"recovery": action.action.value},
                    )
                raise

            response = await self._apply_middlewares_after(request, response)

            if response.is_tool_call():
                tool_iterations += 1
                conversation.add_message(
                    Message(
                        role="assistant",
                        content=response.content or "",
                        tool_calls=response.tool_calls,
                        reasoning_content=response.reasoning_content,
                    )
                )
                if (
                    response.content
                    and not streamed_text
                    and not buffer_response_text
                ):
                    yield AgentEvent(type="text", content=response.content)

                for tool_call in response.tool_calls or []:
                    tool_context.metadata["tool_call_id"] = tool_call.id
                    yield AgentEvent(
                        type="tool_start",
                        content=f"调用工具: {tool_call.name}",
                        tool_name=tool_call.name,
                        tool_call_id=tool_call.id,
                        metadata={"arguments": tool_call.arguments},
                    )

                    tool = (
                        await self.tool_registry.get_tool(tool_call.name)
                        if await self.tool_registry.is_llm_exposed(tool_call.name)
                        else None
                    )
                    if tool:
                        for hook in self.lifecycle_hooks:
                            await hook.before_tool(tool, tool_context)

                    if time.monotonic() >= deadline:
                        request_budget_stopped = True
                        result = ToolResult(success=False, result_for_llm="本轮时间预算耗尽，未执行该工具，请结束回答。",
                                            user_error="本轮时间预算已耗尽。", metadata={"error_code": "request_budget_exhausted"})
                    else:
                        result = await self.tool_registry.execute(tool_call, tool_context)

                    if tool_call.name == "run_sql" and self.knowledge_service is not None:
                        query_ids.pop(tool_call.id, None)
                        query_questions.pop(tool_call.id, None)
                        try:
                            query_id = await asyncio.to_thread(
                                self.knowledge_service.record_execution,
                                working_message, tool_context, tool_call, result,
                            )
                            query_ids[tool_call.id] = query_id
                            query_questions[tool_call.id] = tool_call.arguments.get("question") or working_message
                            result.metadata["query_id"] = query_id
                        except Exception as error:
                            logger.warning("Query provenance unavailable (%s)", type(error).__name__)

                    for hook in self.lifecycle_hooks:
                        maybe = await hook.after_tool(result)
                        if maybe is not None:
                            result = maybe

                    if tool_call.name == "run_sql":
                        if result.success and isinstance(
                            result.ui_component, DataFrameComponent
                        ):
                            last_sql_result = (
                                tool_call.id,
                                result.ui_component,
                            )
                        else:
                            # A newer failed SQL attempt means the previous result
                            # is no longer a trustworthy final answer.
                            last_sql_result = None

                    preview = truncate_tool_text(result.result_for_llm, max(
                        estimate_text_tokens(TRUNCATION_NOTICE), input_budget // 2
                    ))
                    if preview != result.result_for_llm:
                        tool_context.metadata.pop("known_schema", None)
                        tool_context.metadata.pop("schema_searches", None)
                        truncated_tool_ids.add(tool_call.id)
                        yield AgentEvent(type="status", content="context_tool_truncated", metadata={
                            "message": "工具返回文本过大，已限制发给模型的内容并标记不完整；查询结果面板保留。",
                            "tool_call_id": tool_call.id,
                        })
                    yield AgentEvent(
                        type="tool_result",
                        content=(
                            preview
                            if result.success
                            else result.user_error or "工具执行失败。"
                        ),
                        tool_name=tool_call.name,
                        tool_call_id=tool_call.id,
                        ui_component=result.ui_component,
                        metadata={
                            "success": result.success,
                            "error": result.user_error,
                            **result.metadata,
                        },
                    )
                    conversation.add_message(
                        Message(
                            role="tool",
                            content=preview,
                            tool_call_id=tool_call.id,
                        )
                    )
                    tool_context.metadata["visible_tool_ids"].add(tool_call.id)

            else:
                if (
                    self.config.auto_finalize_results
                    and last_sql_result is not None
                ):
                    finalize_draft = response.content
                    if response.reasoning_content is not None:
                        # Keep the original model turn for the next tools request;
                        # finalization emits its separate, public result below.
                        conversation.add_message(Message(
                            role="assistant", content=response.content or "",
                            reasoning_content=response.reasoning_content,
                        ))
                elif response.content or response.reasoning_content is not None:
                    conversation.add_message(
                        Message(role="assistant", content=response.content or "",
                                reasoning_content=response.reasoning_content)
                    )
                    if response.content and not streamed_text:
                        yield AgentEvent(type="text", content=response.content)
                break

        reached_tool_limit = tool_iterations >= self.config.max_tool_iterations
        if reached_tool_limit:
            warn = (
                f"已达到工具调用上限 ({self.config.max_tool_iterations})，"
                "任务可能未完成。"
            )
            logger.warning(warn)
            yield AgentEvent(type="status", content=warn)

        finalized = False
        final_source_tool_call_id: Optional[str] = None
        if (
            self.config.auto_finalize_results
            and last_sql_result is not None
            and not context_overflow_stopped
        ):
            source_tool_call_id, dataframe = last_sql_result
            final_source_tool_call_id = source_tool_call_id
            final_call = finalization_call(self.config, source_tool_call_id, dataframe, working_message,
                finalize_draft, tool_limit=reached_tool_limit, time_limit=request_budget_stopped)

            yield AgentEvent(type="status", content="summarizing")
            yield AgentEvent(
                type="tool_start",
                content="正在生成查询结论",
                tool_name=final_call.name,
                tool_call_id=final_call.id,
                metadata={"source_tool_call_id": source_tool_call_id},
            )

            finalizer = await self.tool_registry.get_tool(final_call.name)
            if finalizer:
                for hook in self.lifecycle_hooks:
                    await hook.before_tool(finalizer, tool_context)
            final_result = await self.tool_registry.execute(
                final_call, tool_context, allow_internal=True
            )
            for hook in self.lifecycle_hooks:
                maybe = await hook.after_tool(final_result)
                if maybe is not None:
                    final_result = maybe

            if final_result.success and isinstance(
                final_result.ui_component, FinalResultComponent
            ):
                component = final_result.ui_component
                conversation.add_message(
                    Message(
                        role="assistant",
                        content=component.summary,
                        metadata={
                            "final_result": component.model_dump(mode="json")
                        },
                    )
                )
                yield AgentEvent(
                    type="final_result",
                    content=component.summary,
                    tool_name=final_call.name,
                    tool_call_id=final_call.id,
                    ui_component=component,
                    metadata={
                        "success": True,
                        "error": None,
                        **final_result.metadata,
                    },
                )
                finalized = True
            else:
                yield AgentEvent(
                    type="tool_result",
                    content=final_result.user_error or "查询结论生成失败。",
                    tool_name=final_call.name,
                    tool_call_id=final_call.id,
                    metadata={
                        "success": False,
                        "error": final_result.user_error,
                        **final_result.metadata,
                    },
                )
                qualifier = "" if dataframe.row_count_is_exact else "至少 "
                fallback_text = finalize_draft or (
                    f"查询已完成，共返回 {qualifier}{dataframe.row_count} 行结果。"
                )
                conversation.add_message(
                    Message(role="assistant", content=fallback_text)
                )
                yield AgentEvent(type="text", content=fallback_text)

        if not self.config.auto_finalize_results and last_sql_result is not None and not context_overflow_stopped:
            final_source_tool_call_id = last_sql_result[0]

        if self.config.auto_save_conversations:
            await self.conversation_store.update_conversation(conversation)

        for hook in self.lifecycle_hooks:
            await hook.after_message(conversation)

        final_query_id = None
        if self.knowledge_service is not None:
            if (not context_overflow_stopped and not reached_tool_limit and not request_budget_stopped
                    and time.monotonic() < deadline and final_source_tool_call_id):
                final_query_id = query_ids.get(final_source_tool_call_id)
            try:
                await asyncio.to_thread(self.knowledge_service.complete_request, user.id, request_id, final_query_id)
            except Exception as error:
                final_query_id = None
                logger.warning("Final query provenance unavailable (%s)", type(error).__name__)

        # Do not rerun request middleware merely to update the UI counter.
        if not context_overflow_stopped:
            context_tokens = estimate_request_tokens(request) + sum(
                estimate_message_tokens(msg)
                for msg in conversation.messages[request_message_count:]
            )
        yield AgentEvent(
            type="done",
            metadata={
                "conversation_id": conversation.id,
                "tool_iterations": tool_iterations,
                "request_id": request_id,
                "tool_limit_stopped": reached_tool_limit,
                "finalized": finalized,
                "source_tool_call_id": final_source_tool_call_id,
                "query_id": final_query_id,
                "confirmed_question": query_questions.get(final_source_tool_call_id) if final_query_id else None,
                "context_tokens": context_tokens,
                "context_window_tokens": context_window,
                "context_refreshed": context_refreshed,
                "context_overflow_stopped": context_overflow_stopped,
                "context_refresh_count": context_refresh_count,
                "context_tokens_estimated": True,
                "request_budget_stopped": request_budget_stopped or time.monotonic() >= deadline,
            },
        )

    async def get_available_tools(self, user: User) -> List[ToolSchema]:
        return await self.tool_registry.get_schemas(user)

    async def _stream_with_deadline(self, request, deadline):
        async with asyncio.timeout(max(0.001, deadline - time.monotonic())):
            async for chunk in self.llm_service.stream_request(request):
                yield chunk

    async def _build_llm_request(
        self,
        conversation: Conversation,
        tool_schemas: List[ToolSchema],
        user: User,
        system_prompt: Optional[str] = None,
    ) -> LlmRequest:
        filtered = conversation.messages
        for filt in self.conversation_filters:
            filtered = await filt.filter_messages(filtered)

        messages = [
            LlmMessage(
                role=msg.role,
                content=msg.content,
                tool_calls=msg.tool_calls,
                tool_call_id=msg.tool_call_id,
                reasoning_content=msg.reasoning_content,
            )
            for msg in filtered
        ]
        messages = await self.llm_context_enhancer.enhance_user_messages(messages, user)

        return LlmRequest(
            messages=messages,
            tools=tool_schemas or None,
            user=user,
            stream=self.config.stream_responses,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            system_prompt=system_prompt,
        )

    async def _apply_middlewares_before(self, request: LlmRequest) -> LlmRequest:
        for mw in self.llm_middlewares:
            request = await mw.before_llm_request(request)
        return request

    async def _apply_middlewares_after(
        self, request: LlmRequest, response: LlmResponse
    ) -> LlmResponse:
        for mw in self.llm_middlewares:
            response = await mw.after_llm_response(request, response)
        return response
