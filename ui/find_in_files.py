import os
import fnmatch
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, 
                             QPushButton, QTreeWidget, QTreeWidgetItem, QLabel, QProgressBar)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QDir
from PyQt6.QtGui import QFont, QColor

# ==========================================
# Background Worker to prevent GUI freezing
# ==========================================
class SearchWorker(QThread):
    # Signals: file_path, list of (line_number, line_text)
    file_matches_found = pyqtSignal(str, list)
    search_finished = pyqtSignal(int) # Returns total match count

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
                
            # Skip hidden directories like .git
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
                except UnicodeDecodeError:
                    # Ignore binary files (images, compiled pyc, etc.)
                    pass
                except Exception:
                    pass

        self.search_finished.emit(total_matches)

    def stop(self):
        self._is_running = False

# ==========================================
# The UI Panel
# ==========================================
class FindInFilesWidget(QWidget):
    # Signal to tell main.py to open a specific file and jump to a line
    open_file_request = pyqtSignal(str, int) 

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.worker = None
        self.setup_ui()

    def setup_ui(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #252526;
                color: #CCCCCC;
                font-family: 'Inter', 'SF Pro Text', 'Segoe UI', sans-serif;
                font-size: 10pt;
            }
            QLineEdit {
                background-color: #3C3C3C;
                color: #FFFFFF;
                border: 1px solid #3E3E42;
                border-radius: 4px;
                padding: 6px;
            }
            QLineEdit:focus { border: 1px solid #0E639C; }
            QPushButton {
                background-color: #0E639C;
                color: white;
                border-radius: 4px;
                padding: 6px 16px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #1177BB; }
            QTreeWidget {
                background-color: #1E1E1E;
                color: #CCCCCC;
                border: 1px solid #3E3E42;
                border-radius: 4px;
                font-size: 10pt;
            }
            QTreeWidget::item { padding: 4px; }
            QTreeWidget::item:selected { background-color: #37373D; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # --- Search Inputs ---
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

        # --- Status Bar ---
        status_layout = QHBoxLayout()
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #888888;")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0) # Indeterminate spinning mode
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.hide()
        
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        status_layout.addWidget(self.progress_bar)

        # --- Results Tree ---
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

        # Stop existing search if one is running
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait()

        self.results_tree.clear()
        self.status_label.setText("Searching...")
        self.progress_bar.show()

        # Get project root from the main window's Explorer
        search_dir = QDir.currentPath()
        if hasattr(self.main_window, 'tree_view') and self.main_window.file_model:
            search_dir = self.main_window.file_model.filePath(self.main_window.tree_view.rootIndex())

        file_pattern = self.filter_input.text() or "*"

        self.worker = SearchWorker(search_dir, query, file_pattern)
        self.worker.file_matches_found.connect(self.add_file_results)
        self.worker.search_finished.connect(self.on_search_finished)
        self.worker.start()

    def add_file_results(self, file_path, matches):
        # Create a parent node for the File
        filename = os.path.basename(file_path)
        file_node = QTreeWidgetItem([f"{filename} ({len(matches)} matches)"])
        file_node.setForeground(0, QColor("#569CD6")) # Blue for files
        file_node.setData(0, Qt.ItemDataRole.UserRole, file_path)
        
        font = QFont()
        font.setBold(True)
        file_node.setFont(0, font)

        # Add child nodes for the specific lines
        for line_num, text in matches:
            # Truncate super long lines so the UI looks clean
            display_text = text if len(text) < 150 else text[:150] + "..."
            
            line_node = QTreeWidgetItem([f"{line_num}: {display_text}"])
            line_node.setForeground(0, QColor("#CCCCCC"))
            line_node.setFont(0, QFont("JetBrains Mono", 9))
            
            # Store data so double clicking knows exactly where to go
            line_node.setData(0, Qt.ItemDataRole.UserRole, file_path)
            line_node.setData(0, Qt.ItemDataRole.UserRole + 1, line_num)
            
            file_node.addChild(line_node)

        self.results_tree.addTopLevelItem(file_node)
        file_node.setExpanded(True)

    def on_search_finished(self, total_matches):
        self.progress_bar.hide()
        if total_matches == 0:
            self.status_label.setText("No matches found.")
        else:
            self.status_label.setText(f"Found {total_matches} results.")

    def on_item_double_clicked(self, item, column):
        file_path = item.data(0, Qt.ItemDataRole.UserRole)
        line_num = item.data(0, Qt.ItemDataRole.UserRole + 1)
        
        if file_path:
            # If it's a file node, line_num will be None. If it's a line node, it has an int.
            self.open_file_request.emit(file_path, line_num or 1)

    def focus_search(self):
        self.search_input.selectAll()
        self.search_input.setFocus()