"""
main.py — QuillAI entry point.

Instantiates CodeEditor and starts the Qt event loop.
All application logic lives in editor/code_editor.py and its mixins.
"""

import sys
import os

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont

from ui.theme import apply_theme
from ui.settings_manager import SettingsManager
from editor.code_editor import CodeEditor


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("QuillAI")
    app.setOrganizationName("QuillAI")

    # Apply saved theme before the window is shown
    sm = SettingsManager()
    apply_theme(app, sm.get("theme", "gruvbox_dark"), settings_manager=sm)

    window = CodeEditor()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
