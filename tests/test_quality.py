from pia.domain.models import ProductInput, ReviewInput
from pia.ingestion.quality import crawl_status, product_from_input, review_from_input


def test_drop_product_without_sku():
    assert (
        product_from_input(ProductInput(sku="", name="X", url="https://example.invalid/x")) is None
    )


def test_drop_review_without_body():
    assert review_from_input(ReviewInput(sku="A", rating=5, body="", title="")) is None


def test_accept_review_with_title_only():
    review = review_from_input(ReviewInput(sku="A", rating=4, title="OK"))
    assert review is not None
    assert review.external_review_id


def test_crawl_status_partial():
    assert crawl_status(6, 4) == "partial"
    assert crawl_status(10, 0) == "success"
    assert crawl_status(0, 3) == "failed"
