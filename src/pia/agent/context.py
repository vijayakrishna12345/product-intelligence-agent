"""Model context: last N completed user+assistant turns. Not DB pagination."""

from __future__ import annotations

from uuid import UUID

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from pia.domain.models import ChatMessage
from pia.services.usage import estimate_tokens
from pia.settings import Settings, get_settings


def build_context(
    persisted_messages: list[ChatMessage] | None,
    *,
    running_turn_ids: set[UUID] | None = None,
    settings: Settings | None = None,
) -> tuple[list[BaseMessage], int]:
    """Return history without the current query. System prompt lives on create_agent."""
    settings = settings or get_settings()
    running = running_turn_ids or set()
    messages = list(persisted_messages or [])
    turns: dict[UUID, list[ChatMessage]] = {}
    order: list[UUID] = []
    for item in messages:
        if item.turn_id in running:
            continue
        if item.turn_id not in turns:
            turns[item.turn_id] = []
            order.append(item.turn_id)
        turns[item.turn_id].append(item)

    completed: list[tuple[ChatMessage, ChatMessage]] = []
    for turn_id in order:
        rows = turns[turn_id]
        users = [row for row in rows if row.role == "user"]
        assistants = [row for row in rows if row.role == "assistant"]
        final = assistants[-1] if assistants else None
        if not users or not final:
            continue
        if len(assistants) == 1 and not (final.content or "").strip():
            continue
        completed.append((users[0], final))

    window = completed[-settings.recent_turns :]
    while window:
        history: list[BaseMessage] = []
        tokens = 0
        for user, assistant in window:
            history.append(HumanMessage(content=user.content))
            content = assistant.content
            tokens += estimate_tokens(user.content) + estimate_tokens(content)
            history.append(AIMessage(content=content))
        if tokens <= settings.max_history_tokens:
            return history, tokens
        window = window[1:]
    return [], 0
