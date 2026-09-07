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
