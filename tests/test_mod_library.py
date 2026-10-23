"""Tests for safe mod library import."""

import tempfile
import unittest
from pathlib import Path

from services.mod_library import import_mods, scan_mods


class ModLibraryTests(unittest.TestCase):
    """Verify scanning and importing without moving originals."""

    def test_import_copies_file_and_keeps_source(self) -> None:
        """Import copies a file into the library and preserves the original."""
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
        """Identical content is not imported again under another name."""
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
        """A file with the same name but different content gets a new name."""
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
