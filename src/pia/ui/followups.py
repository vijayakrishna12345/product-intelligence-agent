"""Heuristic follow-up chips. Not a second LLM."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from pia.analysis.taxonomy import kind_from_text, species_from_text

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


def infer_category(name: str, *, category: str | None = None) -> str:
    """Species bucket; prefers stored category from catalog metadata."""
    return species_from_text(name, category=category)


def infer_kind(name: str, *, category: str | None = None) -> str:
    """Product kind; prefers stored category from catalog metadata."""
    return kind_from_text(name, category=category)


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


def _candidate_name(item: Any) -> str | None:
    if isinstance(item, dict):
        name = item.get("name") or item.get("sku")
        return str(name).strip() if name else None
    text = str(item).strip()
    if not text:
        return None
    if " (" in text and text.endswith(")"):
        return text.rsplit(" (", 1)[0].strip()
    return text


def _catalog_rows(
    catalog_products: list[Any] | None,
    catalog_names: list[str] | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in catalog_products or []:
        if isinstance(item, str) and item.strip():
            rows.append({"name": item.strip()})
        elif isinstance(item, dict) and item.get("name"):
            rows.append(item)
    for name in catalog_names or []:
        if name and str(name).strip():
            rows.append({"name": str(name).strip()})
    return rows


def _row_context(row: dict[str, Any]) -> tuple[str, str | None]:
    name = str(row.get("name") or "").strip()
    category = row.get("category")
    if isinstance(category, str) and category.strip():
        return name, category.strip()
    return name, None


def _same_category_names(
    anchor_row: dict[str, Any],
    catalog_rows: list[dict[str, Any]],
    seen: set[str],
) -> list[str]:
    anchor_name, anchor_category = _row_context(anchor_row)
    species = infer_category(anchor_name, category=anchor_category)
    kind = infer_kind(anchor_name, category=anchor_category)
    same_both: list[str] = []
    same_species: list[str] = []
    same_kind: list[str] = []
    for row in catalog_rows:
        name, category = _row_context(row)
        if not name or name.lower() in seen or name.lower() == anchor_name.lower():
            continue
        row_species = infer_category(name, category=category)
        row_kind = infer_kind(name, category=category)
        if species != "other" and row_species == species and kind != "other" and row_kind == kind:
            same_both.append(name)
        elif species != "other" and row_species == species:
            same_species.append(name)
        elif kind != "other" and row_kind == kind:
            same_kind.append(name)
    return same_both or same_species or same_kind


def _anchor_row(payloads: list[dict[str, Any]], unique_names: list[str]) -> dict[str, Any]:
    if not unique_names:
        return {}
    target = unique_names[0].lower()
    for payload in payloads:
        product = payload.get("product")
        if isinstance(product, str) and product.lower() == target:
            return {"name": product, "category": payload.get("category")}
        for row in list(payload.get("products") or []) + list(payload.get("matches") or []):
            if isinstance(row, dict) and str(row.get("name") or "").lower() == target:
                return row
    return {"name": unique_names[0]}


def suggest_followups(
    payloads: list[dict[str, Any]],
    *,
    catalog_names: list[str] | None = None,
    catalog_products: list[Any] | None = None,
    asked: list[str] | None = None,
) -> list[str]:
    names: list[str] = []
    not_found = False
    compared = False
    ambiguous_names: list[str] = []
    for payload in payloads:
        if payload.get("error") == "not_found":
            not_found = True
        if payload.get("error") == "ambiguous":
            for candidate in payload.get("candidates") or []:
                label = _candidate_name(candidate)
                if label:
                    ambiguous_names.append(label)
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
    catalog_rows = _catalog_rows(catalog_products, catalog_names)
    anchor = _anchor_row(payloads, unique_names)
    suggestions: list[str] = []
    for name in ambiguous_names[:3]:
        suggestions.append(f"Tell me about {name}")
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
    elif unique_names and catalog_rows and not ambiguous_names:
        others = _same_category_names(anchor or {"name": unique_names[0]}, catalog_rows, seen)
        for other in others[:2]:
            suggestions.append(f"Compare {unique_names[0]} vs {other}")
    elif catalog_rows and not unique_names and not ambiguous_names:
        first = catalog_rows[0]
        first_name = first.get("name")
        if first_name:
            suggestions.append(f"Tell me about {first_name}")
        if len(catalog_rows) >= 2:
            peers = _same_category_names(first, catalog_rows, {str(first_name or "").lower()})
            if peers:
                suggestions.append(f"Compare {first_name} vs {peers[0]} on reviews")
            else:
                second = catalog_rows[1].get("name")
                if second:
                    suggestions.append(f"Compare {first_name} vs {second} on reviews")
            if len(catalog_rows) >= 3:
                third = catalog_rows[2].get("name")
                if third:
                    suggestions.append(f"Tell me about {third}")
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
