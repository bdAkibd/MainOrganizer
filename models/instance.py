"""Prism Launcher instance model."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class PrismInstance:
    """Store information about one Prism instance."""

    name: str
    instance_id: str
    path: Path
    minecraft_version: str
    loader: str
    loader_version: str
    status: str
    launcher: str = "Prism Launcher"
