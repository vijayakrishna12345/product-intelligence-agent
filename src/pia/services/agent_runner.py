"""In-process agent worker. Must not call st.* from the worker thread."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pia.agent.factory import run_query
from pia.domain.models import AgentRun, ToolCall
from pia.logging import get_logger
from pia.repositories.agent_runs import AgentRunRepository
from pia.repositories.chats import ChatRepository
from pia.settings import Settings, get_settings

log = get_logger("pia.agent")


def _now() -> datetime:
    return datetime.now(UTC)


class AgentRunner:
    """Queue a run, persist the timeline, invoke LangChain off the script thread."""

    def __init__(
        self,
        chats: ChatRepository,
        runs: AgentRunRepository,
        agent,
        catalog,
        executor: ThreadPoolExecutor,
        settings: Settings | None = None,
    ) -> None:
        self._chats = chats
        self._runs = runs
        self._agent = agent
        self._catalog = catalog
        self._executor = executor
        self._settings = settings or get_settings()

    def submit(self, chat_id: UUID, user_text: str) -> UUID:
        turn_id = uuid4()
        chat = self._chats.get(chat_id)
        if chat is None:
            self._chats.create(title=user_text[:80], chat_id=chat_id)
        elif (chat.title or "New chat") == "New chat":
            self._chats.set_title(chat_id, user_text[:80])
        user_message = self._chats.append_message(
            chat_id, turn_id=turn_id, role="user", content=user_text
        )
        run = AgentRun(
            id=uuid4(),
            chat_id=chat_id,
            turn_id=turn_id,
            status="queued",
            user_message_id=user_message.id,
            started_at=_now(),
            prompt_version=self._settings.prompt_version,
            model=self._settings.groq_model,
        )
        self._runs.create_run(run)
        history = self._chats.list_messages_for_context(chat_id)
        running = {turn_id}
        run.status = "running"
        self._runs.update_run(run)
        self._executor.submit(
            self._execute,
            run.id,
            chat_id,
            turn_id,
            user_text,
            history,
            running,
        )
        return run.id

    def _execute(
        self,
        run_id: UUID,
        chat_id: UUID,
        turn_id: UUID,
        user_text: str,
        history,
        running: set[UUID],
    ) -> None:
        run = self._runs.get(run_id)
        if run is None:
            return
        try:
            result = run_query(
                user_text,
                persisted_messages=history,
                thread_id=str(chat_id),
                running_turn_ids=running,
                agent=self._agent,
                catalog=self._catalog,
                settings=self._settings,
            )
            for tool in result.tools_called:
                compact = self._chats.append_message(
                    chat_id,
                    turn_id=turn_id,
                    role="tool",
                    content=f"{tool.get('name')} completed",
                )
                payload = tool.get("result")
                parsed: dict[str, Any] | None
                if isinstance(payload, dict):
                    parsed = payload
                elif isinstance(payload, str):
                    try:
                        parsed = json.loads(payload)
                    except json.JSONDecodeError:
                        parsed = {"text": payload[: self._settings.max_tool_result_chars]}
                else:
                    parsed = None
                self._runs.insert_tool_call(
                    ToolCall(
                        id=uuid4(),
                        chat_id=chat_id,
                        turn_id=turn_id,
                        message_id=compact.id,
                        tool_name=str(tool.get("name") or "tool"),
                        arguments=tool.get("args") or {},
                        result=parsed if isinstance(parsed, dict) else None,
                        status="success",
                        started_at=_now(),
                        completed_at=_now(),
                    )
                )
            assistant = self._chats.append_message(
                chat_id,
                turn_id=turn_id,
                role="assistant",
                content=result.answer,
                prompt_version=self._settings.prompt_version,
            )
            run.status = "completed"
            run.assistant_message_id = assistant.id
            run.completed_at = _now()
            run.tools_called_count = result.usage.tools_called
            run.agent_steps = result.usage.agent_steps
            run.input_tokens = result.usage.input_tokens
            run.output_tokens = result.usage.output_tokens
            run.cached_tokens = result.usage.cached_tokens
            run.history_tokens = result.usage.history_tokens
            run.tool_result_tokens = result.usage.tool_result_tokens
            run.system_tools_tokens = result.usage.system_tools_tokens
            run.latency_ms = result.usage.latency_ms
            run.model = result.usage.model
            run.prompt_version = result.usage.prompt_version
            self._runs.update_run(run)
        except Exception as exc:
            log.exception("agent run failed")
            run.status = "failed"
            run.error_type = type(exc).__name__
            run.error_message = str(exc)[:300]
            run.completed_at = _now()
            try:
                self._runs.update_run(run)
                self._chats.append_message(
                    chat_id,
                    turn_id=turn_id,
                    role="assistant",
                    content="I could not complete that request. Please try again.",
                    prompt_version=self._settings.prompt_version,
                )
            except Exception:
                log.exception("failed to persist agent error")
