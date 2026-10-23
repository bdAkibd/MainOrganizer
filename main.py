"""MainOrginizer entry point."""

import sys

from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow


def main() -> int:
    """Start the application."""
    application = QApplication(sys.argv)
    application.setApplicationName("MainOrginizer")
    application.setOrganizationName("MainOrginizer")
    window = MainWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
