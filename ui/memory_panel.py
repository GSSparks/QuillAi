from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QListWidget, QListWidgetItem,
                             QLabel, QLineEdit, QMessageBox,
                             QTabWidget, QCheckBox)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
import os

from ui.theme import get_theme


class MemoryPanel(QWidget):
    restore_conversation_requested = pyqtSignal(str, str)

    def __init__(self, memory_manager, parent=None):
        super().__init__(parent)
        self.mm = memory_manager
        self._parent = parent
        self.setup_ui()
        self.refresh()

    def _get_theme(self) -> dict:
        theme_name = None
        if self._parent and hasattr(self._parent, 'settings_manager'):
            theme_name = self._parent.settings_manager.get('theme')
        return get_theme(theme_name or 'gruvbox_dark')

    def setup_ui(self):
        t = self._get_theme()

        self.setStyleSheet(f"background-color: {t['bg1']};")

        label_style = (
            f"color: {t['fg4']}; font-size: 9pt; font-weight: bold;"
        )
        list_style = f"""
            QListWidget {{
                background-color: {t['bg0_hard']};
                color: {t['fg1']};
                border: 1px solid {t['border']};
                border-radius: 4px;
                font-size: 9pt;
            }}
            QListWidget::item {{ padding: 4px 8px; }}
            QListWidget::item:selected {{
                background-color: {t['bg2']};
                color: {t['fg0']};
            }}
            QListWidget::item:hover:!selected {{
                background-color: {t['bg1']};
            }}
        """
        input_style = f"""
            QLineEdit {{
                background-color: {t['bg0_hard']};
                color: {t['fg0']};
                border: 1px solid {t['border']};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 9pt;
            }}
            QLineEdit:focus {{ border: 1px solid {t['border_focus']}; }}
        """

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # ── Facts section ──────────────────────────────────────────
        facts_label = QLabel("📌 Pinned Facts")
        facts_label.setStyleSheet(label_style)
        layout.addWidget(facts_label)

        self.facts_tabs = QTabWidget()
        self.facts_tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {t['border']};
                background: {t['bg0_hard']};
            }}
            QTabBar::tab {{
                background: {t['bg1']};
                color: {t['fg4']};
                padding: 4px 10px;
                font-size: 9pt;
            }}
            QTabBar::tab:selected {{
                background: {t['bg0_hard']};
                color: {t['fg0']};
                border-top: 1px solid {t['tab_active_bar']};
            }}
        """)
        self.facts_tabs.setMaximumHeight(160)

        self.global_facts_list = QListWidget()
        self.global_facts_list.setStyleSheet(list_style)
        self.facts_tabs.addTab(self.global_facts_list, "Global")

        self.project_facts_list = QListWidget()
        self.project_facts_list.setStyleSheet(list_style)
        self.facts_tabs.addTab(self.project_facts_list, "Project")

        layout.addWidget(self.facts_tabs)

        # Add fact input
        fact_input_layout = QHBoxLayout()
        self.fact_input = QLineEdit()
        self.fact_input.setPlaceholderText("Add a fact...")
        self.fact_input.setStyleSheet(input_style)
        self.fact_input.returnPressed.connect(self.add_fact)

        self.project_scope_check = QCheckBox("Project")
        self.project_scope_check.setStyleSheet(
            f"color: {t['fg4']}; font-size: 9pt;"
        )
        self.project_scope_check.setToolTip("Save to project memory instead of global")

        add_btn = QPushButton("+")
        add_btn.setFixedWidth(28)
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t['accent']};
                color: {t['bg0_hard']};
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {t['yellow']}; }}
        """)
        add_btn.clicked.connect(self.add_fact)

        del_btn = QPushButton("🗑")
        del_btn.setFixedWidth(28)
        del_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t['bg2']};
                color: {t['fg1']};
                border: none;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {t['red']};
                color: {t['bg0_hard']};
            }}
        """)
        del_btn.clicked.connect(self.delete_fact)

        fact_input_layout.addWidget(self.fact_input)
        fact_input_layout.addWidget(self.project_scope_check)
        fact_input_layout.addWidget(add_btn)
        fact_input_layout.addWidget(del_btn)
        layout.addLayout(fact_input_layout)

        # ── Conversations section ──────────────────────────────────
        conv_label = QLabel("💬 Past Conversations")
        conv_label.setStyleSheet(label_style)
        layout.addWidget(conv_label)

        self.conv_search = QLineEdit()
        self.conv_search.setPlaceholderText("Search conversations...")
        self.conv_search.setStyleSheet(input_style)
        self.conv_search.textChanged.connect(self._filter_conversations)
        layout.addWidget(self.conv_search)

        self.conv_list = QListWidget()
        self.conv_list.itemDoubleClicked.connect(self._on_conversation_clicked)
        self.conv_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {t['bg0_hard']};
                color: {t['fg1']};
                border: 1px solid {t['border']};
                border-radius: 4px;
                font-size: 9pt;
            }}
            QListWidget::item {{
                padding: 6px 8px;
                border-bottom: 1px solid {t['bg1']};
            }}
            QListWidget::item:selected {{
                background-color: {t['bg2']};
                color: {t['fg0']};
            }}
            QListWidget::item:hover:!selected {{
                background-color: {t['bg1']};
            }}
        """)
        layout.addWidget(self.conv_list)

        # Bottom buttons
        btn_layout = QHBoxLayout()

        clear_conv_btn = QPushButton("Clear History")
        clear_conv_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t['bg2']};
                color: {t['fg1']};
                border: none;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 9pt;
            }}
            QPushButton:hover {{ background-color: {t['bg3']}; }}
        """)
        clear_conv_btn.clicked.connect(self.clear_conversations)

        clear_all_btn = QPushButton("Clear All")
        clear_all_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t['bg2']};
                color: {t['fg1']};
                border: none;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 9pt;
            }}
            QPushButton:hover {{
                background-color: {t['red']};
                color: {t['bg0_hard']};
            }}
        """)
        clear_all_btn.clicked.connect(self.clear_all)

        btn_layout.addWidget(clear_conv_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(clear_all_btn)
        layout.addLayout(btn_layout)

    def _on_conversation_clicked(self, item):
        row = self.conv_list.currentRow()
        if row < 0:
            return

        if self.mm.project_path and self.mm.project_memory:
            convs = list(reversed(self.mm.project_memory["conversations"]))
        else:
            convs = list(reversed(self.mm.global_memory["conversations"]))

        full_convs = [c for c in convs if c.get("user_message")]

        if row < len(full_convs):
            conv = full_convs[row]
            user_msg = conv.get("user_message", "")
            ai_resp = conv.get("ai_response", "")
            if user_msg:
                self.restore_conversation_requested.emit(user_msg, ai_resp)

    def _filter_conversations(self, query):
        t = self._get_theme()
        self.conv_list.clear()
        if query.strip():
            convs = self.mm.search_conversations(query, limit=20)
        else:
            convs = self.mm.get_conversations()[:30]

        for conv in convs:
            tags = f" [{', '.join(conv['tags'])}]" if conv.get("tags") else ""
            has_full = "💬 " if conv.get("user_message") else "   "
            item = QListWidgetItem(
                f"{has_full}{conv['date']}{tags}\n{conv['summary']}"
            )
            item.setForeground(QColor(t['fg3']))
            self.conv_list.addItem(item)

    def refresh(self):
        self.global_facts_list.clear()
        for fact in self.mm.get_global_facts():
            self.global_facts_list.addItem(QListWidgetItem(fact))

        self.project_facts_list.clear()
        for fact in self.mm.get_project_facts():
            self.project_facts_list.addItem(QListWidgetItem(fact))

        if self.mm.project_path:
            name = os.path.basename(self.mm.project_path)
            self.facts_tabs.setTabText(1, f"Project: {name}")
        else:
            self.facts_tabs.setTabText(1, "Project")

        self._filter_conversations(self.conv_search.text())

    def add_fact(self):
        text = self.fact_input.text().strip()
        if text:
            project_scoped = self.project_scope_check.isChecked()
            self.mm.add_fact(text, project_scoped=project_scoped)
            self.fact_input.clear()
            self.refresh()

    def delete_fact(self):
        is_project = self.facts_tabs.currentIndex() == 1
        list_widget = (self.project_facts_list
                       if is_project else self.global_facts_list)
        row = list_widget.currentRow()
        if row >= 0:
            self.mm.remove_fact(row, project_scoped=is_project)
            self.refresh()

    def clear_conversations(self):
        reply = QMessageBox.question(
            self, "Clear History",
            "Clear all conversation summaries?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.mm.clear_conversations()
            self.refresh()

    def clear_all(self):
        reply = QMessageBox.question(
            self, "Clear All Memory",
            "Clear all facts and conversation history?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.mm.clear_all()
            self.refresh()