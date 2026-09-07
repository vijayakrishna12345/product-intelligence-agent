from pathlib import Path

from pia.ingestion.reviews import parse_reviews_html, parse_reviews_jsonld

FIXTURE = Path(__file__).parent / "fixtures" / "reviews" / "reviews_page.html"


def test_parse_bv_fixture():
    html = FIXTURE.read_text(encoding="utf-8")
    reviews = parse_reviews_html(html, "FIX-001")
    assert len(reviews) == 2
    assert reviews[0].external_review_id
    assert "Cats loved it" in (reviews[0].body or "")


def test_parse_bv_jsonld_script():
    html = """
    <script type="application/ld+json" id="bv-jsonld-reviews-data">
    {"review":[{"headline":"Love it","reviewBody":"Amazing!!!",
      "reviewRating":{"ratingValue":5},"datePublished":"2026-08-09T02:53:00.000+00:00"}],
     "@id":"x","@context":"https://schema.org/"}
    </script>
    """
    reviews = parse_reviews_jsonld(html, "75550")
    assert len(reviews) == 1
    assert reviews[0].rating == 5
    assert "Amazing" in (reviews[0].body or "")

    html = """
    <script type="application/ld+json">
    {"@type":"Product","sku":"X","review":[
      {"@type":"Review","reviewBody":"Great flyer.","reviewRating":{"ratingValue":5},
       "datePublished":"2026-08-01","author":{"name":"Pat"}}
    ]}
    </script>
    """
    reviews = parse_reviews_jsonld(html, "75550")
    assert len(reviews) == 1
    assert reviews[0].rating == 5
    assert reviews[0].body == "Great flyer."
