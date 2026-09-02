"""Agent orchestrator with Vanna-style extension points."""

from __future__ import annotations

import logging
import traceback
import uuid
from typing import AsyncGenerator, List, Optional

from sql_agent.core.agent.config import AgentConfig
from sql_agent.core.audit import AuditLogger
from sql_agent.core.enhancer import LlmContextEnhancer, NoOpLlmContextEnhancer
from sql_agent.core.enricher import ToolContextEnricher
from sql_agent.core.errors import AgentError
from sql_agent.core.events import AgentEvent
from sql_agent.core.filter import ConversationFilter
from sql_agent.core.lifecycle import LifecycleHook
from sql_agent.core.llm import LlmMessage, LlmRequest, LlmResponse, LlmService
from sql_agent.capabilities.agent_memory import AgentMemory
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
from sql_agent.core.tool import ToolContext, ToolSchema
from sql_agent.core.user import RequestContext, User, UserResolver
from sql_agent.core.workflow import NoOpWorkflowHandler, WorkflowHandler

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
            yield AgentEvent(type="error", content=str(e))
            yield AgentEvent(type="done")
        except Exception as e:
            logger.error(
                "Error in send_message (conversation_id=%s): %s\n%s",
                conversation_id,
                e,
                traceback.format_exc(),
            )
            yield AgentEvent(type="error", content=f"处理消息时出错: {e}")
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

        conversation.add_message(Message(role="user", content=working_message))
        await self.conversation_store.update_conversation(conversation)

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

        tool_context = ToolContext(
            user=user,
            conversation_id=conversation.id,
            request_id=request_id,
            agent_memory=self.agent_memory,
        )
        for enricher in self.context_enrichers:
            tool_context = await enricher.enrich_context(tool_context)

        request = await self._build_llm_request(
            conversation, tool_schemas, user, system_prompt
        )

        tool_iterations = 0
        while tool_iterations < self.config.max_tool_iterations:
            streamed_text = False
            request = await self._apply_middlewares_before(request)

            try:
                if self.config.stream_responses:
                    content_parts: List[str] = []
                    tool_calls = None
                    finish_reason = None
                    async for chunk in self.llm_service.stream_request(request):
                        if chunk.content:
                            content_parts.append(chunk.content)
                            streamed_text = True
                            yield AgentEvent(type="text_delta", content=chunk.content)
                        if chunk.tool_calls:
                            tool_calls = chunk.tool_calls
                        if chunk.finish_reason:
                            finish_reason = chunk.finish_reason
                    response = LlmResponse(
                        content="".join(content_parts) or None,
                        tool_calls=tool_calls,
                        finish_reason=finish_reason,
                    )
                else:
                    response = await self.llm_service.send_request(request)
            except Exception as e:
                if self.error_recovery_strategy:
                    action = await self.error_recovery_strategy.handle_llm_error(
                        e, request
                    )
                    yield AgentEvent(
                        type="error",
                        content=action.message or str(e),
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
                    )
                )
                if response.content and not streamed_text:
                    yield AgentEvent(type="text", content=response.content)

                for tool_call in response.tool_calls or []:
                    yield AgentEvent(
                        type="tool_start",
                        content=f"调用工具: {tool_call.name}",
                        tool_name=tool_call.name,
                        tool_call_id=tool_call.id,
                        metadata={"arguments": tool_call.arguments},
                    )

                    tool = await self.tool_registry.get_tool(tool_call.name)
                    if tool:
                        for hook in self.lifecycle_hooks:
                            await hook.before_tool(tool, tool_context)

                    result = await self.tool_registry.execute(tool_call, tool_context)

                    for hook in self.lifecycle_hooks:
                        maybe = await hook.after_tool(result)
                        if maybe is not None:
                            result = maybe

                    yield AgentEvent(
                        type="tool_result",
                        content=result.result_for_llm,
                        tool_name=tool_call.name,
                        tool_call_id=tool_call.id,
                        metadata={
                            "success": result.success,
                            "error": result.error,
                            **result.metadata,
                        },
                    )
                    conversation.add_message(
                        Message(
                            role="tool",
                            content=result.result_for_llm,
                            tool_call_id=tool_call.id,
                        )
                    )

                request = await self._build_llm_request(
                    conversation, tool_schemas, user, system_prompt
                )
            else:
                if response.content:
                    conversation.add_message(
                        Message(role="assistant", content=response.content)
                    )
                    if not streamed_text:
                        yield AgentEvent(type="text", content=response.content)
                break

        if tool_iterations >= self.config.max_tool_iterations:
            warn = (
                f"已达到工具调用上限 ({self.config.max_tool_iterations})，"
                "任务可能未完成。"
            )
            logger.warning(warn)
            yield AgentEvent(type="status", content=warn)

        if self.config.auto_save_conversations:
            await self.conversation_store.update_conversation(conversation)

        for hook in self.lifecycle_hooks:
            await hook.after_message(conversation)

        yield AgentEvent(
            type="done",
            metadata={
                "conversation_id": conversation.id,
                "tool_iterations": tool_iterations,
            },
        )

    async def get_available_tools(self, user: User) -> List[ToolSchema]:
        return await self.tool_registry.get_schemas(user)

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
