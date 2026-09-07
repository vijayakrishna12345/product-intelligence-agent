import json

from pia.agent.tools import build_tools
from pia.settings import reset_settings


def _invoke(tools, name, payload):
    tool = next(item for item in tools if item.name == name)
    return json.loads(tool.invoke(payload))


def test_four_tools_and_source_type(catalog_service, comparison_service, sample_settings):
    tools = build_tools(catalog_service, comparison_service, sample_settings)
    assert [item.name for item in tools] == [
        "search_catalog",
        "get_product_details",
        "get_product_reviews",
        "compare_products",
    ]
    details = _invoke(tools, "get_product_details", {"product_query": "KONG Classic Flyer"})
    assert details["source_type"] == "synthetic_sample"
    assert details["sku"] == "SYN-KONG-FLYER"


def test_reviews_newest_and_aggregates(catalog_service, comparison_service, sample_settings):
    tools = build_tools(catalog_service, comparison_service, sample_settings)
    payload = _invoke(
        tools,
        "get_product_reviews",
        {"product_query": "Advance Indoor", "limit": 2},
    )
    assert payload["examples_count"] == 2
    assert payload["review_count"] >= 2
    assert "positive" in payload["sentiment"]
    assert "author" not in json.dumps(payload)


def test_compare_table(catalog_service, comparison_service, sample_settings):
    tools = build_tools(catalog_service, comparison_service, sample_settings)
    payload = _invoke(
        tools,
        "compare_products",
        {"product_queries": ["KONG Classic Flyer", "Catit 2.0 Senses Digger"]},
    )
    assert payload["ok"] is True
    assert len(payload["products"]) == 2
    assert payload["source_type"] == "synthetic_sample"
    reset_settings()
