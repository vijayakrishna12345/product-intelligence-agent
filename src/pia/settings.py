"""Environment and Streamlit-secret settings. Secrets are never logged."""

from __future__ import annotations

import os
from functools import lru_cache


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(override=False)


def _from_streamlit(name: str) -> str | None:
    try:
        import streamlit as st
    except Exception:
        return None
    try:
        secrets = st.secrets
    except Exception:
        return None
    try:
        value = secrets.get(name)  # type: ignore[attr-defined]
    except Exception:
        return None
    if value is None:
        return None
    return str(value)


def _get(name: str, default: str | None = None) -> str | None:
    env = os.environ.get(name)
    if env is not None and env != "":
        return env
    secret = _from_streamlit(name)
    if secret is not None and secret != "":
        return secret
    return default


def _get_str(name: str, default: str) -> str:
    return _get(name, default) or default


def _get_int(name: str, default: int) -> int:
    raw = _get(name)
    if raw is None:
        return default
    return int(raw)


def _get_float(name: str, default: float) -> float:
    raw = _get(name)
    if raw is None:
        return default
    return float(raw)


def _get_bool(name: str, default: bool) -> bool:
    raw = _get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    """All tunables. Secrets have no defaults."""

    def __init__(self) -> None:
        _load_dotenv()
        self.groq_api_key: str = _get("GROQ_API_KEY") or ""
        self.supabase_url: str = _get("SUPABASE_URL") or ""
        self.supabase_secret_key: str = (
            _get("SUPABASE_SECRET_KEY") or _get("SUPABASE_SERVICE_ROLE_KEY") or ""
        )
        self.groq_model: str = _get_str("GROQ_MODEL", "openai/gpt-oss-120b")
        self.groq_simulator_model: str = _get_str("GROQ_SIMULATOR_MODEL", "openai/gpt-oss-20b")
        self.include_reasoning: bool = _get_bool("INCLUDE_REASONING", False)
        self.prompt_version: str = _get_str("PROMPT_VERSION", "v1")
        self.model_call_limit: int = _get_int("MODEL_CALL_LIMIT", 15)
        self.tool_call_limit: int = _get_int("TOOL_CALL_LIMIT", 6)
        self.recursion_limit: int = _get_int("RECURSION_LIMIT", 20)
        self.max_requests_per_session: int = _get_int("MAX_REQUESTS_PER_SESSION", 30)
        self.recent_turns: int = _get_int("RECENT_TURNS", 4)
        self.max_history_tokens: int = _get_int("MAX_HISTORY_TOKENS", 6000)
        self.max_reviews: int = _get_int("MAX_REVIEWS", 15)
        self.max_review_text: int = _get_int("MAX_REVIEW_TEXT", 400)
        self.compare_min_products: int = _get_int("COMPARE_MIN_PRODUCTS", 2)
        self.compare_max_products: int = _get_int("COMPARE_MAX_PRODUCTS", 3)
        self.compare_review_excerpts: int = _get_int("COMPARE_REVIEW_EXCERPTS", 3)
        self.max_tool_result_chars: int = _get_int("MAX_TOOL_RESULT_CHARS", 8000)
        self.chat_page_size: int = _get_int("CHAT_PAGE_SIZE", 50)
        self.agent_poll_seconds: int = _get_int("AGENT_POLL_SECONDS", 2)
        self.agent_run_stale_seconds: int = _get_int("AGENT_RUN_STALE_SECONDS", 180)
        self.agent_worker_max_workers: int = _get_int("AGENT_WORKER_MAX_WORKERS", 2)
        self.stream_final_answer: bool = _get_bool("STREAM_FINAL_ANSWER", False)
        self.retailer: str = _get_str("RETAILER", "petbarn")
        self.data_mode: str = _get_str("DATA_MODE", "auto")
        self.catalog_cache_ttl_seconds: int = _get_int("CATALOG_CACHE_TTL_SECONDS", 300)
        self.seed_products_path: str = _get_str("SEED_PRODUCTS_PATH", "data/seed_products.json")
        self.ingest_min_delay_seconds: float = _get_float("INGEST_MIN_DELAY_SECONDS", 1.0)
        self.ingest_http_timeout_seconds: float = _get_float("INGEST_HTTP_TIMEOUT_SECONDS", 20.0)
        self.ingest_max_retries: int = _get_int("INGEST_MAX_RETRIES", 3)
        self.ingest_max_products: int = _get_int("INGEST_MAX_PRODUCTS", 500)
        self.ingest_target_reviews: int = _get_int("INGEST_TARGET_REVIEWS", 10)
        self.max_review_pages: int = _get_int("MAX_REVIEW_PAGES", 8)
        self.snapshot_excerpt_count: int = _get_int("SNAPSHOT_EXCERPT_COUNT", 10)
        self.sitemap_required: bool = _get_bool("SITEMAP_REQUIRED", False)
        self.max_sitemap_children: int = _get_int("MAX_SITEMAP_CHILDREN", 8)
        self.max_sitemap_bytes: int = _get_int("MAX_SITEMAP_BYTES", 25_000_000)
        self.sitemap_cache_dir: str = _get_str("SITEMAP_CACHE_DIR", "data/raw/sitemap")
        self.log_level: str = _get_str("LOG_LEVEL", "INFO")

    def __repr__(self) -> str:
        return "Settings(redacted)"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings() -> None:
    get_settings.cache_clear()
