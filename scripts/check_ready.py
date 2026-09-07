"""Local readiness checks: secrets scan, catalog, optional Groq/Supabase."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pia.db import create_client  # noqa: E402
from pia.logging import configure_logging  # noqa: E402
from pia.repositories.catalog import CatalogRepository  # noqa: E402
from pia.settings import get_settings  # noqa: E402

SECRET_MARKERS = ("gsk_", "BEGIN RSA PRIVATE KEY", "BEGIN OPENSSH PRIVATE KEY")


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return [line for line in result.stdout.splitlines() if line]


def secret_scan() -> list[str]:
    hits: list[str] = []
    for rel in tracked_files():
        path = ROOT / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for marker in SECRET_MARKERS:
            if marker in text:
                hits.append(f"{rel}: {marker}")
        if "eyJ" in text and "service_role" in text.lower():
            hits.append(f"{rel}: jwt-like service role")
    return hits


def main() -> int:
    settings = get_settings()
    configure_logging(settings.log_level)
    errors: list[str] = []
    hits = secret_scan()
    if hits:
        errors.extend(hits)
    repo = CatalogRepository(settings=settings)
    products = repo.list_products()
    if not products:
        errors.append("catalog is empty")
    client = create_client(settings)
    if settings.supabase_url and settings.supabase_secret_key and client is None:
        errors.append("supabase client failed")
    if not settings.groq_api_key:
        errors.append("GROQ_API_KEY missing")
    else:
        try:
            from pia.agent.factory import build_model

            build_model(settings)
        except Exception as exc:
            errors.append(f"groq model init failed: {exc}")
        gate = subprocess.run(
            ["uv", "run", "pytest", "-m", "release", "-q"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if gate.returncode != 0:
            errors.append("release gate failed (pytest -m release)")
            tail = (gate.stdout + gate.stderr).strip()[-3000:]
            if tail:
                errors.append(tail)
    if errors:
        for item in errors:
            sys.stderr.write(item + "\n")
        return 1
    sys.stdout.write("ready\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
