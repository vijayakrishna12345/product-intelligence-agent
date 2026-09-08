from pia.analysis.taxonomy import (
    breadcrumb_category,
    kind_from_text,
    normalize_category,
    species_from_text,
    species_matches,
)


def test_species_from_stored_category():
    assert species_from_text("Savory Stew with Chicken", category="Dog food") == "dog"
    assert species_from_text("Savory Stew with Chicken", category=None) == "other"


def test_kind_from_stored_category():
    assert kind_from_text("Classic Flyer", category="Dog toys") == "toy"
    assert kind_from_text("Indoor Chicken Turkey Pouches", category="Cat food") == "food"


def test_normalize_category_prefers_page_metadata():
    assert normalize_category("Cat/Food", name="Indoor Pouches") == "Cat/Food"
    assert (
        normalize_category(None, name="Indoor Pouches", url="https://www.petbarn.com.au/p/cat-food")
        == "Cat food"
    )


def test_breadcrumb_category():
    node = {
        "itemListElement": [
            {"name": "Home"},
            {"name": "Cat"},
            {"name": "Food"},
            {"name": "Dry Food"},
        ]
    }
    assert breadcrumb_category(node) == "Food > Dry Food"


def test_species_matches_uses_category():
    assert species_matches(
        "dog",
        name="Adult Savory Stew with Chicken Vegetables",
        category="Dog food",
    )
    assert not species_matches(
        "cat",
        name="Adult Savory Stew with Chicken Vegetables",
        category="Dog food",
    )
