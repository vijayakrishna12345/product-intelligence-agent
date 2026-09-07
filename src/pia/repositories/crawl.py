"""Crawl run, product, and review upserts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pia.domain.errors import PersistenceError
from pia.domain.models import Product, Review
from pia.logging import get_logger

log = get_logger("pia.ingest")


def _now() -> datetime:
    return datetime.now(UTC)


class CrawlRepository:
    """Persist crawl runs, products, reviews, and page metadata."""

    def __init__(self, client: Any | None = None) -> None:
        self._client = client
        self.products: dict[str, Product] = {}
        self.reviews: dict[str, list[Review]] = {}
        self.pages: dict[str, dict[str, Any]] = {}
        self.runs: dict[UUID, dict[str, Any]] = {}

    def start_run(self, source: str = "petbarn") -> UUID:
        run_id = uuid4()
        row = {
            "id": str(run_id),
            "source": source,
            "status": "running",
            "started_at": _now().isoformat(),
            "urls_discovered": 0,
            "products_ok": 0,
            "products_failed": 0,
            "reviews_ok": 0,
            "error_summary": [],
        }
        self.runs[run_id] = row
        if self._client is not None:
            try:
                self._client.table("crawl_runs").insert(row).execute()
            except Exception as exc:
                raise PersistenceError(str(exc)) from exc
        log.info("crawl_run started id=%s", run_id)
        return run_id

    def finish_run(
        self,
        run_id: UUID,
        *,
        status: str,
        urls_discovered: int,
        products_ok: int,
        products_failed: int,
        reviews_ok: int,
        error_summary: list[dict[str, Any]],
        notes: str | None = None,
    ) -> None:
        payload = {
            "status": status,
            "finished_at": _now().isoformat(),
            "urls_discovered": urls_discovered,
            "products_ok": products_ok,
            "products_failed": products_failed,
            "reviews_ok": reviews_ok,
            "error_summary": error_summary,
            "notes": notes,
        }
        self.runs[run_id] = {**self.runs.get(run_id, {}), **payload}
        if self._client is not None:
            self._client.table("crawl_runs").update(payload).eq("id", str(run_id)).execute()
        log.info("crawl_run finished id=%s status=%s", run_id, status)

    def upsert_product(self, product: Product, crawl_run_id: UUID) -> None:
        self.products[product.sku] = product
        if self._client is None:
            return
        row = {
            "sku": product.sku,
            "name": product.name,
            "brand": product.brand,
            "category": product.category,
            "url": product.url,
            "description": product.description,
            "price": product.price,
            "currency": product.currency,
            "availability": product.availability,
            "rating_value": product.rating_value,
            "review_count": product.review_count,
            "payload": product.payload,
            "crawl_run_id": str(crawl_run_id),
            "scraped_at": (product.scraped_at or _now()).isoformat(),
        }
        try:
            self._client.table("products").upsert(row, on_conflict="sku").execute()
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc

    def upsert_reviews(self, sku: str, reviews: list[Review], crawl_run_id: UUID) -> None:
        existing = {item.external_review_id: item for item in self.reviews.get(sku, [])}
        for review in reviews:
            existing[review.external_review_id] = review
        self.reviews[sku] = list(existing.values())
        if self._client is None:
            return
        rows = []
        for review in reviews:
            rows.append(
                {
                    "sku": sku,
                    "external_review_id": review.external_review_id,
                    "rating": review.rating,
                    "title": review.title,
                    "body": review.body,
                    "author": review.author,
                    "reviewed_at": review.reviewed_at.isoformat() if review.reviewed_at else None,
                    "sentiment_label": review.sentiment_label,
                    "sentiment_score": review.sentiment_score,
                    "source": review.source,
                    "crawl_run_id": str(crawl_run_id),
                    "payload": review.payload,
                }
            )
        if not rows:
            return
        try:
            self._client.table("product_reviews").upsert(
                rows, on_conflict="sku,external_review_id"
            ).execute()
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc

    def stored_review_count(self, sku: str) -> int:
        if self._client is None:
            return len(self.reviews.get(sku, []))
        try:
            result = (
                self._client.table("product_reviews")
                .select("external_review_id", count="exact")
                .eq("sku", sku)
                .execute()
            )
        except Exception:
            return len(self.reviews.get(sku, []))
        if result.count is not None:
            return int(result.count)
        return len(result.data or [])

    def stored_reviews(self, sku: str) -> list[Review]:
        if self._client is None:
            return list(self.reviews.get(sku, []))
        try:
            result = (
                self._client.table("product_reviews")
                .select("*")
                .eq("sku", sku)
                .order("reviewed_at", desc=True)
                .order("created_at", desc=True)
                .execute()
            )
        except Exception:
            return list(self.reviews.get(sku, []))
        from pia.repositories.catalog import review_from_dict

        return [review_from_dict(row, sku) for row in (result.data or [])]

    def record_page(
        self, url: str, *, sku: str | None, content_hash: str, status: str = "fetched"
    ) -> None:
        row = {
            "url": url,
            "sku": sku,
            "content_hash": content_hash,
            "status": status,
            "fetched_at": _now().isoformat(),
        }
        self.pages[url] = row
        if self._client is None:
            return
        self._client.table("crawl_pages").upsert(row, on_conflict="url").execute()
