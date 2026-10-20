"""Тесты безопасного импорта библиотеки модов."""

import tempfile
import unittest
from pathlib import Path

from services.mod_library import import_mods, scan_mods


class ModLibraryTests(unittest.TestCase):
    """Проверяет сканирование и импорт без перемещения оригиналов."""

    def test_import_copies_file_and_keeps_source(self) -> None:
        """Импорт копирует файл в библиотеку, сохраняя исходный файл."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            source = root / "external.jar"
            library = root / "library"
            source.write_bytes(b"test mod contents")

            imported, skipped, errors = import_mods([source], library)

            self.assertEqual((imported, skipped, errors), (1, 0, []))
            self.assertTrue(source.is_file())
            self.assertEqual([mod.name for mod in scan_mods(library)], ["external.jar"])

    def test_duplicate_content_is_skipped(self) -> None:
        """Одинаковое содержимое не импортируется повторно под другим именем."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            first = root / "first.jar"
            second = root / "second.jar"
            library = root / "library"
            first.write_bytes(b"same content")
            second.write_bytes(b"same content")

            imported, skipped, errors = import_mods([first, second], library)

            self.assertEqual((imported, skipped, errors), (1, 1, []))
            self.assertEqual(len(scan_mods(library)), 1)

    def test_different_content_with_same_name_is_renamed(self) -> None:
        """Файл с тем же именем, но другим содержимым получает новое имя."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            source_a = root / "mod.jar"
            source_b = root / "other" / "mod.jar"
            source_b.parent.mkdir()
            library = root / "library"
            source_a.write_bytes(b"one")
            source_b.write_bytes(b"two")

            imported, skipped, errors = import_mods([source_a, source_b], library)

            self.assertEqual((imported, skipped, errors), (2, 0, []))
            self.assertEqual({mod.name for mod in scan_mods(library)}, {"mod.jar", "mod (2).jar"})
