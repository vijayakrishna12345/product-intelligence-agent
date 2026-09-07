from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.eval

from pia.settings import get_settings  # noqa: E402
from tests.eval.load_dataset import as_deepeval_goldens  # noqa: E402


@pytest.fixture(scope="module")
def groq_ready():
    if not get_settings().groq_api_key:
        pytest.skip("GROQ_API_KEY unset")


def test_single_turn_eval(groq_ready, monkeypatch):
    from deepeval.metrics import (
        AnswerRelevancyMetric,
        ArgumentCorrectnessMetric,
        GEval,
        ToolCorrectnessMetric,
    )
    from deepeval.test_case import LLMTestCase, LLMTestCaseParams, ToolCall

    from pia.agent.factory import run_query
    from pia.repositories.catalog import CatalogRepository
    from pia.services.catalog import CatalogService
    from pia.settings import get_settings, reset_settings
    from tests.eval.groq_judge import GroqJudge

    monkeypatch.setenv("DATA_MODE", "sample")
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "")
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

    judge = GroqJudge.build()
    goldens = as_deepeval_goldens()
    results = []
    metrics = [
        ToolCorrectnessMetric(
            model=judge,
            async_mode=False,
            should_exact_match=True,
            should_consider_ordering=False,
        ),
        ArgumentCorrectnessMetric(model=judge, async_mode=False),
        AnswerRelevancyMetric(model=judge, async_mode=False),
        GEval(
            name="CatalogGrounding",
            criteria=(
                "Answer must be grounded in actual tool retrieval_context, "
                "not invented catalog facts."
            ),
            evaluation_params=[
                LLMTestCaseParams.ACTUAL_OUTPUT,
                LLMTestCaseParams.RETRIEVAL_CONTEXT,
            ],
            model=judge,
            async_mode=False,
        ),
    ]
    for golden in goldens:
        result = run_query(golden.input, catalog=catalog, settings=settings)
        tools = [ToolCall(name=item["name"]) for item in result.tools_called]
        case = LLMTestCase(
            input=golden.input,
            actual_output=result.answer,
            expected_output=golden.expected_output,
            retrieval_context=result.retrieval_context,
            tools_called=tools,
            expected_tools=golden.expected_tools,
        )
        scores = {}
        for metric in metrics:
            label = metric.__class__.__name__
            if label == "GEval":
                label = getattr(metric, "name", None) or "GEval"
            try:
                metric.measure(case)
                scores[label] = getattr(metric, "score", None)
            except (ValueError, json.JSONDecodeError):
                scores[label] = None
        results.append(
            {
                "input": golden.input,
                "scores": scores,
                "tools": [item["name"] for item in result.tools_called],
            }
        )
    means: dict[str, float | None] = {}
    metric_names = sorted({key for row in results for key in row["scores"]})
    for name in metric_names:
        vals = [
            float(row["scores"][name]) for row in results if row["scores"].get(name) is not None
        ]
        means[name] = round(sum(vals) / len(vals), 3) if vals else None
    extra = []
    for golden, row in zip(goldens, results, strict=True):
        expected = {tool.name for tool in golden.expected_tools}
        if set(row["tools"]) != expected:
            extra.append({"input": row["input"], "tools": row["tools"]})
    payload = {
        "cases": len(results),
        "means": means,
        "tool_mismatches": extra,
        "results": results,
    }
    out = Path("eval/results/latest.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print({"cases": len(results), "means": means, "tool_mismatches": extra})
    reset_settings()
