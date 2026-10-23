"""Tests for application settings persistence."""

import json
import tempfile
import unittest
from pathlib import Path

from services.app_config import AppConfig


class AppConfigTests(unittest.TestCase):
    def test_new_config_defaults_to_english(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(AppConfig(Path(directory) / "config.json").locale, "en")

    def test_theme_and_locale_survive_reload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            config = AppConfig(path)
            config.set_theme("dark")
            config.set_locale("en")

            loaded = AppConfig(path)
            self.assertEqual(loaded.theme, "dark")
            self.assertEqual(loaded.locale, "en")
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["version"], 1)

    def test_invalid_theme_falls_back_to_light(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"theme": "unknown"}), encoding="utf-8")
            self.assertEqual(AppConfig(path).theme, "light")
