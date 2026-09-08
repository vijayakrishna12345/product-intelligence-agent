from pia.services.ingest import build_ingest_targets
from pia.ui.followups import (
    already_asked,
    asked_for_charts,
    asked_for_sources,
    infer_category,
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


def test_followups_stay_in_category():
    questions = suggest_followups(
        [
            {
                "product": "Advance Indoor Chicken Turkey Adult Cat Pouches 85gx12",
                "price": 22.99,
            }
        ],
        catalog_names=[
            "KONG Classic Flyer Dog Toy Large",
            "Royal Canin Dermacomfort Mini Adult Dog Food 3kg",
            "Dine Daily Adult Cat Food Chicken 85g",
            "Catit 2.0 Senses Digger Cat Bowl",
        ],
    )
    blob = " ".join(questions).lower()
    assert questions
    assert "kong" not in blob
    assert "flyer" not in blob
    assert "dermacomfort" not in blob
    if "compare" in blob:
        assert "dine" in blob or "cat food" in blob


def test_followups_from_ambiguous_candidates():
    questions = suggest_followups(
        [
            {
                "ok": False,
                "error": "ambiguous",
                "candidates": [
                    {
                        "name": "Hikari Cichlid Gold Sinking Medium",
                        "sku": "99936",
                        "brand": "Hikari",
                        "price": 18.99,
                        "rating_value": 4.5,
                    },
                    {
                        "name": "Hikari Cichlid Gold Sinking Mini",
                        "sku": "99934",
                        "brand": "Hikari",
                        "price": 18.99,
                        "rating_value": 4.4,
                    },
                ],
            }
        ]
    )
    assert any("Hikari Cichlid Gold Sinking Medium" in item for item in questions)
    assert any("Hikari Cichlid Gold Sinking Mini" in item for item in questions)
    assert all(item.startswith("Tell me about ") for item in questions)


def test_infer_category_from_name():
    assert infer_category("Advance Indoor Chicken Turkey Adult Cat Pouches") == "cat"
    assert infer_category("KONG Classic Flyer Dog Toy Large") == "dog"
    assert infer_category("Hikari Cichlid Gold Sinking Medium") == "fish"


def test_infer_category_prefers_stored_metadata():
    assert infer_category("Savory Stew with Chicken", category="Dog food") == "dog"
    assert infer_category("Savory Stew with Chicken", category=None) == "other"


def test_followups_use_stored_category_for_comparisons():
    questions = suggest_followups(
        [
            {
                "product": "Hill's Science Diet Adult Savory Stew with Chicken Vegetables",
                "category": "Dog food",
            }
        ],
        catalog_products=[
            {"name": "Royal Canin Dermacomfort Mini Adult Dog Food 3kg", "category": "Dog food"},
            {"name": "Advance Indoor Chicken Turkey Adult Cat Pouches", "category": "Cat food"},
            {"name": "KONG Classic Flyer Dog Toy Large", "category": "Dog toys"},
        ],
    )
    blob = " ".join(questions).lower()
    assert questions
    assert "cat" not in blob or "compare" not in blob
    if "compare" in blob:
        assert "royal canin" in blob or "dermacomfort" in blob
        assert "kong" not in blob


def test_asked_for_charts_and_sources():
    assert asked_for_charts("Show me the chart for ratings")
    assert not asked_for_charts("What is the price of GREENIES?")
    assert asked_for_sources("What are the sources for this?")
    assert not asked_for_sources("Is this a good resource for puppies?")
    assert payload_has_charts([{"price": 10, "rating_value": 4.5}])
    assert not payload_has_charts([{"error": "not_found"}])
