"""Tests for conflict detection in a selected mod set."""

import unittest

from services.mod_conflicts import check_mod_conflicts
from services.mod_metadata import ModMetadata


class ModConflictTests(unittest.TestCase):
    def test_duplicate_mod_ids_are_reported(self):
        first = ModMetadata(name="First", mod_id="same", version="1", minecraft_ranges=["1.20.1"], loader_ids=["fabric"], source="Fabric metadata")
        second = ModMetadata(name="Second", mod_id="SAME", version="2", minecraft_ranges=["1.20.1"], loader_ids=["fabric"], source="Fabric metadata")
        conflicts = check_mod_conflicts([("first.jar", first), ("second.jar", second)], "1.20.1", "fabric")
        self.assertTrue(any("Duplicate mod ID" in conflict.message for conflict in conflicts))

    def test_missing_dependency_is_reported(self):
        addon = ModMetadata(name="Addon", mod_id="addon", version="1", minecraft_ranges=["1.20.1"], loader_ids=["fabric"], dependencies=["core >=2"], required_mod_ids=["core"], source="Fabric metadata")
        conflicts = check_mod_conflicts([("addon.jar", addon)], "1.20.1", "fabric")
        self.assertTrue(any("core" in conflict.message for conflict in conflicts))

    def test_dependency_version_mismatch_is_reported(self):
        addon = ModMetadata(name="Addon", mod_id="addon", version="1", minecraft_ranges=["1.20.1"], loader_ids=["fabric"], dependencies=["core >=2"], required_mod_ids=["core"], source="Fabric metadata")
        core = ModMetadata(name="Core", mod_id="core", version="1.0", minecraft_ranges=["1.20.1"], loader_ids=["fabric"], source="Fabric metadata")
        conflicts = check_mod_conflicts([("addon.jar", addon), ("core.jar", core)], "1.20.1", "fabric")
        self.assertTrue(any("requires version" in conflict.message for conflict in conflicts))


if __name__ == "__main__":
    unittest.main()
