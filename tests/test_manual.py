from services.manual import load_manual_html, manual_path


def test_manual_is_available_in_english():
    manual = load_manual_html()

    assert "MainOrginizer User Manual" in manual
    assert "Game environments" in manual
    assert "Resource packs and shaders" in manual
    assert "<html lang=\"en\">" in manual


def test_localized_manuals_are_available_for_supported_locales():
    for locale in ("ru", "de", "es", "fr", "uk", "it", "zh_CN", "zh_TW", "ja", "pt"):
        manual = load_manual_html(locale)
        assert manual_path(locale).is_file()
        assert "<html" in manual
        assert "<h1>" in manual


def test_russian_manual_is_selected_for_russian_locale():
    manual = load_manual_html("ru")

    assert manual_path("ru").name == "manual_ru.html"
    assert '<html lang="ru">' in manual


def test_missing_manual_locale_falls_back_to_english():
    assert load_manual_html("missing") == load_manual_html("en")
