from uuid import uuid4

from langchain_core.messages import HumanMessage

from pia.agent.context import build_context
from pia.domain.models import ChatMessage
from pia.settings import get_settings


def _msg(role, content, turn, seq):
    from datetime import UTC, datetime

    return ChatMessage(
        id=uuid4(),
        chat_id=uuid4(),
        turn_id=turn,
        sequence_no=seq,
        role=role,
        content=content,
        created_at=datetime.now(UTC),
    )


def test_last_n_completed_without_tools_or_current(sample_settings):
    t1, t2, t3 = uuid4(), uuid4(), uuid4()
    messages = [
        _msg("user", "one", t1, 1),
        _msg("tool", "get_product_details completed", t1, 2),
        _msg("assistant", "first answer", t1, 3),
        _msg("user", "two", t2, 4),
        _msg("assistant", "second answer", t2, 5),
        _msg("user", "current should not be here", t3, 6),
    ]
    history, tokens = build_context(messages, running_turn_ids={t3}, settings=get_settings())
    texts = [item.content for item in history]
    assert "current should not be here" not in texts
    assert "get_product_details completed" not in texts
    assert isinstance(history[0], HumanMessage)
    assert tokens > 0
