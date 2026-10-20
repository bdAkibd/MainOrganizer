"""Проверка распространённых конфликтов в выбранном наборе модов."""

from collections import defaultdict
from dataclasses import dataclass

from services.mod_metadata import ModMetadata, compatibility_for_profile, version_matches


@dataclass(slots=True)
class Conflict:
    """Одно предупреждение или ошибка набора модов."""

    severity: str
    mod_name: str
    message: str


def check_mod_conflicts(
    mods: list[tuple[str, ModMetadata]], minecraft_version: str, loader: str
) -> list[Conflict]:
    """Ищет дубли ID, несовместимость и отсутствующие/неподходящие зависимости."""
    conflicts: list[Conflict] = []
    by_id: dict[str, list[tuple[str, ModMetadata]]] = defaultdict(list)
    for name, metadata in mods:
        if metadata.mod_id:
            by_id[metadata.mod_id.casefold()].append((name, metadata))

    for mod_id, entries in by_id.items():
        if len(entries) > 1:
            names = ", ".join(name for name, _ in entries)
            conflicts.append(Conflict("Ошибка", names, f"Повторяется ID мода «{mod_id}» в нескольких файлах."))

    available_ids = set(by_id)
    for name, metadata in mods:
        if not metadata.source:
            conflicts.append(Conflict("Предупреждение", name, "Не удалось прочитать метаданные; автоматическая проверка ограничена."))
            continue
        status, reason = compatibility_for_profile(metadata, minecraft_version, loader, available_ids)
        if status == "Несовместим":
            conflicts.append(Conflict("Ошибка", name, reason))
        elif status == "Не хватает зависимостей":
            conflicts.append(Conflict("Ошибка", name, reason))
        elif status == "Неизвестно":
            conflicts.append(Conflict("Предупреждение", name, reason))

        for dependency in metadata.required_mod_ids:
            target_entries = by_id.get(dependency.casefold(), [])
            if not target_entries:
                # Missing dependencies are already covered by compatibility_for_profile.
                continue
            constraints = [value for value in metadata.dependencies if value.split(maxsplit=1)[0].casefold() == dependency.casefold()]
            for target_name, target_metadata in target_entries:
                for constraint in constraints:
                    parts = constraint.split(maxsplit=1)
                    if len(parts) == 2 and target_metadata.version and parts[1] not in {"", "*"}:
                        if not version_matches(target_metadata.version, parts[1]):
                            conflicts.append(Conflict(
                                "Предупреждение", name,
                                f"Зависимость «{dependency}» требует версию {parts[1]}, "
                                f"но у «{target_name}» указана {target_metadata.version}.",
                            ))
                            break
    return conflicts
