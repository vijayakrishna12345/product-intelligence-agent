from pia.services.ingest import build_ingest_targets
from pia.ui.followups import (
    already_asked,
    asked_for_charts,
    asked_for_sources,
    payload_has_charts,
    suggest_followups,
)


def test_build_ingest_targets_prefers_seeds():
    seeds = [{"sku": "A", "url": "https://www.petbarn.com.au/p/a", "name": "A"}]
    extra = [
        "https://www.petbarn.com.au/p/a",
        "https://www.petbarn.com.au/p/b",
        "https://www.petbarn.com.au/p/c",
    ]
    targets = build_ingest_targets(seeds, extra, limit=2)
    assert [item["url"] for item in targets] == [
        "https://www.petbarn.com.au/p/a",
        "https://www.petbarn.com.au/p/b",
    ]


def test_followups_from_details_payload():
    questions = suggest_followups(
        [{"product": "KONG Classic Flyer", "price": 35, "source_type": "petbarn_snapshot"}],
        catalog_names=["FURminator Short Hair Cat Deshedding Tool Small"],
    )
    assert questions
    assert any("KONG" in item for item in questions)


def test_followups_skip_already_asked():
    payload = [{"product": "KONG Classic Flyer", "price": 35, "source_type": "synthetic_sample"}]
    names = ["FURminator Short Hair Cat Deshedding Tool Small"]
    first = suggest_followups(payload, catalog_names=names)
    assert first
    again = suggest_followups(payload, catalog_names=names, asked=first)
    assert first[0] not in again
    assert already_asked(
        "What is the price and rating of KONG Classic Flyer?",
        ["what is the price and rating of kong classic flyer"],
    )


def test_asked_for_charts_and_sources():
    assert asked_for_charts("Show me the chart for ratings")
    assert not asked_for_charts("What is the price of GREENIES?")
    assert asked_for_sources("What are the sources for this?")
    assert not asked_for_sources("Is this a good resource for puppies?")
    assert payload_has_charts([{"price": 10, "rating_value": 4.5}])
    assert not payload_has_charts([{"error": "not_found"}])
