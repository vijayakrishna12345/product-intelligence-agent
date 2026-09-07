from pia.domain.models import Review, ReviewInput
from pia.ingestion.quality import review_from_input
from pia.repositories.crawl import CrawlRepository


def test_unique_review_id_and_idempotent_upsert():
    repo = CrawlRepository()
    run_id = repo.start_run()
    first = review_from_input(ReviewInput(sku="FIX-001", rating=5, body="Loved it", title="Great"))
    second = review_from_input(ReviewInput(sku="FIX-001", rating=5, body="Loved it", title="Great"))
    assert first is not None and second is not None
    assert first.external_review_id == second.external_review_id
    repo.upsert_reviews("FIX-001", [first], run_id)
    repo.upsert_reviews("FIX-001", [second], run_id)
    assert len(repo.reviews["FIX-001"]) == 1
    other = Review(
        sku="FIX-001",
        external_review_id="other",
        rating=4,
        body="Different",
    )
    repo.upsert_reviews("FIX-001", [other], run_id)
    assert len(repo.reviews["FIX-001"]) == 2
    assert repo.stored_review_count("FIX-001") == 2
