"""Tests for safe resource pack and shader pack profile application."""

import tempfile
import unittest
import zipfile
from pathlib import Path

from services.asset_library import import_assets
from services.asset_virtualization import apply_assets, preview_assets, rollback_assets


class AssetVirtualizationTests(unittest.TestCase):
    """Ensures previews are read-only and only managed links are changed."""

    def test_apply_and_rollback_asset_link(self) -> None:
        """Applying creates a symlink and rollback removes only that link."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            library = root / "library"
            source = root / "pack.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("pack.mcmeta", "{}")
            import_assets([source], library, "resourcepacks")
            asset = next(iter((library / "resourcepacks").iterdir()))
            instance = root / "instance"
            (instance / ".minecraft").mkdir(parents=True)
            from services.mod_library import file_sha256
            profile = {"name": "test", "instance_path": str(instance), "enabled_resourcepack_hashes": [file_sha256(asset)]}
            plan = preview_assets(profile, library, "resourcepacks")
            self.assertTrue(plan.can_apply)
            self.assertFalse((instance / ".minecraft" / "resourcepacks").exists())
            backup = root / "rollback"
            success, _ = apply_assets(profile, library, "resourcepacks", backup)
            self.assertTrue(success)
            link = instance / ".minecraft" / "resourcepacks" / asset.name
            self.assertTrue(link.is_symlink())
            success, _ = rollback_assets(backup, library)
            self.assertTrue(success)
            self.assertFalse(link.exists())

    def test_conflict_blocks_application(self) -> None:
        """An ordinary file with a selected asset name is never overwritten."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            library = root / "library"
            source = root / "pack.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("shader.txt", "shader")
            import_assets([source], library, "shaderpacks")
            asset = next(iter((library / "shaderpacks").iterdir()))
            instance = root / "instance"
            target = instance / "shaderpacks"
            target.mkdir(parents=True)
            conflict = target / asset.name
            conflict.write_bytes(b"user file")
            from services.mod_library import file_sha256
            profile = {"name": "test", "instance_path": str(instance), "enabled_shaderpack_hashes": [file_sha256(asset)]}
            plan = preview_assets(profile, library, "shaderpacks")
            self.assertFalse(plan.can_apply)
            self.assertTrue(plan.errors)
            self.assertEqual(conflict.read_bytes(), b"user file")
