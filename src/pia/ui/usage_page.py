"""Per-conversation context, tools, and token usage."""

from __future__ import annotations

from uuid import UUID

import streamlit as st

from pia.domain.errors import PersistenceError
from pia.services.usage import usage_from_run, usage_tables
from pia.ui.stores import get_stores


def render_usage() -> None:
    chats, runs, _catalog, _runner = get_stores()
    st.title("Usage & Execution")
    st.caption(
        "Telemetry for conversations opened in this browser. "
        "Token splits that Groq does not provide use a len/4 heuristic."
    )
    recents: list[str] = st.session_state.get("recent_chats") or []
    if not recents:
        st.info("Open Chat and send a message to create a conversation, then return here.")
        return
    labels: dict[str, str] = {}
    for item in recents:
        try:
            rec = chats.get(UUID(item))
        except (ValueError, PersistenceError):
            rec = None
        labels[item] = (rec.title if rec else None) or "New chat"
    chosen = st.selectbox(
        "Conversation",
        recents,
        format_func=lambda key: labels.get(key, key[:8]),
    )
    try:
        chat_id = UUID(chosen)
    except ValueError:
        st.error("Invalid chat id.")
        return
    try:
        rows = runs.list_runs_for_chat(chat_id)
    except PersistenceError:
        st.error("Could not load usage for this conversation.")
        return
    if not rows:
        st.info("No agent runs stored for this conversation yet.")
        return
    st.dataframe(
        [
            {
                "Status": run.status,
                "Model": run.model,
                "Input tokens": run.input_tokens,
                "Output tokens": run.output_tokens,
                "Cached": run.cached_tokens,
                "History tokens": run.history_tokens,
                "Tool-result tokens": run.tool_result_tokens,
                "Tools": run.tools_called_count,
                "Steps": run.agent_steps,
                "Latency ms": run.latency_ms,
            }
            for run in rows
        ],
        hide_index=True,
        width="stretch",
    )
    for run in rows:
        tokens = f"{run.input_tokens or 0}/{run.output_tokens or 0}"
        heading = f"{run.status} · {run.started_at} · {tokens} tokens"
        with st.expander(heading):
            if run.status == "completed":
                usage = usage_from_run(run)
                table_a, table_b = usage_tables(usage, history_messages=usage.history_messages)
                st.dataframe(table_a, hide_index=True)
                st.dataframe(table_b, hide_index=True)
            try:
                tools = runs.list_tool_calls(run.turn_id)
            except PersistenceError:
                st.warning("Could not load tool calls for this turn.")
                continue
            if not tools:
                st.write("No tool calls on this turn.")
                continue
            for tool in tools:
                st.markdown(f"**{tool.tool_name}** · {tool.status}")
                if tool.arguments:
                    st.json(tool.arguments)
                if isinstance(tool.result, dict):
                    preview = {
                        key: tool.result.get(key)
                        for key in (
                            "sku",
                            "product",
                            "ok",
                            "error",
                            "source_type",
                            "review_count",
                        )
                        if key in tool.result
                    }
                    if preview:
                        st.json(preview)
            if run.error_message:
                st.error(run.error_message)
