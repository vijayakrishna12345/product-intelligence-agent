---
name: petbarn-ingest
description: Offline Petbarn catalog ingestion with sitemap-index traversal, URL policy, JSON-LD parsing, Playwright reviews, VADER, quality gate, and compact snapshot export. Use when running or changing scripts/ingest.py, crawl policy, parsers, or data/catalog.json.
---

# Petbarn ingest

## Run

```powershell
uv sync --group dev
uv run playwright install chromium
uv run python scripts/ingest.py
```

Selection is `data/seed_products.json` first, then sitemap `/p/...` fill up to `INGEST_MAX_PRODUCTS` (default 500). No `--url` bypass. Resume skips SKUs that already have `INGEST_TARGET_REVIEWS` (default 10) stored reviews. Snapshot merges into `data/catalog.json` as the run proceeds.

## Pipeline

1. Confirm sitemap origin is in `ALLOWED_RETAILERS`.
2. GET sitemap index; traverse `sitemap-1-*.xml` children (capped, cached under `data/raw/sitemap/`). Missing seed URL = warning.
3. Full URL policy per seed URL, including `DENY_PATTERNS` (`bvstate=`).
4. Fetch product HTML. Parse JSON-LD → `ProductInput`. Playwright reviews via widget next-click (never `?bvstate=`).
5. Quality gate. Upsert Postgres. Write compact `data/catalog.json` (excerpts only) and `data/manifest.json`.

## Tests

Parser tests use `tests/fixtures/product/` and `tests/fixtures/reviews/` only. Policy tests must not hit the network.
