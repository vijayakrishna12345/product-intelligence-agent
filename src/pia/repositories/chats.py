"""Chat timeline persistence. No list_all for the public UI."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pia.domain.errors import PersistenceError
from pia.domain.models import Chat, ChatMessage, MessageRole
from pia.logging import get_logger
from pia.repositories.catalog import _as_datetime

log = get_logger("pia.chats")

Role = MessageRole


def _now() -> datetime:
    return datetime.now(UTC)


def _chat_from_row(row: dict[str, Any]) -> Chat:
    return Chat(
        id=UUID(str(row["id"])),
        title=row.get("title") or "New chat",
        created_at=_as_datetime(row.get("created_at")) or _now(),
        updated_at=_as_datetime(row.get("updated_at")) or _now(),
        next_sequence_no=int(row.get("next_sequence_no") or 0),
    )


def _message_from_row(row: dict[str, Any]) -> ChatMessage:
    return ChatMessage(
        id=UUID(str(row["id"])),
        chat_id=UUID(str(row["chat_id"])),
        turn_id=UUID(str(row["turn_id"])),
        sequence_no=int(row["sequence_no"]),
        role=row["role"],
        content=row.get("content") or "",
        created_at=_as_datetime(row.get("created_at")) or _now(),
        prompt_version=row.get("prompt_version"),
    )


class ChatRepository:
    """Create/get/append/keyset page. Never list every chat."""

    def __init__(self, client: Any | None = None) -> None:
        self._client = client
        self._chats: dict[UUID, Chat] = {}
        self._messages: dict[UUID, list[ChatMessage]] = {}
        self._seq: dict[UUID, int] = {}

    def create(self, title: str = "New chat", chat_id: UUID | None = None) -> Chat:
        chat_id = chat_id or uuid4()
        now = _now()
        chat = Chat(
            id=chat_id,
            title=title[:80] or "New chat",
            created_at=now,
            updated_at=now,
            next_sequence_no=0,
        )
        if self._client is None:
            self._chats[chat_id] = chat
            self._messages[chat_id] = []
            self._seq[chat_id] = 0
            log.info("chat created id=%s", chat_id)
            return chat
        try:
            result = (
                self._client.table("chats")
                .insert(
                    {
                        "id": str(chat.id),
                        "title": chat.title,
                        "created_at": chat.created_at.isoformat(),
                        "updated_at": chat.updated_at.isoformat(),
                        "next_sequence_no": 0,
                    }
                )
                .execute()
            )
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        row = (result.data or [{}])[0]
        log.info("chat created id=%s", chat_id)
        return _chat_from_row(row) if row.get("id") else chat

    def set_title(self, chat_id: UUID, title: str) -> None:
        cleaned = (title or "").strip()[:80] or "New chat"
        if self._client is None:
            chat = self._chats.get(chat_id)
            if chat:
                chat.title = cleaned
                chat.updated_at = _now()
            return
        try:
            self._client.table("chats").update(
                {"title": cleaned, "updated_at": _now().isoformat()}
            ).eq("id", str(chat_id)).execute()
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        chat = self.get(chat_id)
        if chat:
            chat.title = cleaned

    def get(self, chat_id: UUID) -> Chat | None:
        if self._client is None:
            return self._chats.get(chat_id)
        try:
            result = (
                self._client.table("chats").select("*").eq("id", str(chat_id)).limit(1).execute()
            )
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        rows = result.data or []
        return _chat_from_row(rows[0]) if rows else None

    def allocate_sequence(self, chat_id: UUID) -> int:
        if self._client is None:
            self._seq[chat_id] = self._seq.get(chat_id, 0) + 1
            chat = self._chats.get(chat_id)
            if chat:
                chat.next_sequence_no = self._seq[chat_id]
                chat.updated_at = _now()
            return self._seq[chat_id]
        try:
            result = self._client.rpc(
                "allocate_chat_sequence", {"p_chat_id": str(chat_id)}
            ).execute()
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        data = result.data
        if isinstance(data, list) and data:
            return int(data[0])
        return int(data)

    def append_message(
        self,
        chat_id: UUID,
        *,
        turn_id: UUID,
        role: Literal["user", "assistant", "tool"],
        content: str,
        prompt_version: str | None = None,
        message_id: UUID | None = None,
    ) -> ChatMessage:
        if role == "system":
            raise PersistenceError("system messages must not be persisted")
        sequence_no = self.allocate_sequence(chat_id)
        message = ChatMessage(
            id=message_id or uuid4(),
            chat_id=chat_id,
            turn_id=turn_id,
            sequence_no=sequence_no,
            role=role,
            content=content,
            created_at=_now(),
            prompt_version=prompt_version,
        )
        if self._client is None:
            self._messages.setdefault(chat_id, []).append(message)
            return message
        try:
            self._client.table("chat_messages").insert(
                {
                    "id": str(message.id),
                    "chat_id": str(chat_id),
                    "turn_id": str(turn_id),
                    "sequence_no": sequence_no,
                    "role": role,
                    "content": content,
                    "created_at": message.created_at.isoformat(),
                    "prompt_version": prompt_version,
                }
            ).execute()
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        return message

    def list_messages(
        self,
        chat_id: UUID,
        *,
        before_sequence: int | None = None,
        limit: int = 50,
    ) -> list[ChatMessage]:
        """Keyset page: sequence_no DESC limit, reversed for display."""
        if self._client is None:
            rows = list(self._messages.get(chat_id, []))
            if before_sequence is not None:
                rows = [item for item in rows if item.sequence_no < before_sequence]
            rows.sort(key=lambda item: item.sequence_no, reverse=True)
            page = rows[:limit]
            page.reverse()
            return page
        query = (
            self._client.table("chat_messages")
            .select("*")
            .eq("chat_id", str(chat_id))
            .order("sequence_no", desc=True)
            .limit(limit)
        )
        if before_sequence is not None:
            query = query.lt("sequence_no", before_sequence)
        try:
            result = query.execute()
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        page = [_message_from_row(row) for row in (result.data or [])]
        page.reverse()
        return page

    def list_messages_for_context(self, chat_id: UUID) -> list[ChatMessage]:
        """Full timeline for context building (not UI pagination)."""
        if self._client is None:
            rows = list(self._messages.get(chat_id, []))
            rows.sort(key=lambda item: item.sequence_no)
            return rows
        try:
            result = (
                self._client.table("chat_messages")
                .select("*")
                .eq("chat_id", str(chat_id))
                .order("sequence_no")
                .execute()
            )
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        return [_message_from_row(row) for row in (result.data or [])]
