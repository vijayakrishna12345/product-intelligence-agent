"""Heuristic follow-up chips. Not a second LLM."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

_CHART_ASK = re.compile(
    r"\b(charts?|graphs?|plots?|visuali[sz]e|rating distribution|show (?:me )?(?:the )?table)\b",
    re.I,
)
_SOURCE_ASK = re.compile(
    r"\b(sources?|citations?|where (?:did|does) (?:this|that|the data)|catalog snapshot)\b",
    re.I,
)


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def already_asked(suggestion: str, asked: list[str] | None) -> bool:
    needle = _norm(suggestion)
    if not needle:
        return False
    for item in asked or []:
        hay = _norm(item)
        if not hay:
            continue
        if needle == hay or needle in hay or hay in needle:
            return True
        if SequenceMatcher(None, needle, hay).ratio() >= 0.86:
            return True
    return False


def suggest_followups(
    payloads: list[dict[str, Any]],
    *,
    catalog_names: list[str] | None = None,
    asked: list[str] | None = None,
) -> list[str]:
    names: list[str] = []
    not_found = False
    compared = False
    for payload in payloads:
        if payload.get("error") == "not_found":
            not_found = True
        if payload.get("products") and payload.get("ok") is not False:
            compared = True
        product = payload.get("product") or payload.get("name")
        if isinstance(product, str) and product.strip():
            names.append(product.strip())
        for row in list(payload.get("products") or []) + list(payload.get("matches") or []):
            if isinstance(row, dict):
                label = row.get("name")
                if isinstance(label, str) and label.strip():
                    names.append(label.strip())
    seen: set[str] = set()
    unique_names: list[str] = []
    for name in names:
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        unique_names.append(name)
    suggestions: list[str] = []
    if not_found:
        suggestions.append("Search the catalog for indoor cat food")
        suggestions.append("Which products have the highest ratings?")
    for name in unique_names[:4]:
        suggestions.append(f"What are people saying about {name}?")
        suggestions.append(f"What is the price and rating of {name}?")
    if len(unique_names) >= 2:
        suggestions.append(f"Compare {unique_names[0]} vs {unique_names[1]} on price and reviews")
        if len(unique_names) >= 3:
            suggestions.append(
                f"Compare {unique_names[0]} vs {unique_names[2]} on price and reviews"
            )
    elif unique_names and catalog_names:
        others = [item for item in catalog_names if item.lower() not in seen]
        for other in others[:2]:
            suggestions.append(f"Compare {unique_names[0]} vs {other}")
    elif catalog_names:
        suggestions.append(f"Tell me about {catalog_names[0]}")
        if len(catalog_names) >= 2:
            suggestions.append(f"Compare {catalog_names[0]} vs {catalog_names[1]} on reviews")
            if len(catalog_names) >= 3:
                suggestions.append(f"Tell me about {catalog_names[2]}")
    if compared:
        suggestions.append("Which of these has stronger recent review sentiment?")
    out: list[str] = []
    seen_q: set[str] = set()
    for item in suggestions:
        key = item.lower()
        if key in seen_q or already_asked(item, asked):
            continue
        seen_q.add(key)
        out.append(item)
        if len(out) >= 3:
            break
    return out


def asked_for_charts(text: str | None) -> bool:
    return bool(text and _CHART_ASK.search(text))


def asked_for_sources(text: str | None) -> bool:
    return bool(text and _SOURCE_ASK.search(text))


def payload_has_charts(payloads: list[dict[str, Any]]) -> bool:
    for payload in payloads:
        if payload.get("error") == "not_found":
            continue
        if payload.get("products") and payload.get("ok") is not False:
            return True
        if payload.get("rating_distribution") or payload.get("reviews"):
            return True
        if payload.get("price") is not None or payload.get("rating_value") is not None:
            return True
    return False
