from pathlib import Path

import pytest

from pia.domain.models import Product
from pia.repositories.catalog import CatalogRepository
from pia.settings import get_settings, reset_settings

ROOT = Path(__file__).resolve().parents[1]


def test_sample_source_type(catalog_repo):
    product = catalog_repo.get_by_sku("SYN-KONG-FLYER")
    assert product is not None
    assert product.source_type == "synthetic_sample"


def test_postgres_hit(monkeypatch):
    monkeypatch.setenv("DATA_MODE", "auto")
    reset_settings()
    settings = get_settings()
    pg = {
        "PG-1": Product(
            sku="PG-1",
            name="Postgres Only Kibble",
            url="https://www.petbarn.com.au/p/pg",
            source_type="petbarn_snapshot",
        )
    }
    repo = CatalogRepository(
        postgres_products=pg,
        catalog_path=ROOT / "missing-catalog.json",
        sample_path=ROOT / "data" / "sample_catalog.json",
        settings=settings,
    )
    product = repo.get_by_sku("PG-1")
    assert product is not None
    assert product.source_type == "petbarn_snapshot"
    reset_settings()


def test_query_miss_uses_sample(monkeypatch):
    monkeypatch.setenv("DATA_MODE", "auto")
    reset_settings()
    settings = get_settings()
    pg = {
        "PG-1": Product(
            sku="PG-1",
            name="Postgres Only Kibble",
            url="https://www.petbarn.com.au/p/pg",
            source_type="petbarn_snapshot",
        )
    }
    repo = CatalogRepository(
        postgres_products=pg,
        catalog_path=ROOT / "missing-catalog.json",
        sample_path=ROOT / "data" / "sample_catalog.json",
        settings=settings,
    )
    product = repo.get_by_sku("SYN-KONG-FLYER")
    assert product is not None
    assert product.source_type == "synthetic_sample"
    reset_settings()


def test_fuzzy_match(catalog_service):
    product = catalog_service.resolve("kong flyer")
    assert product.sku == "SYN-KONG-FLYER"


def test_search_max_price_filter(catalog_service):
    hits = catalog_service.search("advance indoor", max_price=25.0)
    assert hits
    assert all(item.price is None or item.price <= 25.0 for item in hits)


def test_snapshot_file_is_compact():
    path = ROOT / "data" / "catalog.json"
    if not path.exists():
        pytest.skip("data/catalog.json is produced by ingest")
    text = path.read_text(encoding="utf-8")
    assert "source_type" in text
    assert len(text) < 5_000_000


def test_json_snapshot_reloads_after_ingest(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_MODE", "auto")
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "")
    reset_settings()
    settings = get_settings()
    catalog_path = tmp_path / "catalog.json"
    repo = CatalogRepository(
        client=None,
        catalog_path=catalog_path,
        sample_path=ROOT / "data" / "sample_catalog.json",
        settings=settings,
    )
    first = repo.list_products()
    assert first[0].source_type == "synthetic_sample"
    catalog_path.write_text(
        (
            '{"source_type":"petbarn_snapshot","products":['
            '{"sku":"140242","name":"Advance Indoor",'
            '"url":"https://www.petbarn.com.au/p/advance","source_type":"petbarn_snapshot"}]}'
        ),
        encoding="utf-8",
    )
    second = repo.list_products()
    assert second[0].sku == "140242"
    assert second[0].source_type == "petbarn_snapshot"
    reset_settings()


class _CountingQuery:
    def __init__(self, owner):
        self._owner = owner

    def select(self, *args, **kwargs):
        return self

    def execute(self):
        return self._owner._execute()


class _CountingClient:
    def __init__(self, rows):
        self.calls = 0
        self.rows = rows

    def table(self, _name):
        return _CountingQuery(self)

    def _execute(self):
        self.calls += 1
        return type("Result", (), {"data": self.rows})()


def test_postgres_list_uses_ttl_cache(monkeypatch):
    monkeypatch.setenv("DATA_MODE", "postgres")
    monkeypatch.setenv("CATALOG_CACHE_TTL_SECONDS", "300")
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "")
    reset_settings()
    client = _CountingClient(
        [
            {
                "sku": "140242",
                "name": "Advance Indoor",
                "url": "https://www.petbarn.com.au/p/advance",
                "source_type": "petbarn_snapshot",
            }
        ]
    )
    repo = CatalogRepository(
        client,
        catalog_path=ROOT / "missing-catalog.json",
        sample_path=ROOT / "data" / "sample_catalog.json",
        settings=get_settings(),
    )
    first = repo.list_products()
    second = repo.list_products()
    assert first[0].sku == "140242"
    assert second[0].sku == "140242"
    assert client.calls == 1
    reset_settings()
