"""Review extraction. Playwright is ingest-only and imported lazily."""

from __future__ import annotations

import json
import re
from datetime import date
from html.parser import HTMLParser

from pia.domain.errors import IngestionError
from pia.domain.models import ReviewExtractionResult, ReviewInput
from pia.logging import get_logger
from pia.privacy import review_identity
from pia.settings import Settings, get_settings

log = get_logger("pia.ingest")

_RATING = re.compile(r"([1-5](?:\.\d)?)\s*(?:out of|/)\s*5", re.I)
_DATE = re.compile(r"(20\d{2}-\d{2}-\d{2})")
_REVIEW_NODES = (
    ".bv-content-review, [data-bv-review-id], [itemprop='review'], .bv-content-review-wrapper"
)
_SCRIPT = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)


class _ReviewHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.reviews: list[dict[str, str]] = []
        self._buf: list[str] = []
        self._in_review = False
        self._depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key: (value or "") for key, value in attrs}
        cls = f"{attr.get('class', '')} {attr.get('data-testid', '')}".lower()
        review_id = attr.get("data-bv-review-id") or attr.get("data-review-id")
        if review_id or "bv-content-review" in cls or "review-item" in cls:
            self._in_review = True
            self._depth = 1
            self._buf = [f"id={review_id}"]
            return
        if self._in_review:
            self._depth += 1
            if attr.get("datetime"):
                self._buf.append(attr["datetime"])

    def handle_endtag(self, tag: str) -> None:
        if not self._in_review:
            return
        self._depth -= 1
        if self._depth <= 0:
            self.reviews.append({"text": " ".join(self._buf)})
            self._in_review = False
            self._buf = []

    def handle_data(self, data: str) -> None:
        if self._in_review and data.strip():
            self._buf.append(data.strip())


def parse_reviews_html(html: str, sku: str) -> list[ReviewInput]:
    parser = _ReviewHTMLParser()
    parser.feed(html)
    results: list[ReviewInput] = []
    for block in parser.reviews:
        text = block.get("text") or ""
        widget_id = None
        if text.startswith("id=") and " " in text:
            widget_id = text.split(" ", 1)[0][3:] or None
            text = text.split(" ", 1)[1]
        rating_match = _RATING.search(text)
        rating = int(float(rating_match.group(1))) if rating_match else 5
        date_match = _DATE.search(text)
        reviewed = date.fromisoformat(date_match.group(1)) if date_match else None
        body = text
        ident = review_identity(
            sku,
            widget_id=widget_id,
            reviewed_at=reviewed.isoformat() if reviewed else None,
            body=body,
        )
        results.append(
            ReviewInput(
                sku=sku,
                rating=rating,
                external_review_id=ident,
                body=body,
                reviewed_at=reviewed,
                source="html",
            )
        )
    return results


def _objects(node: object) -> list[dict]:
    if isinstance(node, list):
        items: list[dict] = []
        for child in node:
            items.extend(_objects(child))
        return items
    if isinstance(node, dict):
        items = [node]
        if "@graph" in node:
            items.extend(_objects(node["@graph"]))
        return items
    return []


def _text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return _text(value.get("reviewBody") or value.get("name") or value.get("@value"))
    if isinstance(value, list):
        for item in value:
            text = _text(item)
            if text:
                return text
        return None
    text = str(value).strip()
    return text or None


def parse_reviews_jsonld(html: str, sku: str) -> list[ReviewInput]:
    results: list[ReviewInput] = []
    for match in _SCRIPT.finditer(html):
        try:
            payload = json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            continue
        for node in _objects(payload):
            types = node.get("@type") or node.get("type") or ""
            if isinstance(types, list):
                type_set = {str(item).lower() for item in types}
            else:
                type_set = {str(types).lower()}
            reviews = node.get("review")
            if "review" in type_set and not reviews:
                reviews = [node]
            if not reviews:
                continue
            if isinstance(reviews, dict):
                reviews = [reviews]
            for item in reviews:
                if not isinstance(item, dict):
                    continue
                body = _text(item.get("reviewBody") or item.get("description"))
                title = _text(item.get("name") or item.get("headline"))
                if not body and not title:
                    continue
                rating_node = item.get("reviewRating")
                rating_val = 5
                if isinstance(rating_node, dict):
                    try:
                        rating_val = int(float(str(rating_node.get("ratingValue") or 5)))
                    except ValueError:
                        rating_val = 5
                published = _text(item.get("datePublished"))
                reviewed = None
                if published:
                    try:
                        reviewed = date.fromisoformat(published[:10])
                    except ValueError:
                        reviewed = None
                ident = review_identity(
                    sku,
                    widget_id=_text(item.get("@id")),
                    reviewed_at=reviewed.isoformat() if reviewed else None,
                    title=title,
                    body=body or title,
                )
                combined = body
                if title and body and title not in body:
                    combined = f"{title} {body}"
                elif not combined:
                    combined = title
                results.append(
                    ReviewInput(
                        sku=sku,
                        rating=max(1, min(5, rating_val)),
                        external_review_id=ident,
                        title=title,
                        body=combined,
                        reviewed_at=reviewed,
                        source="jsonld",
                    )
                )
    return results


def _click_first(page, selectors: list[str], timeout: int = 2_000) -> bool:
    for selector in selectors:
        loc = page.locator(selector)
        try:
            if loc.count() == 0:
                continue
            loc.first.click(timeout=timeout)
            return True
        except Exception:
            continue
    return False


def _shadow_review_html(page) -> str:
    try:
        blocks = page.evaluate(
            """() => {
              const roots = [];
              const visit = (node) => {
                if (!node) return;
                if (node.shadowRoot) {
                  roots.push(node.shadowRoot);
                  visit(node.shadowRoot);
                }
                const children = node.querySelectorAll ? node.querySelectorAll('*') : [];
                for (const el of children) {
                  if (el.shadowRoot) {
                    roots.push(el.shadowRoot);
                    visit(el.shadowRoot);
                  }
                }
              };
              visit(document);
              const host = document.querySelector('[data-bv-show="reviews"]');
              if (host) roots.push(host);
              const html = [];
              for (const root of roots) {
                const nodes = root.querySelectorAll(
                  '.bv-content-review, [data-bv-review-id], [itemprop="review"]'
                );
                for (const node of nodes) html.push(node.outerHTML);
              }
              const jsonld = document.querySelector('#bv-jsonld-reviews-data');
              if (jsonld) html.push(jsonld.outerHTML);
              return html;
            }"""
        )
    except Exception:
        return ""
    if not isinstance(blocks, list):
        return ""
    return "\n".join(str(item) for item in blocks if item)


def _click_bv_next(page) -> bool:
    try:
        return bool(
            page.evaluate(
                """() => {
                  const roots = [];
                  const visit = (node) => {
                    if (!node) return;
                    if (node.shadowRoot) {
                      roots.push(node.shadowRoot);
                      visit(node.shadowRoot);
                    }
                    const children = node.querySelectorAll ? node.querySelectorAll('*') : [];
                    for (const el of children) {
                      if (el.shadowRoot) {
                        roots.push(el.shadowRoot);
                        visit(el.shadowRoot);
                      }
                    }
                  };
                  visit(document);
                  const host = document.querySelector('[data-bv-show="reviews"]');
                  if (host) roots.push(host);
                  roots.push(document);
                  const selectors = [
                    'a.bv-content-btn-pages-next',
                    'button.bv-content-btn-pages-next',
                    'button[aria-label="Next Page"]',
                    'a[aria-label="Next Page"]',
                    'button[aria-label*="Next"]',
                    'a[aria-label*="Next"]',
                    '.bv-content-pagination-container a[aria-label*="Next"]',
                    '.bv-content-pagination-buttons-item-next a',
                    'button.bv-content-btn-pages-load-more',
                    'button[aria-label*="Show more"]',
                  ];
                  for (const root of roots) {
                    if (!root.querySelectorAll) continue;
                    for (const selector of selectors) {
                      let btn;
                      try { btn = root.querySelector(selector); } catch { continue; }
                      if (!btn) continue;
                      const disabled = btn.getAttribute('aria-disabled') === 'true'
                        || btn.classList.contains('bv-content-disabled')
                        || btn.hasAttribute('disabled');
                      if (disabled) continue;
                      btn.click();
                      return true;
                    }
                  }
                  return false;
                }"""
            )
        )
    except Exception:
        return False


def _html_from_page(page) -> str:
    chunks = [page.content()]
    for frame in page.frames:
        if frame == page.main_frame:
            continue
        url = (frame.url or "").lower()
        if "bvstate=" in url:
            continue
        try:
            chunks.append(frame.content())
        except Exception:
            continue
    return "\n".join(chunks)


def extract_reviews_playwright(
    url: str, sku: str, settings: Settings | None = None
) -> ReviewExtractionResult:
    """Page reviews by clicking the widget next control. Never navigate to ?bvstate=."""
    settings = settings or get_settings()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise IngestionError(
            "Playwright is not installed. "
            "Run: uv sync --group dev && uv run playwright install chromium"
        ) from exc

    pages_fetched = 0
    truncated = False
    unique: dict[str, ReviewInput] = {}
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            raise IngestionError(
                "Playwright Chromium is missing. Run: uv run playwright install chromium"
            ) from exc
        page = browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        _click_first(
            page,
            [
                "#onetrust-accept-btn-handler",
                "button:has-text('Accept Cookies')",
                "button:has-text('Accept all')",
            ],
        )
        _click_first(page, ["#tab-reviews", "button[aria-controls='panel-reviews']"])
        lazy = page.locator(
            "[data-identifier-id='lazy-bazaarvoice-integration'], #panel-reviews, #reviews"
        )
        try:
            if lazy.count() > 0:
                lazy.first.scroll_into_view_if_needed(timeout=8_000)
        except Exception:
            pass
        try:
            page.wait_for_selector("#bv-jsonld-reviews-data", state="attached", timeout=25_000)
        except Exception:
            try:
                page.wait_for_selector(_REVIEW_NODES, timeout=5_000)
            except Exception:
                log.warning("bazaarvoice widget did not render sku=%s", sku)
        try:
            page.wait_for_timeout(800)
        except Exception:
            pass
        target = settings.ingest_target_reviews
        for _page_no in range(settings.max_review_pages):
            pages_fetched += 1
            html = _html_from_page(page) + "\n" + _shadow_review_html(page)
            if "bvstate=" in page.url.lower():
                log.warning("aborting review pagination: bvstate URL")
                break
            parsed = parse_reviews_html(html, sku) + parse_reviews_jsonld(html, sku)
            for item in parsed:
                ident = item.external_review_id or review_identity(sku, body=item.body)
                unique[ident] = item
            if len(unique) >= target:
                break
            clicked = _click_bv_next(page)
            if not clicked:
                next_btn = page.locator(
                    "a.bv-content-btn-pages-next, button.bv-content-btn-pages-next"
                )
                if next_btn.count() == 0:
                    break
                try:
                    next_btn.first.click(timeout=5_000)
                    clicked = True
                except Exception:
                    truncated = True
                    break
                if "bvstate=" in page.url.lower():
                    log.warning("clicked into bvstate URL; stopping")
                    truncated = True
                    break
            if not clicked:
                break
            try:
                page.wait_for_timeout(1_200)
            except Exception:
                truncated = True
                break
        else:
            truncated = True
        browser.close()
    reviews = list(unique.values())[:target]
    if not reviews:
        log.warning("no reviews parsed sku=%s pages=%s", sku, pages_fetched)
    return ReviewExtractionResult(
        reviews=reviews,
        pages_fetched=pages_fetched,
        truncated=truncated or len(reviews) < target,
    )
