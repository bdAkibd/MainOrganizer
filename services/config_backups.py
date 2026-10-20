"""Backup and safe restore of an instance's config directory."""

import os
import zipfile
from datetime import datetime
from pathlib import Path


def default_config_backup_dir() -> Path:
    """Returns the directory for configuration backups."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    return (Path(local_app_data) / "MainOrginizer" / "config_backups") if local_app_data else Path.home() / ".local" / "share" / "MainOrginizer" / "config_backups"


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
        return False, "Папка config не найдена в экземпляре."
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
        return False, f"Не удалось создать резервную копию: {error}"
    return True, f"Резервная копия создана: {destination}"


def list_config_backups(backup_root: Path | None = None) -> list[Path]:
    """Lists available configuration archives newest first."""
    backup_root = backup_root or default_config_backup_dir()
    if not backup_root.is_dir():
        return []
    return sorted(backup_root.glob("*.zip"), key=lambda path: path.stat().st_mtime, reverse=True)


def restore_config_backup(archive_path: Path, instance_path: Path, backup_root: Path | None = None) -> tuple[bool, str]:
    """Restores a backup after validating every archive path and creates a safety backup first."""
    if not archive_path.is_file():
        return False, "Архив резервной копии не найден."
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
                    return False, f"Небезопасный путь в архиве: {member.filename}"
            if config_dir.is_dir():
                safety_ok, safety_message = create_config_backup(instance_path, backup_root)
                if not safety_ok:
                    return False, "Не удалось сохранить текущие конфиги перед восстановлением: " + safety_message
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
        return False, f"Не удалось восстановить конфигурации: {error}"
    return True, f"Конфигурации восстановлены из {archive_path.name}. Файлы, отсутствующие в архиве, не удалялись."
