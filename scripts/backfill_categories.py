"""Backfill category on compact catalog.json from name/url/description metadata."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pia.analysis.taxonomy import normalize_category  # noqa: E402


def main() -> int:
    catalog_path = ROOT / "data" / "catalog.json"
    if not catalog_path.exists():
        print("catalog.json not found", file=sys.stderr)
        return 1
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    products = payload.get("products") or []
    updated = 0
    for row in products:
        if not isinstance(row, dict):
            continue
        category = normalize_category(
            row.get("category"),
            name=str(row.get("name") or ""),
            url=str(row.get("url") or ""),
            description=str(row.get("description") or ""),
        )
        if category and row.get("category") != category:
            updated += 1
        row["category"] = category
    catalog_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"backfilled categories for {len(products)} products ({updated} changed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
