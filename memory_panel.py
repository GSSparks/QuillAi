from PyQt6.QtWidgets import (QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QListWidget, QListWidgetItem,
                             QLabel, QLineEdit, QMessageBox, QAbstractItemView)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor


class MemoryPanel(QDockWidget):
    def __init__(self, memory_manager, parent=None):
        super().__init__("Memory", parent)
        self.mm = memory_manager
        self.setStyleSheet("""
            QDockWidget {
                color: #CCCCCC;
                font-family: 'Inter', sans-serif;
                font-weight: bold;
                font-size: 10pt;
            }
            QDockWidget::title {
                background-color: #252526;
                padding: 6px 10px;
            }
        """)
        self.setup_ui()
        self.refresh()

    def setup_ui(self):
        container = QWidget()
        container.setStyleSheet("background-color: #252526;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # ── Facts section ──────────────────────────────────────────
        facts_label = QLabel("📌 Pinned Facts")
        facts_label.setStyleSheet("color: #888888; font-size: 9pt; font-weight: bold;")
        layout.addWidget(facts_label)

        self.facts_list = QListWidget()
        self.facts_list.setMaximumHeight(160)
        self.facts_list.setStyleSheet("""
            QListWidget {
                background-color: #1E1E1E;
                color: #CCCCCC;
                border: 1px solid #3E3E42;
                border-radius: 4px;
                font-size: 9pt;
            }
            QListWidget::item { padding: 4px 8px; }
            QListWidget::item:selected { background-color: #37373D; }
        """)
        self.facts_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        layout.addWidget(self.facts_list)

        # Add fact input
        fact_input_layout = QHBoxLayout()
        self.fact_input = QLineEdit()
        self.fact_input.setPlaceholderText("Add a fact to remember...")
        self.fact_input.setStyleSheet("""
            QLineEdit {
                background-color: #1E1E1E;
                color: #FFFFFF;
                border: 1px solid #3E3E42;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 9pt;
            }
            QLineEdit:focus { border: 1px solid #0E639C; }
        """)
        self.fact_input.returnPressed.connect(self.add_fact)

        add_btn = QPushButton("+")
        add_btn.setFixedWidth(28)
        add_btn.setStyleSheet("""
            QPushButton { background-color: #0E639C; color: white;
                          border: none; border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background-color: #1177BB; }
        """)
        add_btn.clicked.connect(self.add_fact)

        del_btn = QPushButton("🗑")
        del_btn.setFixedWidth(28)
        del_btn.setStyleSheet("""
            QPushButton { background-color: #3E3E42; color: #CCCCCC;
                          border: none; border-radius: 4px; }
            QPushButton:hover { background-color: #F44336; color: white; }
        """)
        del_btn.clicked.connect(self.delete_fact)

        fact_input_layout.addWidget(self.fact_input)
        fact_input_layout.addWidget(add_btn)
        fact_input_layout.addWidget(del_btn)
        layout.addLayout(fact_input_layout)

        # ── Conversations section ───────────────────────────────────
        conv_label = QLabel("💬 Past Conversations")
        conv_label.setStyleSheet("color: #888888; font-size: 9pt; font-weight: bold;")
        layout.addWidget(conv_label)

        self.conv_list = QListWidget()
        self.conv_list.setStyleSheet("""
            QListWidget {
                background-color: #1E1E1E;
                color: #CCCCCC;
                border: 1px solid #3E3E42;
                border-radius: 4px;
                font-size: 9pt;
            }
            QListWidget::item { padding: 6px 8px; border-bottom: 1px solid #2A2A2A; }
            QListWidget::item:selected { background-color: #37373D; }
        """)
        layout.addWidget(self.conv_list)

        # Bottom buttons
        btn_layout = QHBoxLayout()
        clear_conv_btn = QPushButton("Clear History")
        clear_conv_btn.setStyleSheet("""
            QPushButton { background-color: #3E3E42; color: #CCCCCC;
                          border: none; border-radius: 4px; padding: 4px 10px;
                          font-size: 9pt; }
            QPushButton:hover { background-color: #4E4E52; }
        """)
        clear_conv_btn.clicked.connect(self.clear_conversations)

        clear_all_btn = QPushButton("Clear All")
        clear_all_btn.setStyleSheet("""
            QPushButton { background-color: #3E3E42; color: #CCCCCC;
                          border: none; border-radius: 4px; padding: 4px 10px;
                          font-size: 9pt; }
            QPushButton:hover { background-color: #F44336; color: white; }
        """)
        clear_all_btn.clicked.connect(self.clear_all)

        btn_layout.addWidget(clear_conv_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(clear_all_btn)
        layout.addLayout(btn_layout)

        self.setWidget(container)
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable |
            QDockWidget.DockWidgetFeature.DockWidgetMovable
        )

    def refresh(self):
        self.facts_list.clear()
        for fact in self.mm.get_facts():
            self.facts_list.addItem(QListWidgetItem(fact))

        self.conv_list.clear()
        for conv in reversed(self.mm.get_conversations()):
            tags = f" [{', '.join(conv['tags'])}]" if conv.get("tags") else ""
            item = QListWidgetItem(f"{conv['date']}{tags}\n{conv['summary']}")
            item.setForeground(QColor("#AAAAAA"))
            self.conv_list.addItem(item)

    def add_fact(self):
        text = self.fact_input.text().strip()
        if text:
            self.mm.add_fact(text)
            self.fact_input.clear()
            self.refresh()

    def delete_fact(self):
        row = self.facts_list.currentRow()
        if row >= 0:
            self.mm.remove_fact(row)
            self.refresh()

    def clear_conversations(self):
        reply = QMessageBox.question(self, "Clear History",
                                     "Clear all conversation summaries?",
                                     QMessageBox.StandardButton.Yes |
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.mm.clear_conversations()
            self.refresh()

    def clear_all(self):
        reply = QMessageBox.question(self, "Clear All Memory",
                                     "Clear all facts and conversation history?",
                                     QMessageBox.StandardButton.Yes |
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.mm.clear_all()
            self.refresh()