import subprocess
import os
from PyQt6.QtWidgets import (QDockWidget, QWidget, QVBoxLayout, QTreeWidget, 
                             QTreeWidgetItem, QPushButton, QHBoxLayout)
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

        btn_layout = QHBoxLayout()
        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.setStyleSheet("QPushButton { background-color: #3E3E42; color: white; border-radius: 4px; padding: 4px; } QPushButton:hover { background-color: #4E4E52; }")
        self.refresh_btn.clicked.connect(self.refresh_status)
        btn_layout.addWidget(self.refresh_btn)
        btn_layout.addStretch()

        # [NEW] Swapped QListWidget for QTreeWidget
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(15)
        # Inherited the exact CSS from your main.py QTreeView
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
        """)
        self.tree.itemDoubleClicked.connect(self.on_item_double_clicked)

        layout.addLayout(btn_layout)
        layout.addWidget(self.tree)
        self.setWidget(container)

    def refresh_status(self):
        self.tree.clear()
        current_dir = QDir.currentPath()

        try:
            result = subprocess.run(
                ['git', 'status', '--porcelain', '-u'], 
                cwd=current_dir, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )
            
            output = result.stdout.strip()
            if not output:
                item = QTreeWidgetItem(["No changes (Clean working tree)"])
                self.tree.addTopLevelItem(item)
                return

            # [NEW] Dictionary to track folder nodes so we don't duplicate them
            folder_nodes = {}

            for line in output.split('\n'):
                if len(line) < 3: continue
                
                status = line[:2]
                file_path = line[3:].strip('"') # Strip quotes in case of spaces
                parts = file_path.split('/')
                
                # Start at the root of the tree
                current_parent = self.tree.invisibleRootItem()

                # Build the folder hierarchy
                for i, part in enumerate(parts[:-1]):
                    folder_path = '/'.join(parts[:i+1])
                    if folder_path not in folder_nodes:
                        node = QTreeWidgetItem([part])
                        node.setIcon(0, self.folder_icon)
                        current_parent.addChild(node)
                        folder_nodes[folder_path] = node
                    current_parent = folder_nodes[folder_path]

                # Now add the actual file item to the deepest folder
                filename = parts[-1]
                display_text = f"[{status.strip()}] {filename}"
                file_item = QTreeWidgetItem([display_text])
                
                # Apply file icon
                lower_path = filename.lower()
                if lower_path.endswith('.py'):
                    file_item.setIcon(0, self.py_icon)
                elif lower_path.endswith(('.html', '.htm')):
                    file_item.setIcon(0, self.html_icon)
                else:
                    file_item.setIcon(0, self.file_icon)

                # Apply status color
                color = "#CCCCCC" # Default
                if 'M' in status: color = "#FFD700"      # Yellow
                elif '?' in status or 'A' in status: color = "#4CAF50" # Green
                elif 'D' in status: color = "#F44336"    # Red
                
                file_item.setForeground(0, QColor(color))
                
                # Store the relative path ONLY on actual files
                file_item.setData(0, Qt.ItemDataRole.UserRole, file_path)
                current_parent.addChild(file_item)

            # Expand the tree so everything is visible by default
            self.tree.expandAll()

        except subprocess.CalledProcessError:
            self.tree.addTopLevelItem(QTreeWidgetItem(["Not a Git repository."]))
        except FileNotFoundError:
            self.tree.addTopLevelItem(QTreeWidgetItem(["Git is not installed/found."]))

    def on_item_double_clicked(self, item, column):
        # [FIXED] Only files have UserRole data. Clicking folders does nothing.
        rel_path = item.data(0, Qt.ItemDataRole.UserRole)
        if rel_path:
            abs_path = os.path.join(QDir.currentPath(), rel_path)
            self.file_double_clicked.emit(abs_path)