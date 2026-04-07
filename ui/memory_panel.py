import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QListWidget, QListWidgetItem,
                             QLabel, QLineEdit, QMessageBox,
                             QTabWidget, QCheckBox)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor

from ui.theme import (get_theme, theme_signals,
                      build_memory_panel_stylesheet,
                      build_memory_panel_parts)
from ui.memory_manager import memory_signals


class MemoryPanel(QWidget):
    restore_conversation_requested = pyqtSignal(str, str)

    def __init__(self, memory_manager, parent=None):
        super().__init__(parent)
        self.mm = memory_manager
        self._p = build_memory_panel_parts(get_theme())
        self._setup_ui()
        self.refresh()

        theme_signals.theme_changed.connect(self._on_theme_changed)

        # Live refresh when background threads update memory
        memory_signals.facts_changed.connect(self._on_facts_changed)
        memory_signals.conversations_changed.connect(self._on_conversations_changed)

    # ── Signal handlers ───────────────────────────────────────────────────

    def _on_facts_changed(self):
        """Refresh just the facts lists — called from Qt main thread via signal."""
        self.global_facts_list.clear()
        for fact in self.mm.get_global_facts():
            self.global_facts_list.addItem(QListWidgetItem(fact))

        self.project_facts_list.clear()
        for fact in self.mm.get_project_facts():
            self.project_facts_list.addItem(QListWidgetItem(fact))

    def _on_conversations_changed(self):
        """Refresh just the conversation list."""
        self._filter_conversations(self.conv_search.text())

    # ── Theme handling ────────────────────────────────────────────────────

    def _on_theme_changed(self, t: dict):
        self._p = build_memory_panel_parts(t)
        self.apply_styles(t)
        self._filter_conversations(self.conv_search.text())

    def apply_styles(self, t: dict):
        p = self._p
        self.setStyleSheet(build_memory_panel_stylesheet(t))
        for lbl in self._section_labels:
            lbl.setStyleSheet(p["label"])
        self.facts_tabs.setStyleSheet(p["facts_tabs"])
        self.global_facts_list.setStyleSheet(p["list"])
        self.project_facts_list.setStyleSheet(p["list"])
        self.fact_input.setStyleSheet(p["input"])
        self.conv_search.setStyleSheet(p["input"])
        self.conv_list.setStyleSheet(p["conv_list"])
        self.project_scope_check.setStyleSheet(p["scope_check"])
        self._add_btn.setStyleSheet(p["add_btn"])
        self._del_btn.setStyleSheet(p["del_btn"])
        self._clear_conv_btn.setStyleSheet(p["clear_btn"])
        self._clear_all_btn.setStyleSheet(p["clear_all_btn"])

    # ── UI Setup ──────────────────────────────────────────────────────────

    def _setup_ui(self):
        p = self._p
        self._section_labels = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # ── Facts section ──────────────────────────────────────────
        facts_label = QLabel("📌 Pinned Facts")
        self._section_labels.append(facts_label)
        layout.addWidget(facts_label)

        self.facts_tabs = QTabWidget()
        self.facts_tabs.setMaximumHeight(160)

        self.global_facts_list = QListWidget()
        self.facts_tabs.addTab(self.global_facts_list, "Global")

        self.project_facts_list = QListWidget()
        self.facts_tabs.addTab(self.project_facts_list, "Project")

        layout.addWidget(self.facts_tabs)

        # Add fact input row
        fact_input_layout = QHBoxLayout()

        self.fact_input = QLineEdit()
        self.fact_input.setPlaceholderText("Add a fact...")
        self.fact_input.returnPressed.connect(self.add_fact)

        self.project_scope_check = QCheckBox("Project")
        self.project_scope_check.setToolTip("Save to project memory instead of global")

        self._add_btn = QPushButton("+")
        self._add_btn.setFixedWidth(28)
        self._add_btn.clicked.connect(self.add_fact)

        self._del_btn = QPushButton("🗑")
        self._del_btn.setFixedWidth(28)
        self._del_btn.clicked.connect(self.delete_fact)

        fact_input_layout.addWidget(self.fact_input)
        fact_input_layout.addWidget(self.project_scope_check)
        fact_input_layout.addWidget(self._add_btn)
        fact_input_layout.addWidget(self._del_btn)
        layout.addLayout(fact_input_layout)

        # ── Conversations section ──────────────────────────────────
        conv_label = QLabel("💬 Past Conversations")
        self._section_labels.append(conv_label)
        layout.addWidget(conv_label)

        self.conv_search = QLineEdit()
        self.conv_search.setPlaceholderText("Search conversations...")
        self.conv_search.textChanged.connect(self._filter_conversations)
        layout.addWidget(self.conv_search)

        self.conv_list = QListWidget()
        self.conv_list.itemDoubleClicked.connect(self._on_conversation_clicked)
        layout.addWidget(self.conv_list)

        # Bottom buttons
        btn_layout = QHBoxLayout()

        self._clear_conv_btn = QPushButton("Clear History")
        self._clear_conv_btn.clicked.connect(self.clear_conversations)

        self._clear_all_btn = QPushButton("Clear All")
        self._clear_all_btn.clicked.connect(self.clear_all)

        btn_layout.addWidget(self._clear_conv_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self._clear_all_btn)
        layout.addLayout(btn_layout)

        self.apply_styles(get_theme())

    # ── Conversation callbacks ────────────────────────────────────────────

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
            ai_resp  = conv.get("ai_response", "")
            if user_msg:
                self.restore_conversation_requested.emit(user_msg, ai_resp)

    def _filter_conversations(self, query: str):
        self.conv_list.clear()
        if query.strip():
            convs = self.mm.search_conversations(query, limit=20)
        else:
            convs = self.mm.get_conversations()[:30]

        fg = self._p["conv_item_fg"]
        for conv in convs:
            tags = f" [{', '.join(conv['tags'])}]" if conv.get("tags") else ""
            has_full = "💬 " if conv.get("user_message") else "   "
            item = QListWidgetItem(
                f"{has_full}{conv['date']}{tags}\n{conv['summary']}"
            )
            item.setForeground(QColor(fg))
            self.conv_list.addItem(item)

    # ── Data operations ───────────────────────────────────────────────────

    def refresh(self):
        self._on_facts_changed()
        if self.mm.project_path:
            name = os.path.basename(self.mm.project_path)
            self.facts_tabs.setTabText(1, f"Project: {name}")
        else:
            self.facts_tabs.setTabText(1, "Project")
        self._filter_conversations(self.conv_search.text())

    def add_fact(self):
        text = self.fact_input.text().strip()
        if text:
            self.mm.add_fact(text, project_scoped=self.project_scope_check.isChecked())
            self.fact_input.clear()
            # _on_facts_changed fires automatically via memory_signals

    def delete_fact(self):
        is_project = self.facts_tabs.currentIndex() == 1
        list_widget = (self.project_facts_list if is_project
                       else self.global_facts_list)
        row = list_widget.currentRow()
        if row >= 0:
            self.mm.remove_fact(row, project_scoped=is_project)
            # _on_facts_changed fires automatically via memory_signals

    def clear_conversations(self):
        reply = QMessageBox.question(
            self, "Clear History",
            "Clear all conversation summaries?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.mm.clear_conversations()
            self.refresh()

    def clear_all(self):
        reply = QMessageBox.question(
            self, "Clear All Memory",
            "Clear all facts and conversation history?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.mm.clear_all()
            self.refresh()

    # ── Cleanup ───────────────────────────────────────────────────────────

    def closeEvent(self, event):
        try:
            theme_signals.theme_changed.disconnect(self._on_theme_changed)
            memory_signals.facts_changed.disconnect(self._on_facts_changed)
            memory_signals.conversations_changed.disconnect(self._on_conversations_changed)
        except RuntimeError:
            pass
        super().closeEvent(event)