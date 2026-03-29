import subprocess
import os
import threading
from PyQt6.QtWidgets import (QDockWidget, QWidget, QVBoxLayout, QTreeWidget,
                              QTreeWidgetItem, QPushButton, QHBoxLayout,
                              QLineEdit, QMessageBox, QTreeWidgetItemIterator,
                              QMenu, QApplication)
from PyQt6.QtCore import Qt, pyqtSignal, QDir, QThread
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor

from ui.diff_viewer import DiffViewerDialog
from ai.worker import AIWorker


class GitDockWidget(QDockWidget):
    file_double_clicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__("Source Control", parent)
        self.setObjectName("git_dock")
        self.parent_window = parent
        self.repo_path = None
        self._ai_thread = None
        self._ai_worker = None

        self.folder_icon = self._create_icon("#D4A373", is_folder=True)
        self.file_icon   = self._create_icon("#A9A9A9", is_folder=False)
        self.py_icon     = self._create_icon("#4B8BBE", is_folder=False)
        self.html_icon   = self._create_icon("#E34F26", is_folder=False)

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

        # Action bar
        btn_layout = QHBoxLayout()
        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.setStyleSheet(
            "QPushButton { background-color: #3E3E42; color: white; border-radius: 4px; padding: 4px 8px; }"
            "QPushButton:hover { background-color: #4E4E52; }"
        )
        self.refresh_btn.clicked.connect(self.refresh_status)

        self.push_btn = QPushButton("↑ Push")
        self.push_btn.setStyleSheet(
            "QPushButton { background-color: #3E3E42; color: white; border-radius: 4px; padding: 4px 8px; }"
            "QPushButton:hover { background-color: #4E4E52; }"
        )
        self.push_btn.clicked.connect(self.push_changes)

        btn_layout.addWidget(self.refresh_btn)
        btn_layout.addWidget(self.push_btn)
        btn_layout.addStretch()

        # File tree
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
            QTreeWidget::indicator:unchecked {
                border: 1px solid #555; background-color: #1E1E1E;
                border-radius: 2px; width: 12px; height: 12px;
            }
            QTreeWidget::indicator:checked {
                background-color: #0E639C; border: 1px solid #0E639C;
                border-radius: 2px; width: 12px; height: 12px;
            }
        """)
        self.tree.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)

        # Commit message input
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

        # AI message button + commit button row
        commit_btn_layout = QHBoxLayout()
        commit_btn_layout.setSpacing(4)

        self.ai_msg_btn = QPushButton("✨ AI Message")
        self.ai_msg_btn.setStyleSheet("""
            QPushButton {
                background-color: #8A2BE2;
                color: white;
                border-radius: 4px;
                padding: 6px 10px;
                font-weight: bold;
                font-size: 9pt;
            }
            QPushButton:hover { background-color: #9B30FF; }
            QPushButton:disabled { background-color: #4A1A7A; color: #888888; }
        """)
        self.ai_msg_btn.clicked.connect(self.generate_ai_commit_message)

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

        commit_btn_layout.addWidget(self.ai_msg_btn)
        commit_btn_layout.addWidget(self.commit_btn)

        layout.addLayout(btn_layout)
        layout.addWidget(self.tree)
        layout.addWidget(self.commit_input)
        layout.addLayout(commit_btn_layout)
        self.setWidget(container)

    # ── Git operations ────────────────────────────────────────────

    def set_repo_path(self, path):
        self.repo_path = path
        self.refresh_status()

    def run_git_command(self, args):
        try:
            result = subprocess.run(
                args,
                cwd=self.repo_path or None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                check=True
            )
            return True, result.stdout.strip()
        except subprocess.CalledProcessError as e:
            return False, e.stderr.strip()
        except FileNotFoundError:
            return False, "Git executable not found in PATH."
        except Exception as e:
            return False, str(e)

    def _get_diff_for_ai(self) -> str:
        """
        Gets the diff of checked files, or falls back to unstaged
        diff if nothing is checked. Caps at 6000 chars so we don't
        blow the context window.
        """
        CAP = 6000

        # Collect checked files
        checked = []
        it = QTreeWidgetItemIterator(self.tree)
        while it.value():
            item = it.value()
            rel_path = item.data(0, Qt.ItemDataRole.UserRole)
            if rel_path and item.checkState(0) == Qt.CheckState.Checked:
                checked.append(rel_path)
            it += 1

        if checked:
            # Diff only the checked files against HEAD
            ok, diff = self.run_git_command(
                ['git', 'diff', 'HEAD', '--'] + checked
            )
            if not ok or not diff.strip():
                # Try staged diff
                ok, diff = self.run_git_command(
                    ['git', 'diff', '--cached', '--'] + checked
                )
        else:
            # No files checked — diff everything
            ok, diff = self.run_git_command(['git', 'diff', 'HEAD'])
            if not ok or not diff.strip():
                ok, diff = self.run_git_command(['git', 'diff', '--cached'])

        if not ok or not diff.strip():
            return ""

        # Cap the diff size
        if len(diff) > CAP:
            diff = diff[:CAP] + "\n...(diff truncated)..."

        return diff

    def generate_ai_commit_message(self):
        """Generate a commit message using the AI based on the current diff."""
        if not self.parent_window:
            return
    
        if self._ai_thread is not None:
            try:
                if self._ai_thread.isRunning():
                    return
            except RuntimeError:
                self._ai_thread = None
    
        diff = self._get_diff_for_ai()
        if not diff:
            QMessageBox.information(
                self, "No Changes",
                "No changes found to generate a commit message from.\n\n"
                "Make sure you have uncommitted changes or check the files you want to commit."
            )
            return
    
        _, log = self.run_git_command(['git', 'log', '--oneline', '-10'])
    
        prompt = f"""Generate a concise git commit message for the following diff.
    
    Rules:
    - Use the imperative mood ("Add feature" not "Added feature")
    - Keep it under 72 characters — be concise
    - If you cannot fit it in 72 characters, summarize rather than truncate
    - Be specific about what changed and why
    - Do not include bullet points or line breaks — single line only
    - Do not wrap in quotes
    - Match the style of the recent commit history if provided
    
    Recent commit history (for style reference):
    {log if log else "No history available"}
    
    Diff:
    {diff}
    
    Respond with ONLY the commit message. Nothing else."""
    
        self.ai_msg_btn.setText("✨ Thinking...")
        self.ai_msg_btn.setEnabled(False)
        self.commit_input.clear()
        self.commit_input.setPlaceholderText("Generating commit message...")
    
        thread = QThread()
        worker = AIWorker(
            prompt=prompt,
            editor_text="",
            cursor_pos=0,
            is_chat=True,
            model=self.parent_window.settings_manager.get_chat_model(),
            api_url=self.parent_window.settings_manager.get_api_url(),
            api_key=self.parent_window.settings_manager.get_api_key(),
            backend=self.parent_window.settings_manager.get_backend(),
        )
    
        self._ai_thread = thread
        self._ai_worker = worker
        result_buf = []
    
        def on_update(text):
            # Collect silently — do NOT touch the UI here
            result_buf.append(text)
    
        def on_finished():
            self._ai_thread = None
            self._ai_worker = None
    
            raw = ''.join(result_buf).strip()
    
            # Strip any quotes the AI might have added
            raw = raw.strip('"\'`')
    
            # Take only the first non-empty line
            lines = [l.strip() for l in raw.split('\n') if l.strip()]
            message = lines[0] if lines else ""
    
            # Trim to 72 chars if needed
            if len(message) > 72:
                message = message[:69] + "..."
    
            self.commit_input.setText(message)
            self.commit_input.setPlaceholderText("Message (Enter to commit)")
            self.ai_msg_btn.setText("✨ AI Message")
            self.ai_msg_btn.setEnabled(True)
            self.commit_input.setFocus()
            self.commit_input.selectAll()
    
        # Connect update_ghost to collect tokens silently
        worker.chat_update.connect(on_update)
        worker.finished.connect(on_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.started.connect(worker.run)
        thread.start()
    
        if hasattr(self.parent_window, 'active_threads'):
            self.parent_window.active_threads.append(thread)
            thread.finished.connect(
                lambda: self.parent_window.active_threads.remove(thread)
                if thread in self.parent_window.active_threads else None
            )

    def refresh_status(self):
        self.tree.clear()
        success, output = self.run_git_command(['git', 'status', '--porcelain', '-u'])

        if not success:
            self.tree.addTopLevelItem(QTreeWidgetItem([f"Not a git repo or git error: {output}"]))
            return

        if not output:
            self.tree.addTopLevelItem(QTreeWidgetItem(["✓ Clean working tree"]))
            return

        folder_nodes = {}

        for line in output.split('\n'):
            if len(line) < 3:
                continue

            status = line[:2]
            file_path = line[2:].strip().strip('"')
            parts = file_path.split('/')
            current_parent = self.tree.invisibleRootItem()

            for i, part in enumerate(parts[:-1]):
                folder_path = '/'.join(parts[:i + 1])
                if folder_path not in folder_nodes:
                    node = QTreeWidgetItem([part])
                    node.setIcon(0, self.folder_icon)
                    current_parent.addChild(node)
                    folder_nodes[folder_path] = node
                current_parent = folder_nodes[folder_path]

            filename = parts[-1]
            file_item = QTreeWidgetItem([f"[{status.strip()}] {filename}"])

            lower = filename.lower()
            if lower.endswith('.py'):
                file_item.setIcon(0, self.py_icon)
            elif lower.endswith(('.html', '.htm')):
                file_item.setIcon(0, self.html_icon)
            else:
                file_item.setIcon(0, self.file_icon)

            color = "#CCCCCC"
            if 'M' in status:
                color = "#FFD700"
            elif '?' in status or 'A' in status:
                color = "#4CAF50"
            elif 'D' in status:
                color = "#F44336"

            file_item.setForeground(0, QColor(color))
            file_item.setData(0, Qt.ItemDataRole.UserRole, file_path)
            file_item.setFlags(file_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            file_item.setCheckState(0, Qt.CheckState.Unchecked)
            current_parent.addChild(file_item)

        self.tree.expandAll()

    def show_context_menu(self, position):
        item = self.tree.itemAt(position)
        if not item:
            return
        rel_path = item.data(0, Qt.ItemDataRole.UserRole)
        if not rel_path:
            return

        menu = QMenu()
        menu.setStyleSheet("""
            QMenu { background-color: #252526; color: #CCCCCC; border: 1px solid #3E3E42; }
            QMenu::item { padding: 6px 20px; }
            QMenu::item:selected { background-color: #0E639C; color: white; }
        """)
        diff_action    = menu.addAction("🔍 View Diff")
        menu.addSeparator()
        discard_action = menu.addAction("❌ Discard Changes")

        action = menu.exec(self.tree.viewport().mapToGlobal(position))

        if action == diff_action:
            dialog = DiffViewerDialog(rel_path, self.repo_path, self)
            dialog.exec()

        elif action == discard_action:
            reply = QMessageBox.question(
                self, "Discard Changes",
                f"Permanently discard all changes to:\n{rel_path}?\n\nThis cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.run_git_command(['git', 'checkout', '--', rel_path])
                self.run_git_command(['git', 'clean', '-fd', rel_path])
                self.refresh_status()
                QMessageBox.information(
                    self, "Restored",
                    "Changes discarded. If the file is open, close and reopen it to see the original."
                )

    def commit_changes(self):
        message = self.commit_input.text().strip()
        if not message:
            QMessageBox.warning(self, "Commit Error", "Please enter a commit message.")
            return

        files_to_add = []
        it = QTreeWidgetItemIterator(self.tree)
        while it.value():
            item = it.value()
            rel_path = item.data(0, Qt.ItemDataRole.UserRole)
            if rel_path and item.checkState(0) == Qt.CheckState.Checked:
                files_to_add.append(rel_path)
            it += 1

        if not files_to_add:
            QMessageBox.information(
                self, "Nothing Selected",
                "Check the boxes next to the files you want to commit."
            )
            return

        ok, err = self.run_git_command(['git', 'add'] + files_to_add)
        if not ok:
            QMessageBox.critical(self, "Git Add Error", err)
            return

        ok, err = self.run_git_command(['git', 'commit', '-m', message])
        if not ok:
            QMessageBox.critical(self, "Git Commit Error", err)
            return

        self.commit_input.clear()
        self.refresh_status()
        self.commit_btn.setText("✓ Committed!")
        threading.Timer(2.0, lambda: self.commit_btn.setText("✓ Commit Selected")).start()

        if hasattr(self.parent_window, 'update_git_branch'):
            self.parent_window.update_git_branch()

    def push_changes(self):
        self.push_btn.setText("Pushing...")
        self.push_btn.setEnabled(False)
        QApplication.processEvents()

        ok, err = self.run_git_command(['git', 'push'])

        self.push_btn.setEnabled(True)
        self.push_btn.setText("↑ Push")

        if not ok:
            QMessageBox.critical(self, "Git Push Error", err)
        else:
            QMessageBox.information(self, "Push Successful", "Changes pushed successfully!")
            self.refresh_status()

        if hasattr(self.parent_window, 'update_git_branch'):
            self.parent_window.update_git_branch()

    def on_item_double_clicked(self, item, column):
        rel_path = item.data(0, Qt.ItemDataRole.UserRole)
        if rel_path:
            base = self.repo_path if self.repo_path else QDir.currentPath()
            self.file_double_clicked.emit(os.path.join(base, rel_path))