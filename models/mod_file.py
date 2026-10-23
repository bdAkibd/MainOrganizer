"""Mod library file model."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ModFile:
    """Store core information about a mod file."""

    name: str
    path: Path
    size: int
    sha256: str
