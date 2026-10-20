"""Извлечение метаданных и приблизительная проверка совместимости модов."""

import json
import re
import tomllib
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ModMetadata:
    """Нормализованные метаданные JAR-файла мода."""

    name: str = ""
    mod_id: str = ""
    version: str = ""
    minecraft_ranges: list[str] = field(default_factory=list)
    loader_ids: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    required_mod_ids: list[str] = field(default_factory=list)
    source: str = ""
    kind: str = "Мод"


def read_mod_metadata(path: Path) -> ModMetadata:
    """Читает известные форматы Fabric, Quilt, Forge, NeoForge и mcmod.info."""
    result = ModMetadata(name=path.stem)
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            if "plugin.yml" in names:
                try:
                    plugin_text = archive.read("plugin.yml").decode("utf-8-sig")
                    plugin_data = _read_simple_yaml(plugin_text)
                    result.name = str(plugin_data.get("name") or result.name)
                    result.mod_id = str(plugin_data.get("name") or "").casefold().replace(" ", "")
                    result.version = str(plugin_data.get("version") or "")
                    api_version = str(plugin_data.get("api-version") or "")
                    result.source = "Bukkit/Spigot/Paper plugin.yml"
                    result.kind = "Плагин"
                    result.loader_ids = ["Bukkit/Spigot/Paper"]
                    if api_version:
                        result.minecraft_ranges.append(api_version)
                except (UnicodeDecodeError, ValueError):
                    pass
            elif "fabric.mod.json" in names:
                data = _read_json(archive, "fabric.mod.json")
                if isinstance(data, dict):
                    result.name = str(data.get("name") or result.name)
                    result.mod_id = str(data.get("id") or "")
                    result.version = str(data.get("version") or "")
                    result.source = "Fabric metadata"
                    result.loader_ids.append("fabric")
                    _collect_json_dependencies(data.get("depends"), result)
            elif "quilt.mod.json" in names:
                data = _read_json(archive, "quilt.mod.json")
                if isinstance(data, dict):
                    quilt = data.get("quilt_loader", {})
                    if not isinstance(quilt, dict):
                        quilt = {}
                    metadata = quilt.get("metadata", {})
                    if not isinstance(metadata, dict):
                        metadata = {}
                    result.name = str(metadata.get("name") or result.name)
                    result.mod_id = str(quilt.get("id") or "")
                    result.version = str(quilt.get("version") or "")
                    result.source = "Quilt metadata"
                    result.loader_ids.append("quilt")
                    _collect_json_dependencies(quilt.get("depends"), result)
            else:
                toml_name = next((name for name in ("META-INF/neoforge.mods.toml", "META-INF/mods.toml") if name in names), "")
                if toml_name:
                    data = tomllib.loads(archive.read(toml_name).decode("utf-8-sig"))
                    result.source = "NeoForge metadata" if "neoforge" in toml_name else "Forge metadata"
                    result.loader_ids.append("neoforge" if "neoforge" in toml_name else "forge")
                    mods = data.get("mods", [])
                    if isinstance(mods, list) and mods:
                        first = mods[0] if isinstance(mods[0], dict) else {}
                        result.mod_id = str(first.get("modId") or "")
                        result.name = str(first.get("displayName") or result.name)
                        result.version = str(first.get("version") or "")
                    for section in data.get("dependencies", {}).values() if isinstance(data.get("dependencies"), dict) else []:
                        if not isinstance(section, list):
                            continue
                        for dependency in section:
                            if not isinstance(dependency, dict):
                                continue
                            dep_id = str(dependency.get("modId") or "")
                            version_range = str(dependency.get("versionRange") or "")
                            if dep_id.lower() == "minecraft" and version_range:
                                result.minecraft_ranges.append(version_range)
                            elif dep_id:
                                result.dependencies.append(f"{dep_id} {version_range}".strip())
                                if dependency.get("mandatory", False) and dep_id.casefold() not in {"forge", "neoforge", "fabricloader", "quilt_loader"}:
                                    result.required_mod_ids.append(dep_id)
                elif "mcmod.info" in names:
                    data = _read_json(archive, "mcmod.info")
                    if isinstance(data, list) and data and isinstance(data[0], dict):
                        first = data[0]
                        result.name = str(first.get("name") or result.name)
                        result.mod_id = str(first.get("modid") or "")
                        result.version = str(first.get("version") or "")
                        result.source = "mcmod.info"
                        mcversion = str(first.get("mcversion") or "")
                        if mcversion:
                            result.minecraft_ranges.append(mcversion)
                        result.loader_ids.append("forge")
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError, tomllib.TOMLDecodeError, RuntimeError):
        return result
    result.minecraft_ranges = list(dict.fromkeys(result.minecraft_ranges))
    result.loader_ids = list(dict.fromkeys(result.loader_ids))
    result.dependencies = list(dict.fromkeys(result.dependencies))
    result.required_mod_ids = list(dict.fromkeys(result.required_mod_ids))
    return result


def compatibility_for_profile(metadata: ModMetadata, minecraft_version: str, loader: str, available_mod_ids: set[str] | None = None) -> tuple[str, str]:
    """Возвращает статус и пояснение без попытки загрузить или запустить мод."""
    if metadata.kind == "Плагин":
        return "Плагин сервера", "Обнаружен plugin.yml. Это серверный плагин Bukkit/Spigot/Paper, а не клиентский мод Fabric/Forge."
    if not metadata.source:
        return "Неизвестно", "Не найден поддерживаемый формат метаданных; совместимость не подтверждена."
    normalized_loader = loader.casefold()
    supported = {item.casefold() for item in metadata.loader_ids}
    if normalized_loader in {"fabric", "quilt", "forge", "neoforge"} and supported and normalized_loader not in supported:
        # Некоторые Forge-моды также работают на NeoForge и наоборот; автоматически это не предполагается.
        return "Несовместим", f"Метаданные указывают загрузчик: {', '.join(metadata.loader_ids)}."
    if metadata.minecraft_ranges and not any(version_matches(minecraft_version, item) for item in metadata.minecraft_ranges):
        return "Несовместим", f"Версия Minecraft {minecraft_version} не совпадает с диапазоном: {', '.join(metadata.minecraft_ranges)}."
    if not metadata.minecraft_ranges:
        return "Неизвестно", "В метаданных не найден диапазон Minecraft."
    if available_mod_ids is not None:
        missing = sorted(set(metadata.required_mod_ids) - available_mod_ids)
        if missing:
            return "Не хватает зависимостей", "Не выбраны обязательные зависимости: " + ", ".join(missing) + "."
    return "Вероятно совместим", "Метаданные не выявили конфликта Minecraft, загрузчика и известных обязательных зависимостей; это не гарантия запуска."


def minecraft_version_entries(expressions: list[str]) -> list[str]:
    """Разделяет перечисление версий на отдельные варианты, сохраняя диапазоны Maven."""
    result: list[str] = []
    for expression in expressions:
        value = expression.strip()
        if value and not (value.startswith(("[", "(")) and value.endswith(("]", ")"))):
            result.extend(part.strip() for part in value.split(",") if part.strip())
        elif value:
            result.append(value)
    return list(dict.fromkeys(result))


def version_matches(version: str, expression: str) -> bool:
    """Проверяет точную версию, перечисления, простые диапазоны Maven и ограничения."""
    expression = expression.strip()
    if "," in expression and not (expression.startswith(("[", "(")) and expression.endswith(("]", ")"))):
        return any(version_matches(version, part) for part in expression.split(","))
    if not expression or expression in {"*", "any"}:
        return True
    if expression.startswith(("[", "(")) and expression.endswith(("]", ")")):
        inner = expression[1:-1]
        if "," in inner:
            lower, upper = (part.strip() for part in inner.split(",", 1))
            if lower and (_version_key(version) < _version_key(lower) or (expression[0] == "(" and _version_key(version) == _version_key(lower))):
                return False
            if upper and (_version_key(version) > _version_key(upper) or (expression[-1] == ")" and _version_key(version) == _version_key(upper))):
                return False
            return True
        return _version_key(version) == _version_key(inner)
    if expression.startswith((">=", "<=" , ">", "<", "=")):
        operator = next(op for op in (">=", "<=", ">", "<", "=") if expression.startswith(op))
        target = expression[len(operator):].strip()
        left, right = _version_key(version), _version_key(target)
        return {">=": left >= right, "<=": left <= right, ">": left > right, "<": left < right, "=": left == right}[operator]
    if "||" in expression:
        return any(version_matches(version, part) for part in expression.split("||"))
    return _version_key(version) == _version_key(expression)


def _version_key(value: str) -> tuple[tuple[int, object], ...]:
    parts = re.findall(r"\d+|[a-zA-Z]+", value.casefold())
    return tuple((0, int(part)) if part.isdigit() else (1, part) for part in parts)


def _read_json(archive: zipfile.ZipFile, name: str) -> Any:
    return json.loads(archive.read(name).decode("utf-8-sig"))


def _read_simple_yaml(text: str) -> dict[str, str]:
    """Читает простые поля верхнего уровня из plugin.yml без внешних библиотек."""
    result: dict[str, str] = {}
    for line in text.splitlines():
        if not line or line[0].isspace() or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip().strip("\"'")
        if key.strip() and value:
            result[key.strip()] = value
    return result


def _collect_json_dependencies(value: Any, result: ModMetadata) -> None:
    """Нормализует зависимости Fabric (словарь) и Quilt (список объектов)."""
    entries: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        entries = [(str(key), constraint) for key, constraint in value.items()]
    elif isinstance(value, list):
        for item in value:
            if not isinstance(item, dict):
                continue
            dependency = item.get("id") or item.get("name")
            constraint = item.get("versions", item.get("version", "*"))
            if dependency:
                entries.append((str(dependency), constraint))
    for dependency, constraint in entries:
        if isinstance(constraint, dict):
            constraint = constraint.get("versions", constraint.get("version", "*"))
        if not isinstance(constraint, (str, int, float, list)):
            continue
        constraints = constraint if isinstance(constraint, list) else [constraint]
        for item in constraints:
            text = str(item)
            dependency_key = dependency.casefold()
            if dependency_key == "minecraft":
                result.minecraft_ranges.append(text)
            elif dependency_key in {"fabricloader", "quilt_loader", "forge", "neoforge"}:
                result.loader_ids.append({"fabricloader": "fabric", "quilt_loader": "quilt"}.get(dependency_key, dependency_key))
                result.dependencies.append(f"{dependency} {text}".strip())
            else:
                result.dependencies.append(f"{dependency} {text}".strip())
                if dependency_key != "java":
                    result.required_mod_ids.append(dependency)
