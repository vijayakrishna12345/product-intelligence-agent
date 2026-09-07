"""Agent run and tool-call persistence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from pia.domain.errors import PersistenceError
from pia.domain.models import AgentRun, ToolCall
from pia.logging import get_logger
from pia.repositories.catalog import _as_datetime, _as_int

log = get_logger("pia.agent")


def _now() -> datetime:
    return datetime.now(UTC)


def _run_from_row(row: dict[str, Any]) -> AgentRun:
    return AgentRun(
        id=UUID(str(row["id"])),
        chat_id=UUID(str(row["chat_id"])),
        turn_id=UUID(str(row["turn_id"])),
        status=row["status"],
        user_message_id=UUID(str(row["user_message_id"])),
        assistant_message_id=(
            UUID(str(row["assistant_message_id"])) if row.get("assistant_message_id") else None
        ),
        started_at=_as_datetime(row.get("started_at")),
        completed_at=_as_datetime(row.get("completed_at")),
        error_type=row.get("error_type"),
        error_message=row.get("error_message"),
        tools_called_count=int(row.get("tools_called_count") or 0),
        agent_steps=int(row.get("agent_steps") or 0),
        input_tokens=_as_int(row.get("input_tokens")),
        output_tokens=_as_int(row.get("output_tokens")),
        cached_tokens=_as_int(row.get("cached_tokens")),
        history_tokens=_as_int(row.get("history_tokens")),
        tool_result_tokens=_as_int(row.get("tool_result_tokens")),
        system_tools_tokens=_as_int(row.get("system_tools_tokens")),
        latency_ms=_as_int(row.get("latency_ms")),
        prompt_version=row.get("prompt_version"),
        model=row.get("model"),
    )


def _tool_from_row(row: dict[str, Any]) -> ToolCall:
    return ToolCall(
        id=UUID(str(row["id"])),
        chat_id=UUID(str(row["chat_id"])),
        turn_id=UUID(str(row["turn_id"])),
        message_id=UUID(str(row["message_id"])) if row.get("message_id") else None,
        tool_name=row["tool_name"],
        arguments=row.get("arguments") or {},
        result=row.get("result"),
        status=row.get("status") or "running",
        error_type=row.get("error_type"),
        started_at=_as_datetime(row.get("started_at")),
        completed_at=_as_datetime(row.get("completed_at")),
        latency_ms=_as_int(row.get("latency_ms")),
    )


def _run_row(run: AgentRun) -> dict[str, Any]:
    return {
        "id": str(run.id),
        "chat_id": str(run.chat_id),
        "turn_id": str(run.turn_id),
        "status": run.status,
        "user_message_id": str(run.user_message_id),
        "assistant_message_id": str(run.assistant_message_id) if run.assistant_message_id else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "error_type": run.error_type,
        "error_message": run.error_message,
        "tools_called_count": run.tools_called_count,
        "agent_steps": run.agent_steps,
        "input_tokens": run.input_tokens,
        "output_tokens": run.output_tokens,
        "cached_tokens": run.cached_tokens,
        "history_tokens": run.history_tokens,
        "tool_result_tokens": run.tool_result_tokens,
        "system_tools_tokens": run.system_tools_tokens,
        "latency_ms": run.latency_ms,
        "prompt_version": run.prompt_version,
        "model": run.model,
    }


class AgentRunRepository:
    """Lifecycle for agent_runs and tool_calls."""

    def __init__(self, client: Any | None = None) -> None:
        self._client = client
        self._runs: dict[UUID, AgentRun] = {}
        self._tools: dict[UUID, list[ToolCall]] = {}

    def create_run(self, run: AgentRun) -> AgentRun:
        if self._client is None:
            self._runs[run.id] = run
            self._tools.setdefault(run.turn_id, [])
            return run
        try:
            self._client.table("agent_runs").insert(_run_row(run)).execute()
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        return run

    def update_run(self, run: AgentRun) -> AgentRun:
        if self._client is None:
            self._runs[run.id] = run
            return run
        try:
            self._client.table("agent_runs").update(_run_row(run)).eq("id", str(run.id)).execute()
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        return run

    def get(self, run_id: UUID) -> AgentRun | None:
        if self._client is None:
            return self._runs.get(run_id)
        try:
            result = (
                self._client.table("agent_runs")
                .select("*")
                .eq("id", str(run_id))
                .limit(1)
                .execute()
            )
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        rows = result.data or []
        return _run_from_row(rows[0]) if rows else None

    def get_active_run(self, chat_id: UUID) -> AgentRun | None:
        if self._client is None:
            active = [
                run
                for run in self._runs.values()
                if run.chat_id == chat_id and run.status in {"queued", "running"}
            ]
            active.sort(key=lambda item: item.started_at or _now(), reverse=True)
            return active[0] if active else None
        try:
            result = (
                self._client.table("agent_runs")
                .select("*")
                .eq("chat_id", str(chat_id))
                .in_("status", ["queued", "running"])
                .order("started_at", desc=True)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        rows = result.data or []
        return _run_from_row(rows[0]) if rows else None

    def latest_completed(self, chat_id: UUID) -> AgentRun | None:
        if self._client is None:
            done = [
                run
                for run in self._runs.values()
                if run.chat_id == chat_id and run.status == "completed"
            ]
            done.sort(key=lambda item: item.completed_at or _now(), reverse=True)
            return done[0] if done else None
        try:
            result = (
                self._client.table("agent_runs")
                .select("*")
                .eq("chat_id", str(chat_id))
                .eq("status", "completed")
                .order("completed_at", desc=True)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        rows = result.data or []
        return _run_from_row(rows[0]) if rows else None

    def running_turn_ids(self, chat_id: UUID) -> set[UUID]:
        active = self.get_active_run(chat_id)
        return {active.turn_id} if active else set()

    def fail_stale_runs(self, stale_seconds: int) -> int:
        cutoff = _now() - timedelta(seconds=stale_seconds)
        count = 0
        if self._client is None:
            for run in list(self._runs.values()):
                if run.status in {"queued", "running"} and (run.started_at or _now()) < cutoff:
                    run.status = "failed"
                    run.error_type = "stale"
                    run.error_message = "Run exceeded stale timeout"
                    run.completed_at = _now()
                    count += 1
            return count
        try:
            result = (
                self._client.table("agent_runs")
                .select("*")
                .in_("status", ["queued", "running"])
                .lt("started_at", cutoff.isoformat())
                .execute()
            )
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        for row in result.data or []:
            run = _run_from_row(row)
            run.status = "failed"
            run.error_type = "stale"
            run.error_message = "Run exceeded stale timeout"
            run.completed_at = _now()
            self.update_run(run)
            count += 1
        return count

    def insert_tool_call(self, record: ToolCall) -> ToolCall:
        if record.id is None:  # pragma: no cover
            record.id = uuid4()
        if self._client is None:
            self._tools.setdefault(record.turn_id, []).append(record)
            return record
        payload = {
            "id": str(record.id),
            "chat_id": str(record.chat_id),
            "turn_id": str(record.turn_id),
            "message_id": str(record.message_id) if record.message_id else None,
            "tool_name": record.tool_name,
            "arguments": record.arguments,
            "result": record.result,
            "status": record.status,
            "error_type": record.error_type,
            "started_at": record.started_at.isoformat()
            if record.started_at
            else _now().isoformat(),
            "completed_at": record.completed_at.isoformat() if record.completed_at else None,
            "latency_ms": record.latency_ms,
        }
        try:
            self._client.table("tool_calls").insert(payload).execute()
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        return record

    def list_tool_calls(self, turn_id: UUID) -> list[ToolCall]:
        if self._client is None:
            return list(self._tools.get(turn_id, []))
        try:
            result = (
                self._client.table("tool_calls")
                .select("*")
                .eq("turn_id", str(turn_id))
                .order("started_at")
                .execute()
            )
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        return [_tool_from_row(row) for row in (result.data or [])]

    def list_runs_for_chat(self, chat_id: UUID, *, limit: int = 50) -> list[AgentRun]:
        """Runs for one chat. Not a global list of conversations."""
        if self._client is None:
            rows = [run for run in self._runs.values() if run.chat_id == chat_id]
            rows.sort(key=lambda item: item.started_at or _now(), reverse=True)
            return rows[:limit]
        try:
            result = (
                self._client.table("agent_runs")
                .select("*")
                .eq("chat_id", str(chat_id))
                .order("started_at", desc=True)
                .limit(limit)
                .execute()
            )
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        return [_run_from_row(row) for row in (result.data or [])]
