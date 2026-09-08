"""Shared species/kind/category inference from stored metadata and text fallback."""

from __future__ import annotations

from urllib.parse import unquote, urlparse

SPECIES_ALIASES: dict[str, tuple[str, ...]] = {
    "dog": ("dog", "puppy", "puppies", "canine"),
    "cat": ("cat", "kitten", "kittens", "feline"),
    "fish": ("fish", "cichlid", "aquarium", "aquatic"),
    "bird": ("bird", "avian", "parrot", "budgie"),
    "reptile": ("reptile", "turtle", "lizard", "snake", "herp"),
}

_KIND_FOOD = ("food", "kibble", "pouch", "stew", "diet", "nutrition", "feed")
_KIND_TREAT = ("treat", "biscuit", "chew", "snack", "dental")
_KIND_TOY = ("toy", "flyer", "digger", "puzzle", "ball", "play")
_KIND_GROOMING = ("deshedd", "groom", "brush", "conditioner", "shampoo", "comb")

_HOME_CRUMBS = {"home", "petbarn", "shop", "catalog"}


def _blob(*parts: str | None) -> str:
    return " ".join(part.strip() for part in parts if part and part.strip()).lower()


def species_from_text(
    name: str | None = None,
    *,
    category: str | None = None,
    url: str | None = None,
    description: str | None = None,
) -> str:
    """Return dog|cat|fish|bird|reptile|other from stored category first, then text."""
    text = _blob(category, name, description, _url_slug(url))
    if not text:
        return "other"
    if any(token in text for token in SPECIES_ALIASES["dog"]):
        return "dog"
    if any(token in text for token in SPECIES_ALIASES["cat"]):
        return "cat"
    if any(token in text for token in SPECIES_ALIASES["fish"]):
        return "fish"
    if any(token in text for token in SPECIES_ALIASES["bird"]):
        return "bird"
    if any(token in text for token in SPECIES_ALIASES["reptile"]):
        return "reptile"
    return "other"


def kind_from_text(name: str | None = None, *, category: str | None = None) -> str:
    """Return food|treat|toy|grooming|other from stored category first, then name."""
    text = _blob(category, name)
    if not text:
        return "other"
    if any(token in text for token in _KIND_TREAT):
        return "treat"
    if any(token in text for token in _KIND_TOY):
        return "toy"
    if any(token in text for token in _KIND_GROOMING):
        return "grooming"
    if any(token in text for token in _KIND_FOOD):
        return "food"
    return "other"


def species_matches(
    species: str | None,
    *,
    name: str | None = None,
    category: str | None = None,
    url: str | None = None,
    description: str | None = None,
) -> bool:
    if not species:
        return True
    needle = species.lower().strip()
    if species_from_text(name, category=category, url=url, description=description) == needle:
        return True
    text = _blob(category, name, description, _url_slug(url))
    keys = SPECIES_ALIASES.get(needle, (needle,))
    return any(token in text for token in keys)


def normalize_category(
    raw: str | None,
    *,
    name: str | None = None,
    url: str | None = None,
    description: str | None = None,
) -> str | None:
    """Prefer page metadata; fall back to keyword-derived short label."""
    cleaned = _clean_category(raw)
    if cleaned:
        return cleaned
    species = species_from_text(name, url=url, description=description)
    kind = kind_from_text(name)
    if species == "other" and kind == "other":
        return None
    species_label = {
        "dog": "Dog",
        "cat": "Cat",
        "fish": "Fish",
        "bird": "Bird",
        "reptile": "Reptile",
    }.get(species)
    kind_label = {
        "food": "food",
        "treat": "treats",
        "toy": "toys",
        "grooming": "grooming",
    }.get(kind)
    if species_label and kind_label:
        return f"{species_label} {kind_label}"
    if species_label:
        return species_label
    if kind_label:
        return kind_label.title()
    return None


def breadcrumb_category(node: dict) -> str | None:
    """Extract a category string from a BreadcrumbList JSON-LD node."""
    elements = node.get("itemListElement") or []
    if isinstance(elements, dict):
        elements = [elements]
    crumbs: list[str] = []
    for item in elements:
        if not isinstance(item, dict):
            continue
        name = _breadcrumb_name(item.get("name"))
        if not name:
            item_ref = item.get("item")
            if isinstance(item_ref, dict):
                name = _breadcrumb_name(item_ref.get("name"))
            elif isinstance(item_ref, str):
                name = _url_slug(item_ref).replace("-", " ").title()
        if name and name.lower() not in _HOME_CRUMBS:
            crumbs.append(name.strip())
    if not crumbs:
        return None
    if len(crumbs) >= 2:
        return f"{crumbs[-2]} > {crumbs[-1]}"
    return crumbs[-1]


def _breadcrumb_name(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return _breadcrumb_name(value.get("name") or value.get("@value") or value.get("value"))
    if isinstance(value, list):
        for item in value:
            text = _breadcrumb_name(item)
            if text:
                return text
        return None
    text = str(value).strip()
    return text or None


def _clean_category(raw: str | None) -> str | None:
    if not raw:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if ">" in text:
        parts = [part.strip() for part in text.split(">") if part.strip()]
        parts = [part for part in parts if part.lower() not in _HOME_CRUMBS]
        if len(parts) >= 2:
            return f"{parts[-2]} > {parts[-1]}"
        if parts:
            return parts[-1]
    if text.lower() in _HOME_CRUMBS:
        return None
    return text


def _url_slug(url: str | None) -> str:
    if not url:
        return ""
    path = urlparse(url).path.strip("/")
    if not path:
        return ""
    slug = path.split("/")[-1]
    return unquote(slug.replace("-", " "))
