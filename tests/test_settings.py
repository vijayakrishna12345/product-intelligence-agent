from pia.settings import Settings, get_settings, reset_settings


def test_defaults_without_secrets(sample_settings):
    assert sample_settings.groq_model == "openai/gpt-oss-120b"
    assert sample_settings.recent_turns == 4
    assert sample_settings.max_reviews == 15
    assert sample_settings.chat_page_size == 50
    assert sample_settings.max_sitemap_children == 8
    assert sample_settings.ingest_max_products == 500
    assert sample_settings.ingest_target_reviews == 10
    assert sample_settings.sitemap_required is False
    assert sample_settings.include_reasoning is False
    assert sample_settings.groq_api_key == ""


def test_secret_key_fallback(monkeypatch):
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "legacy-key")
    reset_settings()
    settings = get_settings()
    assert settings.supabase_secret_key == "legacy-key"
    reset_settings()
    Settings()


def test_repr_redacted():
    assert "gsk" not in repr(Settings())
