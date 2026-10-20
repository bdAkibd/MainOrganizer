"""Поиск каталогов данных Prism Launcher."""

import os
from pathlib import Path


def default_prism_candidates() -> list[Path]:
    """Возвращает известные стандартные пути Prism."""
    candidates: list[Path] = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.append(Path(appdata) / "PrismLauncher")
    localappdata = os.environ.get("LOCALAPPDATA")
    if localappdata:
        candidates.append(Path(localappdata) / "Programs" / "PrismLauncher")
    home = Path.home()
    candidates.extend(
        [
            home / "AppData" / "Roaming" / "PrismLauncher",
            home / "PrismLauncher",
        ]
    )

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate.resolve(strict=False)).casefold()
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def find_default_prism_data_dir() -> Path | None:
    """Находит стандартный каталог Prism с папкой instances."""
    for candidate in default_prism_candidates():
        if (candidate / "instances").is_dir():
            return candidate
    return None


def is_prism_data_dir(path: Path) -> bool:
    """Проверяет, похожа ли папка на каталог данных Prism."""
    return path.is_dir() and (path / "instances").is_dir()
