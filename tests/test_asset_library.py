"""Tests for resource pack and shader pack libraries."""

import tempfile
import unittest
import zipfile
from pathlib import Path

from services.asset_library import import_assets, scan_assets


class AssetLibraryTests(unittest.TestCase):
    """Checks that importing assets copies files and skips duplicate content."""

    def test_import_copies_and_deduplicates_zip(self) -> None:
        """Import keeps the original archive and skips a matching hash."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            source = root / "pack.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("pack.mcmeta", "{}")
            library = root / "library"
            imported, skipped, errors = import_assets([source], library, "resourcepacks")
            self.assertEqual((imported, skipped, errors), (1, 0, []))
            self.assertTrue(source.exists())
            imported, skipped, errors = import_assets([source], library, "resourcepacks")
            self.assertEqual((imported, skipped, errors), (0, 1, []))
            self.assertEqual(len(scan_assets(library, "resourcepacks")), 1)

    def test_categories_are_separate(self) -> None:
        """Resource packs and shaders have separate catalog folders."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            source = root / "pack.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("shader.txt", "shader")
            import_assets([source], root / "library", "shaderpacks")
            self.assertEqual(scan_assets(root / "library", "resourcepacks"), [])
            self.assertEqual(len(scan_assets(root / "library", "shaderpacks")), 1)
