"""Streamlit chat page helpers."""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import streamlit as st

from pia.domain.errors import CatalogUnavailable, LLMError, PersistenceError
from pia.repositories.agent_runs import AgentRunRepository
from pia.repositories.chats import ChatRepository
from pia.services.usage import token_totals
from pia.settings import get_settings
from pia.ui.charts import (
    render_compare,
    render_details,
    render_reviews,
    sources_caption,
)
from pia.ui.followups import (
    asked_for_charts,
    asked_for_sources,
    payload_has_charts,
    suggest_followups,
)
from pia.ui.stores import get_stores


def _json(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return None


def _ensure_chat(chats: ChatRepository) -> UUID:
    params = st.query_params
    raw = params.get("chat")
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    recents: list[str] = st.session_state.setdefault("recent_chats", [])
    chat_id: UUID | None = None
    if raw:
        try:
            chat_id = UUID(str(raw))
        except ValueError:
            chat_id = None
    if chat_id is None:
        existing = st.session_state.get("pia_chat_id") or st.session_state.get("chat_id")
        if isinstance(existing, UUID):
            chat_id = existing
        elif existing:
            try:
                chat_id = UUID(str(existing))
            except ValueError:
                chat_id = None
    if chat_id is None and recents:
        try:
            chat_id = UUID(recents[0])
        except ValueError:
            chat_id = None
    if chat_id is None:
        chat_id = uuid4()
    if str(raw or "") != str(chat_id):
        st.query_params["chat"] = str(chat_id)
    if chats.get(chat_id) is None:
        chats.create(title="New chat", chat_id=chat_id)
    key = str(chat_id)
    if key not in recents:
        recents.insert(0, key)
        st.session_state.recent_chats = recents[:8]
    st.session_state.pia_chat_id = chat_id
    st.session_state.chat_id = chat_id
    return chat_id


def _chat_title(chats: ChatRepository, chat_id: str) -> str:
    try:
        rec = chats.get(UUID(chat_id))
    except ValueError:
        return "New chat"
    if rec is None:
        return "New chat"
    return rec.title or "New chat"


@st.fragment(run_every="2s")
def _watch_active_run(runs: AgentRunRepository, chat_id: UUID) -> None:
    try:
        active = runs.get_active_run(chat_id)
    except PersistenceError:
        st.warning("Still waiting…")
        return
    if active is None or active.status not in {"queued", "running"}:
        st.rerun()
        return
    st.info("Working…")


def _submit_prompt(runner, chat_id: UUID, prompt: str, settings) -> None:
    count = st.session_state.get("request_count", 0)
    if count >= settings.max_requests_per_session:
        st.error("Session request limit reached.")
        return
    if runner is None:
        st.error("The language model is not configured.")
        return
    try:
        st.session_state.request_count = count + 1
        runner.submit(chat_id, prompt)
        st.rerun()
    except (PersistenceError, LLMError, CatalogUnavailable) as exc:
        st.error(str(exc))


def _reveal_flag(kind: str, turn_id: UUID) -> bool:
    flags: dict[str, bool] = st.session_state.setdefault(f"reveal_{kind}", {})
    return bool(flags.get(str(turn_id)))


def _set_reveal(kind: str, turn_id: UUID, value: bool) -> None:
    flags: dict[str, bool] = st.session_state.setdefault(f"reveal_{kind}", {})
    flags[str(turn_id)] = value
    st.session_state[f"reveal_{kind}"] = flags


def _render_tool_visuals(payloads: list) -> None:
    for payload in payloads:
        if payload.get("products") and payload.get("ok") is not False:
            render_compare(payload)
        elif payload.get("rating_distribution") or payload.get("reviews"):
            render_reviews(payload)
        elif payload.get("price") is not None or payload.get("rating_value") is not None:
            render_details(payload)


def _snapshot_footer(source_type: str) -> str:
    if source_type == "petbarn_snapshot":
        return (
            "All data above comes from a Petbarn catalog snapshot, "
            "not live pricing or live reviews."
        )
    return "All data above comes from synthetic sample data, not live Petbarn pricing or reviews."


def render_chat() -> None:
    try:
        _render_chat()
    except PersistenceError:
        st.error("Could not load this conversation. Refresh to try again.")


def _render_chat() -> None:
    settings = get_settings()
    chats, runs, catalog, runner = get_stores()
    catalog.refresh()
    runs.fail_stale_runs(settings.agent_run_stale_seconds)
    st.title("Chat")
    st.caption("Ask about products, reviews, and comparisons in the ingested catalog.")

    if st.sidebar.button("New chat"):
        new_id = uuid4()
        chats.create(title="New chat", chat_id=new_id)
        recents: list[str] = st.session_state.setdefault("recent_chats", [])
        recents.insert(0, str(new_id))
        st.session_state.recent_chats = recents[:8]
        st.session_state.pia_chat_id = new_id
        st.session_state.chat_id = new_id
        st.query_params["chat"] = str(new_id)
        st.rerun()

    chat_id = _ensure_chat(chats)
    current = chats.get(chat_id)
    st.sidebar.caption("Conversations in this browser")
    recents = st.session_state.get("recent_chats") or []
    for item in recents:
        label = _chat_title(chats, item)
        if len(label) > 42:
            label = label[:41] + "…"
        if st.sidebar.button(label, key=f"recent-{item}", width="stretch"):
            st.session_state.pia_chat_id = UUID(item)
            st.session_state.chat_id = UUID(item)
            st.query_params["chat"] = item
            st.rerun()

    chat_runs = runs.list_runs_for_chat(chat_id, limit=200)
    _in_tokens, _out_tokens, total_tokens = token_totals(chat_runs)
    st.sidebar.metric("Tokens this chat", f"{total_tokens:,}")
    st.sidebar.caption(f"{_in_tokens:,} input · {_out_tokens:,} output")

    products = catalog.list_products()
    source_type = products[0].source_type if products else "synthetic_sample"
    st.sidebar.metric("Products", len(products))
    st.sidebar.write(
        "Source: "
        f"{'Petbarn snapshot' if source_type == 'petbarn_snapshot' else 'Synthetic sample data'}"
    )
    if products and products[0].scraped_at:
        st.sidebar.write(f"Snapshot: {products[0].scraped_at}")
    st.sidebar.write(f"Model: {settings.groq_model}")
    if current:
        st.subheader(current.title or "New chat")

    if st.session_state.get("extra_for_chat") != str(chat_id):
        st.session_state.extra_messages = []
        st.session_state.extra_for_chat = str(chat_id)

    page = chats.list_messages(chat_id, limit=settings.chat_page_size)
    extras = st.session_state.extra_messages
    oldest = extras[0] if extras else (page[0] if page else None)
    if oldest and st.button("Load older"):
        older = chats.list_messages(
            chat_id, before_sequence=oldest.sequence_no, limit=settings.chat_page_size
        )
        st.session_state.extra_messages = older + extras
        st.rerun()
    messages = st.session_state.extra_messages + page
    seen: set[UUID] = set()
    ordered = []
    for item in messages:
        if item.id in seen:
            continue
        seen.add(item.id)
        ordered.append(item)

    active = runs.get_active_run(chat_id)
    if active and active.status in {"queued", "running"}:
        _watch_active_run(runs, chat_id)

    by_turn: dict[UUID, list] = {}
    turn_order: list[UUID] = []
    for item in ordered:
        if item.turn_id not in by_turn:
            turn_order.append(item.turn_id)
        by_turn.setdefault(item.turn_id, []).append(item)

    last_completed = None
    for turn_id in reversed(turn_order):
        rows = by_turn[turn_id]
        if any(row.role == "assistant" for row in rows):
            last_completed = turn_id
            break

    catalog_names = [item.name for item in products[:12] if item.name]
    for turn_id in turn_order:
        rows = by_turn[turn_id]
        users = [row for row in rows if row.role == "user"]
        assistants = [row for row in rows if row.role == "assistant"]
        if users:
            with st.chat_message("user"):
                st.write(users[0].content)
        try:
            tools = runs.list_tool_calls(turn_id)
        except PersistenceError:
            tools = []
        payloads = []
        for tool in tools:
            parsed = tool.result if isinstance(tool.result, dict) else _json(tool.result)
            if isinstance(parsed, dict):
                payloads.append(parsed)
        if assistants:
            with st.chat_message("assistant"):
                st.write(assistants[-1].content)
                user_text = users[0].content if users else ""
                show_charts = asked_for_charts(user_text) or _reveal_flag("charts", turn_id)
                show_sources = asked_for_sources(user_text) or _reveal_flag("sources", turn_id)
                if show_charts:
                    _render_tool_visuals(payloads)
                caption = sources_caption(payloads)
                if show_sources and caption:
                    st.info(caption)
                if turn_id == last_completed and not (
                    active and active.status in {"queued", "running"}
                ):
                    if payload_has_charts(payloads) or caption:
                        cols = st.columns(2)
                        if payload_has_charts(payloads):
                            chart_label = "Hide charts" if show_charts else "Show charts"
                            if cols[0].button(chart_label, key=f"reveal-charts-{turn_id}"):
                                _set_reveal("charts", turn_id, not show_charts)
                                st.rerun()
                        if caption:
                            source_label = "Hide sources" if show_sources else "Show sources"
                            if cols[1].button(source_label, key=f"reveal-sources-{turn_id}"):
                                _set_reveal("sources", turn_id, not show_sources)
                                st.rerun()
                    asked = [row.content for row in ordered if row.role == "user"]
                    used = (st.session_state.get("used_followups") or {}).get(str(chat_id), [])
                    followups = suggest_followups(
                        payloads,
                        catalog_names=catalog_names,
                        asked=asked + list(used),
                    )
                    if followups:
                        st.markdown("**Suggested follow-ups**")
                        for index, question in enumerate(followups):
                            if st.button(
                                question,
                                key=f"followup-{turn_id}-{index}",
                                width="stretch",
                            ):
                                bag = st.session_state.setdefault("used_followups", {})
                                prior = list(bag.get(str(chat_id), []))
                                prior.append(question)
                                bag[str(chat_id)] = prior
                                st.session_state.used_followups = bag
                                _submit_prompt(runner, chat_id, question, settings)

    busy = active is not None and active.status in {"queued", "running"}
    prompt = st.chat_input("Ask about catalog products", disabled=busy)
    note = json.dumps(_snapshot_footer(source_type))
    st.markdown(
        f"""
<style>
[data-testid="stChatInput"] {{
  margin-bottom: 1.55rem !important;
}}
[data-testid="stChatInput"]::after {{
  content: {note};
  position: absolute;
  left: 0;
  right: 0;
  top: calc(100% + 0.28rem);
  text-align: center;
  font-size: 0.8rem;
  line-height: 1.3;
  opacity: 0.7;
  pointer-events: none;
}}
</style>
""",
        unsafe_allow_html=True,
    )
    if prompt:
        _submit_prompt(runner, chat_id, prompt, settings)
