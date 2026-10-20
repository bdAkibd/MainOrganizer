"""Чтение метаданных экземпляров Prism Launcher."""

import configparser
import json
from pathlib import Path
from typing import Any

from models.instance import PrismInstance


def _read_instance_cfg(path: Path) -> dict[str, str]:
    """Читает ключи instance.cfg без предположения о наличии секции INI."""
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    except OSError:
        return values

    # Prism config обычно использует строки key=value. Поддерживаем также INI-подобный формат.
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read_string("[instance]\n" + "\n".join(lines))
        values.update(dict(parser.items("instance")))
    except configparser.Error:
        pass

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", ";", "[")) or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values.setdefault(key.strip().lower(), value.strip())
    return values


def _read_pack(path: Path) -> dict[str, Any]:
    """Читает список компонентов из mmc-pack.json."""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _component_version(component: dict[str, Any]) -> str:
    """Возвращает строку версии компонента."""
    version = component.get("version", "")
    return str(version) if version is not None else ""


def _detect_components(pack: dict[str, Any]) -> tuple[str, str, str]:
    """Определяет Minecraft и загрузчик по компонентам сборки."""
    minecraft_version = "Не определена"
    loader = "Не определён"
    loader_version = ""

    components = pack.get("components", [])
    if not isinstance(components, list):
        return minecraft_version, loader, loader_version

    loader_ids = {
        "net.fabricmc.fabric-loader": "Fabric",
        "net.minecraftforge": "Forge",
        "net.neoforged": "NeoForge",
        "com.mumfrey.liteloader": "LiteLoader",
        "org.quiltmc.quilt-loader": "Quilt",
    }

    for component in components:
        if not isinstance(component, dict):
            continue
        uid = str(component.get("uid", "")).lower()
        version = _component_version(component)

        if uid == "net.minecraft":
            minecraft_version = version or minecraft_version
        for component_id, loader_name in loader_ids.items():
            if uid == component_id or uid.startswith(component_id + "."):
                loader = loader_name
                loader_version = version
                break

    if loader == "Не определён" and minecraft_version != "Не определена":
        loader = "Vanilla"

    return minecraft_version, loader, loader_version


def parse_instance(instance_dir: Path) -> PrismInstance:
    """Читает метаданные одного экземпляра Prism."""
    cfg = _read_instance_cfg(instance_dir / "instance.cfg")
    pack = _read_pack(instance_dir / "mmc-pack.json")
    minecraft_version, loader, loader_version = _detect_components(pack)

    name = cfg.get("name", instance_dir.name).strip() or instance_dir.name
    # Имя каталога — стабильный идентификатор экземпляра внутри Prism.
    instance_id = instance_dir.name

    if not (instance_dir / "instance.cfg").is_file():
        status = "Нет instance.cfg"
    elif not (instance_dir / "mmc-pack.json").is_file():
        status = "Нет mmc-pack.json"
    elif minecraft_version == "Не определена":
        status = "Не удалось определить версию"
    else:
        status = "Готов к проверке"

    return PrismInstance(
        name=name,
        instance_id=instance_id,
        path=instance_dir,
        minecraft_version=minecraft_version,
        loader=loader,
        loader_version=loader_version,
        status=status,
    )


def scan_instances(prism_data_dir: Path) -> list[PrismInstance]:
    """Сканирует подпапки instances и возвращает распознанные записи."""
    instances_dir = prism_data_dir / "instances"
    if not instances_dir.is_dir():
        return []

    results: list[PrismInstance] = []
    try:
        directories = sorted(
            (entry for entry in instances_dir.iterdir() if entry.is_dir()),
            key=lambda entry: entry.name.casefold(),
        )
    except OSError:
        return results

    for directory in directories:
        # Не принимаем произвольные подпапки за экземпляры, если нет ни одного файла-маркера.
        if not (directory / "instance.cfg").is_file() and not (directory / "mmc-pack.json").is_file():
            continue
        results.append(parse_instance(directory))
    return results
