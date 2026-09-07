"""Sitemap index traversal with a byte cap and local cache."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

from pia.domain.errors import DomainNotAllowed, PathNotAllowed
from pia.ingestion.policy import check_url_offline, origin_allowed
from pia.logging import get_logger
from pia.settings import Settings, get_settings

log = get_logger("pia.ingest")

_LOC = re.compile(r"<loc>\s*([^<]+)\s*</loc>", re.I)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def parse_root_kind(xml_text: str) -> str:
    root = ET.fromstring(xml_text)
    name = _local(root.tag)
    if name == "sitemapindex":
        return "index"
    return "urlset"


def child_locs(xml_text: str) -> list[str]:
    return [match.strip() for match in _LOC.findall(xml_text)]


def is_product_child(url: str) -> bool:
    name = Path(urlparse(url).path).name
    return bool(re.fullmatch(r"sitemap-1-\d+\.xml", name))


def seed_in_blob(blob: str, seed_url: str) -> bool:
    return seed_url in blob


def is_product_page_url(url: str) -> bool:
    path = (urlparse(url).path or "").rstrip("/")
    parts = [part for part in path.split("/") if part]
    return len(parts) >= 2 and parts[0].lower() == "p" and bool(parts[1])


def load_sitemap_blobs(
    root_xml: str,
    *,
    fetch_bytes,
    settings: Settings | None = None,
) -> list[str]:
    settings = settings or get_settings()
    kind = parse_root_kind(root_xml)
    if kind == "urlset":
        return [root_xml]
    children = [url for url in child_locs(root_xml) if is_product_child(url)]
    children = children[: settings.max_sitemap_children]
    cache_dir = Path(settings.sitemap_cache_dir)
    blobs: list[str] = []
    for child in children:
        if not origin_allowed(child):
            log.warning("skipping off-allowlist sitemap child")
            continue
        blobs.append(load_or_fetch_child(child, cache_dir, fetch_bytes, settings.max_sitemap_bytes))
    return blobs


def collect_product_page_urls(
    root_xml: str,
    *,
    fetch_bytes,
    settings: Settings | None = None,
    limit: int | None = None,
) -> list[str]:
    """Allowlisted /p/... locs from product sitemap children, capped."""
    settings = settings or get_settings()
    cap = limit if limit is not None else settings.ingest_max_products
    seen: set[str] = set()
    urls: list[str] = []
    for blob in load_sitemap_blobs(root_xml, fetch_bytes=fetch_bytes, settings=settings):
        for loc in child_locs(blob):
            if loc in seen or not is_product_page_url(loc):
                continue
            try:
                check_url_offline(loc, settings.retailer)
            except (DomainNotAllowed, PathNotAllowed):
                continue
            seen.add(loc)
            urls.append(loc)
            if len(urls) >= cap:
                return urls
    return urls


def load_or_fetch_child(url: str, cache_dir: Path, fetch_bytes, max_bytes: int) -> str:
    cache_dir.mkdir(parents=True, exist_ok=True)
    name = Path(urlparse(url).path).name or "child.xml"
    path = cache_dir / name
    if path.exists():
        return path.read_text(encoding="utf-8", errors="replace")
    data = fetch_bytes(url)
    if len(data) > max_bytes:
        log.warning("sitemap child exceeded byte cap url=%s", url)
        data = data[:max_bytes]
    path.write_bytes(data)
    return data.decode("utf-8", errors="replace")


def collect_seed_presence(
    root_xml: str,
    seed_urls: list[str],
    *,
    fetch_bytes,
    settings: Settings | None = None,
) -> dict[str, bool]:
    settings = settings or get_settings()
    found = {url: False for url in seed_urls}
    blobs = load_sitemap_blobs(root_xml, fetch_bytes=fetch_bytes, settings=settings)
    joined = "\n".join(blobs)
    for url in seed_urls:
        found[url] = seed_in_blob(joined, url)
    return found
