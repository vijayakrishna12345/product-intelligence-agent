"""Offline ingest orchestration. Not callable from the runtime agent."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from pia.analysis.sentiment import score_text
from pia.domain.models import Product, Review
from pia.ingestion.http import UrlFetcher, content_hash, write_raw
from pia.ingestion.policy import check_url, configured_sitemap, origin_allowed
from pia.ingestion.product_parser import parse_product_html
from pia.ingestion.quality import crawl_status, product_from_input, review_from_input
from pia.ingestion.reviews import extract_reviews_playwright
from pia.ingestion.sitemap import collect_product_page_urls, collect_seed_presence
from pia.logging import get_logger
from pia.privacy import truncate
from pia.repositories.crawl import CrawlRepository
from pia.settings import Settings, get_settings

log = get_logger("pia.ingest")
ROOT = Path(__file__).resolve().parents[3]


def load_seeds(path: Path) -> list[dict[str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload if isinstance(payload, list) else payload.get("products", [])
    return rows


def build_ingest_targets(
    seeds: list[dict[str, str]], sitemap_urls: list[str], *, limit: int
) -> list[dict[str, str]]:
    seen: set[str] = set()
    targets: list[dict[str, str]] = []
    for item in seeds:
        url = str(item.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        targets.append(item)
        if len(targets) >= limit:
            return targets
    for url in sitemap_urls:
        if url in seen:
            continue
        seen.add(url)
        targets.append({"sku": "", "name": "", "url": url})
        if len(targets) >= limit:
            break
    return targets


class IngestService:
    def __init__(
        self,
        crawl: CrawlRepository,
        fetcher: UrlFetcher | None = None,
        settings: Settings | None = None,
        *,
        extract_reviews=extract_reviews_playwright,
    ) -> None:
        self._crawl = crawl
        self._fetcher = fetcher
        self._settings = settings or get_settings()
        self._extract_reviews = extract_reviews

    def run(self) -> dict:
        settings = self._settings
        seed_path = Path(settings.seed_products_path)
        seeds = load_seeds(seed_path)
        sitemap_url = configured_sitemap(settings.retailer)
        if not origin_allowed(sitemap_url, settings.retailer):
            raise RuntimeError("configured sitemap origin is not allowlisted")
        fetcher = self._fetcher or UrlFetcher(settings)
        run_id = self._crawl.start_run(settings.retailer)
        errors: list[dict] = []
        products_ok = 0
        products_failed = 0
        reviews_ok = 0
        snapshots: list[Product] = []
        try:
            root = fetcher.fetch_text(sitemap_url, policy=False)
            sitemap_urls = collect_product_page_urls(
                root,
                fetch_bytes=lambda url: fetcher.fetch(url, policy=False),
                settings=settings,
                limit=settings.ingest_max_products,
            )
            targets = build_ingest_targets(seeds, sitemap_urls, limit=settings.ingest_max_products)
            seed_url_set = {str(item.get("url") or "") for item in seeds}
            presence = collect_seed_presence(
                root,
                [url for url in seed_url_set if url],
                fetch_bytes=lambda url: fetcher.fetch(url, policy=False),
                settings=settings,
            )
            target_reviews = settings.ingest_target_reviews
            for item in targets:
                url = item["url"]
                sku_hint = item.get("sku") or Path(url).name or url
                try:
                    if url in seed_url_set and not presence.get(url):
                        log.warning("seed URL not in sitemap children url=%s", url)
                        if settings.sitemap_required:
                            raise RuntimeError("seed missing from sitemap")
                    check_url(
                        url,
                        retailer=settings.retailer,
                        fetch_robots=lambda robots_url: fetcher.fetch_text(
                            robots_url, policy=False
                        ),
                    )
                    html = fetcher.fetch(url, policy=True)
                    parsed = parse_product_html(html, url)
                    product = product_from_input(parsed)
                    if product is None:
                        raise RuntimeError("quality gate rejected product")
                    write_raw(ROOT / "data" / "raw" / str(product.sku) / "page.html", html)
                    self._crawl.record_page(url, sku=product.sku, content_hash=content_hash(html))
                    product.scraped_at = datetime.now(UTC)
                    reviews: list[Review] = []
                    stored = self._crawl.stored_review_count(product.sku)
                    if stored >= target_reviews:
                        reviews = self._crawl.stored_reviews(product.sku)[:target_reviews]
                        log.info("skip reviews sku=%s already_have=%s", product.sku, stored)
                    else:
                        try:
                            extraction = self._extract_reviews(url, product.sku, settings)
                            for review_input in extraction.reviews:
                                review_input.sku = product.sku
                                review = review_from_input(review_input)
                                if review is None:
                                    continue
                                label, score = score_text(review.body or review.title)
                                review.sentiment_label = label
                                review.sentiment_score = score
                                reviews.append(review)
                                if len(reviews) >= target_reviews:
                                    break
                        except Exception as exc:
                            log.warning("review branch skipped sku=%s err=%s", product.sku, exc)
                            errors.append(
                                {
                                    "sku": product.sku,
                                    "error_type": type(exc).__name__,
                                    "branch": "reviews",
                                }
                            )
                    reviews = reviews[:target_reviews]
                    if not product.review_count:
                        product.review_count = len(reviews)
                    self._crawl.upsert_product(product, run_id)
                    self._crawl.upsert_reviews(product.sku, reviews, run_id)
                    product.reviews = reviews
                    snapshots.append(product)
                    products_ok += 1
                    reviews_ok += len(reviews)
                    log.info(
                        "product upsert count=%s sku=%s reviews=%s",
                        products_ok,
                        product.sku,
                        len(reviews),
                    )
                    if products_ok == 1 or products_ok % 25 == 0:
                        self._write_snapshot(snapshots, run_id, reviews_ok)
                except Exception as exc:
                    products_failed += 1
                    errors.append(
                        {
                            "sku": sku_hint,
                            "error_type": type(exc).__name__,
                            "message": str(exc)[:200],
                        }
                    )
                    log.error("product failed sku=%s", sku_hint)
            status = crawl_status(products_ok, products_failed)
            self._crawl.finish_run(
                run_id,
                status=status,
                urls_discovered=len(targets),
                products_ok=products_ok,
                products_failed=products_failed,
                reviews_ok=reviews_ok,
                error_summary=errors,
            )
            self._write_snapshot(snapshots, run_id, reviews_ok)
            return {
                "crawl_run_id": str(run_id),
                "status": status,
                "products_ok": products_ok,
                "products_failed": products_failed,
                "reviews_ok": reviews_ok,
            }
        finally:
            if self._fetcher is None:
                fetcher.close()

    def _write_snapshot(self, products: list[Product], run_id: UUID, reviews_ok: int) -> None:
        settings = self._settings
        compact = []
        for product in products:
            newest = sorted(
                product.reviews,
                key=lambda item: (
                    item.reviewed_at.isoformat() if item.reviewed_at else "",
                    item.created_at.isoformat() if item.created_at else "",
                ),
                reverse=True,
            )[: settings.snapshot_excerpt_count]
            labels = {"positive": 0, "neutral": 0, "negative": 0}
            dist = {str(star): 0 for star in range(1, 6)}
            for review in product.reviews:
                labels[review.sentiment_label or "neutral"] += 1
                dist[str(review.rating)] = dist.get(str(review.rating), 0) + 1
            total = max(len(product.reviews), 1)
            compact.append(
                {
                    "sku": product.sku,
                    "name": product.name,
                    "brand": product.brand,
                    "price": product.price,
                    "currency": product.currency,
                    "availability": product.availability,
                    "rating_value": product.rating_value,
                    "review_count": product.review_count or len(product.reviews),
                    "url": product.url,
                    "description": truncate(product.description, 400),
                    "rating_distribution": dist if product.reviews else product.rating_distribution,
                    "sentiment": {key: round(value / total, 4) for key, value in labels.items()}
                    if product.reviews
                    else product.sentiment,
                    "scraped_at": product.scraped_at.isoformat() if product.scraped_at else None,
                    "source_type": "petbarn_snapshot",
                    "reviews": [
                        {
                            "rating": item.rating,
                            "date": item.reviewed_at.isoformat() if item.reviewed_at else None,
                            "text": truncate(item.body or item.title, settings.max_review_text),
                        }
                        for item in newest
                    ],
                }
            )
        catalog_path = ROOT / "data" / "catalog.json"
        catalog_path.parent.mkdir(parents=True, exist_ok=True)
        by_sku: dict[str, dict] = {}
        if catalog_path.exists():
            try:
                previous = json.loads(catalog_path.read_text(encoding="utf-8"))
                for row in previous.get("products") or []:
                    sku = row.get("sku")
                    if sku:
                        by_sku[str(sku)] = row
            except (OSError, json.JSONDecodeError):
                pass
        for row in compact:
            by_sku[str(row["sku"])] = row
        merged = list(by_sku.values())
        catalog_path.write_text(
            json.dumps(
                {
                    "source_type": "petbarn_snapshot",
                    "scraped_at": datetime.now(UTC).isoformat(),
                    "products": merged,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        manifest = {
            "source": settings.retailer,
            "crawl_run_id": str(run_id),
            "scraped_at": datetime.now(UTC).isoformat(),
            "schema_version": 1,
            "counts": {
                "products": len(merged),
                "reviews": reviews_ok,
                "snapshot_excerpts_only": True,
            },
        }
        (ROOT / "data" / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
