"""Tests for the localization layer."""

import unittest

from services.localization import SUPPORTED_LOCALES, locale_name, translate, translate_many


class LocalizationTests(unittest.TestCase):
    def test_english_translation_and_russian_source(self) -> None:
        self.assertEqual(translate("Settings", "en"), "Settings")
        self.assertEqual(translate("Settings", "ru"), "Настройки")
        self.assertEqual(
            translate("Environment check completed: 3 records, external mods not imported: 1", "en"),
            "Environment check completed: 3 records, external mods not imported: 1",
        )
        self.assertEqual(translate("Source", "en"), "Source")
        self.assertEqual(translate("The config folder was not found in the instance.", "en"), "The config folder was not found in the instance.")
        self.assertEqual(translate("Resource packs", "en"), "Resource packs")
        self.assertEqual(translate("Copy of library file", "en"), "Copy of library file")
        self.assertEqual(
            translate("Create a profile to manage resource packs and shaders.", "en"),
            "Create a profile to manage resource packs and shaders.",
        )
        self.assertEqual(
            translate('Profile "Test" created. Game files were not changed.', "en"),
            'Profile "Test" created. Game files were not changed.',
        )

    def test_translate_many_preserves_order(self) -> None:
        self.assertEqual(
            translate_many(["Source", "Size", "Path"], "en"),
            ["Source", "Size", "Path"],
        )

    def test_switching_from_english_to_additional_locale(self) -> None:
        self.assertEqual(translate("Ready", "de"), "Fertig")
        self.assertEqual(translate("Fertig", "en"), "Ready")
        self.assertEqual(translate("Ready", "ru"), "Готово")

    def test_table_header_translation_does_not_repeat_source_text(self) -> None:
        for locale in SUPPORTED_LOCALES:
            self.assertNotIn("NameName", translate("Name", locale))
            self.assertNotIn("Name", translate("Name", locale)[len("Name"):])

    def test_supported_locales_are_stable(self) -> None:
        self.assertIn("en", SUPPORTED_LOCALES)
        self.assertIn("ru", SUPPORTED_LOCALES)
        self.assertEqual(len(SUPPORTED_LOCALES), len(set(SUPPORTED_LOCALES)))
        self.assertTrue(all(locale_name(locale) for locale in SUPPORTED_LOCALES))
