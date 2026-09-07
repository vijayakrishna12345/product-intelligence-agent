"""ConversationSimulator adapter with an in-memory thread store."""

from __future__ import annotations

from pia.agent.factory import run_query
from pia.domain.models import ChatMessage
from pia.settings import get_settings

_THREADS: dict[str, list[ChatMessage]] = {}


def reset_threads() -> None:
    _THREADS.clear()


async def model_callback(user_input: str, turns=None, thread_id: str | None = None):
    import asyncio
    from datetime import UTC, datetime
    from uuid import uuid4

    from deepeval.test_case import Turn

    settings = get_settings()
    key = thread_id or "default"
    history = list(_THREADS.get(key, []))
    result = await asyncio.to_thread(
        run_query,
        user_input,
        persisted_messages=history,
        thread_id=key,
        catalog=_catalog(),
        settings=settings,
    )
    turn_id = uuid4()
    chat_id = uuid4()
    now = datetime.now(UTC)
    history.append(
        ChatMessage(
            id=uuid4(),
            chat_id=chat_id,
            turn_id=turn_id,
            sequence_no=len(history) + 1,
            role="user",
            content=user_input,
            created_at=now,
        )
    )
    history.append(
        ChatMessage(
            id=uuid4(),
            chat_id=chat_id,
            turn_id=turn_id,
            sequence_no=len(history) + 1,
            role="assistant",
            content=result.answer,
            created_at=now,
        )
    )
    _THREADS[key] = history
    return Turn(role="assistant", content=result.answer)


def _catalog():
    from pathlib import Path

    from pia.repositories.catalog import CatalogRepository
    from pia.services.catalog import CatalogService
    from pia.settings import get_settings

    root = Path(__file__).resolve().parents[2]
    settings = get_settings()
    repo = CatalogRepository(
        catalog_path=root / "data" / "catalog.json",
        sample_path=root / "data" / "sample_catalog.json",
        settings=settings,
    )
    return CatalogService(repo, settings)
