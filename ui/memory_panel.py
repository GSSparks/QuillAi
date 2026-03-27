from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QListWidget, QListWidgetItem,
                             QLabel, QLineEdit, QMessageBox,
                             QTabWidget, QCheckBox)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
import os


class MemoryPanel(QWidget):
    restore_conversation_requested = pyqtSignal(str, str)

    def __init__(self, memory_manager, parent=None):
        super().__init__(parent)
        self.mm = memory_manager
        self.setStyleSheet("background-color: #252526;")
        self.setup_ui()
        self.refresh()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        LABEL_STYLE = "color: #888888; font-size: 9pt; font-weight: bold;"
        LIST_STYLE = """
            QListWidget {
                background-color: #1E1E1E;
                color: #CCCCCC;
                border: 1px solid #3E3E42;
                border-radius: 4px;
                font-size: 9pt;
            }
            QListWidget::item { padding: 4px 8px; }
            QListWidget::item:selected { background-color: #37373D; }
        """
        INPUT_STYLE = """
            QLineEdit {
                background-color: #1E1E1E;
                color: #FFFFFF;
                border: 1px solid #3E3E42;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 9pt;
            }
            QLineEdit:focus { border: 1px solid #0E639C; }
        """

        # ── Facts section ──────────────────────────────────────────
        facts_label = QLabel("📌 Pinned Facts")
        facts_label.setStyleSheet(LABEL_STYLE)
        layout.addWidget(facts_label)

        self.facts_tabs = QTabWidget()
        self.facts_tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #3E3E42; background: #1E1E1E; }
            QTabBar::tab {
                background: #2D2D30; color: #888; padding: 4px 10px;
                font-size: 9pt;
            }
            QTabBar::tab:selected { background: #1E1E1E; color: #FFF; }
        """)
        self.facts_tabs.setMaximumHeight(160)

        self.global_facts_list = QListWidget()
        self.global_facts_list.setStyleSheet(LIST_STYLE)
        self.facts_tabs.addTab(self.global_facts_list, "Global")

        self.project_facts_list = QListWidget()
        self.project_facts_list.setStyleSheet(LIST_STYLE)
        self.facts_tabs.addTab(self.project_facts_list, "Project")

        layout.addWidget(self.facts_tabs)

        # Add fact input
        fact_input_layout = QHBoxLayout()
        self.fact_input = QLineEdit()
        self.fact_input.setPlaceholderText("Add a fact...")
        self.fact_input.setStyleSheet(INPUT_STYLE)
        self.fact_input.returnPressed.connect(self.add_fact)

        self.project_scope_check = QCheckBox("Project")
        self.project_scope_check.setStyleSheet("color: #888; font-size: 9pt;")
        self.project_scope_check.setToolTip("Save to project memory instead of global")

        add_btn = QPushButton("+")
        add_btn.setFixedWidth(28)
        add_btn.setStyleSheet(
            "QPushButton { background-color: #0E639C; color: white; border: none;"
            " border-radius: 4px; font-weight: bold; }"
            "QPushButton:hover { background-color: #1177BB; }"
        )
        add_btn.clicked.connect(self.add_fact)

        del_btn = QPushButton("🗑")
        del_btn.setFixedWidth(28)
        del_btn.setStyleSheet(
            "QPushButton { background-color: #3E3E42; color: #CCCCCC; border: none;"
            " border-radius: 4px; }"
            "QPushButton:hover { background-color: #F44336; color: white; }"
        )
        del_btn.clicked.connect(self.delete_fact)

        fact_input_layout.addWidget(self.fact_input)
        fact_input_layout.addWidget(self.project_scope_check)
        fact_input_layout.addWidget(add_btn)
        fact_input_layout.addWidget(del_btn)
        layout.addLayout(fact_input_layout)

        # ── Conversations section ──────────────────────────────────
        conv_label = QLabel("💬 Past Conversations")
        conv_label.setStyleSheet(LABEL_STYLE)
        layout.addWidget(conv_label)

        self.conv_search = QLineEdit()
        self.conv_search.setPlaceholderText("Search conversations...")
        self.conv_search.setStyleSheet(INPUT_STYLE)
        self.conv_search.textChanged.connect(self._filter_conversations)
        layout.addWidget(self.conv_search)

        self.conv_list = QListWidget()
        self.conv_list.itemDoubleClicked.connect(self._on_conversation_clicked)
        self.conv_list.setStyleSheet("""
            QListWidget {
                background-color: #1E1E1E;
                color: #CCCCCC;
                border: 1px solid #3E3E42;
                border-radius: 4px;
                font-size: 9pt;
            }
            QListWidget::item {
                padding: 6px 8px;
                border-bottom: 1px solid #2A2A2A;
            }
            QListWidget::item:selected { background-color: #37373D; }
        """)
        layout.addWidget(self.conv_list)

        # Bottom buttons
        btn_layout = QHBoxLayout()
        clear_conv_btn = QPushButton("Clear History")
        clear_conv_btn.setStyleSheet(
            "QPushButton { background-color: #3E3E42; color: #CCCCCC; border: none;"
            " border-radius: 4px; padding: 4px 10px; font-size: 9pt; }"
            "QPushButton:hover { background-color: #4E4E52; }"
        )
        clear_conv_btn.clicked.connect(self.clear_conversations)

        clear_all_btn = QPushButton("Clear All")
        clear_all_btn.setStyleSheet(
            "QPushButton { background-color: #3E3E42; color: #CCCCCC; border: none;"
            " border-radius: 4px; padding: 4px 10px; font-size: 9pt; }"
            "QPushButton:hover { background-color: #F44336; color: white; }"
        )
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
        self.conv_list.clear()
        if query.strip():
            convs = self.mm.search_conversations(query, limit=20)
        else:
            convs = self.mm.get_conversations()[:30]

        for conv in convs:
            tags = f" [{', '.join(conv['tags'])}]" if conv.get("tags") else ""
            has_full = "💬 " if conv.get("user_message") else "   "
            item = QListWidgetItem(f"{has_full}{conv['date']}{tags}\n{conv['summary']}")
            item.setForeground(QColor("#AAAAAA"))
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
        list_widget = self.project_facts_list if is_project else self.global_facts_list
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