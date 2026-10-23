"""Application identity and bundled resource paths."""

import sys
from pathlib import Path


APP_NAME = "MineOrganizer"
APP_SHORT_NAME = "MOrg"
APP_ICON_FILENAME = "MOrg.ico"


def app_icon_path() -> Path:
    """Return the icon path in development and in a PyInstaller bundle."""
    bundled_root = getattr(sys, "_MEIPASS", None)
    if bundled_root:
        return Path(str(bundled_root)) / APP_ICON_FILENAME
    project_root = Path(__file__).resolve().parents[1]
    project_icon = project_root / APP_ICON_FILENAME
    return project_icon if project_icon.is_file() else project_root.parent / APP_ICON_FILENAME
