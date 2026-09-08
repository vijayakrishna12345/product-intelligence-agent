from __future__ import annotations

import json
from pathlib import Path

from tests.eval.load_dataset import (
    load_conversational_goldens,
    load_difficult_goldens,
    load_goldens,
)

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = json.loads((ROOT / "data" / "sample_catalog.json").read_text(encoding="utf-8"))
SKUS = {item["sku"] for item in SAMPLE["products"]}
NAMES = {item["name"] for item in SAMPLE["products"]}


def test_golden_counts_and_expected_tools():
    rows = load_goldens()
    assert len(rows) == 21
    quality = [row for row in rows if "injection" not in row.get("tags", [])]
    injection = [row for row in rows if "injection" in row.get("tags", [])]
    assert len(quality) == 20
    assert len(injection) == 1
    compares = [row for row in rows if row.get("expected_tools") == ["compare_products"]]
    assert len(compares) == 3
    for row in rows:
        assert "expected_tools" in row
        assert isinstance(row["expected_tools"], list)


def test_goldens_reference_sample_catalog_or_unknown():
    rows = load_goldens()
    for row in rows:
        tags = row.get("tags") or []
        if "unknown" in tags or "injection" in tags or "aggregate" in tags:
            continue
        blob = row["input"] + " " + " ".join(row.get("context") or [])
        assert any(name.split()[0] in blob or sku in blob for sku in SKUS for name in NAMES) or any(
            token in blob
            for token in (
                "KONG",
                "GREENIES",
                "Advance",
                "Royal Canin",
                "Hill",
                "Pedigree",
                "FURminator",
                "Catit",
                "Black Hawk",
            )
        )


def test_conversational_count():
    rows = load_conversational_goldens()
    assert len(rows) == 10
    assert sum(1 for row in rows if "adversarial" in row.get("tags", [])) == 3


def test_difficult_goldens_schema():
    rows = load_difficult_goldens()
    assert len(rows) == 12
    ids = {row["id"] for row in rows}
    assert len(ids) == 12
    for row in rows:
        assert row.get("input")
        assert row.get("tags")
        assert row.get("must_complete") or row.get("refusal")
        if row.get("refusal"):
            assert row.get("max_tool_calls") == 0
