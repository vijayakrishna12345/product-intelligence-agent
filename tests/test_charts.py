from pia.ui.charts import sources_caption


def test_sources_caption_synthetic_without_top_level_type():
    caption = sources_caption(
        [{"ok": True, "products": [{"source_type": "synthetic_sample", "sku": "SYN-X"}]}]
    )
    assert "Synthetic sample data" in caption
    assert "Petbarn snapshot" not in caption


def test_sources_caption_petbarn_snapshot():
    caption = sources_caption(
        [
            {
                "source_type": "petbarn_snapshot",
                "sku": "ABC",
                "scraped_at": "2026-09-07",
                "review_count": 4,
                "examples_count": 2,
            }
        ]
    )
    assert "Petbarn snapshot" in caption
    assert "SKU: ABC" in caption


def test_sources_caption_filters_to_answer_products():
    caption = sources_caption(
        [
            {
                "match_count": 8,
                "matches": [
                    {"name": "Hikari Cichlid Gold", "sku": "99936", "source_type": "petbarn_snapshot"},
                    {"name": "Advance Indoor Cat Food", "sku": "140242", "source_type": "petbarn_snapshot"},
                    {"name": "Royal Canin Dog Food", "sku": "138211", "source_type": "petbarn_snapshot"},
                ],
            }
        ],
        assistant_text="Advance Indoor Cat Food leads the list at 4.8 stars.",
        catalog_scraped_at="2026-09-07",
    )
    assert "Advance Indoor Cat Food" in caption
    assert "Hikari" not in caption
    assert "Catalog snapshot: 2026-09-07" in caption


def test_sources_caption_compare_lists_skus():
    caption = sources_caption(
        [
            {
                "ok": True,
                "products": [
                    {
                        "name": "Advance Indoor",
                        "sku": "140242",
                        "source_type": "petbarn_snapshot",
                        "scraped_at": "2026-09-07",
                    },
                    {
                        "name": "FURminator",
                        "sku": "75550",
                        "source_type": "petbarn_snapshot",
                    },
                ],
            }
        ]
    )
    assert "Petbarn snapshot" in caption
    assert "SKU: 140242, 75550" in caption
    assert "Products: Advance Indoor, FURminator" in caption
