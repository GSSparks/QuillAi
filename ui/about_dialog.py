import os
import sys
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                              QPushButton, QWidget, QFrame, QScrollArea)
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QFont, QDesktopServices


ABOUT_STYLE = """
    QDialog {
        background-color: #1A1A2E;
        color: #CCCCCC;
    }
    QLabel {
        color: #CCCCCC;
        background: transparent;
    }
    QPushButton {
        background-color: #0E639C;
        color: white;
        border: none;
        border-radius: 4px;
        padding: 8px 20px;
        font-size: 10pt;
        font-weight: bold;
    }
    QPushButton:hover { background-color: #1177BB; }
    QPushButton#close {
        background-color: #3E3E42;
        color: #CCCCCC;
    }
    QPushButton#close:hover { background-color: #4E4E52; }
    QFrame#divider {
        background-color: #3E3E42;
    }
"""


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
        self.setStyleSheet(ABOUT_STYLE)
        self._setup_ui()
        # Let the dialog size itself to content
        self.adjustSize()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header with logo ──────────────────────────────────────
        header = QWidget()
        header.setStyleSheet("background-color: #1A1A2E;")
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
            fallback.setStyleSheet("font-size: 64pt; color: #378ADD;")
            header_layout.addWidget(fallback)

        # App name
        name_label = QLabel("QuillAI")
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_label.setFont(QFont("Inter", 20, QFont.Weight.Bold))
        name_label.setStyleSheet("color: #FFFFFF; font-size: 20pt;")
        header_layout.addWidget(name_label)

        version_label = QLabel("v0.1.0  ·  MIT License")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_label.setStyleSheet("color: #888888; font-size: 10pt;")
        header_layout.addWidget(version_label)

        desc = QLabel("A privacy-first, AI-powered code editor.\nYour code stays on your machine.")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #AAAAAA; font-size: 10pt; line-height: 1.6;")
        header_layout.addWidget(desc)

        layout.addWidget(header)

        # ── Divider ───────────────────────────────────────────────
        div1 = QFrame()
        div1.setObjectName("divider")
        div1.setFixedHeight(1)
        layout.addWidget(div1)

        # ── Content area ──────────────────────────────────────────
        content = QWidget()
        content.setStyleSheet("background-color: #1E1E1E;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(32, 20, 32, 20)
        content_layout.setSpacing(12)

        # Dependencies title
        deps_title = QLabel("Dependencies")
        deps_title.setStyleSheet(
            "color: #569CD6; font-size: 10pt; font-weight: bold;"
        )
        content_layout.addWidget(deps_title)

        # Scrollable deps list
        scroll = QScrollArea()
        scroll.setFixedHeight(200)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet("""
            QScrollArea {
                background-color: #252526;
                border: 1px solid #3E3E42;
                border-radius: 6px;
            }
            QScrollArea > QWidget > QWidget {
                background-color: #252526;
            }
            QScrollBar:vertical {
                border: none;
                background: #252526;
                width: 8px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #4E4E52;
                min-height: 20px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover { background: #5E5E62; }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical { height: 0px; }
        """)

        deps_widget = QWidget()
        deps_widget.setStyleSheet("background-color: #252526;")
        deps_layout = QVBoxLayout(deps_widget)
        deps_layout.setContentsMargins(12, 10, 12, 10)
        deps_layout.setSpacing(10)

        for name, version in _get_dependency_versions():
            row = QHBoxLayout()
            name_lbl = QLabel(name)
            name_lbl.setStyleSheet("color: #D4D4D4; font-size: 11pt;")
            ver_lbl = QLabel(version)
            ver_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
            color = "#F44336" if version == "not installed" else "#6A9955"
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
        github_btn.setStyleSheet("""
            QPushButton {
                background-color: #252526;
                color: #4EC9FF;
                border: 1px solid #3E3E42;
                border-radius: 4px;
                padding: 10px 16px;
                font-size: 10pt;
                font-weight: normal;
            }
            QPushButton:hover {
                background-color: #2D2D30;
                border-color: #4EC9FF;
            }
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