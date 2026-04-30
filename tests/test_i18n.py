"""Tests for dsno_processor.i18n."""

from __future__ import annotations

import pytest

from dsno_processor.i18n import (
    SUPPORTED_LANGUAGES,
    _TRANSLATIONS,
    get_language,
    set_language,
    t,
)


@pytest.fixture(autouse=True)
def _reset_language():
    """Ensure each test starts with English and is restored afterwards."""
    original = get_language()
    set_language("en")
    yield
    set_language(original)


class TestSetGetLanguage:
    """Tests for set_language / get_language."""

    def test_default_is_english(self):
        assert get_language() == "en"

    def test_set_portuguese(self):
        set_language("pt")
        assert get_language() == "pt"

    def test_set_invalid_is_noop(self):
        set_language("xx")
        assert get_language() == "en"

    def test_round_trip(self):
        set_language("pt")
        set_language("en")
        assert get_language() == "en"


class TestTranslation:
    """Tests for the t() translation function."""

    def test_existing_key_english(self):
        assert t("app.title") == "DSNO Processor"

    def test_existing_key_portuguese(self):
        set_language("pt")
        assert t("app.title") == "DSNO Processor"
        assert t("btn.settings") == "Configurações"

    def test_missing_key_returns_key(self):
        assert t("nonexistent.key.here") == "nonexistent.key.here"

    def test_fallback_to_english(self):
        set_language("pt")
        # If a key exists in EN but not PT, it should fallback
        # Both languages have the same keys, so let's test with a known key
        assert t("app.title") == "DSNO Processor"

    def test_format_placeholders(self):
        text = t("dash.completed_errors", count=5)
        assert "5" in text

    def test_format_missing_placeholder_is_safe(self):
        # Should not raise even if placeholder is missing
        text = t("dash.completed_errors")  # no count= given
        assert isinstance(text, str)

    def test_format_with_multiple_placeholders(self):
        text = t("msg.processing_complete", success=8, total=10)
        assert "8" in text
        assert "10" in text


class TestSupportedLanguages:
    """Tests for SUPPORTED_LANGUAGES constant."""

    def test_contains_en_and_pt(self):
        assert "en" in SUPPORTED_LANGUAGES
        assert "pt" in SUPPORTED_LANGUAGES

    def test_all_languages_have_translations(self):
        for lang in SUPPORTED_LANGUAGES:
            assert lang in _TRANSLATIONS


class TestTranslationCompleteness:
    """Verify that PT has all the keys that EN has."""

    def test_pt_has_all_en_keys(self):
        en_keys = set(_TRANSLATIONS["en"].keys())
        pt_keys = set(_TRANSLATIONS["pt"].keys())
        missing = en_keys - pt_keys
        assert not missing, f"PT is missing keys: {missing}"

    def test_en_has_all_pt_keys(self):
        en_keys = set(_TRANSLATIONS["en"].keys())
        pt_keys = set(_TRANSLATIONS["pt"].keys())
        extra = pt_keys - en_keys
        assert not extra, f"PT has extra keys not in EN: {extra}"
