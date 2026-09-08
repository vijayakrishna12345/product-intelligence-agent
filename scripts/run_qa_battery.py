"""Run FAQ, edge-case, and difficult-question battery against the live agent."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "eval" / "results"
HISTORY_PATH = RESULTS_DIR / "qa_battery_history.jsonl"
LATEST_PATH = RESULTS_DIR / "qa_battery_latest.json"
REPORT_PATH = RESULTS_DIR / "QA_BATTERY_REPORT.md"

sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))


def _norm(text: str) -> str:
    lowered = text.lower()
    for ch in ("\u202f", "\u2011", "\u2019", "\u2018", "\u00a0"):
        lowered = lowered.replace(ch, " ")
    return " ".join(lowered.split())


def _catalog():
    from pia.repositories.catalog import CatalogRepository
    from pia.services.catalog import CatalogService
    from pia.settings import get_settings

    settings = get_settings()
    return CatalogService(
        CatalogRepository(
            client=None,
            catalog_path=ROOT / "data" / "catalog.json",
            sample_path=ROOT / "data" / "sample_catalog.json",
            settings=settings,
        ),
        settings,
    )


def _run_with_retry(fn, *, attempts: int = 8):
    from pia.domain.errors import LLMError

    last: Exception | None = None
    for attempt in range(attempts):
        try:
            return fn()
        except LLMError as exc:
            last = exc
            message = str(exc).lower()
            if "429" in message or "rate_limit" in message:
                time.sleep(30 * (attempt + 1))
                continue
            raise
    raise last or RuntimeError("agent call failed")


def _assert_difficult(row: dict, result) -> list[str]:
    from pia.agent.guardrails import REFUSAL

    failures: list[str] = []
    answer = _norm(result.answer or "")
    tools = [item["name"] for item in result.tools_called]

    if row.get("refusal"):
        if result.answer != REFUSAL:
            failures.append(f"expected refusal, got: {(result.answer or '')[:120]}")
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


def _assert_faq(row: dict, result) -> list[str]:
    failures: list[str] = []
    tools = [item["name"] for item in result.tools_called]
    expected = row.get("expected_tools") or []
    if expected and set(tools) != set(expected):
        failures.append(f"expected tools {expected}, got {tools}")
    if not (result.answer or "").strip():
        failures.append("empty answer")
    return failures


def _preview(text: str, limit: int = 200) -> str:
    cleaned = " ".join((text or "").split())
    return cleaned[:limit] + ("…" if len(cleaned) > limit else "")


def run_battery(*, sleep_s: float) -> dict:
    from tests.eval.load_dataset import load_difficult_goldens, load_goldens

    from pia.agent.factory import run_query
    from pia.domain.errors import LLMError
    from pia.settings import get_settings, reset_settings

    import os

    os.environ.setdefault("DATA_MODE", "sample")
    os.environ.setdefault("SUPABASE_URL", "")
    os.environ.setdefault("SUPABASE_SECRET_KEY", "")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "")
    reset_settings()
    settings = get_settings()
    if not settings.groq_api_key:
        raise SystemExit("GROQ_API_KEY is not set")

    catalog = _catalog()
    started = datetime.now(UTC).isoformat()
    faq_rows = load_goldens()
    difficult_rows = load_difficult_goldens()

    faq_results: list[dict] = []
    difficult_results: list[dict] = []
    all_failures: list[str] = []

    for index, row in enumerate(faq_rows):
        if index and sleep_s:
            time.sleep(sleep_s)
        try:
            result = _run_with_retry(
                lambda q=row["input"]: run_query(q, catalog=catalog, settings=settings)
            )
            failures = _assert_faq(row, result)
        except LLMError as exc:
            result = None
            failures = [f"agent error: {exc}"]

        if failures:
            label = row.get("input", "")[:60]
            all_failures.append(f"faq: {label}: " + "; ".join(failures))
        faq_results.append(
            {
                "input": row["input"],
                "tags": row.get("tags") or [],
                "expected_tools": row.get("expected_tools") or [],
                "tools": [item["name"] for item in result.tools_called] if result else [],
                "latency_ms": result.usage.latency_ms if result else None,
                "answer_preview": _preview(result.answer if result else ""),
                "failures": failures,
                "pass": not failures,
            }
        )

    for row in difficult_rows:
        if sleep_s:
            time.sleep(sleep_s)
        case_id = row["id"]
        try:
            result = _run_with_retry(
                lambda q=row["input"]: run_query(q, catalog=catalog, settings=settings)
            )
            failures = _assert_difficult(row, result)
        except LLMError as exc:
            failures = [f"agent error: {exc}"] if row.get("must_complete") else []
            result = None

        if failures:
            all_failures.append(f"{case_id}: " + "; ".join(failures))
        difficult_results.append(
            {
                "id": case_id,
                "input": row["input"],
                "tags": row.get("tags") or [],
                "tools": [item["name"] for item in result.tools_called] if result else [],
                "latency_ms": result.usage.latency_ms if result else None,
                "answer_preview": _preview(result.answer if result else ""),
                "failures": failures,
                "pass": not failures,
            }
        )

    faq_pass = sum(1 for row in faq_results if row["pass"])
    diff_pass = sum(1 for row in difficult_results if row["pass"])
    payload = {
        "run_id": started,
        "started_at": started,
        "finished_at": datetime.now(UTC).isoformat(),
        "summary": {
            "faq_total": len(faq_results),
            "faq_pass": faq_pass,
            "faq_fail": len(faq_results) - faq_pass,
            "difficult_total": len(difficult_results),
            "difficult_pass": diff_pass,
            "difficult_fail": len(difficult_results) - diff_pass,
            "overall_pass": not all_failures,
        },
        "failures": all_failures,
        "faq": faq_results,
        "difficult": difficult_results,
    }
    reset_settings()
    return payload


def _write_report(payload: dict, history_count: int) -> None:
    summary = payload["summary"]
    lines = [
        "# QA Battery Report",
        "",
        f"Last run: `{payload['run_id']}`",
        f"History entries: {history_count}",
        "",
        "## Summary",
        "",
        "| Suite | Pass | Fail | Total |",
        "|-------|------|------|-------|",
        (
            f"| FAQ (goldens.json) | {summary['faq_pass']} | {summary['faq_fail']} "
            f"| {summary['faq_total']} |"
        ),
        (
            f"| Edge / tough (difficult_goldens.json) | {summary['difficult_pass']} "
            f"| {summary['difficult_fail']} | {summary['difficult_total']} |"
        ),
        "",
        f"**Overall:** {'PASS' if summary['overall_pass'] else 'FAIL'}",
        "",
    ]
    if payload["failures"]:
        lines.extend(["## Failures", ""])
        for item in payload["failures"]:
            lines.append(f"- {item}")
        lines.append("")

    lines.extend(["## FAQ results", ""])
    for row in payload["faq"]:
        status = "PASS" if row["pass"] else "FAIL"
        tags = ", ".join(row["tags"]) if row["tags"] else "—"
        lines.append(f"### [{status}] {row['input'][:80]}")
        lines.append(f"- Tags: {tags}")
        lines.append(f"- Tools: `{row['tools']}` (expected `{row['expected_tools']}`)")
        lines.append(f"- Latency: {row['latency_ms']} ms")
        lines.append(f"- Answer: {row['answer_preview']}")
        if row["failures"]:
            lines.append(f"- Issues: {'; '.join(row['failures'])}")
        lines.append("")

    lines.extend(["## Edge / tough results", ""])
    for row in payload["difficult"]:
        status = "PASS" if row["pass"] else "FAIL"
        tags = ", ".join(row["tags"]) if row["tags"] else "—"
        lines.append(f"### [{status}] {row['id']}: {row['input'][:80]}")
        lines.append(f"- Tags: {tags}")
        lines.append(f"- Tools: `{row['tools']}`")
        lines.append(f"- Latency: {row['latency_ms']} ms")
        lines.append(f"- Answer: {row['answer_preview']}")
        if row["failures"]:
            lines.append(f"- Issues: {'; '.join(row['failures'])}")
        lines.append("")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run PIA FAQ + edge-case QA battery")
    parser.add_argument("--sleep", type=float, default=2.0, help="Seconds between calls")
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    payload = run_battery(sleep_s=args.sleep)

    LATEST_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with HISTORY_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")

    history_count = sum(1 for _ in HISTORY_PATH.open(encoding="utf-8"))
    _write_report(payload, history_count)

    print(json.dumps(payload["summary"], indent=2))
    return 0 if payload["summary"]["overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
