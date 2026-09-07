"""Map goldens.json into DeepEval Golden objects."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

EVAL_DIR = Path(__file__).parent


def load_goldens() -> list[dict[str, Any]]:
    return json.loads((EVAL_DIR / "goldens.json").read_text(encoding="utf-8"))


def load_conversational_goldens() -> list[dict[str, Any]]:
    return json.loads((EVAL_DIR / "conversational_goldens.json").read_text(encoding="utf-8"))


def as_deepeval_goldens():
    from deepeval.dataset import Golden
    from deepeval.test_case import ToolCall

    goldens = []
    for row in load_goldens():
        tools = [ToolCall(name=name) for name in row.get("expected_tools") or []]
        goldens.append(
            Golden(
                input=row["input"],
                expected_output=row.get("expected_output"),
                context=row.get("context") or [],
                expected_tools=tools,
            )
        )
    return goldens
