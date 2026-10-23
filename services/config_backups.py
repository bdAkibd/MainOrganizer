"""Backup and safe restore of an instance's config directory."""

import os
import shutil
import zipfile
from datetime import datetime
from pathlib import Path


def default_config_backup_dir() -> Path:
    """Returns the directory for configuration backups."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    return (Path(local_app_data) / "MineOrganizer" / "config_backups") if local_app_data else Path.home() / ".local" / "share" / "MineOrganizer" / "config_backups"


def find_config_dir(instance_path: Path) -> Path | None:
    """Finds an existing config directory in a Prism instance."""
    for root in (instance_path / ".minecraft", instance_path / "minecraft", instance_path):
        candidate = root / "config"
        if candidate.is_dir():
            return candidate
    return None


def create_config_backup(instance_path: Path, backup_root: Path | None = None) -> tuple[bool, str]:
    """Archives config files without modifying the game instance."""
    config_dir = find_config_dir(instance_path)
    if config_dir is None:
        return False, "The config folder was not found in the instance."
    backup_root = backup_root or default_config_backup_dir()
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = backup_root / f"{instance_path.name}-{stamp}.zip"
    index = 2
    while destination.exists():
        destination = backup_root / f"{instance_path.name}-{stamp}-{index}.zip"
        index += 1
    try:
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(config_dir.rglob("*")):
                if path.is_file() and not path.is_symlink():
                    archive.write(path, path.relative_to(config_dir).as_posix())
    except (OSError, zipfile.BadZipFile) as error:
        destination.unlink(missing_ok=True)
        return False, f"Could not create backup: {error}"
    return True, f"Backup created: {destination}"


def list_config_backups(backup_root: Path | None = None) -> list[Path]:
    """Lists available configuration archives newest first."""
    backup_root = backup_root or default_config_backup_dir()
    if not backup_root.is_dir():
        return []
    return sorted(backup_root.glob("*.zip"), key=lambda path: path.stat().st_mtime, reverse=True)


def delete_config_backup(archive_path: Path, backup_root: Path | None = None) -> tuple[bool, str]:
    """Delete a backup archive only when it belongs to the backup library."""
    backup_root = (backup_root or default_config_backup_dir()).resolve()
    archive_path = archive_path.resolve()
    try:
        archive_path.relative_to(backup_root)
    except ValueError:
        return False, "The selected archive is outside the backup library."
    if archive_path.suffix.casefold() != ".zip" or not archive_path.is_file():
        return False, "The backup archive was not found."
    try:
        archive_path.unlink()
    except OSError as error:
        return False, f"Could not delete backup: {error}"
    return True, f"Backup deleted: {archive_path.name}"


def delete_config_directory(config_dir: Path) -> tuple[bool, str]:
    """Delete a config directory after validating that it is named ``config``."""
    config_dir = config_dir.resolve()
    if config_dir.name.casefold() != "config" or not config_dir.is_dir():
        return False, "The config folder was not found."
    try:
        shutil.rmtree(config_dir)
    except OSError as error:
        return False, f"Could not delete configs: {error}"
    return True, f"Configs deleted: {config_dir}"


def restore_config_backup(archive_path: Path, instance_path: Path, backup_root: Path | None = None) -> tuple[bool, str]:
    """Restores a backup after validating every archive path and creates a safety backup first."""
    if not archive_path.is_file():
        return False, "The backup archive was not found."
    config_dir = find_config_dir(instance_path)
    if config_dir is None:
        config_dir = (instance_path / ".minecraft" / "config") if (instance_path / ".minecraft").is_dir() else instance_path / "config"
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            for member in archive.infolist():
                target = (config_dir / member.filename).resolve()
                try:
                    target.relative_to(config_dir.resolve())
                except ValueError:
                    return False, f"Unsafe path in archive: {member.filename}"
            if config_dir.is_dir():
                safety_ok, safety_message = create_config_backup(instance_path, backup_root)
                if not safety_ok:
                    return False, "Could not save current configs before restoration: " + safety_message
            config_dir.mkdir(parents=True, exist_ok=True)
            for member in archive.infolist():
                if member.is_dir():
                    (config_dir / member.filename).mkdir(parents=True, exist_ok=True)
                else:
                    target = config_dir / member.filename
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member) as source, target.open("wb") as destination:
                        destination.write(source.read())
    except (OSError, zipfile.BadZipFile, RuntimeError) as error:
        return False, f"Could not restore configs: {error}"
    return True, f"Configs restored from {archive_path.name}. Files missing from the archive were not deleted."
