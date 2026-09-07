from pathlib import Path

import pytest

from pia.domain.errors import DomainNotAllowed, PathNotAllowed
from pia.ingestion.policy import check_url_offline, configured_sitemap, origin_allowed
from pia.ingestion.sitemap import collect_seed_presence, is_product_child, parse_root_kind

FIXTURES = Path(__file__).parent / "fixtures" / "sitemap"


def test_allowlisted_product_url():
    check_url_offline("https://www.petbarn.com.au/p/kong-classic-flyer-dog-toy-large")


def test_other_domain_fails_without_network():
    with pytest.raises(DomainNotAllowed):
        check_url_offline("https://www.amazon.com/dp/B000")


def test_search_and_bvstate_denied():
    with pytest.raises(PathNotAllowed):
        check_url_offline("https://www.petbarn.com.au/search?q=cat")
    with pytest.raises(PathNotAllowed):
        check_url_offline("https://www.petbarn.com.au/p/x?bvstate=pg:2")


def test_sitemap_host_matches_registry():
    url = configured_sitemap("petbarn")
    assert origin_allowed(url)
    assert url.startswith("https://www.petbarn.com.au/")


def test_sitemapindex_soft_check(tmp_path, monkeypatch):
    from pia.settings import get_settings, reset_settings

    monkeypatch.setenv("SITEMAP_CACHE_DIR", str(tmp_path))
    reset_settings()
    xml = (FIXTURES / "sitemapindex.xml").read_text(encoding="utf-8")
    assert parse_root_kind(xml) == "index"
    child = "https://www.petbarn.com.au/media/sitemap/au/sitemap-1-1.xml"
    assert is_product_child(child)
    assert not is_product_child("https://www.petbarn.com.au/media/sitemap/au/sitemap-advice.xml")
    present = "https://www.petbarn.com.au/p/kong-classic-flyer-dog-toy-large"
    missing = "https://www.petbarn.com.au/p/not-in-child"
    child_xml = (FIXTURES / "sitemap_child.xml").read_bytes()

    def fetch(url: str) -> bytes:
        assert origin_allowed(url)
        return child_xml

    found = collect_seed_presence(
        xml, [present, missing], fetch_bytes=fetch, settings=get_settings()
    )
    assert found[present] is True
    assert found[missing] is False
    from pia.ingestion.sitemap import collect_product_page_urls

    urls = collect_product_page_urls(xml, fetch_bytes=fetch, settings=get_settings(), limit=10)
    assert present in urls
    assert all("/p/" in item for item in urls)
    reset_settings()
