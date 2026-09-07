"""Offline catalog ingest CLI."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pia.db import create_client  # noqa: E402
from pia.logging import configure_logging, get_logger  # noqa: E402
from pia.repositories.crawl import CrawlRepository  # noqa: E402
from pia.services.ingest import IngestService  # noqa: E402
from pia.settings import get_settings  # noqa: E402


def main() -> int:
    settings = get_settings()
    configure_logging(settings.log_level)
    log = get_logger("pia.ingest")
    client = create_client(settings)
    service = IngestService(CrawlRepository(client), settings=settings)
    result = service.run()
    log.info(
        "ingest finished status=%s products_ok=%s",
        result.get("status"),
        result.get("products_ok"),
    )
    return 0 if result.get("products_ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
