"""Library management for Minecraft resource packs and shader packs."""

import os
import shutil
import zipfile
from pathlib import Path

from models.mod_file import ModFile
from services.mod_library import file_sha256


def default_asset_library_dir() -> Path:
    """Returns the root directory for asset libraries."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    root = Path(local_app_data) / "MineOrganizer" / "library" if local_app_data else Path.home() / ".local" / "share" / "MineOrganizer" / "library"
    return root / "assets"


def scan_assets(library_dir: Path, kind: str) -> list[ModFile]:
    """Scans zip assets in one category without changing files."""
    category_dir = library_dir / kind
    if not category_dir.is_dir():
        return []
    result: list[ModFile] = []
    try:
        paths = sorted((path for path in category_dir.iterdir() if path.is_file() and path.suffix.lower() == ".zip"), key=lambda path: path.name.casefold())
    except OSError:
        return result
    for path in paths:
        try:
            result.append(ModFile(path.name, path, path.stat().st_size, file_sha256(path)))
        except OSError:
            continue
    return result


def import_assets(source_paths: list[Path], library_dir: Path, kind: str) -> tuple[int, int, list[str]]:
    """Copies zip assets into a category folder and skips content duplicates."""
    category_dir = library_dir / kind
    category_dir.mkdir(parents=True, exist_ok=True)
    known_hashes = {asset.sha256 for asset in scan_assets(library_dir, kind)}
    imported = 0
    skipped = 0
    errors: list[str] = []
    for source in source_paths:
        if not source.is_file() or source.suffix.lower() != ".zip" or not zipfile.is_zipfile(source):
            skipped += 1
            continue
        try:
            digest = file_sha256(source)
            if digest in known_hashes:
                skipped += 1
                continue
            destination = category_dir / source.name
            index = 2
            while destination.exists():
                destination = category_dir / f"{source.stem} ({index}){source.suffix}"
                index += 1
            shutil.copy2(source, destination)
            known_hashes.add(digest)
            imported += 1
        except OSError as error:
            errors.append(f"{source.name}: {error}")
    return imported, skipped, errors
