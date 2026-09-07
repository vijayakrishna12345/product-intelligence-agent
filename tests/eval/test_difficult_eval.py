from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.release

from pia.agent.guardrails import REFUSAL  # noqa: E402
from pia.settings import get_settings  # noqa: E402
from tests.eval.load_dataset import load_difficult_goldens  # noqa: E402


def _norm(text: str) -> str:
    lowered = text.lower()
    for ch in ("\u202f", "\u2011", "\u2019", "\u2018", "\u00a0"):
        lowered = lowered.replace(ch, " ")
    return " ".join(lowered.split())


@pytest.fixture(scope="module")
def groq_ready():
    if not get_settings().groq_api_key:
        pytest.skip("GROQ_API_KEY unset")


def _assert_case(row: dict, result) -> list[str]:
    failures: list[str] = []
    answer = _norm(result.answer or "")
    tools = [item["name"] for item in result.tools_called]

    if row.get("refusal"):
        if result.answer != REFUSAL:
            failures.append(f"expected refusal, got: {result.answer[:120]}")
    if row.get("max_tool_calls") is not None and len(tools) > row["max_tool_calls"]:
        failures.append(f"tool calls {len(tools)} > max {row['max_tool_calls']}: {tools}")
    if expected := row.get("expected_tools_any"):
        if not any(name in tools for name in expected):
            failures.append(f"expected one of {expected}, got {tools}")
    if tokens := row.get("answer_must_contain_any"):
        if not any(_norm(token) in answer for token in tokens):
            failures.append(f"missing any of {tokens}")
    for token in row.get("answer_must_not_contain") or []:
        if _norm(token) in answer:
            failures.append(f"forbidden text present: {token}")
    return failures


def _run_with_retry(fn, *, attempts: int = 6):
    from pia.domain.errors import LLMError

    last: Exception | None = None
    for attempt in range(attempts):
        try:
            return fn()
        except LLMError as exc:
            last = exc
            message = str(exc).lower()
            if "429" in message or "rate_limit" in message:
                time.sleep(2 * (attempt + 1))
                continue
            raise
    raise last or RuntimeError("agent call failed")


def test_difficult_release_gate(groq_ready, monkeypatch):
    from pia.agent.factory import run_query
    from pia.domain.errors import LLMError
    from pia.repositories.catalog import CatalogRepository
    from pia.services.catalog import CatalogService
    from pia.settings import reset_settings

    monkeypatch.setenv("DATA_MODE", "sample")
    reset_settings()
    settings = get_settings()
    catalog = CatalogService(
        CatalogRepository(
            client=None,
            catalog_path=Path("data/catalog.json"),
            sample_path=Path("data/sample_catalog.json"),
            settings=settings,
        ),
        settings,
    )

    rows = load_difficult_goldens()
    results = []
    hard_failures: list[str] = []

    for index, row in enumerate(rows):
        case_id = row["id"]
        if index:
            time.sleep(2)
        try:
            result = _run_with_retry(
                lambda: run_query(row["input"], catalog=catalog, settings=settings)
            )
            case_failures = _assert_case(row, result)
        except LLMError as exc:
            if row.get("must_complete"):
                case_failures = [f"agent error: {exc}"]
            else:
                case_failures = []
            result = None

        if case_failures:
            hard_failures.append(f"{case_id}: " + "; ".join(case_failures))
        results.append(
            {
                "id": case_id,
                "tools": [item["name"] for item in result.tools_called] if result else [],
                "latency_ms": result.usage.latency_ms if result else None,
                "answer": result.answer if result else "",
                "failures": case_failures,
            }
        )

    out = Path("eval/results/difficult_latest.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"cases": len(results), "failures": hard_failures, "results": results}
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    reset_settings()
    assert not hard_failures, "\n".join(hard_failures)
