"""Browse ingested products and review excerpts."""

from __future__ import annotations

import streamlit as st

from pia.settings import get_settings
from pia.ui.charts import render_reviews
from pia.ui.stores import get_stores


def render_catalog() -> None:
    settings = get_settings()
    _chats, _runs, catalog, _runner = get_stores()
    catalog.refresh()
    products = catalog.list_products()
    st.title("Crawled catalog")
    st.caption(
        "Products and review excerpts from the latest ingest snapshot. "
        "This page reads the catalog services, not the live Petbarn site. "
        "Review count is the retailer's listed total; the rows below are crawled excerpts."
    )
    source = products[0].source_type if products else "synthetic_sample"
    cols = st.columns(3)
    cols[0].metric("Products", len(products))
    cols[1].metric(
        "Source",
        "Petbarn snapshot" if source == "petbarn_snapshot" else "Synthetic sample",
    )
    cols[2].metric("Review totals", sum(int(item.review_count or 0) for item in products))
    if not products:
        st.warning("Catalog is empty. Run `uv run python scripts/ingest.py` locally.")
        return
    query = st.text_input("Filter by name, brand, or SKU")
    filtered = products
    if query.strip():
        needle = query.strip().lower()
        filtered = [
            item
            for item in products
            if needle in item.name.lower()
            or needle in (item.brand or "").lower()
            or needle in item.sku.lower()
        ]
    st.dataframe(
        [
            {
                "SKU": item.sku,
                "Name": item.name,
                "Brand": item.brand,
                "Price": item.price,
                "Rating": item.rating_value,
                "Review count": item.review_count,
                "Source": item.source_type,
            }
            for item in filtered
        ],
        hide_index=True,
        width="stretch",
    )
    options = {f"{item.name} ({item.sku})": item.sku for item in filtered}
    if not options:
        return
    selected = st.selectbox("Inspect reviews", list(options))
    sku = options[selected]
    try:
        payload = catalog.reviews_payload(sku, limit=settings.max_reviews)
    except Exception as exc:
        st.error(str(exc))
        return
    st.subheader(payload.get("product") or sku)
    st.caption(payload.get("url") or "")
    render_reviews(payload)
    for review in payload.get("reviews") or []:
        st.markdown(
            f"**{review.get('rating')}★** · {review.get('date') or 'unknown date'}\n\n"
            f"{review.get('text') or ''}"
        )
        st.divider()
