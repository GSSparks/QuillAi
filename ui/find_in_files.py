import os
import fnmatch
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QTreeWidget, QTreeWidgetItem,
    QLabel, QProgressBar
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QDir
from PyQt6.QtGui import QFont, QColor

from ui.theme import (get_theme, theme_signals,
                      build_find_in_files_parts,
                      QFONT_UI, QFONT_CODE)


# ==========================================
# Background Worker
# ==========================================
class SearchWorker(QThread):
    file_matches_found = pyqtSignal(str, list)
    search_finished    = pyqtSignal(int)

    def __init__(self, directory, query, file_pattern="*"):
        super().__init__()
        self.directory    = directory
        self.query        = query
        self.file_pattern = file_pattern
        self._is_running  = True

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
                except Exception:
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

        # QFont objects built from theme constants — one source of truth
        self._ui_font   = QFont(QFONT_UI, 10)
        self._code_font = QFont(QFONT_CODE, 10)
        self._code_font.setStyleHint(QFont.StyleHint.Monospace)

        # Cache the parts dict so add_file_results never needs a theme lookup
        self._p = build_find_in_files_parts(get_theme())

        self._setup_ui()
        theme_signals.theme_changed.connect(self._on_theme_changed)

    # ── Theme handling ────────────────────────────────────────────────────

    def _on_theme_changed(self, t: dict):
        self._p = build_find_in_files_parts(t)
        self._apply_styles()

    def _apply_styles(self):
        p = self._p
        self.search_input.setStyleSheet(p["inputs"])
        self.filter_input.setStyleSheet(p["inputs"])
        self.search_btn.setStyleSheet(p["search_btn"])
        self.results_tree.setStyleSheet(p["results_tree"])
        self.status_label.setStyleSheet(p["status_default"])

    # ── UI Setup ──────────────────────────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # Search inputs
        input_layout = QHBoxLayout()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search project for...")
        self.search_input.setFont(self._ui_font)
        self.search_input.returnPressed.connect(self.start_search)

        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("*.py")
        self.filter_input.setText("*.py")
        self.filter_input.setFixedWidth(150)
        self.filter_input.setFont(self._ui_font)
        self.filter_input.returnPressed.connect(self.start_search)

        self.search_btn = QPushButton("Search")
        self.search_btn.setFont(self._ui_font)
        self.search_btn.clicked.connect(self.start_search)

        input_layout.addWidget(self.search_input)
        input_layout.addWidget(self.filter_input)
        input_layout.addWidget(self.search_btn)

        # Status bar
        status_layout = QHBoxLayout()

        self.status_label = QLabel("Ready")
        self.status_label.setFont(self._ui_font)

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

        self._apply_styles()

    # ── Search logic ──────────────────────────────────────────────────────

    def start_search(self):
        query = self.search_input.text()
        if not query:
            return

        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait()

        self.results_tree.clear()
        self.status_label.setText("Searching...")
        self.status_label.setStyleSheet(self._p["status_default"])
        self.progress_bar.show()

        search_dir = QDir.currentPath()
        if hasattr(self.main_window, 'tree_view') and self.main_window.file_model:
            search_dir = self.main_window.file_model.filePath(
                self.main_window.tree_view.rootIndex()
            )

        self.worker = SearchWorker(
            search_dir, query, self.filter_input.text() or "*"
        )
        self.worker.file_matches_found.connect(self.add_file_results)
        self.worker.search_finished.connect(self.on_search_finished)
        self.worker.start()

    def add_file_results(self, file_path: str, matches: list):
        p = self._p   # no theme lookup — use cached dict

        file_node = QTreeWidgetItem(
            [f"{os.path.basename(file_path)} ({len(matches)} matches)"]
        )
        file_node.setForeground(0, QColor(p["file_node_fg"]))
        file_node.setData(0, Qt.ItemDataRole.UserRole, file_path)
        bold = QFont(self._ui_font)
        bold.setBold(True)
        file_node.setFont(0, bold)

        for line_num, text in matches:
            display = text if len(text) < 150 else text[:150] + "..."
            line_node = QTreeWidgetItem([f"{line_num}: {display}"])
            line_node.setForeground(0, QColor(p["line_node_fg"]))
            line_node.setFont(0, self._code_font)
            line_node.setData(0, Qt.ItemDataRole.UserRole, file_path)
            line_node.setData(0, Qt.ItemDataRole.UserRole + 1, line_num)
            file_node.addChild(line_node)

        self.results_tree.addTopLevelItem(file_node)
        file_node.setExpanded(True)

    def on_search_finished(self, total_matches: int):
        self.progress_bar.hide()
        if total_matches == 0:
            self.status_label.setText("No matches found.")
            self.status_label.setStyleSheet(self._p["status_empty"])
        else:
            self.status_label.setText(f"Found {total_matches} results.")
            self.status_label.setStyleSheet(self._p["status_found"])

    def on_item_double_clicked(self, item, column):
        file_path = item.data(0, Qt.ItemDataRole.UserRole)
        line_num  = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if file_path:
            self.open_file_request.emit(file_path, line_num or 1)

    def focus_search(self):
        self.search_input.selectAll()
        self.search_input.setFocus()

    # ── Cleanup ───────────────────────────────────────────────────────────

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait()
        try:
            theme_signals.theme_changed.disconnect(self._on_theme_changed)
        except RuntimeError:
            pass
        super().closeEvent(event)