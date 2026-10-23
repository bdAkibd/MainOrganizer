"""Read-only scan of mod files inside Prism instances."""

from dataclasses import dataclass
from pathlib import Path

from models.instance import PrismInstance
from services.mod_library import file_sha256, scan_mods


@dataclass(slots=True)
class EnvironmentFinding:
    """Describes one mod-file observation in a game instance."""

    instance_name: str
    filename: str
    status: str
    size: int | None
    sha256: str
    path: Path


def _mods_directories(instance_path: Path) -> list[Path]:
    """Finds common Prism/Minecraft mods directory layouts without creating them."""
    candidates = [
        instance_path / ".minecraft" / "mods",
        instance_path / "minecraft" / "mods",
        instance_path / "mods",
    ]
    found: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        try:
            if candidate.is_dir():
                identity = str(candidate.resolve()).casefold()
                if identity not in seen:
                    found.append(candidate)
                    seen.add(identity)
        except OSError:
            continue
    return found


def scan_environment_mods(
    instances: list[PrismInstance], library_dir: Path
) -> list[EnvironmentFinding]:
    """Reports instance JARs as library copies, library links, or external files."""
    library_hashes = {mod.sha256 for mod in scan_mods(library_dir)}
    findings: list[EnvironmentFinding] = []

    try:
        resolved_library = library_dir.resolve()
    except OSError:
        resolved_library = library_dir.absolute()

    for instance in instances:
        directories = _mods_directories(instance.path)
        if not directories:
            findings.append(EnvironmentFinding(
                instance.name, "—", "mods folder not found", None, "", instance.path
            ))
            continue

        for mods_dir in directories:
            try:
                entries = sorted(mods_dir.iterdir(), key=lambda path: path.name.casefold())
            except OSError:
                findings.append(EnvironmentFinding(
                    instance.name, "—", "No access to mods folder", None, "", mods_dir
                ))
                continue

            jar_entries = [entry for entry in entries if entry.suffix.lower() == ".jar"]
            if not jar_entries:
                findings.append(EnvironmentFinding(
                    instance.name, "—", "mods folder is empty", None, "", mods_dir
                ))
                continue

            for path in jar_entries:
                if path.is_symlink() and not path.exists():
                    findings.append(EnvironmentFinding(
                        instance.name, path.name, "Symbolic link not found", None, "", path
                    ))
                    continue
                try:
                    resolved_path = path.resolve()
                    try:
                        resolved_path.relative_to(resolved_library)
                        links_to_library = path.is_symlink()
                    except ValueError:
                        links_to_library = False
                    if links_to_library:
                        try:
                            digest = file_sha256(path)
                            size = path.stat().st_size
                        except OSError:
                            digest, size = "", None
                        findings.append(EnvironmentFinding(
                            instance.name, path.name, "Library link", size, digest, path
                        ))
                        continue

                    if not path.is_file():
                        findings.append(EnvironmentFinding(
                            instance.name, path.name, "Not a regular file", None, "", path
                        ))
                        continue
                    digest = file_sha256(path)
                    size = path.stat().st_size
                    status = "Copy of library file" if digest in library_hashes else "External mod — not imported"
                    findings.append(EnvironmentFinding(
                        instance.name, path.name, status, size, digest, path
                    ))
                except OSError:
                    findings.append(EnvironmentFinding(
                        instance.name, path.name, "Could not read file", None, "", path
                    ))

    return findings
