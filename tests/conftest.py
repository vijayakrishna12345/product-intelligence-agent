from __future__ import annotations

from pathlib import Path

import pytest

from pia.repositories.catalog import CatalogRepository
from pia.services.catalog import CatalogService
from pia.services.comparison import ComparisonService
from pia.settings import get_settings, reset_settings

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def sample_settings(monkeypatch):
    monkeypatch.setenv("DATA_MODE", "sample")
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "")
    reset_settings()
    yield get_settings()
    reset_settings()


@pytest.fixture
def catalog_repo(sample_settings):
    return CatalogRepository(
        client=None,
        catalog_path=ROOT / "data" / "catalog.json",
        sample_path=ROOT / "data" / "sample_catalog.json",
        settings=sample_settings,
    )


@pytest.fixture
def catalog_service(catalog_repo, sample_settings):
    return CatalogService(catalog_repo, sample_settings)


@pytest.fixture
def comparison_service(catalog_service, sample_settings):
    return ComparisonService(catalog_service, sample_settings)
