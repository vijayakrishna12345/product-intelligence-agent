"""HTTP fetcher: timeout, retry, backoff, delay. Parsers never call this."""

from __future__ import annotations

import hashlib
import random
import time
from pathlib import Path

from pia.domain.errors import IngestionError
from pia.ingestion.policy import USER_AGENT, check_url, origin_allowed
from pia.logging import get_logger
from pia.settings import Settings, get_settings

log = get_logger("pia.http")


class UrlFetcher:
    def __init__(self, settings: Settings | None = None, client=None) -> None:
        self._settings = settings or get_settings()
        self._client = client
        self._owns_client = client is None
        self._last_request_at = 0.0

    def _http(self):
        if self._client is not None:
            return self._client
        import httpx

        self._client = httpx.Client(
            timeout=self._settings.ingest_http_timeout_seconds,
            follow_redirects=False,
            headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"},
        )
        return self._client

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()

    def _delay(self) -> None:
        wait = self._settings.ingest_min_delay_seconds
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < wait:
            time.sleep(wait - elapsed + random.random() * 0.2)

    def fetch(self, url: str, *, policy: bool = True, max_bytes: int | None = None) -> bytes:
        if policy:
            check_url(
                url, fetch_robots=lambda robots_url: self.fetch_text(robots_url, policy=False)
            )
        elif not origin_allowed(url):
            raise IngestionError(f"off-allowlist origin: {url}")
        current = url
        for _hop in range(5):
            if policy:
                check_url(
                    current,
                    fetch_robots=lambda robots_url: self.fetch_text(robots_url, policy=False),
                )
            elif not origin_allowed(current):
                raise IngestionError(f"off-allowlist redirect: {current}")
            body, location = self._get(current, max_bytes=max_bytes)
            if location:
                current = location
                continue
            return body
        raise IngestionError(f"too many redirects: {url}")

    def fetch_text(self, url: str, *, policy: bool = True) -> str:
        return self.fetch(url, policy=policy).decode("utf-8", errors="replace")

    def _get(self, url: str, max_bytes: int | None = None) -> tuple[bytes, str | None]:
        retries = self._settings.ingest_max_retries
        last_error: Exception | None = None
        for attempt in range(retries):
            self._delay()
            try:
                response = self._http().get(url)
                self._last_request_at = time.monotonic()
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise IngestionError("redirect without location")
                    if location.startswith("/"):
                        from urllib.parse import urljoin

                        location = urljoin(url, location)
                    return b"", location
                if response.status_code >= 500:
                    raise IngestionError(f"HTTP {response.status_code}")
                if response.status_code >= 400:
                    raise IngestionError(f"HTTP {response.status_code} for {url}")
                content = response.content
                if max_bytes is not None and len(content) > max_bytes:
                    raise IngestionError("response exceeded MAX_SITEMAP_BYTES")
                return content, None
            except IngestionError as exc:
                last_error = exc
                if "HTTP 4" in str(exc):
                    raise
                time.sleep((2**attempt) * 0.4)
            except Exception as exc:
                last_error = exc
                time.sleep((2**attempt) * 0.4)
        raise IngestionError(str(last_error) if last_error else "fetch failed")


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_raw(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
