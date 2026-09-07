from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import RemoteProtocolError

from pia.agent.context import build_context
from pia.domain.errors import PersistenceError
from pia.domain.models import AgentRun, ToolCall
from pia.repositories.agent_runs import AgentRunRepository
from pia.repositories.chats import ChatRepository


def test_run_lifecycle_and_compact_tool_message():
    chats = ChatRepository()
    runs = AgentRunRepository()
    chat = chats.create("run")
    turn = uuid4()
    user = chats.append_message(chat.id, turn_id=turn, role="user", content="Compare")
    run = AgentRun(
        id=uuid4(),
        chat_id=chat.id,
        turn_id=turn,
        status="running",
        user_message_id=user.id,
        started_at=datetime.now(UTC),
    )
    runs.create_run(run)
    tool_msg = chats.append_message(
        chat.id, turn_id=turn, role="tool", content="get_product_details completed"
    )
    runs.insert_tool_call(
        ToolCall(
            id=uuid4(),
            chat_id=chat.id,
            turn_id=turn,
            message_id=tool_msg.id,
            tool_name="get_product_details",
            arguments={"product_query": "KONG"},
            result={"sku": "SYN-KONG-FLYER", "source_type": "synthetic_sample"},
            status="success",
        )
    )
    assert tool_msg.content == "get_product_details completed"
    stored = runs.list_tool_calls(turn)[0]
    assert stored.result["sku"] == "SYN-KONG-FLYER"
    run.status = "completed"
    runs.update_run(run)
    assert runs.get_active_run(chat.id) is None
    listed = runs.list_runs_for_chat(chat.id)
    assert listed[0].id == run.id


def test_running_turn_omitted_from_context():
    chats = ChatRepository()
    chat = chats.create("ctx")
    done = uuid4()
    running = uuid4()
    chats.append_message(chat.id, turn_id=done, role="user", content="First")
    chats.append_message(chat.id, turn_id=done, role="assistant", content="Answer")
    chats.append_message(chat.id, turn_id=running, role="user", content="Second")
    history, _tokens = build_context(
        chats.list_messages_for_context(chat.id),
        running_turn_ids={running},
    )
    texts = [item.content for item in history]
    assert "First" in texts
    assert "Second" not in texts


def test_stale_failed():
    runs = AgentRunRepository()
    chat_id = uuid4()
    turn = uuid4()
    run = AgentRun(
        id=uuid4(),
        chat_id=chat_id,
        turn_id=turn,
        status="running",
        user_message_id=uuid4(),
        started_at=datetime.now(UTC) - timedelta(seconds=500),
    )
    runs.create_run(run)
    assert runs.fail_stale_runs(180) == 1
    assert runs.get(run.id).status == "failed"


class _BoomQuery:
    def select(self, *args, **kwargs):
        return self

    def eq(self, *args, **kwargs):
        return self

    def order(self, *args, **kwargs):
        return self

    def execute(self):
        raise RemoteProtocolError("Server disconnected")


class _BoomClient:
    def table(self, _name):
        return _BoomQuery()


def test_list_tool_calls_wraps_disconnect():
    runs = AgentRunRepository(client=_BoomClient())
    with pytest.raises(PersistenceError):
        runs.list_tool_calls(uuid4())
