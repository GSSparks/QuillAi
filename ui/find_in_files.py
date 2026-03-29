import os
import fnmatch
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
                             QPushButton, QTreeWidget, QTreeWidgetItem,
                             QLabel, QProgressBar)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QDir
from PyQt6.QtGui import QFont, QColor

from ui.theme import get_theme


# ==========================================
# Background Worker
# ==========================================
class SearchWorker(QThread):
    file_matches_found = pyqtSignal(str, list)
    search_finished = pyqtSignal(int)

    def __init__(self, directory, query, file_pattern="*"):
        super().__init__()
        self.directory = directory
        self.query = query
        self.file_pattern = file_pattern
        self._is_running = True

    def run(self):
        total_matches = 0
        for root, dirs, files in os.walk(self.directory):
            if not self._is_running:
                break
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for filename in fnmatch.filter(files, self.file_pattern):
                if not self._is_running:
                    break
                file_path = os.path.join(root, filename)
                matches_in_file = []
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        for line_num, line in enumerate(f, 1):
                            if self.query in line:
                                matches_in_file.append((line_num, line.strip()))
                                total_matches += 1
                    if matches_in_file:
                        self.file_matches_found.emit(file_path, matches_in_file)
                except (UnicodeDecodeError, Exception):
                    pass
        self.search_finished.emit(total_matches)

    def stop(self):
        self._is_running = False


# ==========================================
# UI Panel
# ==========================================
class FindInFilesWidget(QWidget):
    open_file_request = pyqtSignal(str, int)

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.worker = None
        self.setup_ui()

    def _get_theme(self) -> dict:
        theme_name = None
        if (self.main_window and
                hasattr(self.main_window, 'settings_manager')):
            theme_name = self.main_window.settings_manager.get('theme')
        return get_theme(theme_name or 'gruvbox_dark')

    def setup_ui(self):
        t = self._get_theme()

        self.setStyleSheet(f"""
            QWidget {{
                background-color: {t['bg1']};
                color: {t['fg1']};
                font-family: 'Inter', 'SF Pro Text', 'Segoe UI', sans-serif;
                font-size: 10pt;
            }}
            QLineEdit {{
                background-color: {t['bg0_hard']};
                color: {t['fg0']};
                border: 1px solid {t['border']};
                border-radius: 4px;
                padding: 6px;
            }}
            QLineEdit:focus {{ border: 1px solid {t['border_focus']}; }}
            QPushButton {{
                background-color: {t['accent']};
                color: {t['bg0_hard']};
                border-radius: 4px;
                padding: 6px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {t['yellow']}; }}
            QTreeWidget {{
                background-color: {t['bg0_hard']};
                color: {t['fg1']};
                border: 1px solid {t['border']};
                border-radius: 4px;
                font-size: 10pt;
            }}
            QTreeWidget::item {{ padding: 4px; }}
            QTreeWidget::item:selected {{
                background-color: {t['bg2']};
                color: {t['fg0']};
            }}
            QTreeWidget::item:hover:!selected {{
                background-color: {t['bg1']};
            }}
            QProgressBar {{
                background-color: {t['bg2']};
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {t['accent']};
                border-radius: 2px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # Search inputs
        input_layout = QHBoxLayout()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search project for...")
        self.search_input.returnPressed.connect(self.start_search)

        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Files to include (e.g., *.py)")
        self.filter_input.setText("*.py")
        self.filter_input.setFixedWidth(150)
        self.filter_input.returnPressed.connect(self.start_search)

        self.search_btn = QPushButton("Search")
        self.search_btn.clicked.connect(self.start_search)

        input_layout.addWidget(self.search_input)
        input_layout.addWidget(self.filter_input)
        input_layout.addWidget(self.search_btn)

        # Status bar
        status_layout = QHBoxLayout()
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet(f"color: {t['fg4']};")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.hide()

        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        status_layout.addWidget(self.progress_bar)

        # Results tree
        self.results_tree = QTreeWidget()
        self.results_tree.setHeaderHidden(True)
        self.results_tree.itemDoubleClicked.connect(self.on_item_double_clicked)

        layout.addLayout(input_layout)
        layout.addLayout(status_layout)
        layout.addWidget(self.results_tree)

    def start_search(self):
        query = self.search_input.text()
        if not query:
            return

        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait()

        self.results_tree.clear()
        self.status_label.setText("Searching...")
        self.progress_bar.show()

        search_dir = QDir.currentPath()
        if hasattr(self.main_window, 'tree_view') and self.main_window.file_model:
            search_dir = self.main_window.file_model.filePath(
                self.main_window.tree_view.rootIndex()
            )

        file_pattern = self.filter_input.text() or "*"
        self.worker = SearchWorker(search_dir, query, file_pattern)
        self.worker.file_matches_found.connect(self.add_file_results)
        self.worker.search_finished.connect(self.on_search_finished)
        self.worker.start()

    def add_file_results(self, file_path, matches):
        t = self._get_theme()

        filename = os.path.basename(file_path)
        file_node = QTreeWidgetItem([f"{filename} ({len(matches)} matches)"])
        file_node.setForeground(0, QColor(t['blue']))
        file_node.setData(0, Qt.ItemDataRole.UserRole, file_path)
        bold = QFont()
        bold.setBold(True)
        file_node.setFont(0, bold)

        for line_num, text in matches:
            display_text = text if len(text) < 150 else text[:150] + "..."
            line_node = QTreeWidgetItem([f"{line_num}: {display_text}"])
            line_node.setForeground(0, QColor(t['fg1']))
            line_node.setFont(0, QFont("Fira Code, monospace", 9))
            line_node.setData(0, Qt.ItemDataRole.UserRole, file_path)
            line_node.setData(0, Qt.ItemDataRole.UserRole + 1, line_num)
            file_node.addChild(line_node)

        self.results_tree.addTopLevelItem(file_node)
        file_node.setExpanded(True)

    def on_search_finished(self, total_matches):
        t = self._get_theme()
        self.progress_bar.hide()
        if total_matches == 0:
            self.status_label.setText("No matches found.")
            self.status_label.setStyleSheet(f"color: {t['red']};")
        else:
            self.status_label.setText(f"Found {total_matches} results.")
            self.status_label.setStyleSheet(f"color: {t['green']};")

    def on_item_double_clicked(self, item, column):
        file_path = item.data(0, Qt.ItemDataRole.UserRole)
        line_num = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if file_path:
            self.open_file_request.emit(file_path, line_num or 1)

    def focus_search(self):
        self.search_input.selectAll()
        self.search_input.setFocus()