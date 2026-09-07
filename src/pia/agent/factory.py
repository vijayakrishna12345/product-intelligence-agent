"""LangChain create_agent factory for Groq."""

from __future__ import annotations

from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware, ToolCallLimitMiddleware
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_groq import ChatGroq

from pia.agent.context import build_context
from pia.agent.guardrails import GuardrailMiddleware, LoopGuardMiddleware
from pia.agent.prompts import SYSTEM_PROMPT
from pia.agent.tools import build_tools
from pia.domain.errors import LLMError
from pia.domain.models import AgentResult, ChatMessage, Usage
from pia.logging import get_logger
from pia.services.comparison import ComparisonService
from pia.services.usage import estimate_tokens
from pia.settings import Settings, get_settings

log = get_logger("pia.agent")

_SYSTEM_TOOLS_TOKENS: int | None = None


def build_model(settings: Settings | None = None) -> ChatGroq:
    settings = settings or get_settings()
    if not settings.groq_api_key:
        raise LLMError("GROQ_API_KEY is not set")
    # include_reasoning=false hides GPT-OSS CoT on Groq Chat Completions.
    return ChatGroq(
        model=settings.groq_model,
        api_key=settings.groq_api_key,
        model_kwargs={"include_reasoning": settings.include_reasoning},
    )


def create_catalog_agent(
    catalog,
    comparison: ComparisonService | None = None,
    settings: Settings | None = None,
):
    settings = settings or get_settings()
    comparison = comparison or ComparisonService(catalog, settings)
    tools = build_tools(catalog, comparison, settings)
    middleware = [
        GuardrailMiddleware(),
        LoopGuardMiddleware(),
        ModelCallLimitMiddleware(run_limit=settings.model_call_limit, exit_behavior="end"),
        ToolCallLimitMiddleware(run_limit=settings.tool_call_limit, exit_behavior="end"),
    ]
    model = build_model(settings)
    return create_agent(
        model,
        tools,
        system_prompt=SYSTEM_PROMPT,
        middleware=middleware,
    )


def system_tools_tokens(settings: Settings | None = None) -> int:
    global _SYSTEM_TOOLS_TOKENS
    if _SYSTEM_TOOLS_TOKENS is None:
        from pia.agent.tools import SearchArgs

        schema_blob = SYSTEM_PROMPT + SearchArgs.model_json_schema().__str__()
        _SYSTEM_TOOLS_TOKENS = estimate_tokens(schema_blob) + 400
    return _SYSTEM_TOOLS_TOKENS


def _usage_from_messages(messages: list[Any]) -> dict[str, int | None]:
    input_tokens = output_tokens = cached = None
    for message in reversed(messages):
        meta = getattr(message, "usage_metadata", None) or {}
        if not meta and isinstance(message, dict):
            meta = message.get("usage_metadata") or {}
        if not meta:
            additional = getattr(message, "response_metadata", None) or {}
            token_usage = additional.get("token_usage") or additional.get("usage") or {}
            if token_usage:
                input_tokens = token_usage.get("prompt_tokens") or token_usage.get("input_tokens")
                output_tokens = token_usage.get("completion_tokens") or token_usage.get(
                    "output_tokens"
                )
                cached = (
                    token_usage.get("prompt_tokens_details", {}).get("cached_tokens")
                    if isinstance(token_usage.get("prompt_tokens_details"), dict)
                    else token_usage.get("cached_tokens")
                )
                break
        if meta:
            input_tokens = meta.get("input_tokens") or meta.get("prompt_tokens")
            output_tokens = meta.get("output_tokens") or meta.get("completion_tokens")
            details = meta.get("input_token_details") or {}
            cached = (
                details.get("cache_read")
                or details.get("cached_tokens")
                or meta.get("cached_tokens")
            )
            break
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_tokens": cached,
    }


def _extract_tools(messages: list[Any]) -> list[dict]:
    tools: list[dict] = []
    by_id: dict[str, dict] = {}
    for message in messages:
        if isinstance(message, AIMessage) and message.tool_calls:
            for call in message.tool_calls:
                name = call.get("name") if isinstance(call, dict) else call["name"]
                args = call.get("args") if isinstance(call, dict) else call["args"]
                call_id = call.get("id") if isinstance(call, dict) else getattr(call, "id", None)
                item = {"name": name, "args": args, "id": call_id}
                tools.append(item)
                if call_id:
                    by_id[str(call_id)] = item
        if isinstance(message, ToolMessage):
            call_id = getattr(message, "tool_call_id", None)
            target = by_id.get(str(call_id)) if call_id else None
            if target is None and tools:
                target = tools[-1]
            if target is not None:
                target["result"] = message.content
                target["status"] = "success"
    return tools


def _final_text(messages: list[Any]) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage) and not message.tool_calls:
            content = message.content
            return content if isinstance(content, str) else str(content)
    return ""


def run_query(
    user_input: str,
    *,
    persisted_messages: list[ChatMessage] | None = None,
    thread_id: str | None = None,
    running_turn_ids: set | None = None,
    agent=None,
    catalog=None,
    settings: Settings | None = None,
) -> AgentResult:
    """Synchronous agent invoke. Streamlit uses AgentRunner; eval calls this directly."""
    import time

    del thread_id  # chat id is for callers; context comes from persisted_messages
    settings = settings or get_settings()
    if agent is None:
        if catalog is None:
            raise LLMError("catalog service is required")
        agent = create_catalog_agent(catalog, settings=settings)
    history, history_tokens = build_context(
        persisted_messages,
        running_turn_ids=running_turn_ids,
        settings=settings,
    )
    payload: list[BaseMessage] = [*history, HumanMessage(content=user_input)]
    started = time.perf_counter()
    try:
        result = agent.invoke(
            {"messages": payload},
            config={"recursion_limit": settings.recursion_limit},
        )
    except Exception as exc:
        message = str(exc)
        if "recursion limit" in message.lower() or "GraphRecursionError" in type(exc).__name__:
            raise LLMError(
                "I hit my step limit while looking that up. "
                "Please name one product or SKU, or ask a narrower question."
            ) from exc
        raise LLMError(message) from exc
    latency_ms = int((time.perf_counter() - started) * 1000)
    messages = result.get("messages") if isinstance(result, dict) else result
    messages = list(messages or [])
    tools = _extract_tools(messages)
    answer = _final_text(messages)
    token_usage = _usage_from_messages(messages)
    tool_result_tokens = sum(
        estimate_tokens(str(item.get("result"))) for item in tools if item.get("result")
    )
    retrieval = []
    for item in tools:
        if item.get("result"):
            retrieval.append(str(item["result"])[:2000])
    usage = Usage(
        history_messages=len(history),
        history_tokens=history_tokens,
        tool_result_tokens=tool_result_tokens,
        system_tools_tokens=system_tools_tokens(settings),
        input_tokens=token_usage["input_tokens"],
        output_tokens=token_usage["output_tokens"],
        cached_tokens=token_usage["cached_tokens"],
        tools_called=len(tools),
        agent_steps=len(tools) + 1,
        latency_ms=latency_ms,
        model=settings.groq_model,
        prompt_version=settings.prompt_version,
    )
    log.info(
        "usage input=%s output=%s cached=%s latency_ms=%s tools=%s",
        usage.input_tokens,
        usage.output_tokens,
        usage.cached_tokens,
        usage.latency_ms,
        usage.tools_called,
    )
    return AgentResult(answer=answer, tools_called=tools, retrieval_context=retrieval, usage=usage)
