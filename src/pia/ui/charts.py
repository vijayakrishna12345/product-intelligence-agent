"""Map tool payloads to Streamlit charts. Native charts only."""

from __future__ import annotations

from typing import Any

import streamlit as st


def _num(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def render_details(payload: dict[str, Any]) -> None:
    price = _num(payload.get("price"))
    rating = _num(payload.get("rating_value"))
    cols = st.columns(2)
    if price is not None:
        cols[0].metric("Price", f"{payload.get('currency') or 'AUD'} {price:.2f}")
    if rating is not None:
        cols[1].metric("Rating", f"{rating:.1f}")


def render_reviews(payload: dict[str, Any]) -> None:
    rating = _num(payload.get("rating_value"))
    count = payload.get("review_count")
    cols = st.columns(2)
    if rating is not None:
        cols[0].metric("Average rating", f"{rating:.1f}")
    if count is not None:
        cols[1].metric("Reviews", int(count))
    dist = payload.get("rating_distribution") or {}
    if dist:
        st.caption("Rating distribution")
        st.bar_chart(
            {
                str(star): int(dist.get(str(star), 0) or dist.get(star, 0) or 0)
                for star in range(1, 6)
            }
        )
    sentiment = payload.get("sentiment") or {}
    if sentiment:
        st.caption("Sentiment share")
        st.bar_chart(
            {
                "positive": float(sentiment.get("positive") or 0),
                "neutral": float(sentiment.get("neutral") or 0),
                "negative": float(sentiment.get("negative") or 0),
            }
        )


def render_compare(payload: dict[str, Any]) -> None:
    rows = payload.get("products") or []
    if not rows or not payload.get("ok", True):
        return
    st.dataframe(
        [
            {
                "Product": row.get("name"),
                "SKU": row.get("sku"),
                "Brand": row.get("brand"),
                "Price": row.get("price"),
                "Rating": row.get("rating_value"),
                "Reviews": row.get("review_count"),
                "Source": row.get("source_type"),
            }
            for row in rows
        ],
        hide_index=True,
    )
    ratings = {str(row.get("name"))[:32]: _num(row.get("rating_value")) or 0 for row in rows}
    st.caption("Rating")
    st.bar_chart(ratings)


def render_sidebar_ratings(products: list) -> None:
    data = {
        str(item.name)[:28]: float(item.rating_value)
        for item in products
        if getattr(item, "rating_value", None) is not None
    }
    if data:
        st.bar_chart(data)


def _unique_labels(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        key = value.lower()
        if not value or key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def sources_caption(payloads: list[dict[str, Any]]) -> str:
    if not payloads:
        return ""
    source_types: set[str] = set()
    names: list[str] = []
    skus: list[str] = []
    scraped: str | None = None
    review_count = None
    examples = None

    def _absorb(row: dict[str, Any]) -> None:
        nonlocal scraped, review_count, examples
        if row.get("source_type"):
            source_types.add(str(row["source_type"]))
        sku = row.get("sku")
        if sku:
            skus.append(str(sku))
        name = row.get("product") or row.get("name")
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
        if row.get("scraped_at") and not scraped:
            scraped = str(row["scraped_at"])
        if row.get("review_count") is not None and review_count is None:
            review_count = row.get("review_count")
            examples = row.get("examples_count") or len(row.get("reviews") or [])

    for item in payloads:
        _absorb(item)
        for row in list(item.get("products") or []) + list(item.get("matches") or []):
            if isinstance(row, dict):
                _absorb(row)
    if "petbarn_snapshot" not in source_types:
        return "Source: Synthetic sample data\nNot live Petbarn data"
    lines = ["Source: Petbarn snapshot"]
    unique_names = _unique_labels(names)
    unique_skus = _unique_labels(skus)
    if unique_names:
        lines.append("Products: " + ", ".join(unique_names[:4]))
    if unique_skus:
        lines.append("SKU: " + ", ".join(unique_skus[:4]))
    lines.append(f"Catalog snapshot: {scraped or 'unknown'}")
    if review_count is not None:
        lines.append(f"Review data: {review_count} reviews · newest {examples} examples")
    lines.append("Price shown from the latest available catalog snapshot.")
    return "\n".join(lines)
