"""In-app documentation for the Product Intelligence Agent."""

from __future__ import annotations

import streamlit as st

from pia.ui.stores import get_stores


def render_about() -> None:
    _chats, _runs, catalog, _runner = get_stores()
    catalog.refresh()
    products = catalog.list_products()
    st.title("About")
    st.markdown(
        """
This Streamlit app is a **catalog assistant** for pet product intelligence.
It answers questions about **price, reviews, and comparisons** for products that were
ingested offline from Petbarn. The hosted chat process never crawls the web.

## What you can do

1. **Chat** — Ask in natural language. The agent can search the catalog, open one
   product, read review aggregates plus the newest stored excerpts, or compare two or
   three products. Charts and sources stay hidden until you click **Show charts** /
   **Show sources** (or ask for them in the question). Suggested follow-ups appear
   under the latest reply. Token totals for the open chat are in the left panel.
2. **Crawled catalog** — Browse every ingested SKU, filter by name/brand/SKU, and open
   stored review excerpts. This is the snapshot, not live shop data.
3. **Usage** — Inspect context size, tool names, and token counts for conversations you
   opened in this browser. Telemetry is not fed back into the model.
4. **About** — This page.

## How a question is answered

The UI stores your message, creates an `agent_run`, and polls until a worker thread
finishes. One LangChain `create_agent` loop on Groq may call up to four catalog tools.
Those tools only read **services → repositories**. They cannot fetch URLs, run SQL, or
open Playwright.

Catalog lookup is per product identity: Postgres (when configured) → compact
`data/catalog.json` → `data/sample_catalog.json`. Each row has a `source_type`. Synthetic
sample rows are never labelled as Petbarn.

## How to ask

Use product names or SKUs that exist in **Crawled catalog**. Examples:

- What is the price and rating of Advance Indoor pouches?
- What are people saying about the FURminator deshedding tool?
- Compare Royal Canin Dermacomfort Mini with Pedigree Vital Protection.

If a name is missing, the agent should say so and may offer close catalog matches.

## Ingest (offline, not the chat agent)

Locally, `uv run python scripts/ingest.py` reads seed URLs, walks Petbarn's published
product sitemap (capped), fetches allowlisted `/p/...` pages, parses JSON-LD for product
fields, and uses Playwright only to page Bazaarvoice reviews (no `?bvstate=` URLs).
Target size is about **500 products** and **10 review excerpts** each. Full review rows
stay in Postgres; `catalog.json` keeps compact excerpts.

This limited crawl is for the assessment. The runtime app does not scrape.

## What this is not

Not multi-user auth (`?chat=` is a demo link). Not live prices. Not a general web
browser. Guardrails refuse off-catalog tasks; the hard control is that the agent has no
HTTP, shell, or secrets tools.
"""
    )
    st.metric("Products loaded in this process", len(products))
    if products:
        source = products[0].source_type
        st.write(
            "Current source: "
            + ("Petbarn snapshot" if source == "petbarn_snapshot" else "Synthetic sample data")
        )
