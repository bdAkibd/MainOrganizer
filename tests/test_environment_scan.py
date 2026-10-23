"""Tests for read-only scans of instance mod directories."""

import tempfile
import unittest
from pathlib import Path

from models.instance import PrismInstance
from services.environment_scan import scan_environment_mods
from services.mod_library import import_mods


class EnvironmentScanTests(unittest.TestCase):
    """Checks detection of external files without modifying game folders."""

    def _instance(self, root: Path) -> PrismInstance:
        return PrismInstance(
            name="Test instance", instance_id="test", path=root,
            minecraft_version="1.20.1", loader="Fabric", loader_version="0.15.0",
            status="Ready",
        )

    def test_external_mod_is_reported_without_importing_it(self) -> None:
        """A JAR absent from the library is reported and left in place."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            mods_dir = root / ".minecraft" / "mods"
            mods_dir.mkdir(parents=True)
            external = mods_dir / "external.jar"
            external.write_bytes(b"external mod")
            library = root / "library"

            findings = scan_environment_mods([self._instance(root)], library)

            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].status, "External mod — not imported")
            self.assertTrue(external.is_file())
            self.assertFalse(library.exists())

    def test_matching_library_content_is_recognized(self) -> None:
        """A regular instance JAR with known content is identified as a library copy."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            mods_dir = root / "minecraft" / "mods"
            mods_dir.mkdir(parents=True)
            jar = root / "known.jar"
            jar.write_bytes(b"known mod")
            library = root / "library"
            import_mods([jar], library)
            instance_jar = mods_dir / jar.name
            instance_jar.write_bytes(jar.read_bytes())

            findings = scan_environment_mods([self._instance(root)], library)

            self.assertEqual(findings[0].status, "Copy of library file")
            self.assertEqual(instance_jar.read_bytes(), b"known mod")

    def test_missing_mods_folder_is_reported(self) -> None:
        """An instance without a mods directory gets a clear status row."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            findings = scan_environment_mods([self._instance(root)], root / "library")
            self.assertEqual(findings[0].status, "mods folder not found")


if __name__ == "__main__":
    unittest.main()
