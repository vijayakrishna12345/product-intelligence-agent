"""PII redaction and review identity hashing."""

from __future__ import annotations

import hashlib
import re

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE_RE = re.compile(r"\b(?:\+?61|0)[\s.-]?(?:\d[\s.-]?){8,10}\b")


def redact_text(text: str | None) -> str:
    if not text:
        return ""
    redacted = EMAIL_RE.sub("[redacted-email]", text)
    return PHONE_RE.sub("[redacted-phone]", redacted)


def truncate(text: str | None, max_chars: int) -> str:
    value = text or ""
    if len(value) <= max_chars:
        return value
    return value[: max(0, max_chars - 1)].rstrip() + "…"


def review_identity(
    sku: str,
    *,
    widget_id: str | None = None,
    reviewed_at: str | None = None,
    author: str | None = None,
    title: str | None = None,
    body: str | None = None,
) -> str:
    if widget_id:
        return widget_id
    material = f"{sku}|{reviewed_at or ''}|{author or ''}|{title or ''}|{body or ''}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()
