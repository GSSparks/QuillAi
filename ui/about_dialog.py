import os
import sys
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                              QPushButton, QWidget, QFrame, QScrollArea)
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QFont, QDesktopServices

from ui.theme import (get_theme, theme_signals,
                      build_about_dialog_stylesheet,
                      build_about_dialog_parts)


def _get_dependency_versions() -> list:
    deps = []
    checks = [
        ("Python",   None),
        ("PyQt6",    "PyQt6"),
        ("requests", "requests"),
        ("markdown", "markdown"),
        ("chardet",  "chardet"),
        ("PyYAML",   "yaml"),
    ]
    for name, module in checks:
        if module is None:
            deps.append((name, sys.version.split()[0]))
            continue
        try:
            mod = __import__(module)
            version = getattr(mod, '__version__', 'installed')
            deps.append((name, version))
        except ImportError:
            deps.append((name, "not installed"))
    return deps


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About QuillAI")
        self.setFixedWidth(480)

        self._t = get_theme()
        self._setup_ui()
        self.apply_styles(self._t)
        self.adjustSize()

        theme_signals.theme_changed.connect(self._on_theme_changed)

    # ── Theme handling ────────────────────────────────────────────────────

    def _on_theme_changed(self, t: dict):
        self._t = t
        self.apply_styles(t)

    def apply_styles(self, t: dict):
        p = build_about_dialog_parts(t)
        self.setStyleSheet(build_about_dialog_stylesheet(t))
        self._header.setStyleSheet(p["header"])
        self._content.setStyleSheet(p["content"])
        self._deps_title.setStyleSheet(p["deps_title"])
        self._deps_scroll.setStyleSheet(p["deps_scroll"])
        self._deps_widget.setStyleSheet(p["deps_widget"])
        self._github_btn.setStyleSheet(p["github_btn"])
        self._name_label.setStyleSheet(p["name_label"])
        self._version_label.setStyleSheet(p["version_label"])
        self._desc_label.setStyleSheet(p["desc_label"])

        # Dep row labels — stored as (name_lbl, ver_lbl) pairs
        for name_lbl, ver_lbl in self._dep_rows:
            name_lbl.setStyleSheet(p["dep_name"])
            is_missing = ver_lbl.text() == "not installed"
            ver_lbl.setStyleSheet(p["dep_missing"] if is_missing else p["dep_ok"])

        if hasattr(self, '_logo_fallback'):
            self._logo_fallback.setStyleSheet(p["logo_fallback"])

    # ── UI Setup ──────────────────────────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header ────────────────────────────────────────────────
        self._header = QWidget()
        header_layout = QVBoxLayout(self._header)
        header_layout.setContentsMargins(24, 24, 24, 16)
        header_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.setSpacing(8)

        logo_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "images", "quillai_logo_min.svg"
        )
        if os.path.exists(logo_path):
            from PyQt6.QtSvgWidgets import QSvgWidget
            svg = QSvgWidget(logo_path)
            svg.setFixedSize(200, 200)
            header_layout.addWidget(svg, alignment=Qt.AlignmentFlag.AlignCenter)
        else:
            self._logo_fallback = QLabel("✒")
            self._logo_fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
            header_layout.addWidget(self._logo_fallback)

        self._name_label = QLabel("QuillAI")
        self._name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._name_label.setFont(QFont("Inter, sans-serif", 20, QFont.Weight.Bold))
        header_layout.addWidget(self._name_label)

        self._version_label = QLabel("v0.1.0  ·  MIT License")
        self._version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self._version_label)

        self._desc_label = QLabel(
            "A privacy-first, AI-powered code editor.\nYour code stays on your machine."
        )
        self._desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._desc_label.setWordWrap(True)
        header_layout.addWidget(self._desc_label)

        layout.addWidget(self._header)

        # ── Divider ───────────────────────────────────────────────
        div1 = QFrame()
        div1.setObjectName("divider")
        div1.setFixedHeight(1)
        layout.addWidget(div1)

        # ── Content ───────────────────────────────────────────────
        self._content = QWidget()
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(32, 20, 32, 20)
        content_layout.setSpacing(12)

        self._deps_title = QLabel("Dependencies")
        content_layout.addWidget(self._deps_title)

        # Scrollable deps list
        self._deps_scroll = QScrollArea()
        self._deps_scroll.setFixedHeight(200)
        self._deps_scroll.setWidgetResizable(True)
        self._deps_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._deps_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self._deps_widget = QWidget()
        deps_layout = QVBoxLayout(self._deps_widget)
        deps_layout.setContentsMargins(12, 10, 12, 10)
        deps_layout.setSpacing(10)

        self._dep_rows = []  # [(name_lbl, ver_lbl), ...]
        for name, version in _get_dependency_versions():
            row = QHBoxLayout()
            name_lbl = QLabel(name)
            ver_lbl = QLabel(version)
            ver_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
            row.addWidget(name_lbl)
            row.addStretch()
            row.addWidget(ver_lbl)
            deps_layout.addLayout(row)
            self._dep_rows.append((name_lbl, ver_lbl))

        self._deps_scroll.setWidget(self._deps_widget)
        content_layout.addWidget(self._deps_scroll)

        # Inner divider
        div2 = QFrame()
        div2.setObjectName("divider")
        div2.setFixedHeight(1)
        content_layout.addWidget(div2)

        # GitHub button
        self._github_btn = QPushButton("⭐  github.com/GSSparks/quillai")
        self._github_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._github_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl("https://github.com/GSSparks/quillai")
            )
        )
        content_layout.addWidget(self._github_btn)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.setObjectName("close")
        close_btn.setFixedWidth(120)
        close_btn.clicked.connect(self.accept)
        content_layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self._content)

    # ── Cleanup ───────────────────────────────────────────────────────────

    def closeEvent(self, event):
        try:
            theme_signals.theme_changed.disconnect(self._on_theme_changed)
        except RuntimeError:
            pass
        super().closeEvent(event)