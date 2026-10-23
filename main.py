"""MineOrganizer entry point."""

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from services.app_identity import APP_NAME, app_icon_path
from ui.main_window import MainWindow


def main() -> int:
    """Start the application."""
    application = QApplication(sys.argv)
    application.setApplicationName(APP_NAME)
    application.setOrganizationName(APP_NAME)
    application.setWindowIcon(QIcon(str(app_icon_path())))
    window = MainWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
