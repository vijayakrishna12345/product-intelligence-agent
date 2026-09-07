"""Crawl URL policy: allowlist first, then robots from that origin."""

from __future__ import annotations

import ipaddress
from functools import lru_cache
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from pia.domain.errors import DomainNotAllowed, PathNotAllowed, RobotsDisallowed
from pia.logging import get_logger
from pia.settings import get_settings

log = get_logger("pia.ingest")

ALLOWED_RETAILERS: dict[str, dict[str, object]] = {
    "petbarn": {
        "domains": {"www.petbarn.com.au", "petbarn.com.au"},
        "sitemap": "https://www.petbarn.com.au/media/sitemap/au/sitemap.xml",
    }
}

# urllib.robotparser ignores wildcard/$ rules; these patterns are the real gate.
DENY_PATTERNS = (
    "/catalogsearch/",
    "/search",
    "/catalog/product/view/",
    "/checkout/",
    "/customer/",
    "/wishlist/",
    "bvstate=",
    "?sid=",
    "order=",
    "dir=",
    ".php",
)

USER_AGENT = "PIAAssessmentBot/0.1"


def retailer_config(retailer: str | None = None) -> dict[str, object]:
    name = (retailer or get_settings().retailer).lower()
    config = ALLOWED_RETAILERS.get(name)
    if not config:
        raise DomainNotAllowed(f"Unknown retailer: {name}")
    return config


def allowed_domains(retailer: str | None = None) -> set[str]:
    domains = retailer_config(retailer)["domains"]
    return set(domains)  # type: ignore[arg-type]


def configured_sitemap(retailer: str | None = None) -> str:
    return str(retailer_config(retailer)["sitemap"])


def origin_allowed(url: str, retailer: str | None = None) -> bool:
    try:
        _parse_https_host(url)
        host = urlparse(url).hostname or ""
    except DomainNotAllowed:
        return False
    return host.lower() in allowed_domains(retailer)


def _parse_https_host(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https":
        raise DomainNotAllowed("HTTPS only")
    if parsed.username or parsed.password:
        raise DomainNotAllowed("userinfo is not allowed")
    host = (parsed.hostname or "").lower()
    if not host:
        raise DomainNotAllowed("missing host")
    try:
        ipaddress.ip_address(host)
        raise DomainNotAllowed("IP-literal hosts are not allowed")
    except ValueError:
        pass
    return host, parsed.path or "/"


def check_url_offline(url: str, retailer: str | None = None) -> None:
    """Parse, domain, path, deny-patterns. No network."""
    host, path = _parse_https_host(url)
    if host not in allowed_domains(retailer):
        raise DomainNotAllowed(host)
    lowered = url.lower()
    path_l = path.lower()
    if path_l.startswith("/catalogsearch") or path_l == "/search" or path_l.startswith("/search/"):
        raise PathNotAllowed(path)
    for pattern in DENY_PATTERNS:
        if pattern.lower() in lowered:
            raise PathNotAllowed(pattern)


def check_robots(url: str, robots_txt: str) -> None:
    parser = RobotFileParser()
    parser.parse(robots_txt.splitlines())
    if not parser.can_fetch(USER_AGENT, url):
        raise RobotsDisallowed(url)


@lru_cache(maxsize=8)
def _cached_robots(origin: str, body: str) -> str:
    return body


def check_url(
    url: str,
    *,
    retailer: str | None = None,
    robots_txt: str | None = None,
    fetch_robots=None,
) -> None:
    check_url_offline(url, retailer)
    host = (urlparse(url).hostname or "").lower()
    origin = f"https://{host}"
    body = robots_txt
    if body is None and fetch_robots is not None:
        body = fetch_robots(f"{origin}/robots.txt")
    if body is None:
        return
    check_robots(url, body)
