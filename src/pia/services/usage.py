"""Map agent_runs usage fields into Context & Usage tables."""

from __future__ import annotations

import math

from pia.domain.models import AgentRun, Usage


def estimate_tokens(text: str | None) -> int:
    """Approximate token count: ceil(len/4). Documented as heuristic only."""
    if not text:
        return 0
    return math.ceil(len(text) / 4)


def token_totals(runs: list[AgentRun]) -> tuple[int, int, int]:
    """Sum Groq-reported tokens for one conversation. Missing values count as 0."""
    input_tokens = sum(int(run.input_tokens or 0) for run in runs)
    output_tokens = sum(int(run.output_tokens or 0) for run in runs)
    return input_tokens, output_tokens, input_tokens + output_tokens


def cache_hit_rate(cached: int | None, input_tokens: int | None) -> float | None:
    if cached is None or not input_tokens:
        return None
    return round(cached / input_tokens, 4)


def usage_from_run(run: AgentRun) -> Usage:
    return Usage(
        history_tokens=run.history_tokens or 0,
        tool_result_tokens=run.tool_result_tokens or 0,
        system_tools_tokens=run.system_tools_tokens or 0,
        input_tokens=run.input_tokens,
        output_tokens=run.output_tokens,
        cached_tokens=run.cached_tokens,
        cache_hit_rate=cache_hit_rate(run.cached_tokens, run.input_tokens),
        tools_called=run.tools_called_count,
        agent_steps=run.agent_steps,
        latency_ms=run.latency_ms,
        model=run.model,
        prompt_version=run.prompt_version,
    )


def _cell(value: object) -> str:
    if value is None:
        return "unavailable"
    return str(value)


def usage_tables(usage: Usage, *, history_messages: int = 0) -> tuple[list[dict], list[dict]]:
    if usage.cached_tokens is None:
        cached_display = "unavailable"
        hit_display = "unavailable"
    else:
        cached_display = _cell(usage.cached_tokens)
        hit_display = (
            f"{usage.cache_hit_rate * 100:.1f}%"
            if usage.cache_hit_rate is not None
            else "unavailable"
        )
    table_a = [
        {"Metric": "Conversation messages", "Current turn": _cell(history_messages)},
        {"Metric": "History tokens", "Current turn": _cell(usage.history_tokens)},
        {"Metric": "Tool-result tokens", "Current turn": _cell(usage.tool_result_tokens)},
        {"Metric": "System + tools tokens", "Current turn": _cell(usage.system_tools_tokens)},
        {"Metric": "Total input tokens", "Current turn": _cell(usage.input_tokens)},
        {"Metric": "Cached tokens", "Current turn": cached_display},
        {"Metric": "Cache hit rate", "Current turn": hit_display},
    ]
    total = None
    if usage.input_tokens is not None and usage.output_tokens is not None:
        total = usage.input_tokens + usage.output_tokens
    table_b = [
        {"Metric": "Output tokens", "Value": _cell(usage.output_tokens)},
        {"Metric": "Total tokens", "Value": _cell(total)},
        {"Metric": "Model", "Value": _cell(usage.model)},
        {"Metric": "Tools called", "Value": _cell(usage.tools_called)},
        {"Metric": "Agent steps", "Value": _cell(usage.agent_steps)},
        {
            "Metric": "Latency",
            "Value": (
                f"{usage.latency_ms / 1000:.1f}s" if usage.latency_ms is not None else "unavailable"
            ),
        },
    ]
    return table_a, table_b
