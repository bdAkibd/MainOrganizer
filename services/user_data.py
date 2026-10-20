"""Сохранение пользовательских тегов и профилей вне игровых каталогов."""

import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any


def default_user_data_path() -> Path:
    """Возвращает путь к пользовательским данным MainOrginizer."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "MainOrginizer" / "user_data.json"
    return Path.home() / ".local" / "share" / "MainOrginizer" / "user_data.json"


class UserDataStore:
    """Читает и безопасно сохраняет теги и описания профилей в JSON."""

    def __init__(self, path: Path | None = None) -> None:
        """Загружает пользовательские данные из указанного или стандартного файла."""
        self.path = path or default_user_data_path()
        self.data: dict[str, Any] = {"version": 1, "mod_tags": {}, "profiles": [], "game_dirs": []}
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                tags = loaded.get("mod_tags", {})
                profiles = loaded.get("profiles", [])
                self.data["mod_tags"] = tags if isinstance(tags, dict) else {}
                self.data["profiles"] = profiles if isinstance(profiles, list) else []
                game_dirs = loaded.get("game_dirs", [])
                self.data["game_dirs"] = game_dirs if isinstance(game_dirs, list) else []
                for profile in self.data["profiles"]:
                    if isinstance(profile, dict):
                        profile.setdefault("enabled_resourcepack_hashes", [])
                        profile.setdefault("enabled_shaderpack_hashes", [])
        except (OSError, json.JSONDecodeError):
            pass

    def save(self) -> None:
        """Атомарно сохраняет JSON, не затрагивая файлы игры."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=self.path.parent, delete=False, suffix=".tmp"
            ) as temporary_file:
                json.dump(self.data, temporary_file, ensure_ascii=False, indent=2)
                temporary_path = Path(temporary_file.name)
            temporary_path.replace(self.path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink(missing_ok=True)

    def tags_for(self, sha256: str) -> list[str]:
        """Возвращает метки файла по его хешу."""
        value = self.data["mod_tags"].get(sha256, [])
        return [str(tag) for tag in value if isinstance(tag, str)] if isinstance(value, list) else []

    def set_tags(self, sha256: str, tags: list[str]) -> None:
        """Сохраняет уникальные метки файла по SHA-256."""
        normalized = list(dict.fromkeys(tag.strip() for tag in tags if tag.strip()))
        if normalized:
            self.data["mod_tags"][sha256] = normalized
        else:
            self.data["mod_tags"].pop(sha256, None)
        self.save()

    def profiles(self) -> list[dict[str, Any]]:
        """Возвращает список профилей."""
        return self.data["profiles"]

    def add_profile(self, name: str, instance: dict[str, str], mod_hashes: list[str]) -> dict[str, Any]:
        """Создаёт профиль, связанный с экземпляром Prism и набором модов."""
        profile = {
            "id": uuid.uuid4().hex,
            "name": name.strip(),
            "instance_id": instance["instance_id"],
            "instance_path": instance["instance_path"],
            "minecraft_version": instance["minecraft_version"],
            "loader": instance["loader"],
            "loader_version": instance["loader_version"],
            "enabled_mod_hashes": list(dict.fromkeys(mod_hashes)),
            "enabled_resourcepack_hashes": [],
            "enabled_shaderpack_hashes": [],
        }
        self.data["profiles"].append(profile)
        self.save()
        return profile

    def update_profile_mods(self, profile_id: str, mod_hashes: list[str]) -> bool:
        """Обновляет сохранённый набор модов профиля."""
        for profile in self.data["profiles"]:
            if profile.get("id") == profile_id:
                profile["enabled_mod_hashes"] = list(dict.fromkeys(mod_hashes))
                self.save()
                return True
        return False


    def update_profile_assets(self, profile_id: str, kind: str, asset_hashes: list[str]) -> bool:
        """Updates resource pack or shader pack selection for a profile."""
        field = "enabled_resourcepack_hashes" if kind == "resourcepacks" else "enabled_shaderpack_hashes"
        for profile in self.data["profiles"]:
            if profile.get("id") == profile_id:
                profile[field] = list(dict.fromkeys(asset_hashes))
                self.save()
                return True
        return False

    def rename_profile(self, profile_id: str, name: str) -> bool:
        """Переименовывает профиль."""
        for profile in self.data["profiles"]:
            if profile.get("id") == profile_id:
                profile["name"] = name.strip()
                self.save()
                return True
        return False

    def delete_profile(self, profile_id: str) -> bool:
        """Удаляет описание профиля, не удаляя игровые файлы."""
        before = len(self.data["profiles"])
        self.data["profiles"] = [profile for profile in self.data["profiles"] if profile.get("id") != profile_id]
        if len(self.data["profiles"]) != before:
            self.save()
            return True
        return False
