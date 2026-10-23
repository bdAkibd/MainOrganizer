"""Discover Prism Launcher data directories."""

import os
from pathlib import Path


def default_prism_candidates() -> list[Path]:
    """Return known standard Prism paths."""
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
    """Find the standard Prism directory containing an instances folder."""
    for candidate in default_prism_candidates():
        if (candidate / "instances").is_dir():
            return candidate
    return None


def is_prism_data_dir(path: Path) -> bool:
    """Check whether a folder resembles a Prism data directory."""
    return path.is_dir() and (path / "instances").is_dir()
