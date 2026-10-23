"""Store application settings separately from user data."""

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def default_app_config_path() -> Path:
    """Return the MineOrganizer settings configuration path."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "MineOrganizer" / "config.json"
    return Path.home() / ".local" / "share" / "MineOrganizer" / "config.json"


class AppConfig:
    """Load and safely save application interface settings."""

    defaults: dict[str, Any] = {
        "version": 1,
        "theme": "light",
        "locale": "en",
    }

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_app_config_path()
        self.data = dict(self.defaults)
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            loaded = {}
        if isinstance(loaded, dict):
            self.data.update(loaded)
        self.data["version"] = 1
        self.data["theme"] = self.data["theme"] if self.data.get("theme") in {"light", "dark"} else "light"
        self.data["locale"] = self.data.get("locale") if self.data.get("locale") in {"en", "ru"} else "en"

    def save(self) -> None:
        """Save settings by atomically replacing the file."""
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

    @property
    def theme(self) -> str:
        return str(self.data["theme"])

    @property
    def locale(self) -> str:
        return str(self.data["locale"])

    def set_theme(self, theme: str) -> None:
        """Set a supported theme and save the configuration."""
        self.data["theme"] = theme if theme in {"light", "dark"} else "light"
        self.save()

    def set_locale(self, locale: str) -> None:
        """Set a supported locale and save the configuration."""
        self.data["locale"] = locale if locale in {"en", "ru"} else "en"
        self.save()
