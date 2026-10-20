"""Сканирование игровых окружений TLauncher и Legacy Launcher."""

import hashlib
import json
import os
import re
from pathlib import Path

from models.instance import PrismInstance


def default_game_directory_candidates() -> list[Path]:
    """Возвращает стандартные игровые каталоги TLauncher и Legacy Launcher."""
    candidates: list[Path] = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        roaming = Path(appdata)
        candidates.extend([
            roaming / ".minecraft",
            roaming / "TLauncher" / "minecraft",
            roaming / ".tlauncher" / "legacy" / "Minecraft" / "game",
        ])
    candidates.append(Path.home() / ".minecraft")
    unique: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path.resolve(strict=False)).casefold()
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def launcher_for_game_directory(path: Path) -> str:
    """Определяет подпись лаунчера по известному стандартному пути."""
    parts = [part.casefold() for part in path.parts]
    if ".tlauncher" in parts or ("legacy" in parts and "minecraft" in parts and "game" in parts):
        return "Legacy Launcher"
    if "tlauncher" in parts:
        return "TLauncher"
    if path.name.casefold() == ".minecraft":
        return "Minecraft Launcher / TLauncher"
    return "Minecraft (папка пользователя)"


def is_game_directory(path: Path) -> bool:
    """Проверяет, похожа ли папка на каталог игры или набор окружений."""
    if not path.is_dir():
        return False
    if any((path / name).is_dir() for name in ("versions", "mods", "assets", "libraries", "home", "instances")):
        return True
    return path.parent.name.casefold() == "versions" and any(path.glob("*.json"))


def _version_metadata(version_json: Path) -> tuple[str, str, str]:
    """Извлекает версию Minecraft и загрузчик из JSON установленной версии."""
    try:
        data = json.loads(version_json.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return "", "", ""
    if not isinstance(data, dict):
        return "", "", ""

    version_id = str(data.get("id", version_json.parent.name))
    mc_version = str(data.get("inheritsFrom", "")) or _guess_minecraft_version(version_id)
    loader, loader_version = _guess_loader(version_id)
    libraries = data.get("libraries", [])
    if isinstance(libraries, list):
        for library in libraries:
            if not isinstance(library, dict):
                continue
            detected_loader, detected_version = _loader_from_coordinate(str(library.get("name", "")))
            if detected_loader:
                loader, loader_version = detected_loader, detected_version
                break
    if not loader:
        loader = "Vanilla" if mc_version else "Не определён"
    return mc_version or "Не определена", loader, loader_version


def _guess_minecraft_version(value: str) -> str:
    """Находит похожий на версию Minecraft фрагмент строки."""
    match = re.search(r"(?<!\d)(\d+\.\d+(?:\.\d+)?)(?!\d)", value)
    return match.group(1) if match else ""


def _guess_loader(version_id: str) -> tuple[str, str]:
    """Определяет загрузчик по типичным идентификаторам версий."""
    patterns = [
        (r"fabric-loader[-_]?([\w.+-]+?)-\d+\.\d+", "Fabric"),
        (r"forge[-_]?([\w.+-]+?)-\d+\.\d+", "Forge"),
        (r"neoforge[-_]?([\w.+-]+?)-\d+\.\d+", "NeoForge"),
        (r"quilt-loader[-_]?([\w.+-]+?)-\d+\.\d+", "Quilt"),
    ]
    lower = version_id.lower()
    for pattern, name in patterns:
        match = re.search(pattern, lower)
        if match:
            return name, match.group(1).strip("-_")
    for marker, name in (("fabric", "Fabric"), ("neoforge", "NeoForge"), ("forge", "Forge"),
                         ("quilt", "Quilt"), ("optifine", "OptiFine")):
        if marker in lower:
            return name, ""
    return "", ""


def _loader_from_coordinate(coordinate: str) -> tuple[str, str]:
    """Определяет загрузчик по Maven-координате библиотеки."""
    lower = coordinate.lower()
    markers = [
        ("net.fabricmc:fabric-loader:", "Fabric"),
        ("net.minecraftforge:forge:", "Forge"),
        ("net.neoforged:neoforge:", "NeoForge"),
        ("org.quiltmc:quilt-loader:", "Quilt"),
    ]
    for marker, name in markers:
        if marker in lower:
            return name, coordinate.split(":")[-1]
    if "optifine:optifine:" in lower:
        return "OptiFine", coordinate.split(":")[-1]
    return "", ""


def _json_files_for_environment(path: Path) -> list[Path]:
    """Возвращает JSON именно выбранного окружения, не смешивая соседние версии."""
    direct = sorted(path.glob("*.json")) if path.is_dir() else []
    if direct:
        return direct
    nested_versions = path / "versions"
    if nested_versions.is_dir():
        return sorted(nested_versions.glob("*/*.json"))
    return []


def _metadata_for_environment(path: Path) -> tuple[str, str, str, str]:
    """Определяет версию и загрузчик для одной папки окружения."""
    files = _json_files_for_environment(path)
    detected = [_version_metadata(item) for item in files]
    detected = [item for item in detected if item[0] and item[0] != "Не определена"]
    if detected:
        # Папка конкретной версии обычно содержит один JSON. При нескольких берём наиболее полный набор.
        versions = list(dict.fromkeys(item[0] for item in detected))
        loaders = list(dict.fromkeys(item[1] for item in detected))
        version = versions[0] if len(versions) == 1 else f"Несколько версий ({len(versions)})"
        loader = loaders[0] if len(loaders) == 1 else "Смешанные"
        loader_versions = list(dict.fromkeys(item[2] for item in detected if item[1] == loader and item[2]))
        return version, loader, ", ".join(loader_versions[:3]), "Метаданные прочитаны из JSON окружения"

    guessed_version = _guess_minecraft_version(path.name)
    guessed_loader, guessed_loader_version = _guess_loader(path.name)
    if guessed_version:
        return guessed_version, guessed_loader or "Vanilla", guessed_loader_version, "Версия определена по имени папки"
    return "Не определена", "Не определён", "", "Версия не определена; проверьте метаданные папки"


def scan_game_directory(path: Path, launcher: str = "TLauncher / Legacy Launcher") -> PrismInstance:
    """Представляет одну папку игры или окружения как управляемый экземпляр."""
    version, loader, loader_version, status = _metadata_for_environment(path)
    if version.startswith("Несколько"):
        status = "В папке найдено несколько версий; для точного управления выберите отдельное окружение"
    resolved = str(path.resolve(strict=False)).casefold()
    instance_id = f"{launcher.lower().replace(' ', '-').replace('/', '-')}-{hashlib.sha256(resolved.encode('utf-8')).hexdigest()[:12]}"
    return PrismInstance(
        name=f"{launcher}: {path.name or path.drive}",
        instance_id=instance_id,
        path=path,
        minecraft_version=version,
        loader=loader,
        loader_version=loader_version,
        status=status,
        launcher=launcher,
    )


def _looks_like_home_environment(path: Path) -> bool:
    """Проверяет, похожа ли папка home на отдельное игровое окружение."""
    if not path.is_dir():
        return False
    if any((path / name).is_dir() for name in ("mods", "config", "versions", ".minecraft", "minecraft")):
        return True
    if any(path.glob("*.json")) or any(path.glob("*.jar")):
        return True
    return bool(_guess_minecraft_version(path.name) or _guess_loader(path.name)[0])


def discover_game_environments(path: Path, launcher: str | None = None) -> list[PrismInstance]:
    """Обнаруживает окружения home и изолированные версии с собственными папками mods."""
    if not path.is_dir():
        return []
    launcher = launcher or launcher_for_game_directory(path)

    environments: list[Path] = []
    # MainOrginizer может хранить отдельные игровые каталоги в .minecraft/instances.
    instances_dir = path if path.name.casefold() == "instances" else path / "instances"
    if instances_dir.is_dir():
        environments.extend(sorted(
            (child for child in instances_dir.iterdir() if child.is_dir() and (
                (child / "mods").is_dir() or (child / "config").is_dir()
                or (child / "resourcepacks").is_dir() or (child / "shaderpacks").is_dir()
            )),
            key=lambda item: item.name.casefold(),
        ))

    # Legacy Launcher может хранить отдельные окружения здесь, аналогично Prism instances.
    home = path if path.name.casefold() == "home" else path / "home"
    if home.is_dir():
        environments.extend(sorted(
            (child for child in home.iterdir() if _looks_like_home_environment(child)),
            key=lambda item: item.name.casefold(),
        ))

    # TLauncher и Legacy могут хранить изолированные моды прямо в versions/<версия>/mods.
    # Обычные каталоги versions без собственного mods не считаем отдельными окружениями.
    versions = path if path.name.casefold() == "versions" else path / "versions"
    if versions.is_dir():
        for child in sorted(versions.iterdir(), key=lambda item: item.name.casefold()):
            if not child.is_dir():
                continue
            version_files = sorted(child.glob("*.json"))
            modded_version = any(_version_metadata(item)[1] not in {"", "Vanilla", "Не определён"}
                                 for item in version_files)
            if (child / "mods").is_dir() or modded_version:
                environments.append(child)

    # Если пользователь указал непосредственно папку версии, сохраняем точный путь.
    if path.parent.name.casefold() == "versions" and path.is_dir():
        version_files = sorted(path.glob("*.json"))
        modded_version = any(_version_metadata(item)[1] not in {"", "Vanilla", "Не определён"}
                             for item in version_files)
        if version_files or (path / "mods").is_dir():
            if modded_version or (path / "mods").is_dir():
                environments.append(path)

    unique: list[Path] = []
    seen: set[str] = set()
    for environment in environments:
        key = str(environment.resolve(strict=False)).casefold()
        if key not in seen:
            seen.add(key)
            unique.append(environment)

    # Не предлагаем общий .minecraft как отдельное окружение, если найдены изолированные сборки.
    # Иначе профиль для конкретной версии мог случайно примениться к общей папке mods.
    if path.name.casefold() == ".minecraft" and (path / "mods").is_dir() and not environments:
        environments.append(path)

    unique_paths: list[Path] = []
    seen_paths: set[str] = set()
    for environment in environments:
        key = str(environment.resolve(strict=False)).casefold()
        if key not in seen_paths:
            seen_paths.add(key)
            unique_paths.append(environment)

    if unique_paths:
        return [scan_game_directory(item, launcher) for item in unique_paths]
    return [scan_game_directory(path, launcher)]
