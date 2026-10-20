"""Тесты сохранения пользовательских тегов и профилей."""

import tempfile
import unittest
from pathlib import Path

from services.user_data import UserDataStore


class UserDataTests(unittest.TestCase):
    """Проверяет сохранение метаданных без работы с файлами игры."""

    def test_tags_persist_and_deduplicate(self) -> None:
        """Метки сохраняются и повторяющиеся значения удаляются."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            path = Path(temporary_dir) / "user_data.json"
            store = UserDataStore(path)
            store.set_tags("abc", ["client", " client ", "performance"])
            loaded = UserDataStore(path)
            self.assertEqual(loaded.tags_for("abc"), ["client", "performance"])
            loaded.set_tags("abc", [])
            self.assertEqual(UserDataStore(path).tags_for("abc"), [])

    def test_profile_crud_and_mod_list(self) -> None:
        """Профиль сохраняет экземпляр и набор модов, позволяет обновлять и удалять."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            path = Path(temporary_dir) / "user_data.json"
            store = UserDataStore(path)
            instance = {
                "instance_id": "fabric-1201",
                "instance_path": "C:/Prism/instances/fabric-1201",
                "minecraft_version": "1.20.1",
                "loader": "Fabric",
                "loader_version": "0.15.0",
            }
            profile = store.add_profile("Performance", instance, ["hash1", "hash1", "hash2"])
            self.assertEqual(profile["enabled_mod_hashes"], ["hash1", "hash2"])
            loaded = UserDataStore(path)
            self.assertTrue(loaded.update_profile_mods(profile["id"], ["hash2"]))
            self.assertTrue(loaded.rename_profile(profile["id"], "Client"))
            self.assertEqual(loaded.profiles()[0]["name"], "Client")
            self.assertEqual(loaded.profiles()[0]["enabled_mod_hashes"], ["hash2"])
            self.assertTrue(loaded.delete_profile(profile["id"]))
            self.assertEqual(loaded.profiles(), [])


    def test_profile_asset_selection_persists(self) -> None:
        """Resource pack and shader selections are saved separately."""
        with tempfile.TemporaryDirectory() as temporary_dir:
            path = Path(temporary_dir) / "user_data.json"
            store = UserDataStore(path)
            instance = {
                "instance_id": "fabric-1201",
                "instance_path": "C:/Prism/instances/fabric-1201",
                "minecraft_version": "1.20.1",
                "loader": "Fabric",
                "loader_version": "0.15.0",
            }
            profile = store.add_profile("Assets", instance, [])
            store.update_profile_assets(profile["id"], "resourcepacks", ["pack-hash"])
            store.update_profile_assets(profile["id"], "shaderpacks", ["shader-hash"])
            loaded = UserDataStore(path).profiles()[0]
            self.assertEqual(loaded["enabled_resourcepack_hashes"], ["pack-hash"])
            self.assertEqual(loaded["enabled_shaderpack_hashes"], ["shader-hash"])
