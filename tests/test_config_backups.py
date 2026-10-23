"""Tests for instance config backup and restore."""

import tempfile
import unittest
import zipfile
from pathlib import Path

from services.config_backups import create_config_backup, restore_config_backup


class ConfigBackupTests(unittest.TestCase):
    """Checks backup restore and archive path validation."""

    def test_backup_and_restore(self) -> None:
        """Restoring replaces matching files but preserves files absent from archive."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            instance = root / "instance"
            config = instance / ".minecraft" / "config"
            config.mkdir(parents=True)
            (config / "settings.txt").write_text("before", encoding="utf-8")
            backup_root = root / "backups"
            success, _ = create_config_backup(instance, backup_root)
            self.assertTrue(success)
            backup = next(backup_root.glob("*.zip"))
            (config / "settings.txt").write_text("after", encoding="utf-8")
            (config / "new.txt").write_text("keep", encoding="utf-8")
            success, message = restore_config_backup(backup, instance, backup_root)
            self.assertTrue(success, message)
            self.assertEqual((config / "settings.txt").read_text(encoding="utf-8"), "before")
            self.assertEqual((config / "new.txt").read_text(encoding="utf-8"), "keep")

    def test_rejects_path_traversal(self) -> None:
        """Archive entries cannot write outside the config directory."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            archive_path = root / "unsafe.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("../outside.txt", "unsafe")
            instance = root / "instance"
            instance.mkdir()
            success, message = restore_config_backup(archive_path, instance)
            self.assertFalse(success)
            self.assertIn("Unsafe path", message)
            self.assertFalse((root / "outside.txt").exists())
