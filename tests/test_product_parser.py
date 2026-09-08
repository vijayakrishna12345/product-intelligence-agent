from __future__ import annotations

from pathlib import Path

from pia.ingestion.product_parser import parse_product_html

FIXTURE = Path(__file__).parent / "fixtures" / "product" / "product_group.html"


def test_jsonld_to_product():
    html = FIXTURE.read_bytes()
    product = parse_product_html(html, "https://www.petbarn.com.au/p/fixture-indoor-cat-food-3kg")
    assert product.sku == "FIX-001"
    assert product.name == "Fixture Indoor Cat Food 3kg"
    assert product.price == 19.95
    assert product.currency == "AUD"
    assert product.category == "Food > Dry Food"


def test_category_from_breadcrumb_when_jsonld_category_missing():
    html = b"""<!DOCTYPE html><html><head>
    <script type="application/ld+json">
    {"@type":"BreadcrumbList","itemListElement":[
      {"@type":"ListItem","position":1,"name":"Home"},
      {"@type":"ListItem","position":2,"name":"Dog"},
      {"@type":"ListItem","position":3,"name":"Food"},
      {"@type":"ListItem","position":4,"name":"Dry Food"}
    ]}
    </script>
    <script type="application/ld+json">
    {"@type":"Product","name":"Fixture Dog Kibble 2kg","sku":"DOG-1",
     "offers":{"price":"12.00","priceCurrency":"AUD"}}
    </script>
    </head></html>"""
    product = parse_product_html(html, "https://www.petbarn.com.au/p/dog-kibble-2kg")
    assert product.category == "Food > Dry Food"


def test_missing_sku_rejected():
    html = b'<script type="application/ld+json">{"@type":"Product","name":"X"}</script>'
    try:
        parse_product_html(html, "https://www.petbarn.com.au/p/x")
    except Exception as exc:
        assert "sku" in str(exc).lower() or "json-ld" in str(exc).lower()
    else:
        raise AssertionError("expected parse failure")
