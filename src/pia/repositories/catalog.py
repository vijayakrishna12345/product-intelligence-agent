"""Catalog lookup: Postgres per identity, then compact JSON, then sample."""

from __future__ import annotations

import json
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from pia.domain.errors import PersistenceError
from pia.domain.models import Product, Review, SourceType
from pia.logging import get_logger
from pia.settings import Settings, get_settings

log = get_logger("pia.catalog")

ROOT = Path(__file__).resolve().parents[3]


def _as_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _as_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def review_from_dict(row: dict[str, Any], sku: str | None = None) -> Review:
    return Review(
        sku=str(row.get("sku") or sku or ""),
        external_review_id=str(row.get("external_review_id") or row.get("id") or ""),
        rating=int(row.get("rating") or 0),
        title=row.get("title"),
        body=row.get("body") or row.get("text"),
        author=row.get("author"),
        reviewed_at=_as_date(row.get("reviewed_at") or row.get("date")),
        created_at=_as_datetime(row.get("created_at")),
        sentiment_label=row.get("sentiment_label"),
        sentiment_score=_as_float(row.get("sentiment_score")),
        source=row.get("source"),
        payload=row.get("payload") or {},
    )


def product_from_dict(row: dict[str, Any], default_source: SourceType) -> Product:
    sku = str(row.get("sku") or "")
    source = row.get("source_type") or default_source
    reviews = [review_from_dict(item, sku) for item in (row.get("reviews") or [])]
    crawl_run_id = row.get("crawl_run_id")
    return Product(
        sku=sku,
        name=str(row.get("name") or ""),
        url=str(row.get("url") or ""),
        brand=row.get("brand"),
        category=row.get("category"),
        description=row.get("description"),
        price=_as_float(row.get("price")),
        currency=row.get("currency") or "AUD",
        availability=row.get("availability"),
        rating_value=_as_float(row.get("rating_value")),
        review_count=_as_int(row.get("review_count")) or len(reviews) or None,
        payload=row.get("payload") or {},
        crawl_run_id=UUID(str(crawl_run_id)) if crawl_run_id else None,
        scraped_at=_as_datetime(row.get("scraped_at")),
        source_type=source,
        rating_distribution=row.get("rating_distribution") or {},
        sentiment=row.get("sentiment") or {},
        reviews=reviews,
    )


def load_json_catalog(path: Path, default_source: SourceType) -> dict[str, Product]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows = raw.get("products", raw if isinstance(raw, list) else [])
    products = [product_from_dict(row, default_source) for row in rows]
    return {item.sku: item for item in products if item.sku}


class CatalogRepository:
    """Per-query fallback: Postgres -> compact catalog.json -> sample.json."""

    def __init__(
        self,
        client: Any | None = None,
        *,
        catalog_path: Path | None = None,
        sample_path: Path | None = None,
        settings: Settings | None = None,
        postgres_products: dict[str, Product] | None = None,
        postgres_reviews: dict[str, list[Review]] | None = None,
    ) -> None:
        self._client = client
        self._settings = settings or get_settings()
        self._catalog_path = catalog_path or ROOT / "data" / "catalog.json"
        self._sample_path = sample_path or ROOT / "data" / "sample_catalog.json"
        self._pg_products = postgres_products
        self._pg_reviews = postgres_reviews if postgres_reviews is not None else {}
        self._json_cache: dict[str, Product] | None = None
        self._json_mtime: float | None = None
        self._sample_cache: dict[str, Product] | None = None
        self._pg_list_cache: list[Product] | None = None
        self._pg_list_at: float = 0.0

    def _snapshot_mtime(self) -> float | None:
        try:
            return self._catalog_path.stat().st_mtime
        except OSError:
            return None

    def _json(self) -> dict[str, Product]:
        mtime = self._snapshot_mtime()
        if self._json_cache is not None and self._json_mtime == mtime:
            return self._json_cache
        self._json_mtime = mtime
        self._json_cache = load_json_catalog(self._catalog_path, "petbarn_snapshot")
        return self._json_cache

    def _sample(self) -> dict[str, Product]:
        if self._sample_cache is None:
            self._sample_cache = load_json_catalog(self._sample_path, "synthetic_sample")
        return self._sample_cache

    def reload(self) -> None:
        self._json_cache = None
        self._json_mtime = None
        self._sample_cache = None

    def _pg_get(self, sku: str) -> Product | None:
        if self._pg_products is not None:
            product = self._pg_products.get(sku)
            if product:
                product.source_type = "petbarn_snapshot"
            return product
        if self._client is None:
            return None
        try:
            result = self._client.table("products").select("*").eq("sku", sku).limit(1).execute()
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        rows = result.data or []
        if not rows:
            return None
        product = product_from_dict(rows[0], "petbarn_snapshot")
        product.source_type = "petbarn_snapshot"
        product.reviews = self._pg_reviews_for(sku)
        return product

    def _pg_reviews_for(self, sku: str) -> list[Review]:
        if self._pg_products is not None:
            return list(self._pg_reviews.get(sku, []))
        if self._client is None:
            return []
        try:
            result = (
                self._client.table("product_reviews")
                .select("*")
                .eq("sku", sku)
                .order("reviewed_at", desc=True)
                .order("created_at", desc=True)
                .execute()
            )
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        return [review_from_dict(row, sku) for row in (result.data or [])]

    def _pg_list(self) -> list[Product] | None:
        if self._pg_products is not None:
            return list(self._pg_products.values())
        if self._client is None:
            return None
        ttl = self._settings.catalog_cache_ttl_seconds
        now = time.monotonic()
        if self._pg_list_cache is not None and ttl > 0 and (now - self._pg_list_at) < ttl:
            return self._pg_list_cache
        try:
            result = self._client.table("products").select("*").execute()
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc
        rows = [product_from_dict(row, "petbarn_snapshot") for row in (result.data or [])]
        self._pg_list_cache = rows
        self._pg_list_at = now
        return rows

    def get_by_sku(self, sku: str) -> Product | None:
        mode = self._settings.data_mode
        if mode == "sample":
            product = self._sample().get(sku)
            return product.model_copy(deep=True) if product else None
        if mode == "cache":
            product = self._json().get(sku)
            return product.model_copy(deep=True) if product else None
        if mode != "postgres":
            try:
                product = self._pg_get(sku)
                if product:
                    log.info("catalog source=postgres sku=%s", sku)
                    return product
            except PersistenceError:
                log.warning("postgres unreachable; falling back to JSON")
        product = self._json().get(sku)
        if product:
            log.info("catalog source=json sku=%s", sku)
            return product.model_copy(deep=True)
        product = self._sample().get(sku)
        if product:
            log.info("catalog source=sample sku=%s", sku)
            return product.model_copy(deep=True)
        return None

    def match_pools(self) -> list[list[Product]]:
        """Identity pools for fuzzy match, in fallback order."""
        mode = self._settings.data_mode
        if mode == "sample":
            return [list(self._sample().values())]
        if mode == "cache":
            return [list(self._json().values())]
        pools: list[list[Product]] = []
        try:
            rows = self._pg_list()
            if rows:
                pools.append(rows)
        except PersistenceError:
            log.warning("postgres unreachable; falling back to JSON")
        json_rows = list(self._json().values())
        if json_rows:
            pools.append(json_rows)
        sample_rows = list(self._sample().values())
        if sample_rows:
            pools.append(sample_rows)
        return pools

    def get_reviews(self, sku: str) -> list[Review]:
        if self._settings.data_mode not in {"sample", "cache"}:
            try:
                product = self._pg_get(sku)
                if product is not None:
                    return self._pg_reviews_for(sku)
            except PersistenceError:
                log.warning("postgres unreachable; falling back to JSON")
        product = self._json().get(sku) or self._sample().get(sku)
        return list(product.reviews) if product else []

    def list_products(self) -> list[Product]:
        mode = self._settings.data_mode
        if mode == "sample":
            return [item.model_copy(deep=True) for item in self._sample().values()]
        if mode == "cache":
            return [item.model_copy(deep=True) for item in self._json().values()]
        try:
            rows = self._pg_list()
            if rows:
                log.info("catalog source=postgres count=%s", len(rows))
                return rows
        except PersistenceError:
            log.warning("postgres unreachable; falling back to JSON")
        json_rows = list(self._json().values())
        if json_rows:
            log.info("catalog source=json count=%s", len(json_rows))
            return json_rows
        sample_rows = list(self._sample().values())
        log.info("catalog source=sample count=%s", len(sample_rows))
        return sample_rows

    def snapshot_source_type(self) -> SourceType:
        products = self.list_products()
        if not products:
            return "synthetic_sample"
        return products[0].source_type
