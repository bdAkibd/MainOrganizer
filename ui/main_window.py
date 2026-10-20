"""Главное окно MainOrginizer."""

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QMenu,
    QSplitter,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from launchers.prism.discovery import find_default_prism_data_dir, is_prism_data_dir
from launchers.prism.instance_parser import scan_instances
from launchers.game_directory.scanner import (
    default_game_directory_candidates, is_game_directory, discover_game_environments, launcher_for_game_directory,
)
from models.instance import PrismInstance
from models.mod_file import ModFile
from services.mod_library import default_library_dir, import_mods, scan_mods
from services.mod_metadata import read_mod_metadata, compatibility_for_profile, minecraft_version_entries
from services.mod_conflicts import check_mod_conflicts
from services.asset_library import default_asset_library_dir, import_assets, scan_assets
from services.asset_virtualization import preview_assets, apply_assets, rollback_assets
from services.config_backups import create_config_backup, list_config_backups, restore_config_backup
from services.environment_scan import scan_environment_mods
from services.user_data import UserDataStore
from services.virtualization import (
    VirtualizationPlan, apply_profile, preview_profile, rollback_last,
)


class NaturalSortItem(QTableWidgetItem):
    """Элемент таблицы с сортировкой по числовым частям строк."""

    def __lt__(self, other: QTableWidgetItem) -> bool:
        left = self.data(Qt.ItemDataRole.UserRole)
        right = other.data(Qt.ItemDataRole.UserRole)
        if left is not None and right is not None:
            return left < right
        return self.text().casefold() < other.text().casefold()


def _sort_key(value: str) -> tuple[tuple[int, object], ...]:
    """Разбивает строку на числовые и текстовые части для сортировки версий."""
    import re

    parts = re.findall(r"\d+|\D+", value.casefold())
    return tuple((0, int(part)) if part.isdigit() else (1, part) for part in parts)


class ModSelectionDialog(QDialog):
    """Позволяет выбрать моды с фильтрами по версии Minecraft и загрузчику."""

    def __init__(self, mods: list[ModFile], selected_hashes: set[str] | None = None) -> None:
        """Создаёт список модов с флажками и фильтрами совместимости."""
        super().__init__()
        self.setWindowTitle("Моды профиля")
        self.resize(620, 520)
        self.list_widget = QListWidget()
        self.version_filter = QComboBox()
        self.loader_filter = QComboBox()
        self.version_filter.addItem("Все версии")
        self.loader_filter.addItem("Все загрузчики")
        selected = selected_hashes or set()
        self.mod_metadata: dict[str, tuple[list[str], list[str]]] = {}
        for mod in mods:
            metadata = read_mod_metadata(mod.path)
            versions = minecraft_version_entries(metadata.minecraft_ranges) or ["Не указана"]
            loaders = metadata.loader_ids or ["Не указан"]
            self.mod_metadata[mod.sha256] = (versions, loaders)
            kind_prefix = f"[{metadata.kind}] " if metadata.kind != "Мод" else ""
            item = QListWidgetItem(f"{kind_prefix}{metadata.name or mod.name}  ({mod.size:,} байт)".replace(",", " "))
            item.setData(Qt.ItemDataRole.UserRole, mod.sha256)
            item.setData(Qt.ItemDataRole.UserRole + 1, (versions, loaders))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if mod.sha256 in selected else Qt.CheckState.Unchecked)
            item.setToolTip(f"Тип: {metadata.kind}\nMinecraft: {', '.join(versions)}\nЗагрузчик: {', '.join(loaders)}\n{mod.path}")
            self.list_widget.addItem(item)
        versions = sorted({version for value in self.mod_metadata.values() for version in value[0]}, key=_sort_key)
        loaders = sorted({loader for value in self.mod_metadata.values() for loader in value[1]})
        self.version_filter.addItems(versions)
        self.loader_filter.addItems(loaders)
        self.version_filter.currentTextChanged.connect(self._apply_filters)
        self.loader_filter.currentTextChanged.connect(self._apply_filters)
        self.list_widget.itemDoubleClicked.connect(self._toggle_item)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_item_menu)
        filters = QHBoxLayout()
        filters.addWidget(QLabel("Minecraft:"))
        filters.addWidget(self.version_filter, 1)
        filters.addWidget(QLabel("Загрузчик:"))
        filters.addWidget(self.loader_filter, 1)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Отметьте моды профиля. Фильтры скрывают неподходящие строки, но не снимают отметки."))
        layout.addLayout(filters)
        layout.addWidget(self.list_widget, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _apply_filters(self) -> None:
        """Скрывает моды, не подходящие под выбранные фильтры."""
        version = self.version_filter.currentText()
        loader = self.loader_filter.currentText()
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            item_versions, item_loaders = item.data(Qt.ItemDataRole.UserRole + 1)
            item.setHidden((version != "Все версии" and version not in item_versions)
                           or (loader != "Все загрузчики" and loader not in item_loaders))

    def _toggle_item(self, item: QListWidgetItem) -> None:
        """Переключает состояние мода двойным щелчком."""
        item.setCheckState(Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked)

    def _show_item_menu(self, position) -> None:
        """Показывает контекстное меню для выбора мода."""
        item = self.list_widget.itemAt(position)
        if item is None:
            return
        self.list_widget.setCurrentItem(item)
        menu = QMenu(self)
        toggle_action = menu.addAction("Включить" if item.checkState() != Qt.CheckState.Checked else "Выключить")
        menu.addAction("Показать путь").triggered.connect(lambda: QMessageBox.information(self, "Информация о моде", item.toolTip()))
        chosen = menu.exec(self.list_widget.mapToGlobal(position))
        if chosen == toggle_action:
            self._toggle_item(item)

    def selected_hashes(self) -> list[str]:
        """Возвращает хеши всех отмеченных модов, включая скрытые фильтром."""
        hashes: list[str] = []
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            if item.checkState() == Qt.CheckState.Checked:
                hashes.append(item.data(Qt.ItemDataRole.UserRole))
        return hashes


class MainWindow(QMainWindow):
    """Окно игровых окружений, библиотеки модов, меток и профилей."""

    def __init__(self) -> None:
        """Создаёт интерфейс и выполняет первое сканирование."""
        super().__init__()
        self.setWindowTitle("MainOrginizer")
        self.resize(1180, 720)
        self.prism_data_dir: Path | None = find_default_prism_data_dir()
        self.library_dir = default_library_dir()
        self.asset_library_dir = default_asset_library_dir()
        self.user_data = UserDataStore()
        self.instances: list[PrismInstance] = []
        self.user_data.data.setdefault("game_dirs", [])
        configured_dirs = self.user_data.data["game_dirs"]
        known_dirs = {str(Path(value).resolve(strict=False)).casefold() for value in configured_dirs if isinstance(value, str)}
        for candidate in default_game_directory_candidates():
            if is_game_directory(candidate):
                key = str(candidate.resolve(strict=False)).casefold()
                if key not in known_dirs:
                    configured_dirs.append(str(candidate))
                    known_dirs.add(key)
        self.user_data.save()
        self.mods: list[ModFile] = []

        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        heading = QLabel("MainOrginizer — менеджер модификаций Minecraft")
        heading.setStyleSheet("font-size: 20px; font-weight: 600;")
        layout.addWidget(heading)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        self._build_instances_tab()
        self._build_library_tab()
        self._build_profiles_tab()
        self._build_environment_tab()
        self._build_virtualization_tab()
        self._build_menu_bar()
        self._build_assets_tab()
        self._build_config_backups_tab()
        self.table.customContextMenuRequested.connect(lambda pos: self._show_table_context_menu(self.table, pos))
        self.library_table.customContextMenuRequested.connect(lambda pos: self._show_table_context_menu(self.library_table, pos))
        self.profiles_table.customContextMenuRequested.connect(lambda pos: self._show_table_context_menu(self.profiles_table, pos))
        self.asset_table.customContextMenuRequested.connect(lambda pos: self._show_table_context_menu(self.asset_table, pos))
        self.environment_table.customContextMenuRequested.connect(lambda pos: self._show_table_context_menu(self.environment_table, pos))
        self.virtualization_table.customContextMenuRequested.connect(lambda pos: self._show_table_context_menu(self.virtualization_table, pos))
        self.asset_plan_table.customContextMenuRequested.connect(lambda pos: self._show_table_context_menu(self.asset_plan_table, pos))
        self.library_table.cellDoubleClicked.connect(lambda row, column: self.edit_selected_mod_tags())
        self.profiles_table.cellDoubleClicked.connect(lambda row, column: self.edit_profile_mods())
        self.profiles_table.currentCellChanged.connect(self._profile_row_changed)
        self.virtualization_plan: VirtualizationPlan | None = None

        self.status_label = QLabel("Готово")
        layout.addWidget(self.status_label)
        self.refresh_instances()
        self.refresh_library()
        self.refresh_profiles()
        self.refresh_environment_scan()
        self.refresh_virtualization_profiles()
        self.refresh_assets()
        self.refresh_config_backup_choices()

    def _build_instances_tab(self) -> None:
        """Создаёт вкладку игровых окружений."""
        page = QWidget()
        layout = QVBoxLayout(page)
        self.path_label = QLabel()
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.path_label)
        toolbar = QHBoxLayout()
        self.choose_button = QPushButton("Выбрать папку Prism")
        self.refresh_button = QPushButton("Обновить")
        self.choose_button.clicked.connect(self.choose_prism_folder)
        self.refresh_button.clicked.connect(self.refresh_instances)
        toolbar.addWidget(self.choose_button)
        toolbar.addWidget(self.refresh_button)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Источник", "Название", "Папка (ID)", "Minecraft", "Загрузчик", "Версия загрузчика", "Статус"]
        )
        self._configure_table(self.table)
        self.table.horizontalHeader().setSectionResizeMode(1, self.table.horizontalHeader().ResizeMode.Stretch)
        layout.addWidget(self.table, 1)
        self.add_game_dir_button = QPushButton("Добавить папку игры…")
        self.create_official_instance_button = QPushButton("Создать сборку для Minecraft Launcher…")
        self.remove_game_dir_button = QPushButton("Убрать подключённую папку")
        self.add_game_dir_button.clicked.connect(self.add_game_directory)
        self.create_official_instance_button.clicked.connect(self.create_official_launcher_instance)
        self.remove_game_dir_button.clicked.connect(self.remove_selected_game_directory)
        toolbar.insertWidget(0, self.add_game_dir_button)
        toolbar.insertWidget(1, self.create_official_instance_button)
        toolbar.insertWidget(2, self.remove_game_dir_button)
        self.tabs.addTab(page, "Игровые окружения")

    def _build_library_tab(self) -> None:
        """Создаёт вкладку общей библиотеки модов и меток."""
        page = QWidget()
        layout = QVBoxLayout(page)
        self.library_path_label = QLabel()
        self.library_path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.library_path_label)
        toolbar = QHBoxLayout()
        self.import_button = QPushButton("Импортировать JAR…")
        self.library_refresh_button = QPushButton("Обновить библиотеку")
        self.tags_button = QPushButton("Изменить метки…")
        self.import_button.clicked.connect(self.choose_mods_to_import)
        self.library_refresh_button.clicked.connect(self.refresh_library)
        self.tags_button.clicked.connect(self.edit_selected_mod_tags)
        toolbar.addWidget(self.import_button)
        toolbar.addWidget(self.library_refresh_button)
        toolbar.addWidget(self.tags_button)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)
        self.library_table = QTableWidget(0, 11)
        self.library_table.setHorizontalHeaderLabels(["Название", "Версия", "ID", "Minecraft", "Загрузчик", "Зависимости", "Совместимость", "Файл", "Размер", "Метки", "Путь"])
        self._configure_table(self.library_table)
        self.library_table.horizontalHeader().setSectionResizeMode(0, self.library_table.horizontalHeader().ResizeMode.Stretch)
        self.library_table.horizontalHeader().setSectionResizeMode(10, self.library_table.horizontalHeader().ResizeMode.Stretch)
        layout.addWidget(self.library_table, 1)
        self.tabs.addTab(page, "Библиотека модов")

    def _build_profiles_tab(self) -> None:
        """Создаёт единое окно профилей и виртуализации рядом."""
        page = QWidget()
        outer = QVBoxLayout(page)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.profile_left = QWidget()
        layout = QVBoxLayout(self.profile_left)
        layout.addWidget(QLabel("Профили сохраняют игровое окружение и выбранные моды."))
        selector = QHBoxLayout()
        selector.addWidget(QLabel("Экземпляр для нового профиля:"))
        self.profile_instance_combo = QComboBox()
        selector.addWidget(self.profile_instance_combo, 1)
        layout.addLayout(selector)
        toolbar = QHBoxLayout()
        self.create_profile_button = QPushButton("Создать профиль…")
        self.edit_profile_button = QPushButton("Изменить моды…")
        self.rename_profile_button = QPushButton("Переименовать…")
        self.delete_profile_button = QPushButton("Удалить профиль")
        self.create_profile_button.clicked.connect(self.create_profile)
        self.edit_profile_button.clicked.connect(self.edit_profile_mods)
        self.rename_profile_button.clicked.connect(self.rename_profile)
        self.delete_profile_button.clicked.connect(self.delete_profile)
        for button in (self.create_profile_button, self.edit_profile_button,
                       self.rename_profile_button, self.delete_profile_button):
            toolbar.addWidget(button)
        layout.addLayout(toolbar)
        self.profiles_table = QTableWidget(0, 5)
        self.profiles_table.setHorizontalHeaderLabels(
            ["Профиль", "Игровое окружение", "Minecraft", "Загрузчик", "Модов выбрано"]
        )
        self._configure_table(self.profiles_table)
        self.profiles_table.horizontalHeader().setSectionResizeMode(0, self.profiles_table.horizontalHeader().ResizeMode.Stretch)
        layout.addWidget(self.profiles_table, 1)
        self.profile_right = QWidget()
        splitter.addWidget(self.profile_left)
        splitter.addWidget(self.profile_right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)
        outer.addWidget(splitter, 1)
        self.tabs.addTab(page, "Профили")

    def _build_environment_tab(self) -> None:
        """Creates a read-only report of mod files in Prism instances."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel(
            "Проверка только читает файлы. Внешние моды не импортируются автоматически, "
            "а игровые каталоги не изменяются."
        ))
        toolbar = QHBoxLayout()
        self.environment_scan_button = QPushButton("Проверить окружения")
        self.environment_scan_button.clicked.connect(self.refresh_environment_scan)
        toolbar.addWidget(self.environment_scan_button)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)
        self.environment_table = QTableWidget(0, 5)
        self.environment_table.setHorizontalHeaderLabels(
            ["Экземпляр", "Файл", "Результат проверки", "Размер", "Путь"]
        )
        self._configure_table(self.environment_table)
        self.environment_table.horizontalHeader().setSectionResizeMode(
            2, self.environment_table.horizontalHeader().ResizeMode.Stretch
        )
        self.environment_table.horizontalHeader().setSectionResizeMode(
            4, self.environment_table.horizontalHeader().ResizeMode.Stretch
        )
        layout.addWidget(self.environment_table, 1)
        self.tabs.addTab(page, "Проверка окружений")

    def _build_virtualization_tab(self) -> None:
        """Builds the preview-and-apply UI for profile symlinks."""
        page = self.profile_right
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel(
            "Виртуализация профиля. Проверьте целевой путь и изменения перед применением. "
            "Перед применением закройте игру."
        ))
        selector = QHBoxLayout()
        selector.addWidget(QLabel("Профиль:"))
        self.virtualization_profile_combo = QComboBox()
        self.virtualization_profile_combo.currentIndexChanged.connect(self._refresh_profile_compatibility)
        selector.addWidget(self.virtualization_profile_combo, 1)
        layout.addLayout(selector)
        toolbar = QHBoxLayout()
        self.preview_virtualization_button = QPushButton("Предварительный просмотр")
        self.apply_virtualization_button = QPushButton("Применить профиль")
        self.rollback_virtualization_button = QPushButton("Откатить последнее применение")
        self.check_conflicts_button = QPushButton("Проверить конфликты")
        self.check_conflicts_button.clicked.connect(self.check_selected_profile_conflicts)
        self.preview_virtualization_button.clicked.connect(self.preview_selected_profile)
        self.apply_virtualization_button.clicked.connect(self.apply_selected_profile)
        self.rollback_virtualization_button.clicked.connect(self.rollback_virtualization)
        toolbar.addWidget(self.preview_virtualization_button)
        toolbar.addWidget(self.apply_virtualization_button)
        toolbar.addWidget(self.rollback_virtualization_button)
        toolbar.addWidget(self.check_conflicts_button)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)
        self.virtualization_path_label = QLabel("Сначала выберите профиль.")
        self.virtualization_path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.virtualization_path_label)
        self.virtualization_table = QTableWidget(0, 3)
        self.virtualization_table.setHorizontalHeaderLabels(["Файл", "Действие", "Подробности"])
        self._configure_table(self.virtualization_table)
        self.virtualization_table.horizontalHeader().setSectionResizeMode(2, self.virtualization_table.horizontalHeader().ResizeMode.Stretch)
        layout.addWidget(self.virtualization_table, 1)

    def _build_menu_bar(self) -> None:
        """Создаёт стандартные меню приложения."""
        file_menu = self.menuBar().addMenu("Файл")
        import_action = file_menu.addAction("Импортировать моды…")
        import_action.triggered.connect(self.choose_mods_to_import)
        file_menu.addSeparator()
        file_menu.addAction("Выход", self.close)
        view_menu = self.menuBar().addMenu("Вид")
        for index, title in enumerate(["Игровые окружения", "Библиотека модов", "Профили", "Проверка окружений", "Ресурспаки и шейдеры", "Конфиги и резервные копии"]):
            action = view_menu.addAction(title)
            action.triggered.connect(lambda checked=False, tab_index=index: self.tabs.setCurrentIndex(tab_index))
        settings_menu = self.menuBar().addMenu("Настройки")
        settings_menu.addAction("Открыть папку библиотеки", self.open_library_folder)
        help_menu = self.menuBar().addMenu("Помощь")
        help_menu.addAction("О программе", lambda: QMessageBox.about(self, "О MainOrginizer", "MainOrginizer — менеджер профилей и модификаций Minecraft."))

    def open_library_folder(self) -> None:
        """Открывает папку библиотеки модов."""
        self.library_dir.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.library_dir)))

    def _build_assets_tab(self) -> None:
        """Creates asset library, profile selection, and safe apply controls."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel(
            "ZIP-архивы ресурспаков и шейдеров копируются в отдельную библиотеку. "
            "Применение профиля создаёт ссылки; обычные файлы не перезаписываются."
        ))
        toolbar = QHBoxLayout()
        self.asset_kind_combo = QComboBox()
        self.asset_kind_combo.addItem("Ресурспаки", "resourcepacks")
        self.asset_kind_combo.addItem("Шейдеры", "shaderpacks")
        self.asset_kind_combo.currentIndexChanged.connect(self.refresh_assets)
        self.asset_import_button = QPushButton("Импортировать ZIP…")
        self.asset_refresh_button = QPushButton("Обновить библиотеку")
        self.asset_assign_button = QPushButton("Выбрать для профиля…")
        self.asset_import_button.clicked.connect(self.choose_assets_to_import)
        self.asset_refresh_button.clicked.connect(self.refresh_assets)
        self.asset_assign_button.clicked.connect(self.assign_assets_to_profile)
        for button in (self.asset_kind_combo, self.asset_import_button, self.asset_refresh_button, self.asset_assign_button):
            toolbar.addWidget(button)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)
        self.asset_table = QTableWidget(0, 3)
        self.asset_table.setHorizontalHeaderLabels(["Архив", "Размер", "Путь"])
        self._configure_table(self.asset_table)
        self.asset_table.horizontalHeader().setSectionResizeMode(0, self.asset_table.horizontalHeader().ResizeMode.Stretch)
        self.asset_table.horizontalHeader().setSectionResizeMode(2, self.asset_table.horizontalHeader().ResizeMode.Stretch)
        layout.addWidget(self.asset_table, 1)
        profile_row = QHBoxLayout()
        profile_row.addWidget(QLabel("Профиль для применения:"))
        self.asset_profile_combo = QComboBox()
        self.asset_profile_combo.currentIndexChanged.connect(self.preview_selected_assets)
        profile_row.addWidget(self.asset_profile_combo, 1)
        self.asset_preview_button = QPushButton("Предпросмотр")
        self.asset_apply_button = QPushButton("Применить ассеты")
        self.asset_rollback_button = QPushButton("Откатить ассеты")
        self.asset_preview_button.clicked.connect(self.preview_selected_assets)
        self.asset_apply_button.clicked.connect(self.apply_selected_assets)
        self.asset_rollback_button.clicked.connect(self.rollback_selected_assets)
        profile_row.addWidget(self.asset_preview_button)
        profile_row.addWidget(self.asset_apply_button)
        profile_row.addWidget(self.asset_rollback_button)
        layout.addLayout(profile_row)
        self.asset_preview_label = QLabel("Выберите профиль для просмотра изменений.")
        self.asset_preview_label.setWordWrap(True)
        self.asset_preview_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.asset_preview_label)
        self.asset_plan_table = QTableWidget(0, 3)
        self.asset_plan_table.setHorizontalHeaderLabels(["Архив", "Действие", "Подробности"])
        self._configure_table(self.asset_plan_table)
        self.asset_plan_table.horizontalHeader().setSectionResizeMode(2, self.asset_plan_table.horizontalHeader().ResizeMode.Stretch)
        layout.addWidget(self.asset_plan_table, 1)
        self.tabs.addTab(page, "Ресурспаки и шейдеры")

    def _build_config_backups_tab(self) -> None:
        """Creates manual backup and restore controls for instance configs."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel(
            "Резервная копия архивирует папку config выбранного экземпляра. "
            "Восстановление сначала сохраняет текущие конфиги и не удаляет файлы, отсутствующие в архиве."
        ))
        row = QHBoxLayout()
        row.addWidget(QLabel("Игровое окружение:"))
        self.config_instance_combo = QComboBox()
        row.addWidget(self.config_instance_combo, 1)
        self.config_backup_button = QPushButton("Создать резервную копию")
        self.config_backup_button.clicked.connect(self.backup_selected_config)
        row.addWidget(self.config_backup_button)
        layout.addLayout(row)
        backup_row = QHBoxLayout()
        backup_row.addWidget(QLabel("Архив для восстановления:"))
        self.config_backup_combo = QComboBox()
        backup_row.addWidget(self.config_backup_combo, 1)
        self.config_restore_button = QPushButton("Восстановить архив…")
        self.config_restore_button.clicked.connect(self.restore_selected_config)
        backup_row.addWidget(self.config_restore_button)
        self.config_refresh_button = QPushButton("Обновить список")
        self.config_refresh_button.clicked.connect(self.refresh_config_backup_choices)
        backup_row.addWidget(self.config_refresh_button)
        layout.addLayout(backup_row)
        self.tabs.addTab(page, "Конфиги и резервные копии")

    def refresh_virtualization_profiles(self) -> None:
        """Refreshes the profile selector while preserving its current choice."""
        if not hasattr(self, "virtualization_profile_combo"):
            return
        previous_id = self.virtualization_profile_combo.currentData()
        self.virtualization_profile_combo.blockSignals(True)
        self.virtualization_profile_combo.clear()
        for profile in self.user_data.profiles():
            label = f"{profile.get('name', '(без имени)')} — {profile.get('instance_id', '')}"
            self.virtualization_profile_combo.addItem(label, profile.get("id"))
        for index in range(self.virtualization_profile_combo.count()):
            if self.virtualization_profile_combo.itemData(index) == previous_id:
                self.virtualization_profile_combo.setCurrentIndex(index)
                break
        self.virtualization_profile_combo.blockSignals(False)
        self.preview_selected_profile()
        if hasattr(self, "asset_profile_combo"):
            previous_asset_id = self.asset_profile_combo.currentData()
            self.asset_profile_combo.blockSignals(True)
            self.asset_profile_combo.clear()
            for profile in self.user_data.profiles():
                self.asset_profile_combo.addItem(f"{profile.get('name', '(без имени)')} — {profile.get('instance_id', '')}", profile.get("id"))
            for index in range(self.asset_profile_combo.count()):
                if self.asset_profile_combo.itemData(index) == previous_asset_id:
                    self.asset_profile_combo.setCurrentIndex(index)
                    break
            self.asset_profile_combo.blockSignals(False)
            self.preview_selected_assets()
        if hasattr(self, "config_instance_combo"):
            self.refresh_config_instance_choices()
        if hasattr(self, "library_table"):
            self.refresh_library()

    def _refresh_profile_compatibility(self) -> None:
        """Обновляет статусы совместимости для выбранного профиля."""
        if hasattr(self, "library_table"):
            self.refresh_library()
        else:
            self.preview_selected_profile()

    def _virtualization_profile(self) -> dict | None:
        """Returns the profile selected for virtualization."""
        profile_id = self.virtualization_profile_combo.currentData()
        return next((profile for profile in self.user_data.profiles() if profile.get("id") == profile_id), None)

    def preview_selected_profile(self) -> None:
        """Displays a non-mutating plan for the selected profile."""
        if not hasattr(self, "virtualization_table"):
            return
        profile = self._virtualization_profile()
        self.virtualization_plan = None
        if profile is None:
            self.virtualization_table.setRowCount(0)
            self.virtualization_path_label.setText("Нет профилей. Создайте профиль на вкладке «Профили».")
            self.apply_virtualization_button.setEnabled(False)
            return
        plan = preview_profile(profile, self.library_dir)
        self.virtualization_plan = plan
        self.virtualization_table.setSortingEnabled(False)
        self.virtualization_table.setRowCount(len(plan.actions))
        for row, action in enumerate(plan.actions):
            self._set_item(self.virtualization_table, row, 0, action.filename, action.filename.casefold(), str(action.path))
            self._set_item(self.virtualization_table, row, 1, action.action, action.action.casefold(), str(action.path))
            self._set_item(self.virtualization_table, row, 2, action.details, action.details.casefold(), str(action.path))
        self.virtualization_table.setSortingEnabled(True)
        target = str(plan.mods_dir) if plan.mods_dir else "папка mods не найдена"
        summary = f"Целевая папка: {target}"
        if plan.errors:
            summary += "\nПроблемы: " + "; ".join(plan.errors)
        else:
            creates = sum(action.action == "Создать ссылку" for action in plan.actions)
            removes = sum(action.action == "Убрать ссылку" for action in plan.actions)
            summary += f"\nБудет создано ссылок: {creates}; удалено управляемых ссылок: {removes}."
        self.virtualization_path_label.setText(summary)
        self.apply_virtualization_button.setEnabled(plan.can_apply)

    def apply_selected_profile(self) -> None:
        """Confirms and applies the selected profile after previewing changes."""
        profile = self._virtualization_profile()
        if profile is None:
            return
        self.preview_selected_profile()
        plan = self.virtualization_plan
        if plan is None or not plan.can_apply:
            QMessageBox.information(self, "Виртуализация", "Нет безопасных изменений для применения. Проверьте предварительный просмотр.")
            return
        creates = sum(action.action == "Создать ссылку" for action in plan.actions)
        removes = sum(action.action == "Убрать ссылку" for action in plan.actions)
        answer = QMessageBox.warning(
            self, "Применить профиль",
            f"Применить профиль «{profile.get('name', '')}»?\n\n"
            f"Будет создано ссылок: {creates}; убрано ссылок MainOrginizer: {removes}.\n"
            "Обычные файлы останутся без изменений. Закройте Minecraft перед продолжением.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        success, message = apply_profile(profile, self.library_dir)
        if success:
            QMessageBox.information(self, "Виртуализация", message)
            self.refresh_environment_scan()
            self.preview_selected_profile()
        else:
            QMessageBox.critical(self, "Ошибка виртуализации", message)
            self.preview_selected_profile()

    def rollback_virtualization(self) -> None:
        """Reverts the most recent completed virtualization operation."""
        answer = QMessageBox.question(
            self, "Откат виртуализации",
            "Отменить последнее применение профиля? Файлы, изменённые вручную после применения, будут сохранены.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        success, message = rollback_last(library_dir=self.library_dir)
        if success:
            QMessageBox.information(self, "Откат", message)
            self.refresh_environment_scan()
            self.preview_selected_profile()
        else:
            QMessageBox.warning(self, "Откат", message)

    def _asset_kind(self) -> str:
        """Returns the active asset category."""
        return str(self.asset_kind_combo.currentData() or "resourcepacks")

    def refresh_assets(self) -> None:
        """Scans and displays the selected asset library."""
        if not hasattr(self, "asset_table"):
            return
        kind = self._asset_kind()
        assets = scan_assets(self.asset_library_dir, kind)
        self.asset_table.setSortingEnabled(False)
        self.asset_table.setRowCount(len(assets))
        for row, asset in enumerate(assets):
            values = [asset.name, self._format_size(asset.size), str(asset.path)]
            sorts = [asset.name.casefold(), asset.size, str(asset.path).casefold()]
            for column, value in enumerate(values):
                self._set_item(self.asset_table, row, column, value, sorts[column], str(asset.path))
        self.asset_table.setSortingEnabled(True)
        self.preview_selected_assets()

    def choose_assets_to_import(self) -> None:
        """Copies selected ZIP archives into the active asset category."""
        kind = self._asset_kind()
        title = "Выберите ресурспаки" if kind == "resourcepacks" else "Выберите шейдерпаки"
        selected, _ = QFileDialog.getOpenFileNames(self, title, str(Path.home()), "ZIP-архивы (*.zip)")
        if not selected:
            return
        imported, skipped, errors = import_assets([Path(path) for path in selected], self.asset_library_dir, kind)
        self.refresh_assets()
        message = f"Импортировано: {imported}\nПропущено (дубликаты или неподходящие файлы): {skipped}"
        if errors:
            message += "\n\nОшибки:\n" + "\n".join(errors[:10])
        QMessageBox.information(self, "Импорт ассетов", message)

    def assign_assets_to_profile(self) -> None:
        """Stores selected asset hashes in the chosen profile."""
        profile_id = self.asset_profile_combo.currentData()
        profile = next((item for item in self.user_data.profiles() if item.get("id") == profile_id), None)
        if profile is None:
            QMessageBox.information(self, "Ассеты профиля", "Сначала создайте профиль.")
            return
        kind = self._asset_kind()
        field = "enabled_resourcepack_hashes" if kind == "resourcepacks" else "enabled_shaderpack_hashes"
        dialog = ModSelectionDialog(scan_assets(self.asset_library_dir, kind), set(profile.get(field, [])))
        dialog.setWindowTitle("Выбор ресурспаков" if kind == "resourcepacks" else "Выбор шейдерпаков")
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.user_data.update_profile_assets(profile_id, kind, dialog.selected_hashes())
            self.preview_selected_assets()
            QMessageBox.information(self, "Ассеты профиля", "Состав сохранён. Чтобы изменить файлы игры, отдельно примените профиль.")

    def _asset_profile(self) -> dict | None:
        """Returns the profile selected for asset application."""
        profile_id = self.asset_profile_combo.currentData()
        return next((profile for profile in self.user_data.profiles() if profile.get("id") == profile_id), None)

    def preview_selected_assets(self) -> None:
        """Shows planned asset changes without modifying files."""
        if not hasattr(self, "asset_plan_table"):
            return
        profile = self._asset_profile()
        if profile is None:
            self.asset_plan_table.setRowCount(0)
            self.asset_preview_label.setText("Создайте профиль, чтобы управлять ресурспаками и шейдерами.")
            self.asset_apply_button.setEnabled(False)
            return
        plan = preview_assets(profile, self.asset_library_dir, self._asset_kind())
        self.asset_plan_table.setSortingEnabled(False)
        self.asset_plan_table.setRowCount(len(plan.actions))
        for row, action in enumerate(plan.actions):
            for column, value in enumerate((action.filename, action.action, action.details)):
                self._set_item(self.asset_plan_table, row, column, value, value.casefold(), str(action.path))
        self.asset_plan_table.setSortingEnabled(True)
        summary = f"Целевой каталог: {plan.target_dir}"
        if plan.errors:
            summary += "\nПроблемы: " + "; ".join(plan.errors)
        else:
            creates = sum(action.action == "Создать ссылку" for action in plan.actions)
            removes = sum(action.action == "Убрать ссылку" for action in plan.actions)
            summary += f"\nБудет создано ссылок: {creates}; убрано управляемых ссылок: {removes}."
        self.asset_preview_label.setText(summary)
        self.asset_apply_button.setEnabled(plan.can_apply)

    def apply_selected_assets(self) -> None:
        """Confirms and applies resource pack or shader pack links."""
        profile = self._asset_profile()
        if profile is None:
            return
        self.preview_selected_assets()
        if not self.asset_apply_button.isEnabled():
            QMessageBox.information(self, "Ассеты", "Нет безопасных изменений для применения.")
            return
        answer = QMessageBox.warning(self, "Применить ассеты", "Применить выбранные архивы? Закройте Minecraft перед продолжением.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
        if answer != QMessageBox.StandardButton.Yes:
            return
        success, message = apply_assets(profile, self.asset_library_dir, self._asset_kind())
        (QMessageBox.information if success else QMessageBox.critical)(self, "Ассеты", message)
        self.preview_selected_assets()

    def rollback_selected_assets(self) -> None:
        """Rolls back the latest asset application."""
        answer = QMessageBox.question(self, "Откат ассетов", "Отменить последнее применение ресурспаков/шейдеров?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
        if answer != QMessageBox.StandardButton.Yes:
            return
        success, message = rollback_assets(library_root=self.asset_library_dir)
        (QMessageBox.information if success else QMessageBox.warning)(self, "Откат ассетов", message)
        self.preview_selected_assets()

    def refresh_config_instance_choices(self) -> None:
        """Refreshes the Prism instance list for config backup operations."""
        if not hasattr(self, "config_instance_combo"):
            return
        previous = self.config_instance_combo.currentData()
        self.config_instance_combo.clear()
        for instance in self.instances:
            self.config_instance_combo.addItem(f"{instance.launcher}: {instance.name} — {instance.minecraft_version}", str(instance.path))
        index = self.config_instance_combo.findData(previous)
        if index >= 0:
            self.config_instance_combo.setCurrentIndex(index)

    def refresh_config_backup_choices(self) -> None:
        """Refreshes the available config backup archives."""
        if not hasattr(self, "config_backup_combo"):
            return
        previous = self.config_backup_combo.currentData()
        self.config_backup_combo.clear()
        for path in list_config_backups():
            self.config_backup_combo.addItem(path.name, str(path))
        index = self.config_backup_combo.findData(previous)
        if index >= 0:
            self.config_backup_combo.setCurrentIndex(index)
        if hasattr(self, "config_instance_combo"):
            self.refresh_config_instance_choices()

    def backup_selected_config(self) -> None:
        """Creates a backup of the selected instance config directory."""
        path = self.config_instance_combo.currentData()
        if not path:
            QMessageBox.information(self, "Резервные копии", "Сначала выберите экземпляр Prism.")
            return
        success, message = create_config_backup(Path(path))
        (QMessageBox.information if success else QMessageBox.warning)(self, "Резервная копия", message)
        self.refresh_config_backup_choices()

    def restore_selected_config(self) -> None:
        """Restores the selected backup after explicit confirmation."""
        instance_path = self.config_instance_combo.currentData()
        backup_path = self.config_backup_combo.currentData()
        if not instance_path or not backup_path:
            QMessageBox.information(self, "Восстановление", "Выберите экземпляр и архив.")
            return
        answer = QMessageBox.warning(self, "Восстановить конфиги", "Перед восстановлением будет создана копия текущих конфигов. Файлы, отсутствующие в архиве, удаляться не будут. Продолжить?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
        if answer != QMessageBox.StandardButton.Yes:
            return
        success, message = restore_config_backup(Path(backup_path), Path(instance_path))
        (QMessageBox.information if success else QMessageBox.critical)(self, "Восстановление конфигов", message)
        self.refresh_config_backup_choices()

    def refresh_environment_scan(self) -> None:
        """Scans instance mods folders without importing or changing files."""
        if not hasattr(self, "environment_table"):
            return
        findings = scan_environment_mods(self.instances, self.library_dir)
        self.environment_table.setSortingEnabled(False)
        self.environment_table.setRowCount(len(findings))
        for row, finding in enumerate(findings):
            size = self._format_size(finding.size) if finding.size is not None else "—"
            values = [finding.instance_name, finding.filename, finding.status,
                      size, str(finding.path)]
            sort_values = [value.casefold() for value in values]
            sort_values[3] = finding.size if finding.size is not None else -1
            for column, value in enumerate(values):
                self._set_item(self.environment_table, row, column, value,
                               sort_values[column], str(finding.path))
        self.environment_table.setSortingEnabled(True)
        external_count = sum(
            finding.status == "Внешний мод — не импортирован" for finding in findings
        )
        self.status_label.setText(
            f"Проверка окружений завершена: {len(findings)} записей, "
            f"внешних модов не импортировано: {external_count}"
        )

    @staticmethod
    def _configure_table(table: QTableWidget) -> None:
        """Настраивает таблицу и включает сортировку."""
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setSortingEnabled(True)
        table.horizontalHeader().setStretchLastSection(True)
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    def _set_item(self, table: QTableWidget, row: int, column: int, value: str,
                  sort_value: object | None = None, tooltip: str = "") -> None:
        """Добавляет ячейку с ключом сортировки и подсказкой."""
        item = NaturalSortItem(value)
        if sort_value is not None:
            item.setData(Qt.ItemDataRole.UserRole, sort_value)
        if tooltip:
            item.setToolTip(tooltip)
            item.setData(Qt.ItemDataRole.UserRole + 2, tooltip)
        table.setItem(row, column, item)

    def _show_table_context_menu(self, table: QTableWidget, position) -> None:
        """Показывает набор действий, подходящий выбранной таблице."""
        index = table.indexAt(position)
        if not index.isValid():
            return
        table.setCurrentCell(index.row(), index.column())
        menu = QMenu(self)
        if table is self.library_table:
            edit_tags = menu.addAction("Изменить метки…")
            rename = menu.addAction("Переименовать файл…")
            delete = menu.addAction("Удалить из библиотеки…")
            menu.addSeparator()
            open_folder = menu.addAction("Открыть папку с файлом")
            copy_path = menu.addAction("Копировать путь")
            chosen = menu.exec(table.viewport().mapToGlobal(position))
            if chosen == edit_tags:
                self.edit_selected_mod_tags()
            elif chosen == rename:
                self.rename_selected_mod()
            elif chosen == delete:
                self.delete_selected_mod()
            elif chosen == copy_path:
                self._copy_selected_path(table, 10)
            elif chosen == open_folder:
                self._open_selected_path(table)
        elif table is self.profiles_table:
            edit = menu.addAction("Изменить состав модов…")
            rename = menu.addAction("Переименовать профиль…")
            delete = menu.addAction("Удалить профиль…")
            chosen = menu.exec(table.viewport().mapToGlobal(position))
            if chosen == edit:
                self.edit_profile_mods()
            elif chosen == rename:
                self.rename_profile()
            elif chosen == delete:
                self.delete_profile()
        elif table is self.asset_table:
            rename = menu.addAction("Переименовать файл…")
            delete = menu.addAction("Удалить из библиотеки…")
            open_folder = menu.addAction("Открыть папку с файлом")
            copy_path = menu.addAction("Копировать путь")
            chosen = menu.exec(table.viewport().mapToGlobal(position))
            if chosen == rename:
                self.rename_selected_asset()
            elif chosen == delete:
                self.delete_selected_asset()
            elif chosen == copy_path:
                self._copy_selected_path(table, 2)
            elif chosen == open_folder:
                self._open_selected_path(table)
        else:
            open_folder = menu.addAction("Открыть папку")
            copy_path = menu.addAction("Копировать путь")
            chosen = menu.exec(table.viewport().mapToGlobal(position))
            if chosen == copy_path:
                self._copy_selected_path(table, table.currentColumn())
            elif chosen == open_folder:
                self._open_selected_path(table)

    def _selected_path(self, table: QTableWidget) -> Path | None:
        """Получает путь строки из служебных данных ячейки."""
        row, column = table.currentRow(), table.currentColumn()
        item = table.item(row, column) if row >= 0 and column >= 0 else None
        if item is None:
            return None
        raw = item.data(Qt.ItemDataRole.UserRole + 2)
        if not raw:
            raw = item.toolTip()
        try:
            candidate = Path(str(raw))
            return candidate if candidate.exists() or candidate.is_symlink() else None
        except (OSError, TypeError, ValueError):
            return None

    def _open_selected_path(self, table: QTableWidget) -> None:
        """Открывает файл или содержащую его папку системным файловым менеджером."""
        path = self._selected_path(table)
        if path is None:
            return
        target = path.parent if path.is_file() or path.is_symlink() else path
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def _copy_selected_path(self, table: QTableWidget, column: int) -> None:
        """Копирует путь выбранного файла/экземпляра."""
        row = table.currentRow()
        item = table.item(row, column) if row >= 0 else None
        if item is None:
            return
        raw = item.data(Qt.ItemDataRole.UserRole + 2) or item.toolTip() or item.text()
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(str(raw))
        self.status_label.setText("Путь скопирован в буфер обмена")

    def _path_is_link_target(self, target: Path) -> bool:
        """Проверяет, используется ли файл как цель символической ссылки в Prism."""
        for instance in self.instances:
            for folder_name in ("mods", "resourcepacks", "shaderpacks"):
                folder = instance.path / folder_name
                try:
                    for entry in folder.iterdir():
                        if entry.is_symlink():
                            try:
                                if entry.resolve() == target.resolve():
                                    return True
                            except OSError:
                                continue
                except OSError:
                    continue
        return False

    def rename_selected_mod(self) -> None:
        """Переименовывает JAR без изменения его содержимого."""
        row = self.library_table.currentRow()
        if row < 0:
            return
        path = Path(self.library_table.item(row, 10).text())
        if self._path_is_link_target(path):
            QMessageBox.warning(self, "Переименование запрещено", "Мод сейчас используется символической ссылкой в игровом окружении. Сначала уберите его из активного профиля.")
            return
        name, accepted = QInputDialog.getText(self, "Переименовать мод", "Новое имя файла (с .jar):", text=path.name)
        if not accepted or not name.strip() or name.strip() == path.name:
            return
        new_name = Path(name.strip()).name
        if Path(new_name).suffix.lower() != ".jar" or new_name in {".", ".."}:
            QMessageBox.warning(self, "Некорректное имя", "Укажите имя JAR-файла с расширением .jar.")
            return
        destination = path.with_name(new_name)
        if destination.exists():
            QMessageBox.warning(self, "Файл существует", "Файл с таким именем уже есть в библиотеке.")
            return
        try:
            path.rename(destination)
        except OSError as error:
            QMessageBox.critical(self, "Переименование", str(error))
            return
        self.refresh_library()

    def delete_selected_mod(self) -> None:
        """Удаляет мод из библиотеки после подтверждения."""
        row = self.library_table.currentRow()
        if row < 0:
            return
        path = Path(self.library_table.item(row, 10).text())
        if self._path_is_link_target(path):
            QMessageBox.warning(self, "Удаление запрещено", "Мод сейчас используется символической ссылкой в игровом окружении. Сначала уберите его из активного профиля.")
            return
        answer = QMessageBox.question(self, "Удалить мод", f"Удалить «{path.name}» из общей библиотеки? Профили, содержащие этот мод, потеряют ссылку на него.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            path.unlink()
        except OSError as error:
            QMessageBox.critical(self, "Удаление", str(error))
            return
        self.refresh_library()
        self.refresh_profiles()

    def rename_selected_asset(self) -> None:
        """Переименовывает архив ассета, если он не используется активной ссылкой."""
        row = self.asset_table.currentRow()
        if row < 0:
            return
        path = Path(self.asset_table.item(row, 2).text())
        if self._path_is_link_target(path):
            QMessageBox.warning(self, "Переименование запрещено", "Архив используется символической ссылкой. Сначала уберите его из активного профиля.")
            return
        name, accepted = QInputDialog.getText(self, "Переименовать архив", "Новое имя файла (с .zip):", text=path.name)
        if not accepted or not name.strip() or name.strip() == path.name:
            return
        new_name = Path(name.strip()).name
        if Path(new_name).suffix.lower() != ".zip":
            QMessageBox.warning(self, "Некорректное имя", "Укажите имя ZIP-файла с расширением .zip.")
            return
        destination = path.with_name(new_name)
        if destination.exists():
            QMessageBox.warning(self, "Файл существует", "Файл с таким именем уже есть.")
            return
        try:
            path.rename(destination)
        except OSError as error:
            QMessageBox.critical(self, "Переименование", str(error))
            return
        self.refresh_assets()

    def delete_selected_asset(self) -> None:
        """Удаляет архив из библиотеки после проверки использования и подтверждения."""
        row = self.asset_table.currentRow()
        if row < 0:
            return
        path = Path(self.asset_table.item(row, 2).text())
        if self._path_is_link_target(path):
            QMessageBox.warning(self, "Удаление запрещено", "Архив используется символической ссылкой. Сначала уберите его из активного профиля.")
            return
        answer = QMessageBox.question(self, "Удалить архив", f"Удалить «{path.name}» из библиотеки? Профили, содержащие его, больше не смогут применить этот архив.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            path.unlink()
        except OSError as error:
            QMessageBox.critical(self, "Удаление", str(error))
            return
        self.refresh_assets()

    def choose_prism_folder(self) -> None:
        """Позволяет выбрать каталог данных Prism вручную."""
        selected = QFileDialog.getExistingDirectory(
            self, "Выберите каталог данных Prism Launcher", str(self.prism_data_dir or Path.home())
        )
        if not selected:
            return
        selected_path = Path(selected)
        if not is_prism_data_dir(selected_path):
            QMessageBox.warning(self, "Каталог не распознан",
                                "В выбранной папке не найдена подпапка instances. "
                                "Выберите корневой каталог данных Prism Launcher.")
            return
        self.prism_data_dir = selected_path
        self.refresh_instances()

    def create_official_launcher_instance(self) -> None:
        """Создаёт отдельный игровой каталог для установки официального лаунчера."""
        candidates = [path for path in default_game_directory_candidates()
                      if path.name.casefold() == ".minecraft"]
        base = candidates[0] if candidates else Path.home() / ".minecraft"
        instances_dir = base / "instances"
        name, accepted = QInputDialog.getText(
            self, "Новая сборка", "Название сборки (например, Fabric-1.21.1):"
        )
        if not accepted:
            return
        name = name.strip()
        if not name or name in {".", ".."} or any(char in name for char in '<>:/\\|?*'):
            QMessageBox.warning(self, "Некорректное название", "Название не должно содержать запрещённые символы пути Windows.")
            return
        target = instances_dir / name
        if target.exists():
            QMessageBox.warning(self, "Папка уже существует", f"Каталог уже существует:\n{target}")
            return
        try:
            for folder in ("mods", "config", "resourcepacks", "shaderpacks", "saves"):
                (target / folder).mkdir(parents=True, exist_ok=True)
        except OSError as error:
            QMessageBox.critical(self, "Не удалось создать сборку", str(error))
            return
        configured_dirs = self.user_data.data.setdefault("game_dirs", [])
        base_key = str(base.resolve(strict=False)).casefold()
        if not any(isinstance(value, str) and str(Path(value).resolve(strict=False)).casefold() == base_key
                   for value in configured_dirs):
            configured_dirs.append(str(base))
        self.user_data.save()
        self.refresh_instances()
        QMessageBox.information(
            self, "Сборка создана",
            "Каталог сборки создан. Теперь откройте официальный Minecraft Launcher, "
            "измените нужную установку и укажите этот путь в поле «Каталог игры» (Game Directory):\n\n"
            f"{target}\n\nМоды и настройки этой установки будут храниться отдельно."
        )

    def add_game_directory(self) -> None:
        """Подключает игровую папку Minecraft, TLauncher или Legacy Launcher."""
        selected = QFileDialog.getExistingDirectory(
            self, "Выберите игровую папку Minecraft", str(Path.home())
        )
        if not selected:
            return
        path = Path(selected)
        if not is_game_directory(path):
            QMessageBox.warning(
                self, "Папка не распознана",
                "В папке не найдены типичные каталоги Minecraft: versions, mods, assets или libraries. "
                "В Legacy Launcher выберите именно папку игры через кнопку открытия папки в лаунчере.",
            )
            return
        paths = self.user_data.data.setdefault("game_dirs", [])
        key = str(path.resolve(strict=False)).casefold()
        if any(str(Path(value).resolve(strict=False)).casefold() == key for value in paths if isinstance(value, str)):
            QMessageBox.information(self, "Уже подключено", "Эта игровая папка уже подключена.")
            return
        paths.append(str(path))
        self.user_data.save()
        self.refresh_instances()

    def remove_selected_game_directory(self) -> None:
        """Отключает выбранную внешнюю папку, не удаляя её файлы."""
        row = self.table.currentRow()
        if row < 0:
            return
        path_item = self.table.item(row, 2)
        if path_item is None:
            return
        selected_path = str(Path(path_item.toolTip() or path_item.text()).resolve(strict=False))
        stored = self.user_data.data.setdefault("game_dirs", [])
        selected_resolved = Path(selected_path)
        matching = None
        for value in stored:
            if not isinstance(value, str):
                continue
            registered = Path(value).resolve(strict=False)
            try:
                selected_resolved.relative_to(registered)
                matching = value
                break
            except ValueError:
                if str(registered).casefold() == selected_path.casefold():
                    matching = value
                    break
        if matching is None:
            QMessageBox.information(self, "Отключение папки", "Выбранное окружение не связано с подключённой папкой, которую можно отключить этой кнопкой.")
            return
        answer = QMessageBox.question(
            self, "Отключить папку", "Убрать папку из MainOrginizer? Файлы Minecraft не будут удалены.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        stored.remove(matching)
        self.user_data.save()
        self.refresh_instances()

    def refresh_instances(self) -> None:
        """Сканирует Prism и автоматически обнаруженные игровые папки TLauncher/Legacy."""
        self.table.setSortingEnabled(False)
        instances: list[PrismInstance] = []
        prism_available = self.prism_data_dir is not None and is_prism_data_dir(self.prism_data_dir)
        if prism_available and self.prism_data_dir is not None:
            instances.extend(scan_instances(self.prism_data_dir))
            prism_label = f"Prism: {self.prism_data_dir}"
        else:
            prism_label = "Prism не найден автоматически; при необходимости выберите каталог данных вручную."

        configured_dirs = self.user_data.data.setdefault("game_dirs", [])
        known_dirs = {
            str(Path(value).resolve(strict=False)).casefold()
            for value in configured_dirs if isinstance(value, str)
        }
        added_default = False
        for candidate in default_game_directory_candidates():
            if not is_game_directory(candidate):
                continue
            candidate_key = str(candidate.resolve(strict=False)).casefold()
            if candidate_key not in known_dirs:
                configured_dirs.append(str(candidate))
                known_dirs.add(candidate_key)
                added_default = True
        if added_default:
            self.user_data.save()

        known_paths = {str(instance.path.resolve(strict=False)).casefold() for instance in instances}
        for value in configured_dirs:
            if not isinstance(value, str):
                continue
            path = Path(value)
            if not is_game_directory(path):
                continue
            key = str(path.resolve(strict=False)).casefold()
            if key in known_paths:
                continue
            discovered = discover_game_environments(path, launcher_for_game_directory(path))
            for instance in discovered:
                instance_key = str(instance.path.resolve(strict=False)).casefold()
                if instance_key not in known_paths:
                    instances.append(instance)
                    known_paths.add(instance_key)

        self.instances = instances
        self.path_label.setText(prism_label + "\nАвтопоиск: Minecraft Launcher / TLauncher (.minecraft), Legacy Launcher и Prism. Для официального лаунчера можно создать отдельную сборку и указать её путь в настройках установки → «Каталог игры».")
        self.table.setRowCount(len(self.instances))
        for row, instance in enumerate(self.instances):
            values = [instance.launcher, instance.name, instance.instance_id, instance.minecraft_version,
                      instance.loader, instance.loader_version or "—", instance.status]
            for column, value in enumerate(values):
                sort_value = _sort_key(value) if column in (2, 3, 5) else value.casefold()
                self._set_item(self.table, row, column, value, sort_value, str(instance.path))
        self.table.setSortingEnabled(True)
        self.status_label.setText(f"Найдено игровых окружений: {len(self.instances)}")
        self.refresh_profile_instance_choices()
        self.refresh_config_instance_choices()
        self.refresh_environment_scan()

    def refresh_profile_instance_choices(self) -> None:
        """Обновляет список экземпляров, доступных при создании профиля."""
        if not hasattr(self, "profile_instance_combo"):
            return
        previous = self.profile_instance_combo.currentData()
        previous_id = previous.get("instance_id") if isinstance(previous, dict) else None
        self.profile_instance_combo.clear()
        for instance in self.instances:
            details = {
                "instance_id": instance.instance_id,
                "instance_path": str(instance.path),
                "minecraft_version": instance.minecraft_version,
                "loader": instance.loader,
                "loader_version": instance.loader_version,
            }
            self.profile_instance_combo.addItem(f"{instance.launcher}: {instance.name} — {instance.minecraft_version} / {instance.loader}", details)
        for index in range(self.profile_instance_combo.count()):
            if self.profile_instance_combo.itemData(index).get("instance_id") == previous_id:
                self.profile_instance_combo.setCurrentIndex(index)
                break

    def choose_mods_to_import(self) -> None:
        """Копирует выбранные JAR-файлы в библиотеку."""
        selected, _ = QFileDialog.getOpenFileNames(self, "Выберите моды для импорта",
                                                   str(Path.home()), "Файлы модов (*.jar)")
        if not selected:
            return
        imported, skipped, errors = import_mods([Path(path) for path in selected], self.library_dir)
        self.refresh_library()
        message = f"Импортировано: {imported}\nПропущено (дубликаты или неподходящие файлы): {skipped}"
        if errors:
            message += "\n\nОшибки:\n" + "\n".join(errors[:10])
        QMessageBox.information(self, "Импорт модов", message)

    def refresh_library(self) -> None:
        """Сканирует библиотеку, извлекает метаданные и показывает совместимость."""
        self.library_path_label.setText(f"Библиотека: {self.library_dir}")
        self.library_table.setSortingEnabled(False)
        self.mods = scan_mods(self.library_dir)
        profile = self._virtualization_profile() if hasattr(self, "virtualization_profile_combo") else None
        metadata_by_hash = {mod.sha256: read_mod_metadata(mod.path) for mod in self.mods}
        selected_hashes = set(profile.get("enabled_mod_hashes", [])) if profile else set()
        available_mod_ids = {
            metadata_by_hash[digest].mod_id for digest in selected_hashes
            if digest in metadata_by_hash and metadata_by_hash[digest].mod_id
        } if profile else None
        self.library_table.setRowCount(len(self.mods))
        for row, mod in enumerate(self.mods):
            metadata = metadata_by_hash[mod.sha256]
            if profile:
                compatibility, reason = compatibility_for_profile(
                    metadata, str(profile.get("minecraft_version", "")), str(profile.get("loader", "")), available_mod_ids
                )
                target_text = str(profile.get("minecraft_version", "")) + " / " + str(profile.get("loader", ""))
            else:
                compatibility, reason = ("Не проверено", "Выберите профиль на вкладке «Виртуализация» для проверки совместимости.")
                target_text = ""
            tags = ", ".join(self.user_data.tags_for(mod.sha256))
            mc_text = ", ".join(metadata.minecraft_ranges) or "—"
            loader_text = ", ".join(metadata.loader_ids) or "—"
            display_name = f"[{metadata.kind}] {metadata.name or mod.path.stem}" if metadata.kind == "Плагин" else (metadata.name or mod.path.stem)
            dependencies_text = ", ".join(metadata.dependencies) or "—"
            values = [display_name, metadata.version or "—", metadata.mod_id or "—", mc_text,
                      loader_text, dependencies_text, compatibility, mod.name, self._format_size(mod.size),
                      tags or "—", str(mod.path)]
            sorts = [display_name.casefold(), _sort_key(metadata.version), metadata.mod_id.casefold(),
                     mc_text.casefold(), loader_text.casefold(), dependencies_text.casefold(), compatibility.casefold(),
                     mod.name.casefold(), mod.size, tags.casefold(), str(mod.path).casefold()]
            for column, value in enumerate(values):
                self._set_item(self.library_table, row, column, value, sorts[column], str(mod.path))
                self.library_table.item(row, column).setData(Qt.ItemDataRole.UserRole + 3, mod.sha256)
                self.library_table.item(row, column).setToolTip(
                    f"{reason}\nМетаданные: {metadata.source or 'не найдены'}\nПроверяемый профиль: {target_text}\nПуть: {mod.path}"
                )
        self.library_table.setSortingEnabled(True)
        plugin_count = sum(read_mod_metadata(mod.path).kind == "Плагин" for mod in self.mods)
        self.status_label.setText(f"Файлов в библиотеке: {len(self.mods)} (плагинов: {plugin_count})")
        self.refresh_environment_scan()
        self.preview_selected_profile()

    def check_selected_profile_conflicts(self) -> None:
        """Показывает конфликты и предупреждения выбранного профиля."""
        profile = self._virtualization_profile()
        if not profile:
            QMessageBox.information(self, "Проверка конфликтов", "Сначала выберите профиль на вкладке «Виртуализация».")
            return
        selected_hashes = set(profile.get("enabled_mod_hashes", []))
        selected_mods = [(mod.name, read_mod_metadata(mod.path)) for mod in self.mods if mod.sha256 in selected_hashes]
        conflicts = check_mod_conflicts(
            selected_mods, str(profile.get("minecraft_version", "")), str(profile.get("loader", ""))
        )
        if not conflicts:
            QMessageBox.information(self, "Проверка конфликтов", "По доступным метаданным конфликтов не обнаружено. Это не гарантирует успешный запуск игры.")
            return
        lines = [f"[{item.severity}] {item.mod_name}: {item.message}" for item in conflicts]
        title = f"Найдено предупреждений: {len(conflicts)}"
        QMessageBox.warning(self, "Проверка конфликтов", title + "\n\n" + "\n".join(lines[:40]) + ("\n… список сокращён" if len(lines) > 40 else ""))

    def edit_selected_mod_tags(self) -> None:
        """Редактирует метки выбранного файла, сохраняя их по SHA-256."""
        row = self.library_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Метки модов", "Сначала выберите мод в таблице.")
            return
        sha_item = self.library_table.item(row, 0)
        sha256 = sha_item.data(Qt.ItemDataRole.UserRole + 3)
        current = ", ".join(self.user_data.tags_for(sha256))
        tags, accepted = QInputDialog.getText(self, "Метки мода", "Метки через запятую:", text=current)
        if accepted:
            self.user_data.set_tags(sha256, [tag.strip() for tag in tags.split(",")])
            self.refresh_library()

    def create_profile(self) -> None:
        """Создаёт профиль для выбранного игрового окружения."""
        if self.profile_instance_combo.count() == 0:
            QMessageBox.information(self, "Создание профиля", "Сначала выберите игровое окружение на вкладке «Игровые окружения».")
            return
        name, accepted = QInputDialog.getText(self, "Новый профиль", "Название профиля:")
        if not accepted or not name.strip():
            return
        dialog = ModSelectionDialog(self.mods)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        instance = self.profile_instance_combo.currentData()
        self.user_data.add_profile(name, instance, dialog.selected_hashes())
        self.refresh_profiles()
        self.status_label.setText(f"Профиль «{name.strip()}» создан. Файлы игры не изменялись.")

    def _profile_row_changed(self, row: int, column: int, previous_row: int, previous_column: int) -> None:
        """Синхронизирует выбранную строку профиля с панелью виртуализации."""
        if row < 0 or not hasattr(self, "virtualization_profile_combo"):
            return
        item = self.profiles_table.item(row, 0)
        if item is None:
            return
        profile_id = item.data(Qt.ItemDataRole.UserRole + 1)
        index = self.virtualization_profile_combo.findData(profile_id)
        if index >= 0:
            self.virtualization_profile_combo.setCurrentIndex(index)

    def _selected_profile(self) -> dict | None:
        """Возвращает профиль, выбранный в таблице."""
        row = self.profiles_table.currentRow()
        if row < 0:
            return None
        profile_id = self.profiles_table.item(row, 0).data(Qt.ItemDataRole.UserRole + 1)
        return next((profile for profile in self.user_data.profiles() if profile.get("id") == profile_id), None)

    def edit_profile_mods(self) -> None:
        """Меняет сохранённый список модов профиля."""
        profile = self._selected_profile()
        if profile is None:
            QMessageBox.information(self, "Профили", "Сначала выберите профиль.")
            return
        selected = set(profile.get("enabled_mod_hashes", []))
        dialog = ModSelectionDialog(self.mods, selected)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.user_data.update_profile_mods(profile["id"], dialog.selected_hashes())
            self.refresh_profiles()

    def rename_profile(self) -> None:
        """Переименовывает выбранный профиль."""
        profile = self._selected_profile()
        if profile is None:
            QMessageBox.information(self, "Профили", "Сначала выберите профиль.")
            return
        name, accepted = QInputDialog.getText(self, "Переименовать профиль", "Новое название:",
                                              text=profile.get("name", ""))
        if accepted and name.strip():
            self.user_data.rename_profile(profile["id"], name)
            self.refresh_profiles()

    def delete_profile(self) -> None:
        """Удаляет профиль из метаданных, не затрагивая моды и экземпляр Prism."""
        profile = self._selected_profile()
        if profile is None:
            QMessageBox.information(self, "Профили", "Сначала выберите профиль.")
            return
        answer = QMessageBox.question(self, "Удалить профиль",
                                      f"Удалить профиль «{profile.get('name', '')}»? Файлы игры не будут изменены.")
        if answer == QMessageBox.StandardButton.Yes:
            self.user_data.delete_profile(profile["id"])
            self.refresh_profiles()

    def refresh_profiles(self) -> None:
        """Обновляет таблицу сохранённых профилей."""
        if not hasattr(self, "profiles_table"):
            return
        self.profiles_table.setSortingEnabled(False)
        profiles = self.user_data.profiles()
        self.profiles_table.setRowCount(len(profiles))
        for row, profile in enumerate(profiles):
            values = [str(profile.get("name", "")), str(profile.get("instance_id", "")),
                      str(profile.get("minecraft_version", "")),
                      " ".join(part for part in [str(profile.get("loader", "")),
                                                 str(profile.get("loader_version", ""))] if part),
                      str(len(profile.get("enabled_mod_hashes", [])))]
            for column, value in enumerate(values):
                sort_value = int(value) if column == 4 and value.isdigit() else _sort_key(value)
                self._set_item(self.profiles_table, row, column, value, sort_value,
                               str(profile.get("instance_path", "")))
            self.profiles_table.item(row, 0).setData(Qt.ItemDataRole.UserRole + 1, profile.get("id"))
        self.profiles_table.setSortingEnabled(True)
        self.refresh_virtualization_profiles()

    @staticmethod
    def _format_size(size: int) -> str:
        """Преобразует размер файла в читаемый формат."""
        if size < 1024 * 1024:
            return f"{size / 1024:.1f} КБ"
        return f"{size / (1024 * 1024):.2f} МБ"
