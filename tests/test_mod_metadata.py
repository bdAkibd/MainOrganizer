"""Тесты чтения метаданных модов и проверки совместимости."""

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from services.mod_metadata import compatibility_for_profile, minecraft_version_entries, read_mod_metadata, version_matches


class ModMetadataTests(unittest.TestCase):
    def test_reads_bukkit_plugin_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            jar = Path(directory) / "example-plugin.jar"
            with zipfile.ZipFile(jar, "w") as archive:
                archive.writestr("plugin.yml", "name: ExamplePlugin\nversion: 1.2.3\nmain: example.plugin.Main\napi-version: '1.20'\n")
            metadata = read_mod_metadata(jar)
            self.assertEqual(metadata.kind, "Плагин")
            self.assertEqual(metadata.name, "ExamplePlugin")
            self.assertEqual(metadata.version, "1.2.3")
            self.assertEqual(metadata.loader_ids, ["Bukkit/Spigot/Paper"])
            self.assertEqual(compatibility_for_profile(metadata, "1.20.1", "fabric")[0], "Плагин сервера")

    def test_reads_fabric_metadata_and_compatibility(self):
        with tempfile.TemporaryDirectory() as directory:
            jar = Path(directory) / "example.jar"
            with zipfile.ZipFile(jar, "w") as archive:
                archive.writestr("fabric.mod.json", json.dumps({
                    "id": "example", "name": "Example Mod", "version": "1.2.3",
                    "depends": {"minecraft": "1.20.1", "fabricloader": ">=0.14.0"},
                }))
            metadata = read_mod_metadata(jar)
            self.assertEqual(metadata.name, "Example Mod")
            self.assertEqual(metadata.mod_id, "example")
            self.assertEqual(metadata.version, "1.2.3")
            status, _ = compatibility_for_profile(metadata, "1.20.1", "fabric")
            self.assertEqual(status, "Вероятно совместим")
            status, _ = compatibility_for_profile(metadata, "1.19.4", "fabric")
            self.assertEqual(status, "Несовместим")

    def test_reads_quilt_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            jar = Path(directory) / "quilt.jar"
            data = {
                "quilt_loader": {
                    "id": "quilt_demo", "version": "1.0", "metadata": {"name": "Quilt Demo"},
                    "depends": [
                        {"id": "quilt_loader", "versions": ">=0.20"},
                        {"id": "minecraft", "versions": "1.20.1"},
                        {"id": "base_mod", "versions": "*"},
                    ],
                }
            }
            with zipfile.ZipFile(jar, "w") as archive:
                archive.writestr("quilt.mod.json", json.dumps(data))
            metadata = read_mod_metadata(jar)
            self.assertEqual(metadata.name, "Quilt Demo")
            self.assertEqual(metadata.mod_id, "quilt_demo")
            self.assertIn("1.20.1", metadata.minecraft_ranges)
            self.assertIn("base_mod", metadata.required_mod_ids)
            self.assertEqual(compatibility_for_profile(metadata, "1.20.1", "quilt", {"quilt_demo", "base_mod"})[0], "Вероятно совместим")

    def test_reads_forge_toml(self):
        with tempfile.TemporaryDirectory() as directory:
            jar = Path(directory) / "forge.jar"
            toml = '''modLoader="javafml"\nloaderVersion="[40,)"\n[[mods]]\nmodId="demo"\ndisplayName="Demo Mod"\nversion="2.0"\n[[dependencies.demo]]\nmodId="minecraft"\nmandatory=true\nversionRange="[1.18,1.19)"\nordering="NONE"\nside="BOTH"\n'''
            with zipfile.ZipFile(jar, "w") as archive:
                archive.writestr("META-INF/mods.toml", toml)
            metadata = read_mod_metadata(jar)
            self.assertEqual(metadata.name, "Demo Mod")
            self.assertEqual(metadata.mod_id, "demo")
            self.assertIn("[1.18,1.19)", metadata.minecraft_ranges)
            self.assertEqual(compatibility_for_profile(metadata, "1.18.2", "forge")[0], "Вероятно совместим")
            self.assertEqual(compatibility_for_profile(metadata, "1.19.2", "forge")[0], "Несовместим")

    def test_required_dependency_is_reported(self):
        from services.mod_metadata import ModMetadata
        metadata = ModMetadata(
            name="Addon", mod_id="addon", version="1.0", minecraft_ranges=["1.20.1"],
            loader_ids=["fabric"], required_mod_ids=["base_mod"], source="Fabric metadata",
        )
        status, reason = compatibility_for_profile(metadata, "1.20.1", "fabric", {"addon"})
        self.assertEqual(status, "Не хватает зависимостей")
        self.assertIn("base_mod", reason)
        self.assertEqual(compatibility_for_profile(metadata, "1.20.1", "fabric", {"addon", "base_mod"})[0], "Вероятно совместим")

    def test_version_ranges(self):
        self.assertEqual(minecraft_version_entries(["1.20, 1.21", "[1.18,1.19)"]), ["1.20", "1.21", "[1.18,1.19)"])
        self.assertTrue(version_matches("1.21", "1.20, 1.21"))
        self.assertTrue(version_matches("1.20.1", "[1.20,1.21)"))
        self.assertFalse(version_matches("1.21", "[1.20,1.21)"))
        self.assertTrue(version_matches("1.20.1", ">=1.20"))
        self.assertTrue(version_matches("1.20.1", "1.19 || 1.20.1"))

    def test_unknown_metadata_is_not_assumed_compatible(self):
        with tempfile.TemporaryDirectory() as directory:
            jar = Path(directory) / "empty.jar"
            with zipfile.ZipFile(jar, "w") as archive:
                archive.writestr("readme.txt", "not a mod")
            metadata = read_mod_metadata(jar)
            self.assertEqual(compatibility_for_profile(metadata, "1.20.1", "fabric")[0], "Неизвестно")


if __name__ == "__main__":
    unittest.main()
