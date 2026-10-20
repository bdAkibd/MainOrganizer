"""Модель экземпляра Prism Launcher."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class PrismInstance:
    """Хранит сведения об одном экземпляре Prism."""

    name: str
    instance_id: str
    path: Path
    minecraft_version: str
    loader: str
    loader_version: str
    status: str
    launcher: str = "Prism Launcher"
