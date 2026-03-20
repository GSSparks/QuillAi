import subprocess
import os
from PyQt6.QtWidgets import (QDockWidget, QWidget, QVBoxLayout, QTreeWidget, 
                             QTreeWidgetItem, QPushButton, QHBoxLayout, 
                             QLineEdit, QMessageBox, QTreeWidgetItemIterator)
from PyQt6.QtCore import Qt, pyqtSignal, QDir
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor 

class GitDockWidget(QDockWidget):
    file_double_clicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__("Source Control", parent)
        self.parent_window = parent
        
        self.folder_icon = self._create_icon("#D4A373", is_folder=True)
        self.file_icon = self._create_icon("#A9A9A9", is_folder=False)
        self.py_icon = self._create_icon("#4B8BBE", is_folder=False)
        self.html_icon = self._create_icon("#E34F26", is_folder=False)
        
        self.setup_ui()
        self.refresh_status()

    def _create_icon(self, color, is_folder):
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if is_folder:
            painter.setBrush(QColor(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(1, 2, 7, 4, 1, 1)
            painter.drawRoundedRect(1, 5, 14, 9, 2, 2)
        else:
            painter.setBrush(QColor(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(3, 1, 10, 14, 1, 1)
            painter.setBrush(QColor("#1E1E1E"))
            painter.drawRect(5, 5, 6, 1)
            painter.drawRect(5, 8, 6, 1)
            painter.drawRect(5, 11, 4, 1)

        painter.end()
        return QIcon(pixmap)

    def setup_ui(self):
        self.setStyleSheet("""
            QDockWidget {
                color: #CCCCCC;
                font-family: 'Inter', 'SF Pro Text', 'Segoe UI', sans-serif;
                font-weight: bold;
                font-size: 10pt;
            }
            QDockWidget::title { background-color: #252526; padding: 6px 10px; }
        """)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(5, 5, 5, 5)

        # --- Top Action Bar ---
        btn_layout = QHBoxLayout()
        
        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.setStyleSheet("QPushButton { background-color: #3E3E42; color: white; border-radius: 4px; padding: 4px 8px; } QPushButton:hover { background-color: #4E4E52; }")
        self.refresh_btn.clicked.connect(self.refresh_status)
        
        self.push_btn = QPushButton("↑ Push")
        self.push_btn.setStyleSheet("QPushButton { background-color: #3E3E42; color: white; border-radius: 4px; padding: 4px 8px; } QPushButton:hover { background-color: #4E4E52; }")
        self.push_btn.clicked.connect(self.push_changes)

        btn_layout.addWidget(self.refresh_btn)
        btn_layout.addWidget(self.push_btn)
        btn_layout.addStretch()

        # --- Tree View ---
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(15)
        self.tree.setStyleSheet("""
            QTreeWidget {
                background-color: #1E1E1E;
                color: #CCCCCC;
                border: none;
                font-family: 'Inter', 'SF Pro Text', 'Segoe UI', sans-serif;
                font-size: 11pt; 
            }
            QTreeWidget::item { padding: 4px; }
            QTreeWidget::item:selected { background-color: #37373D; border-radius: 4px; }
            QTreeWidget::item:hover:!selected { background-color: #2A2D2E; border-radius: 4px; }
            QTreeWidget::branch { background-color: transparent; }
            QTreeWidget::indicator:unchecked { border: 1px solid #555; background-color: #1E1E1E; border-radius: 2px; width: 12px; height: 12px; }
            QTreeWidget::indicator:checked { background-color: #0E639C; border: 1px solid #0E639C; border-radius: 2px; width: 12px; height: 12px; }
        """)
        self.tree.itemDoubleClicked.connect(self.on_item_double_clicked)

        # --- Commit Area ---
        self.commit_input = QLineEdit()
        self.commit_input.setPlaceholderText("Message (Enter to commit)")
        self.commit_input.setStyleSheet("""
            QLineEdit {
                background-color: #2D2D30;
                color: #FFFFFF;
                border: 1px solid #3E3E42;
                border-radius: 4px;
                padding: 6px;
                font-family: 'Inter', 'SF Pro Text', 'Segoe UI', sans-serif;
            }
        """)
        self.commit_input.returnPressed.connect(self.commit_changes)

        self.commit_btn = QPushButton("✓ Commit Selected")
        self.commit_btn.setStyleSheet("""
            QPushButton {
                background-color: #0E639C; 
                color: white; 
                border-radius: 4px; 
                padding: 6px; 
                font-weight: bold;
            } 
            QPushButton:hover { background-color: #1177BB; }
        """)
        self.commit_btn.clicked.connect(self.commit_changes)

        # Add everything to main layout
        layout.addLayout(btn_layout)
        layout.addWidget(self.tree)
        layout.addWidget(self.commit_input)
        layout.addWidget(self.commit_btn)
        
        self.setWidget(container)

    # --- Git Command Helper ---
    def run_git_command(self, args):
        """Runs a git command safely and returns (success_bool, output_string)"""
        try:
            result = subprocess.run(
                args,
                cwd=QDir.currentPath(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )
            return True, result.stdout.strip()
        except subprocess.CalledProcessError as e:
            return False, e.stderr.strip()

    # --- Actions ---
    def refresh_status(self):
        self.tree.clear()
        
        success, output = self.run_git_command(['git', 'status', '--porcelain', '-u'])
        if not success:
            self.tree.addTopLevelItem(QTreeWidgetItem(["Git error or not a repository."]))
            return
            
        if not output:
            self.tree.addTopLevelItem(QTreeWidgetItem(["No changes (Clean working tree)"]))
            return

        folder_nodes = {}

        for line in output.split('\n'):
            if len(line) < 3: continue
            
            status = line[:2]
            file_path = line[3:].strip('"') 
            file_path = line[2:].strip().strip('"')
            parts = file_path.split('/')
            
            current_parent = self.tree.invisibleRootItem()

            for i, part in enumerate(parts[:-1]):
                folder_path = '/'.join(parts[:i+1])
                if folder_path not in folder_nodes:
                    node = QTreeWidgetItem([part])
                    node.setIcon(0, self.folder_icon)
                    current_parent.addChild(node)
                    folder_nodes[folder_path] = node
                current_parent = folder_nodes[folder_path]

            filename = parts[-1]
            display_text = f"[{status.strip()}] {filename}"
            file_item = QTreeWidgetItem([display_text])
            
            lower_path = filename.lower()
            if lower_path.endswith('.py'): file_item.setIcon(0, self.py_icon)
            elif lower_path.endswith(('.html', '.htm')): file_item.setIcon(0, self.html_icon)
            else: file_item.setIcon(0, self.file_icon)

            color = "#CCCCCC"
            if 'M' in status: color = "#FFD700"      
            elif '?' in status or 'A' in status: color = "#4CAF50" 
            elif 'D' in status: color = "#F44336"    
            
            file_item.setForeground(0, QColor(color))
            file_item.setData(0, Qt.ItemDataRole.UserRole, file_path)
            
            # [NEW] Make the file checkable so we can "git add" it!
            file_item.setFlags(file_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            file_item.setCheckState(0, Qt.CheckState.Unchecked)
            
            current_parent.addChild(file_item)

        self.tree.expandAll()

    def commit_changes(self):
        message = self.commit_input.text().strip()
        if not message:
            QMessageBox.warning(self, "Commit Error", "Please enter a commit message.")
            return

        # 1. Find all checked files
        files_to_add = []
        iterator = QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            item = iterator.value()
            rel_path = item.data(0, Qt.ItemDataRole.UserRole)
            if rel_path and item.checkState(0) == Qt.CheckState.Checked:
                files_to_add.append(rel_path)
            iterator += 1

        if not files_to_add:
            QMessageBox.information(self, "Nothing Selected", "Please check the boxes next to the files you want to commit.")
            return

        # 2. Git Add
        add_success, add_err = self.run_git_command(['git', 'add'] + files_to_add)
        if not add_success:
            QMessageBox.critical(self, "Git Add Error", add_err)
            return

        # 3. Git Commit
        commit_success, commit_err = self.run_git_command(['git', 'commit', '-m', message])
        if not commit_success:
            QMessageBox.critical(self, "Git Commit Error", commit_err)
            return

        # 4. Cleanup UI
        self.commit_input.clear()
        self.refresh_status()
        self.commit_btn.setText("✓ Committed!")
        
        # Reset button text after 2 seconds
        import threading
        threading.Timer(2.0, lambda: self.commit_btn.setText("✓ Commit Selected")).start()

    def push_changes(self):
        self.push_btn.setText("Pushing...")
        self.push_btn.setEnabled(False)
        
        # We use QApplication.processEvents() to force the UI to update the button text 
        # before the synchronous subprocess call freezes the thread for a second.
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()

        success, err = self.run_git_command(['git', 'push'])
        
        self.push_btn.setEnabled(True)
        self.push_btn.setText("↑ Push")
        
        if not success:
            QMessageBox.critical(self, "Git Push Error", err)
        else:
            QMessageBox.information(self, "Push Successful", "Changes pushed to remote successfully!")
            self.refresh_status()

    def on_item_double_clicked(self, item, column):
        rel_path = item.data(0, Qt.ItemDataRole.UserRole)
        if rel_path:
            abs_path = os.path.join(QDir.currentPath(), rel_path)
            self.file_double_clicked.emit(abs_path)