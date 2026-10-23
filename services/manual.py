"""Load the user manual shown by the Help menu."""

from pathlib import Path

from services.localization import SUPPORTED_LOCALES

MANUAL_DIR = Path(__file__).resolve().parents[1] / "docs"
DEFAULT_LOCALE = "en"


def manual_path(locale: str = DEFAULT_LOCALE) -> Path:
    """Return the localized manual path, falling back to English."""
    selected_locale = locale if locale in SUPPORTED_LOCALES else DEFAULT_LOCALE
    localized_path = MANUAL_DIR / f"manual_{selected_locale}.html"
    return localized_path if localized_path.is_file() else MANUAL_DIR / "manual_en.html"


def load_manual_html(locale: str = DEFAULT_LOCALE) -> str:
    """Return the manual for *locale*, with a safe English fallback."""
    try:
        return manual_path(locale).read_text(encoding="utf-8")
    except OSError:
        return (
            "<h1>MineOrganizer User Manual</h1>"
            "<p>The manual file could not be loaded. Please check the installation.</p>"
        )
