import os
import sys
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                              QPushButton, QWidget, QFrame, QScrollArea)
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QFont, QDesktopServices

from ui.theme import get_theme


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

        # Get theme from parent window if available
        theme_name = None
        if parent and hasattr(parent, 'settings_manager'):
            theme_name = parent.settings_manager.get('theme')
        self._t = get_theme(theme_name)

        self._apply_style()
        self._setup_ui()
        self.adjustSize()

    def _apply_style(self):
        t = self._t
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {t['bg0']};
                color: {t['fg1']};
            }}
            QLabel {{
                color: {t['fg1']};
                background: transparent;
            }}
            QPushButton {{
                background-color: {t['accent']};
                color: {t['bg0_hard']};
                border: none;
                border-radius: 4px;
                padding: 8px 20px;
                font-size: 10pt;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {t['yellow']}; }}
            QPushButton#close {{
                background-color: {t['bg2']};
                color: {t['fg1']};
            }}
            QPushButton#close:hover {{ background-color: {t['bg3']}; }}
            QFrame#divider {{
                background-color: {t['border']};
            }}
        """)

    def _setup_ui(self):
        t = self._t

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header with logo ──────────────────────────────────────
        header = QWidget()
        header.setStyleSheet(f"background-color: {t['bg0_hard']};")
        header_layout = QVBoxLayout(header)
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
            fallback = QLabel("✒")
            fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
            fallback.setStyleSheet(f"font-size: 64pt; color: {t['blue']};")
            header_layout.addWidget(fallback)

        name_label = QLabel("QuillAI")
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_label.setFont(QFont("Inter, sans-serif", 20, QFont.Weight.Bold))
        name_label.setStyleSheet(f"color: {t['fg0']}; font-size: 20pt;")
        header_layout.addWidget(name_label)

        version_label = QLabel("v0.1.0  ·  MIT License")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_label.setStyleSheet(f"color: {t['fg4']}; font-size: 10pt;")
        header_layout.addWidget(version_label)

        desc = QLabel("A privacy-first, AI-powered code editor.\nYour code stays on your machine.")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {t['fg2']}; font-size: 10pt;")
        header_layout.addWidget(desc)

        layout.addWidget(header)

        # ── Divider ───────────────────────────────────────────────
        div1 = QFrame()
        div1.setObjectName("divider")
        div1.setFixedHeight(1)
        layout.addWidget(div1)

        # ── Content area ──────────────────────────────────────────
        content = QWidget()
        content.setStyleSheet(f"background-color: {t['bg0']};")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(32, 20, 32, 20)
        content_layout.setSpacing(12)

        # Dependencies title
        deps_title = QLabel("Dependencies")
        deps_title.setStyleSheet(
            f"color: {t['blue']}; font-size: 10pt; font-weight: bold;"
        )
        content_layout.addWidget(deps_title)

        # Scrollable deps list
        scroll = QScrollArea()
        scroll.setFixedHeight(200)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: {t['bg1']};
                border: 1px solid {t['border']};
                border-radius: 6px;
            }}
            QScrollArea > QWidget > QWidget {{
                background-color: {t['bg1']};
            }}
            QScrollBar:vertical {{
                border: none;
                background: {t['bg1']};
                width: 8px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {t['scrollbar']};
                min-height: 20px;
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {t['scrollbar_hover']};
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{ height: 0px; }}
        """)

        deps_widget = QWidget()
        deps_widget.setStyleSheet(f"background-color: {t['bg1']};")
        deps_layout = QVBoxLayout(deps_widget)
        deps_layout.setContentsMargins(12, 10, 12, 10)
        deps_layout.setSpacing(10)

        for name, version in _get_dependency_versions():
            row = QHBoxLayout()
            name_lbl = QLabel(name)
            name_lbl.setStyleSheet(f"color: {t['fg1']}; font-size: 11pt;")
            ver_lbl = QLabel(version)
            ver_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
            color = t['red'] if version == "not installed" else t['green']
            ver_lbl.setStyleSheet(f"color: {color}; font-size: 11pt;")
            row.addWidget(name_lbl)
            row.addStretch()
            row.addWidget(ver_lbl)
            deps_layout.addLayout(row)

        scroll.setWidget(deps_widget)
        content_layout.addWidget(scroll)

        # Divider
        div2 = QFrame()
        div2.setObjectName("divider")
        div2.setFixedHeight(1)
        content_layout.addWidget(div2)

        # GitHub button
        github_btn = QPushButton("⭐  github.com/GSSparks/quillai")
        github_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t['bg1']};
                color: {t['aqua']};
                border: 1px solid {t['border']};
                border-radius: 4px;
                padding: 10px 16px;
                font-size: 10pt;
                font-weight: normal;
            }}
            QPushButton:hover {{
                background-color: {t['bg2']};
                border-color: {t['aqua']};
            }}
        """)
        github_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        github_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl("https://github.com/GSSparks/quillai")
            )
        )
        content_layout.addWidget(github_btn)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.setObjectName("close")
        close_btn.setFixedWidth(120)
        close_btn.clicked.connect(self.accept)
        content_layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(content)