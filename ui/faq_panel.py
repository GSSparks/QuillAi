"""
ui/faq_panel.py

FAQ panel — searchable list of codebase how-to knowledge.
Lives in the sliding chat panel as the third tab.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QScrollArea, QFrame, QTextEdit,
    QDialog, QFormLayout, QDialogButtonBox, QApplication,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from ui.theme import get_theme, theme_signals
from core.faq_manager import faq_signals


# ── Entry card ────────────────────────────────────────────────────────────────

class FAQCard(QFrame):
    edit_clicked   = pyqtSignal(dict)
    delete_clicked = pyqtSignal(str)   # entry_id
    copy_clicked   = pyqtSignal(str)   # answer text

    def __init__(self, entry: dict, parent=None):
        super().__init__(parent)
        self.entry    = entry
        self._expanded = False
        self._build(entry)
        self._apply_theme(get_theme())

    def _build(self, entry: dict):
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        # Header row
        header = QHBoxLayout()

        self._q_label = QPushButton(entry["question"])
        self._q_label.setFlat(True)
        self._q_label.setCheckable(True)
        self._q_label.clicked.connect(self._toggle)
        self._q_label.setStyleSheet("text-align: left; padding: 0;")
        header.addWidget(self._q_label, stretch=1)

        # Source badge
        src_colors = {"conversation": "aqua", "wiki": "green", "manual": "yellow"}
        src = entry.get("source", "manual")
        self._src_label = QLabel(src[0].upper())
        self._src_label.setFixedSize(16, 16)
        self._src_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(self._src_label)

        layout.addLayout(header)

        # Tags
        tags = entry.get("tags", [])
        if tags:
            self._tags_label = QLabel("  ".join(f"#{t}" for t in tags))
            layout.addWidget(self._tags_label)
        else:
            self._tags_label = None

        # Answer (collapsed by default)
        self._answer_widget = QWidget()
        answer_layout = QVBoxLayout(self._answer_widget)
        answer_layout.setContentsMargins(0, 4, 0, 0)
        answer_layout.setSpacing(4)

        self._answer_label = QLabel(entry["answer"])
        self._answer_label.setWordWrap(True)
        self._answer_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        answer_layout.addWidget(self._answer_label)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        copy_btn = QPushButton("⎘ Copy")
        copy_btn.setFixedHeight(20)
        copy_btn.clicked.connect(lambda: self.copy_clicked.emit(entry["answer"]))
        btn_row.addWidget(copy_btn)

        edit_btn = QPushButton("✎ Edit")
        edit_btn.setFixedHeight(20)
        edit_btn.clicked.connect(lambda: self.edit_clicked.emit(self.entry))
        btn_row.addWidget(edit_btn)

        del_btn = QPushButton("✕")
        del_btn.setFixedHeight(20)
        del_btn.clicked.connect(lambda: self.delete_clicked.emit(entry["id"]))
        btn_row.addWidget(del_btn)

        answer_layout.addLayout(btn_row)
        self._answer_widget.hide()
        layout.addWidget(self._answer_widget)

    def _toggle(self):
        self._expanded = not self._expanded
        self._answer_widget.setVisible(self._expanded)
        self._q_label.setChecked(self._expanded)

    def _apply_theme(self, t: dict):
        src = self.entry.get("source", "manual")
        src_color_map = {
            "conversation": t.get("aqua",   "#689d6a"),
            "wiki":         t.get("green",  "#98971a"),
            "manual":       t.get("yellow", "#d79921"),
        }
        color = src_color_map.get(src, t.get("fg4", "#a89984"))

        self.setStyleSheet(f"""
            QFrame {{
                background: {t.get('bg1', '#3c3836')};
                border: 1px solid {t.get('bg3', '#665c54')};
                border-radius: 4px;
            }}
        """)
        self._q_label.setStyleSheet(f"""
            QPushButton {{
                color: {t.get('fg1', '#ebdbb2')};
                font-size: 9pt;
                font-weight: bold;
                text-align: left;
                border: none;
                background: transparent;
                padding: 0;
            }}
            QPushButton:checked {{
                color: {t.get('yellow', '#d79921')};
            }}
        """)
        self._src_label.setStyleSheet(f"""
            QLabel {{
                background: {color};
                color: {t.get('bg0', '#282828')};
                border-radius: 3px;
                font-size: 7pt;
                font-weight: bold;
            }}
        """)
        if self._tags_label:
            self._tags_label.setStyleSheet(f"""
                QLabel {{
                    color: {t.get('fg4', '#a89984')};
                    font-size: 8pt;
                }}
            """)
        self._answer_label.setStyleSheet(f"""
            QLabel {{
                color: {t.get('fg1', '#ebdbb2')};
                font-size: 9pt;
                background: transparent;
            }}
        """)
        btn_style = f"""
            QPushButton {{
                background: {t.get('bg2', '#504945')};
                color: {t.get('fg4', '#a89984')};
                border: none;
                border-radius: 3px;
                font-size: 8pt;
                padding: 2px 8px;
            }}
            QPushButton:hover {{
                background: {t.get('bg3', '#665c54')};
                color: {t.get('fg1', '#ebdbb2')};
            }}
        """
        for btn in self._answer_widget.findChildren(QPushButton):
            btn.setStyleSheet(btn_style)


# ── Edit dialog ───────────────────────────────────────────────────────────────

class FAQEditDialog(QDialog):
    def __init__(self, entry: dict = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit FAQ Entry" if entry else "New FAQ Entry")
        self.setMinimumWidth(480)
        self.setModal(True)
        self._entry = entry or {}
        self._build()
        self._apply_theme(get_theme())
        theme_signals.theme_changed.connect(self._apply_theme)

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        form = QFormLayout()
        form.setSpacing(8)

        self._q_edit = QLineEdit(self._entry.get("question", ""))
        self._q_edit.setPlaceholderText("How do I...?")
        form.addRow("Question:", self._q_edit)

        self._a_edit = QTextEdit()
        self._a_edit.setPlainText(self._entry.get("answer", ""))
        self._a_edit.setPlaceholderText("Answer...")
        self._a_edit.setMinimumHeight(120)
        form.addRow("Answer:", self._a_edit)

        self._t_edit = QLineEdit(", ".join(self._entry.get("tags", [])))
        self._t_edit.setPlaceholderText("tag1, tag2, tag3")
        form.addRow("Tags:", self._t_edit)

        layout.addLayout(form)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_values(self) -> tuple[str, str, list]:
        q    = self._q_edit.text().strip()
        a    = self._a_edit.toPlainText().strip()
        tags = [t.strip() for t in self._t_edit.text().split(",") if t.strip()]
        return q, a, tags

    def _apply_theme(self, t: dict):
        self.setStyleSheet(f"""
            QDialog, QWidget {{
                background: {t.get('bg1', '#3c3836')};
                color: {t.get('fg1', '#ebdbb2')};
            }}
            QLineEdit, QTextEdit {{
                background: {t.get('bg0', '#282828')};
                color: {t.get('fg1', '#ebdbb2')};
                border: 1px solid {t.get('bg3', '#665c54')};
                border-radius: 3px;
                padding: 4px 6px;
                font-size: 9pt;
            }}
            QLineEdit:focus, QTextEdit:focus {{
                border-color: {t.get('yellow', '#d79921')};
            }}
            QLabel {{
                color: {t.get('fg4', '#a89984')};
                font-size: 9pt;
                background: transparent;
            }}
            QPushButton {{
                background: {t.get('bg2', '#504945')};
                color: {t.get('fg1', '#ebdbb2')};
                border: 1px solid {t.get('bg3', '#665c54')};
                border-radius: 3px;
                padding: 4px 16px;
                font-size: 9pt;
            }}
            QPushButton:hover {{
                background: {t.get('bg3', '#665c54')};
            }}
            QPushButton:default {{
                border-color: {t.get('yellow', '#d79921')};
                color: {t.get('yellow', '#d79921')};
            }}
        """)

    def closeEvent(self, event):
        try:
            theme_signals.theme_changed.disconnect(self._apply_theme)
        except (RuntimeError, TypeError):
            pass
        super().closeEvent(event)


# ── FAQ Panel ─────────────────────────────────────────────────────────────────

class FAQPanel(QWidget):
    def __init__(self, faq_manager, parent=None):
        super().__init__(parent)
        self._fm    = faq_manager
        self._cards: list[FAQCard] = []
        self._build()
        self._apply_theme(get_theme())
        faq_signals.faq_changed.connect(self._reload)
        theme_signals.theme_changed.connect(self._apply_theme)

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Toolbar
        toolbar = QHBoxLayout()

        self._search = QLineEdit()
        self._search.setPlaceholderText("🔍  Search FAQ…")
        self._search.textChanged.connect(self._on_search)
        toolbar.addWidget(self._search, stretch=1)

        add_btn = QPushButton("＋")
        add_btn.setFixedSize(28, 28)
        add_btn.setToolTip("Add FAQ entry manually")
        add_btn.clicked.connect(self._on_add)
        toolbar.addWidget(add_btn)

        layout.addLayout(toolbar)

        # Count label
        self._count_label = QLabel("")
        self._count_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self._count_label)

        # Scroll area for cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._cards_widget = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_widget)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(6)
        self._cards_layout.addStretch()

        scroll.setWidget(self._cards_widget)
        layout.addWidget(scroll, stretch=1)

        self._scroll = scroll
        self._reload()

    def _reload(self):
        query   = self._search.text().strip()
        entries = self._fm.search(query) if query else self._fm.get_all()

        # Remove old cards
        for card in self._cards:
            card.setParent(None)
            card.deleteLater()
        self._cards.clear()

        # Remove stretch
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        t = get_theme()
        for entry in reversed(entries):  # newest first
            card = FAQCard(entry, self._cards_widget)
            card.edit_clicked.connect(self._on_edit)
            card.delete_clicked.connect(self._on_delete)
            card.copy_clicked.connect(self._on_copy)
            self._cards.append(card)
            self._cards_layout.addWidget(card)

        self._cards_layout.addStretch()

        total = len(self._fm.get_all())
        shown = len(entries)
        if query:
            self._count_label.setText(f"{shown} of {total} entries")
        else:
            self._count_label.setText(f"{total} entr{'y' if total == 1 else 'ies'}")

    def _on_search(self):
        self._reload()

    def _on_add(self):
        dlg = FAQEditDialog(parent=self)
        if dlg.exec():
            q, a, tags = dlg.get_values()
            if q and a:
                self._fm.add_entry(q, a, tags=tags, source="manual",
                                   deduplicate=False)

    def _on_edit(self, entry: dict):
        dlg = FAQEditDialog(entry, parent=self)
        if dlg.exec():
            q, a, tags = dlg.get_values()
            self._fm.update_entry(entry["id"], q, a, tags)

    def _on_delete(self, entry_id: str):
        self._fm.remove_entry(entry_id)

    def _on_copy(self, text: str):
        QApplication.clipboard().setText(text)

    def _apply_theme(self, t: dict):
        self.setStyleSheet(f"""
            QWidget {{ background: {t.get('bg0', '#282828')}; }}
        """)
        self._search.setStyleSheet(f"""
            QLineEdit {{
                background: {t.get('bg1', '#3c3836')};
                color: {t.get('fg1', '#ebdbb2')};
                border: 1px solid {t.get('bg3', '#665c54')};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 9pt;
            }}
            QLineEdit:focus {{
                border-color: {t.get('yellow', '#d79921')};
            }}
        """)
        self._count_label.setStyleSheet(f"""
            QLabel {{
                color: {t.get('fg4', '#a89984')};
                font-size: 8pt;
                background: transparent;
            }}
        """)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{
                background: {t.get('bg0', '#282828')};
                border: none;
            }}
            QScrollBar:vertical {{
                background: {t.get('bg1', '#3c3836')};
                width: 8px; border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {t.get('bg3', '#665c54')};
                border-radius: 4px; min-height: 20px;
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        for card in self._cards:
            card._apply_theme(t)