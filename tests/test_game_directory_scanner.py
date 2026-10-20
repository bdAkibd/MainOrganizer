"""Тесты адаптера игровых папок TLauncher и Legacy Launcher."""

import json
import tempfile
import unittest
from pathlib import Path

from launchers.game_directory.scanner import is_game_directory, scan_game_directory


class GameDirectoryScannerTests(unittest.TestCase):
    """Проверяет распознавание версий из JSON обычного каталога игры."""

    def test_detects_fabric_from_version_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            version_dir = root / "versions" / "fabric-loader-0.16.5-1.21.1"
            version_dir.mkdir(parents=True)
            (root / "mods").mkdir()
            (version_dir / "fabric-loader-0.16.5-1.21.1.json").write_text(
                json.dumps({
                    "id": "fabric-loader-0.16.5-1.21.1",
                    "inheritsFrom": "1.21.1",
                    "libraries": [{"name": "net.fabricmc:fabric-loader:0.16.5"}],
                }),
                encoding="utf-8",
            )
            self.assertTrue(is_game_directory(root))
            instance = scan_game_directory(root, "Legacy Launcher")
            self.assertEqual(instance.minecraft_version, "1.21.1")
            self.assertEqual(instance.loader, "Fabric")
            self.assertEqual(instance.loader_version, "0.16.5")
            self.assertEqual(instance.launcher, "Legacy Launcher")

    def test_recognizes_version_specific_subfolder(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "home" / "Forge-1.20.1"
            (root / "mods").mkdir(parents=True)
            instance = scan_game_directory(root, "TLauncher / Legacy Launcher")
            self.assertEqual(instance.minecraft_version, "1.20.1")
            self.assertEqual(instance.loader, "Forge")


class LegacyEnvironmentDiscoveryTests(unittest.TestCase):
    """Проверяет обнаружение отдельных окружений Legacy Launcher."""

    def test_discovers_home_environments_separately(self) -> None:
        from launchers.game_directory.scanner import discover_game_environments

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "game"
            first = root / "home" / "Fabric 1.21.1"
            second = root / "home" / "Forge 1.20.1"
            (first / "mods").mkdir(parents=True)
            (second / "mods").mkdir(parents=True)
            found = discover_game_environments(root, "Legacy Launcher")
            self.assertEqual({item.path for item in found}, {first, second})
            self.assertEqual({item.minecraft_version for item in found}, {"1.21.1", "1.20.1"})

    def test_discovers_version_folders_only_when_isolated_mods_folder_exists(self) -> None:
        from launchers.game_directory.scanner import discover_game_environments

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "game"
            normal = root / "versions" / "1.20.1"
            isolated = root / "versions" / "fabric-loader-0.16.5-1.21.1"
            normal.mkdir(parents=True)
            (normal / "1.20.1.json").write_text(json.dumps({"id": "1.20.1"}), encoding="utf-8")
            (isolated / "mods").mkdir(parents=True)
            (isolated / "fabric-loader-0.16.5-1.21.1.json").write_text(
                json.dumps({"id": "fabric-loader-0.16.5-1.21.1", "inheritsFrom": "1.21.1",
                            "libraries": [{"name": "net.fabricmc:fabric-loader:0.16.5"}]}),
                encoding="utf-8",
            )
            found = discover_game_environments(root, "Legacy Launcher")
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0].path, isolated)
            self.assertEqual(found[0].minecraft_version, "1.21.1")
            self.assertEqual(found[0].loader, "Fabric")


    def test_discovers_tlauncher_isolated_versions(self) -> None:
        from launchers.game_directory.scanner import discover_game_environments

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / ".minecraft"
            vanilla = root / "versions" / "1.20.1"
            isolated = root / "versions" / "fabric-loader-0.16.5-1.21.1"
            vanilla.mkdir(parents=True)
            (vanilla / "1.20.1.json").write_text(
                json.dumps({"id": "1.20.1", "libraries": []}), encoding="utf-8"
            )
            (isolated / "mods").mkdir(parents=True)
            (isolated / "fabric-loader-0.16.5-1.21.1.json").write_text(
                json.dumps({
                    "id": "fabric-loader-0.16.5-1.21.1",
                    "inheritsFrom": "1.21.1",
                    "libraries": [{"name": "net.fabricmc:fabric-loader:0.16.5"}],
                }), encoding="utf-8"
            )
            found = discover_game_environments(root, "TLauncher")
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0].path, isolated)
            self.assertEqual(found[0].minecraft_version, "1.21.1")
            self.assertEqual(found[0].loader, "Fabric")

    def test_launcher_is_inferred_from_standard_paths(self) -> None:
        from launchers.game_directory.scanner import launcher_for_game_directory

        self.assertEqual(
            launcher_for_game_directory(Path("C:/Users/test/AppData/Roaming/.minecraft")),
            "Minecraft Launcher / TLauncher",
        )
        self.assertEqual(
            launcher_for_game_directory(Path("C:/Users/test/AppData/Roaming/.tlauncher/legacy/Minecraft/game")),
            "Legacy Launcher",
        )


    def test_discovers_mainorginizer_instances_for_official_launcher(self) -> None:
        from launchers.game_directory.scanner import discover_game_environments

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / ".minecraft"
            first = root / "instances" / "Fabric-1.21.1"
            second = root / "instances" / "Vanilla-1.20.4"
            (first / "mods").mkdir(parents=True)
            (second / "mods").mkdir(parents=True)
            (first / "fabric-loader-0.16.5-1.21.1.json").write_text(
                json.dumps({"id": "fabric-loader-0.16.5-1.21.1", "inheritsFrom": "1.21.1",
                            "libraries": [{"name": "net.fabricmc:fabric-loader:0.16.5"}]}),
                encoding="utf-8",
            )
            found = discover_game_environments(root, "Minecraft Launcher / TLauncher")
            self.assertEqual({item.path for item in found}, {first, second})
            fabric = next(item for item in found if item.path == first)
            self.assertEqual(fabric.minecraft_version, "1.21.1")
            self.assertEqual(fabric.loader, "Fabric")

    def test_selecting_home_root_discovers_its_children(self) -> None:
        from launchers.game_directory.scanner import discover_game_environments

        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "home"
            profile = home / "1.19.4"
            (profile / "mods").mkdir(parents=True)
            found = discover_game_environments(home, "Legacy Launcher")
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0].path, profile)


    def test_discovers_loader_version_without_mods_folder_and_ignores_shared_root(self):
        from launchers.game_directory.scanner import discover_game_environments

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / ".minecraft"
            (root / "mods").mkdir(parents=True)
            version = root / "versions" / "fabric-loader-0.16.5-1.21.1"
            version.mkdir(parents=True)
            (version / "fabric-loader-0.16.5-1.21.1.json").write_text(
                json.dumps({"id": "fabric-loader-0.16.5-1.21.1", "inheritsFrom": "1.21.1",
                            "libraries": [{"name": "net.fabricmc:fabric-loader:0.16.5"}]}),
                encoding="utf-8",
            )
            found = discover_game_environments(root, "TLauncher")
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0].path, version)
            self.assertEqual(found[0].loader, "Fabric")


if __name__ == "__main__":
    unittest.main()
