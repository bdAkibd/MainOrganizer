"""Tests for safe profile virtualization and rollback."""

import errno
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from services.virtualization import apply_profile, preview_profile, rollback_last


class VirtualizationTests(unittest.TestCase):
    """Ensures applying profiles only changes managed symbolic links."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.library = self.root / "library"
        self.library.mkdir()
        self.instance = self.root / "instances" / "fabric-test"
        self.mods_dir = self.instance / ".minecraft" / "mods"
        self.mods_dir.mkdir(parents=True)
        self.backups = self.root / "rollback"
        self.mod_a = self.library / "alpha.jar"
        self.mod_b = self.library / "beta.jar"
        self.mod_a.write_bytes(b"alpha mod")
        self.mod_b.write_bytes(b"beta mod")
        self.profile = {
            "id": "profile-1",
            "name": "Test profile",
            "instance_path": str(self.instance),
            "enabled_mod_hashes": [self._hash(self.mod_a)],
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _hash(path: Path) -> str:
        import hashlib
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_preview_does_not_change_files(self) -> None:
        plan = preview_profile(self.profile, self.library)
        self.assertTrue(plan.can_apply)
        self.assertEqual([item.action for item in plan.actions], ["Create link"])
        self.assertFalse((self.mods_dir / "alpha.jar").exists())

    def test_apply_creates_symlink_and_rollback_removes_it(self) -> None:
        success, message = apply_profile(self.profile, self.library, self.backups)
        self.assertTrue(success, message)
        link = self.mods_dir / "alpha.jar"
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.resolve(), self.mod_a.resolve())
        success, message = rollback_last(self.backups, self.library)
        self.assertTrue(success, message)
        self.assertFalse(link.exists())
        self.assertFalse(link.is_symlink())

    def test_profile_switch_replaces_only_managed_link_and_can_rollback(self) -> None:
        first = self.mods_dir / "alpha.jar"
        first.symlink_to(self.mod_a)
        self.profile["enabled_mod_hashes"] = [self._hash(self.mod_b)]
        success, message = apply_profile(self.profile, self.library, self.backups)
        self.assertTrue(success, message)
        self.assertFalse(first.exists())
        second = self.mods_dir / "beta.jar"
        self.assertTrue(second.is_symlink())
        success, message = rollback_last(self.backups, self.library)
        self.assertTrue(success, message)
        self.assertTrue(first.is_symlink())
        self.assertFalse(second.exists())

    def test_external_file_is_preserved_and_name_conflict_blocks_apply(self) -> None:
        external = self.mods_dir / "alpha.jar"
        external.write_bytes(b"external content")
        plan = preview_profile(self.profile, self.library)
        self.assertFalse(plan.can_apply)
        self.assertTrue(plan.errors)
        success, _ = apply_profile(self.profile, self.library, self.backups)
        self.assertFalse(success)
        self.assertEqual(external.read_bytes(), b"external content")

    def test_missing_library_mod_blocks_apply(self) -> None:
        self.profile["enabled_mod_hashes"] = ["not-present"]
        plan = preview_profile(self.profile, self.library)
        self.assertFalse(plan.can_apply)
        self.assertTrue(any("missing" in error for error in plan.errors))


    def test_hardlink_fallback_when_symlink_privilege_is_missing(self) -> None:
        with patch("services.virtualization.os.symlink", side_effect=OSError(errno.EPERM, "privilege missing")):
            success, message = apply_profile(self.profile, self.library, self.backups)
        self.assertTrue(success, message)
        installed = self.mods_dir / "alpha.jar"
        self.assertTrue(installed.exists())
        self.assertTrue(__import__("os").path.samefile(installed, self.mod_a))
        success, message = rollback_last(self.backups, self.library)
        self.assertTrue(success, message)
        self.assertFalse(installed.exists())

    def test_root_minecraft_profile_targets_matching_isolated_version(self) -> None:
        from services.virtualization import find_mods_dir

        minecraft = self.root / ".minecraft"
        first = minecraft / "versions" / "fabric-loader-0.16.5-1.21.1" / "mods"
        second = minecraft / "versions" / "forge-52.0-1.21.1" / "mods"
        first.mkdir(parents=True)
        second.mkdir(parents=True)
        selected = find_mods_dir(minecraft, {"minecraft_version": "1.21.1", "loader": "Fabric"})
        self.assertEqual(selected, first)
        self.assertIsNone(find_mods_dir(minecraft, {"minecraft_version": "1.21.1", "loader": "Quilt"}))


    def test_hardlink_profile_switch_and_rollback(self) -> None:
        import os
        first = self.mods_dir / "alpha.jar"
        os.link(self.mod_a, first)
        self.profile["enabled_mod_hashes"] = [self._hash(self.mod_b)]
        success, message = apply_profile(self.profile, self.library, self.backups)
        self.assertTrue(success, message)
        self.assertFalse(first.exists())
        second = self.mods_dir / "beta.jar"
        self.assertTrue(os.path.samefile(second, self.mod_b))
        success, message = rollback_last(self.backups, self.library)
        self.assertTrue(success, message)
        self.assertTrue(os.path.samefile(first, self.mod_a))
        self.assertFalse(second.exists())


if __name__ == "__main__":
    unittest.main()
