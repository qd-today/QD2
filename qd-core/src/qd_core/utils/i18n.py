"""Internationalization (i18n) utilities for QD2.

Uses Python's built-in gettext module with Babel for translation management.
"""

import gettext as gettext_module
from pathlib import Path
from typing import Optional

# Default locale directory
_LOCALE_DIR = Path(__file__).parent.parent / "locale"
_current_translations: Optional[gettext_module.GNUTranslations] = None


def setup_i18n(locale: str = "zh_CN", locale_dir: Optional[Path] = None) -> None:
    """Initialize the i18n system.

    Args:
        locale: Locale code (e.g., 'zh_CN', 'en_US').
        locale_dir: Path to locale directory. Defaults to qd_core/locale.
    """
    global _current_translations

    if locale_dir is None:
        locale_dir = _LOCALE_DIR

    try:
        _current_translations = gettext_module.translation(
            "messages",
            localedir=str(locale_dir),
            languages=[locale],
        )
    except FileNotFoundError:
        # No translation file found, use identity function
        _current_translations = None


def gettext(message: str) -> str:
    """Translate a message string.

    Args:
        message: The message to translate.

    Returns:
        Translated message, or original if no translation found.
    """
    if _current_translations is None:
        return message
    return _current_translations.gettext(message)
