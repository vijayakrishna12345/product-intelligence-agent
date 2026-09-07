"""Quality gate before Postgres upsert."""

from __future__ import annotations

from pia.domain.models import Product, ProductInput, Review, ReviewInput
from pia.privacy import review_identity


def product_from_input(item: ProductInput) -> Product | None:
    sku = (item.sku or "").strip()
    name = (item.name or "").strip()
    url = (item.url or "").strip()
    if not sku or not name or not url:
        return None
    return Product(
        sku=sku,
        name=name,
        url=url,
        brand=item.brand,
        category=item.category,
        description=item.description,
        price=item.price,
        currency=item.currency,
        availability=item.availability,
        rating_value=item.rating_value,
        review_count=item.review_count,
        payload=item.payload,
        source_type="petbarn_snapshot",
    )


def review_from_input(item: ReviewInput) -> Review | None:
    body = (item.body or "").strip()
    title = (item.title or "").strip()
    if not body and not title:
        return None
    if item.rating is None or not (1 <= int(item.rating) <= 5):
        return None
    ident = item.external_review_id or review_identity(
        item.sku,
        reviewed_at=item.reviewed_at.isoformat() if item.reviewed_at else None,
        author=item.author,
        title=title,
        body=body,
    )
    if not ident:
        return None
    return Review(
        sku=item.sku,
        external_review_id=ident,
        rating=int(item.rating),
        title=title or None,
        body=body or None,
        author=item.author,
        reviewed_at=item.reviewed_at,
        source=item.source,
        payload=item.payload,
    )


def crawl_status(products_ok: int, products_failed: int) -> str:
    if products_ok <= 0:
        return "failed"
    if products_failed > 0:
        return "partial"
    return "success"
