import subprocess
import os
import threading
from PyQt6.QtWidgets import (QDockWidget, QWidget, QVBoxLayout, QTreeWidget,
                              QTreeWidgetItem, QPushButton, QHBoxLayout,
                              QLineEdit, QMessageBox, QTreeWidgetItemIterator,
                              QMenu, QApplication, QComboBox, QInputDialog)
from PyQt6.QtCore import Qt, pyqtSignal, QDir, QThread
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor

from ui.diff_viewer import DiffViewerDialog
from ui.theme import (get_theme, theme_signals,
                      build_git_panel_stylesheet,
                      build_git_panel_parts)
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

        self._p = build_git_panel_parts(get_theme())
        self._rebuild_icons()
        self._setup_ui()
        self.refresh_status()

        theme_signals.theme_changed.connect(self._on_theme_changed)

    # ── Theme handling ────────────────────────────────────────────────────

    def _on_theme_changed(self, t: dict):
        self._p = build_git_panel_parts(t)
        self.apply_styles(t)
        self._rebuild_icons()
        self.refresh_status()

    def apply_styles(self, t: dict):
        p = self._p
        self.setStyleSheet(build_git_panel_stylesheet(t))
        self.refresh_btn.setStyleSheet(p["action_btn"])
        self.push_btn.setStyleSheet(p["action_btn"])
        self.blame_btn.setStyleSheet(p["action_btn"])
        self.tree.setStyleSheet(p["tree"])
        self.commit_input.setStyleSheet(p["commit_input"])
        self.ai_msg_btn.setStyleSheet(p["ai_msg_btn"])
        self.commit_btn.setStyleSheet(p["commit_btn"])
        self.branch_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {t['bg2']};
                color: {t['fg1']};
                border: 1px solid {t['border']};
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 9pt;
            }}
            QComboBox::drop-down {{ border: none; width: 16px; }}
            QComboBox QAbstractItemView {{
                background-color: {t['bg1']};
                color: {t['fg1']};
                selection-background-color: {t['highlight']};
                border: 1px solid {t['border']};
            }}
        """)

    def _rebuild_icons(self):
        t = get_theme()
        self.folder_icon = self._create_icon(t['yellow'],  t['bg0_hard'], is_folder=True)
        self.file_icon   = self._create_icon(t['fg4'],     t['bg0_hard'], is_folder=False)
        self.py_icon     = self._create_icon(t['blue'],    t['bg0_hard'], is_folder=False)
        self.html_icon   = self._create_icon(t['orange'],  t['bg0_hard'], is_folder=False)

    @staticmethod
    def _create_icon(color: str, bg_hard: str, is_folder: bool) -> QIcon:
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
            painter.setBrush(QColor(bg_hard))
            painter.drawRect(5, 5, 6, 1)
            painter.drawRect(5, 8, 6, 1)
            painter.drawRect(5, 11, 4, 1)
        painter.end()
        return QIcon(pixmap)

    # ── UI Setup ──────────────────────────────────────────────────────────

    def _setup_ui(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(4)

        # ── Branch row ────────────────────────────────────────────────────
        branch_layout = QHBoxLayout()
        branch_layout.setSpacing(4)

        self.branch_combo = QComboBox()
        self.branch_combo.setToolTip("Current branch — select to switch")
        self.branch_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToContents
        )
        self.branch_combo.activated.connect(self._on_branch_selected)

        new_branch_btn = QPushButton("+ Branch")
        new_branch_btn.setToolTip("Create a new branch")
        new_branch_btn.setFixedHeight(26)
        new_branch_btn.clicked.connect(self._create_branch)
        new_branch_btn.setStyleSheet(self._p["action_btn"])

        tag_btn = QPushButton("🏷 Tag")
        tag_btn.setToolTip("Create a tag at HEAD")
        tag_btn.setFixedHeight(26)
        tag_btn.clicked.connect(self._create_tag)
        tag_btn.setStyleSheet(self._p["action_btn"])

        branch_layout.addWidget(self.branch_combo, 1)
        branch_layout.addWidget(new_branch_btn)
        branch_layout.addWidget(tag_btn)

        # ── Action bar ────────────────────────────────────────────────────
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(4)

        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.clicked.connect(self.refresh_status)

        self.push_btn = QPushButton("↑ Push")
        self.push_btn.clicked.connect(self.push_changes)

        self.blame_btn = QPushButton("👤 Blame")
        self.blame_btn.setToolTip("Toggle git blame in the editor gutter")
        self.blame_btn.setCheckable(True)
        self.blame_btn.clicked.connect(self._toggle_blame)

        btn_layout.addWidget(self.refresh_btn)
        btn_layout.addWidget(self.push_btn)
        btn_layout.addWidget(self.blame_btn)
        btn_layout.addStretch()

        # ── File tree ─────────────────────────────────────────────────────
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(15)
        self.tree.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)

        # ── Commit area ───────────────────────────────────────────────────
        self.commit_input = QLineEdit()
        self.commit_input.setPlaceholderText("Message (Enter to commit)")
        self.commit_input.returnPressed.connect(self.commit_changes)

        commit_btn_layout = QHBoxLayout()
        commit_btn_layout.setSpacing(4)

        self.ai_msg_btn = QPushButton("✨ AI Message")
        self.ai_msg_btn.clicked.connect(self.generate_ai_commit_message)

        self.commit_btn = QPushButton("✓ Commit Selected")
        self.commit_btn.clicked.connect(self.commit_changes)

        commit_btn_layout.addWidget(self.ai_msg_btn)
        commit_btn_layout.addWidget(self.commit_btn)

        layout.addLayout(branch_layout)
        layout.addLayout(btn_layout)
        layout.addWidget(self.tree)
        layout.addWidget(self.commit_input)
        layout.addLayout(commit_btn_layout)
        self.setWidget(container)

        self.apply_styles(get_theme())

    # ── Branch management ─────────────────────────────────────────────────

    def _refresh_branches(self):
        ok, output = self.run_git_command(['git', 'branch'])
        if not ok:
            return
        self.branch_combo.blockSignals(True)
        self.branch_combo.clear()
        current = ''
        for line in output.splitlines():
            name = line.strip().lstrip('* ').strip()
            if name:
                self.branch_combo.addItem(name)
            if line.startswith('*'):
                current = name
        if current:
            self.branch_combo.setCurrentText(current)
        self.branch_combo.blockSignals(False)

    def _on_branch_selected(self, index: int):
        name = self.branch_combo.itemText(index)
        ok, current = self.run_git_command(['git', 'branch', '--show-current'])
        if ok and current.strip() == name:
            return

        ok2, status = self.run_git_command(['git', 'status', '--porcelain'])
        if ok2 and status.strip():
            reply = QMessageBox.question(
                self, "Uncommitted Changes",
                f"You have uncommitted changes. Switch to '{name}' anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                self._refresh_branches()
                return

        ok3, err = self.run_git_command(['git', 'checkout', name])
        if not ok3:
            QMessageBox.critical(self, "Switch Branch Failed", err)
            self._refresh_branches()
        else:
            self.refresh_status()
            if hasattr(self.parent_window, 'update_git_branch'):
                self.parent_window.update_git_branch()
            if self.parent_window:
                self.parent_window.statusBar().showMessage(
                    f"Switched to branch '{name}'", 3000
                )

    def _create_branch(self):
        name, ok = QInputDialog.getText(self, "New Branch", "Branch name:")
        if not ok or not name.strip():
            return
        name = name.strip().replace(' ', '-')

        reply = QMessageBox.question(
            self, "Switch to Branch",
            f"Create branch '{name}' and switch to it now?",
            QMessageBox.StandardButton.Yes |
            QMessageBox.StandardButton.No |
            QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Cancel:
            return

        if reply == QMessageBox.StandardButton.Yes:
            ok2, err = self.run_git_command(['git', 'checkout', '-b', name])
        else:
            ok2, err = self.run_git_command(['git', 'branch', name])

        if not ok2:
            QMessageBox.critical(self, "Create Branch Failed", err)
        else:
            self.refresh_status()
            if hasattr(self.parent_window, 'update_git_branch'):
                self.parent_window.update_git_branch()
            if self.parent_window:
                self.parent_window.statusBar().showMessage(
                    f"Branch '{name}' created", 3000
                )

    def _create_tag(self):
        name, ok = QInputDialog.getText(
            self, "Create Tag", "Tag name (e.g. v1.0.0):"
        )
        if not ok or not name.strip():
            return
        name = name.strip()

        msg, ok2 = QInputDialog.getText(
            self, "Tag Message",
            "Annotation message (leave blank for lightweight tag):"
        )
        if not ok2:
            return

        if msg.strip():
            success, err = self.run_git_command(
                ['git', 'tag', '-a', name, '-m', msg.strip()]
            )
        else:
            success, err = self.run_git_command(['git', 'tag', name])

        if not success:
            QMessageBox.critical(self, "Tag Failed", err)
            return

        reply = QMessageBox.question(
            self, "Tag Created",
            f"Tag '{name}' created. Push it to remote now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            ok3, err2 = self.run_git_command(['git', 'push', 'origin', name])
            if not ok3:
                QMessageBox.critical(self, "Push Tag Failed", err2)
            elif self.parent_window:
                self.parent_window.statusBar().showMessage(
                    f"Tag '{name}' pushed to origin", 3000
                )

    # ── Git blame ─────────────────────────────────────────────────────────

    def _toggle_blame(self):
        editor = self.parent_window.current_editor() if self.parent_window else None
        if not editor or not hasattr(editor, 'toggle_blame'):
            self.blame_btn.setChecked(False)
            return
        editor.toggle_blame()
        self.blame_btn.setChecked(editor._blame_visible)

    # ── Git operations ────────────────────────────────────────────────────

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
                check=True,
            )
            return True, result.stdout.strip()
        except subprocess.CalledProcessError as e:
            return False, e.stderr.strip()
        except FileNotFoundError:
            return False, "Git executable not found in PATH."
        except Exception as e:
            return False, str(e)

    def _get_diff_for_ai(self) -> str:
        CAP = 6000
        checked = []
        it = QTreeWidgetItemIterator(self.tree)
        while it.value():
            item = it.value()
            rel_path = item.data(0, Qt.ItemDataRole.UserRole)
            if rel_path and item.checkState(0) == Qt.CheckState.Checked:
                checked.append(rel_path)
            it += 1

        if checked:
            ok, diff = self.run_git_command(['git', 'diff', 'HEAD', '--'] + checked)
            if not ok or not diff.strip():
                ok, diff = self.run_git_command(['git', 'diff', '--cached', '--'] + checked)
        else:
            ok, diff = self.run_git_command(['git', 'diff', 'HEAD'])
            if not ok or not diff.strip():
                ok, diff = self.run_git_command(['git', 'diff', '--cached'])

        if not ok or not diff.strip():
            return ""
        if len(diff) > CAP:
            diff = diff[:CAP] + "\n...(diff truncated)..."
        return diff

    def generate_ai_commit_message(self):
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
            result_buf.append(text)

        def on_finished():
            self._ai_thread = None
            self._ai_worker = None
            raw = ''.join(result_buf).strip().strip('"\'`')
            lines = [l.strip() for l in raw.split('\n') if l.strip()]
            message = lines[0] if lines else ""
            self.commit_input.setText(message)
            self.commit_input.setPlaceholderText("Message (Enter to commit)")
            self.ai_msg_btn.setText("✨ AI Message")
            self.ai_msg_btn.setEnabled(True)
            self.commit_input.setFocus()
            self.commit_input.selectAll()

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
        p = self._p
        self.tree.clear()
        self._refresh_branches()

        success, output = self.run_git_command(['git', 'status', '--porcelain', '-u'])

        if not success:
            self.tree.addTopLevelItem(
                QTreeWidgetItem([f"Not a git repo or git error: {output}"])
            )
            return

        if not output:
            self.tree.addTopLevelItem(QTreeWidgetItem(["✓ Clean working tree"]))
            return

        folder_nodes = {}

        for line in output.split('\n'):
            if len(line) < 3:
                continue
            status    = line[:2]
            file_path = line[2:].strip().strip('"')
            parts     = file_path.split('/')
            current_parent = self.tree.invisibleRootItem()

            for i, part in enumerate(parts[:-1]):
                folder_path = '/'.join(parts[:i + 1])
                if folder_path not in folder_nodes:
                    node = QTreeWidgetItem([part])
                    node.setIcon(0, self.folder_icon)
                    current_parent.addChild(node)
                    folder_nodes[folder_path] = node
                current_parent = folder_nodes[folder_path]

            filename  = parts[-1]
            file_item = QTreeWidgetItem([f"[{status.strip()}] {filename}"])

            lower = filename.lower()
            if lower.endswith('.py'):
                file_item.setIcon(0, self.py_icon)
            elif lower.endswith(('.html', '.htm')):
                file_item.setIcon(0, self.html_icon)
            else:
                file_item.setIcon(0, self.file_icon)

            if 'M' in status:
                color = p["status_modified"]
            elif '?' in status or 'A' in status:
                color = p["status_added"]
            elif 'D' in status:
                color = p["status_deleted"]
            else:
                color = p["status_default"]

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
        menu.setStyleSheet(self._p["context_menu"])
        diff_action    = menu.addAction("🔍 View Diff")
        blame_action   = menu.addAction("👤 Blame This File")
        menu.addSeparator()
        discard_action = menu.addAction("❌ Discard Changes")

        action = menu.exec(self.tree.viewport().mapToGlobal(position))

        if action == diff_action:
            dialog = DiffViewerDialog(rel_path, self.repo_path, self)
            dialog.exec()
        elif action == blame_action:
            if self.parent_window:
                base = self.repo_path or QDir.currentPath()
                full = os.path.join(base, rel_path)
                self.parent_window.open_file_in_tab(full)
                editor = self.parent_window.current_editor()
                if editor and hasattr(editor, 'toggle_blame'):
                    if not editor._blame_visible:
                        editor.toggle_blame()
                    self.blame_btn.setChecked(True)
        elif action == discard_action:
            reply = QMessageBox.question(
                self, "Discard Changes",
                f"Permanently discard all changes to:\n{rel_path}?\n\nThis cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
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

    def closeEvent(self, event):
        try:
            theme_signals.theme_changed.disconnect(self._on_theme_changed)
        except RuntimeError:
            pass
        super().closeEvent(event)