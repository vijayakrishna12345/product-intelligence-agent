from uuid import uuid4

import pytest

from pia.domain.errors import PersistenceError
from pia.repositories.chats import ChatRepository


def test_one_row_per_role_and_sequence():
    repo = ChatRepository()
    chat = repo.create("Hello there")
    turn = uuid4()
    user = repo.append_message(chat.id, turn_id=turn, role="user", content="Hi")
    tool = repo.append_message(
        chat.id, turn_id=turn, role="tool", content="search_catalog completed"
    )
    assistant = repo.append_message(chat.id, turn_id=turn, role="assistant", content="Done")
    assert user.sequence_no == 1
    assert tool.sequence_no == 2
    assert assistant.sequence_no == 3
    rows = repo.list_messages_for_context(chat.id)
    assert [row.role for row in rows] == ["user", "tool", "assistant"]


def test_system_role_rejected():
    repo = ChatRepository()
    chat = repo.create("x")
    with pytest.raises(PersistenceError):
        repo.append_message(chat.id, turn_id=uuid4(), role="system", content="nope")  # type: ignore[arg-type]


def test_keyset_older_page():
    repo = ChatRepository()
    chat = repo.create("paged")
    turn = uuid4()
    for index in range(6):
        repo.append_message(chat.id, turn_id=turn, role="user", content=f"m{index}")
    latest = repo.list_messages(chat.id, limit=2)
    assert [row.content for row in latest] == ["m4", "m5"]
    older = repo.list_messages(chat.id, before_sequence=latest[0].sequence_no, limit=2)
    assert [row.content for row in older] == ["m2", "m3"]


def test_no_list_all():
    repo = ChatRepository()
    assert not hasattr(repo, "list_all")


def test_set_title():
    repo = ChatRepository()
    chat = repo.create("New chat")
    repo.set_title(chat.id, "Advance Indoor pouches")
    assert repo.get(chat.id).title == "Advance Indoor pouches"
