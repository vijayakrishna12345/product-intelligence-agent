"""JSON-LD product parser. Receives HTML bytes only — no HTTP."""

from __future__ import annotations

import json
import re
from typing import Any

from pia.analysis.taxonomy import breadcrumb_category, normalize_category
from pia.domain.errors import IngestionError
from pia.domain.models import ProductInput

_SCRIPT = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)


def _objects(node: Any) -> list[dict[str, Any]]:
    if node is None:
        return []
    if isinstance(node, list):
        items: list[dict[str, Any]] = []
        for child in node:
            items.extend(_objects(child))
        return items
    if not isinstance(node, dict):
        return []
    items = [node]
    if "@graph" in node:
        items.extend(_objects(node["@graph"]))
    return items


def _type_set(node: dict[str, Any]) -> set[str]:
    raw = node.get("@type") or node.get("type") or ""
    if isinstance(raw, list):
        return {str(item).lower() for item in raw}
    return {str(raw).lower()}


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return _text(value.get("name") or value.get("@value") or value.get("value"))
    if isinstance(value, list):
        for item in value:
            text = _text(item)
            if text:
                return text
        return None
    text = str(value).strip()
    return text or None


def _float(value: Any) -> float | None:
    text = _text(value)
    if text is None:
        return None
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def _offer(node: dict[str, Any]) -> dict[str, Any]:
    offers = node.get("offers")
    if isinstance(offers, list) and offers:
        first = offers[0]
        return first if isinstance(first, dict) else {}
    return offers if isinstance(offers, dict) else {}


def _collect_breadcrumb(text: str) -> str | None:
    for match in _SCRIPT.finditer(text):
        raw = match.group(1).strip()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for node in _objects(payload):
            if "breadcrumblist" not in _type_set(node):
                continue
            category = breadcrumb_category(node)
            if category:
                return category
    return None


def parse_product_html(html: bytes | str, page_url: str) -> ProductInput:
    """JSON-LD is cheaper and more stable than CSS selectors for Magento product pages."""
    text = html.decode("utf-8", errors="replace") if isinstance(html, bytes) else html
    breadcrumb = _collect_breadcrumb(text)
    for match in _SCRIPT.finditer(text):
        raw = match.group(1).strip()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for node in _objects(payload):
            types = _type_set(node)
            if "product" not in types:
                continue
            sku = _text(node.get("sku") or node.get("productID") or node.get("mpn"))
            name = _text(node.get("name"))
            url = _text(node.get("url")) or page_url
            if not sku or not name:
                continue
            offer = _offer(node)
            aggregate = (
                node.get("aggregateRating") if isinstance(node.get("aggregateRating"), dict) else {}
            )
            brand = node.get("brand")
            description = _text(node.get("description"))
            raw_category = _text(node.get("category")) or breadcrumb
            category = normalize_category(
                raw_category,
                name=name,
                url=url,
                description=description,
            )
            return ProductInput(
                sku=sku,
                name=name,
                url=url,
                brand=_text(brand),
                category=category,
                description=description,
                price=_float(offer.get("price") or node.get("price")),
                currency=_text(offer.get("priceCurrency")) or "AUD",
                availability=_text(offer.get("availability")),
                rating_value=_float(aggregate.get("ratingValue")),
                review_count=int(aggregate["reviewCount"])
                if aggregate.get("reviewCount")
                else None,
                payload={"jsonld": True},
            )
    raise IngestionError("no Product JSON-LD with sku and name")
