"""Supabase client factory. Not a repository."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx

from pia.domain.errors import PersistenceError
from pia.logging import get_logger
from pia.settings import Settings, get_settings

log = get_logger("pia.db")

_TRANSIENT = {
    "ConnectError",
    "ConnectTimeout",
    "LocalProtocolError",
    "PoolTimeout",
    "ReadError",
    "ReadTimeout",
    "RemoteProtocolError",
    "TimeoutException",
    "WriteError",
}


def is_transient(exc: BaseException) -> bool:
    """True for dropped connections that are safe to retry."""
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if type(current).__name__ in _TRANSIENT:
            return True
        current = current.__cause__ or current.__context__
    return False


def retry_call[T](operation: Callable[[], T], *, attempts: int = 3) -> T:
    """Retry a PostgREST/httpx call after a dropped connection."""
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            return operation()
        except Exception as exc:
            last = exc
            if not is_transient(exc) or attempt == attempts - 1:
                raise
            log.warning("transient request retry attempt=%s", attempt + 1)
            time.sleep(0.2 * (2**attempt))
    assert last is not None
    raise last


class _RetryTransport(httpx.BaseTransport):
    """HTTP/1.1 transport. postgrest-py otherwise enables HTTP/2 by default."""

    def __init__(self) -> None:
        self._inner = httpx.HTTPTransport(http2=False)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return retry_call(lambda: self._inner.handle_request(request))

    def close(self) -> None:
        self._inner.close()


def _httpx_client() -> httpx.Client:
    return httpx.Client(
        http2=False,
        timeout=30.0,
        follow_redirects=True,
        transport=_RetryTransport(),
    )


def create_client(settings: Settings | None = None) -> Any | None:
    """Return a supabase-py client, or None if URL/key are missing."""
    settings = settings or get_settings()
    if not settings.supabase_url or not settings.supabase_secret_key:
        log.warning("Supabase URL or secret key missing; persistence disabled")
        return None
    try:
        from supabase import ClientOptions
        from supabase import create_client as _create
    except ImportError as exc:
        raise PersistenceError("supabase package is not installed") from exc
    options = ClientOptions(httpx_client=_httpx_client())
    return _create(settings.supabase_url, settings.supabase_secret_key, options)
