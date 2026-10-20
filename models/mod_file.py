"""Модель файла мода в библиотеке."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ModFile:
    """Хранит основные сведения о файле мода."""

    name: str
    path: Path
    size: int
    sha256: str
