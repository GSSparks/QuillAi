import subprocess
import os
import threading
from PyQt6.QtWidgets import (QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
                              QTreeWidget, QTreeWidgetItem, QPushButton,
                              QLineEdit, QMessageBox, QTreeWidgetItemIterator,
                              QMenu, QApplication, QComboBox, QInputDialog,
                              QLabel, QFrame, QSizePolicy)
from PyQt6.QtCore import Qt, pyqtSignal, QDir, QThread, QSize
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont

from ui.diff_viewer import DiffViewerDialog
from ui.theme import (get_theme, theme_signals,
                      build_git_panel_stylesheet,
                      build_git_panel_parts,
                      FONT_UI, QFONT_UI)
from ai.worker import AIWorker

# ── SVG icon helpers ──────────────────────────────────────────────────────────

def _svg_icon(svg_path: str, color: str, size: int = 14) -> QIcon:
    """Render a simple SVG path as a QIcon at the given size."""
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QColor(color))
    p.setBrush(Qt.BrushStyle.NoBrush)
    # We paint simple shapes rather than full SVG parsing
    p.end()
    return QIcon(pix)


class StatusBadge(QLabel):
    """Coloured letter badge (M / A / D / ?) shown next to each file."""
    _LABELS = {'M': 'M', 'A': 'A', 'D': 'D', '?': '?', 'R': 'R'}

    def __init__(self, status: str, parts: dict, parent=None):
        super().__init__(parent)
        letter = 'M' if 'M' in status else \
                 'A' if ('A' in status or '?' in status) else \
                 'D' if 'D' in status else \
                 'R' if 'R' in status else '?'
        self.setText(letter)
        fg = (parts['status_modified'] if letter == 'M' else
              parts['status_added']    if letter in ('A', '?') else
              parts['status_deleted']  if letter == 'D' else
              parts['status_default'])
        self.setStyleSheet(f"""
            QLabel {{
                color: {fg};
                background: transparent;
                font-family: {FONT_UI};
                font-size: 8pt;
                font-weight: bold;
                padding: 0 3px;
                border-radius: 2px;
            }}
        """)
        self.setFixedWidth(16)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)


class GitDockWidget(QDockWidget):
    file_double_clicked = pyqtSignal(str)

    # Unicode symbols used as button labels — no emoji, clean monospace
    _ICON_REFRESH = "↻"
    _ICON_SYNC    = "⇅"
    _ICON_BRANCH  = "+ Branch"
    _ICON_TAG     = "⊕ Tag"
    _ICON_BLAME   = "Show blame"
    _ICON_AI      = "✦ AI message"
    _ICON_COMMIT  = "✓ Commit"

    def __init__(self, parent=None):
        super().__init__("Source Control", parent)
        self.setObjectName("git_dock")
        self.parent_window = parent
        self.repo_path  = None
        self._ai_thread = None
        self._ai_worker = None
        self._has_remote = False   # tracks whether push or pull makes sense

        self._p = build_git_panel_parts(get_theme())
        self._rebuild_icons()
        self._setup_ui()
        self.refresh_status()

        theme_signals.theme_changed.connect(self._on_theme_changed)

    # ── Theme ─────────────────────────────────────────────────────────────

    def _on_theme_changed(self, t: dict):
        self._p = build_git_panel_parts(t)
        self.apply_styles(t)
        self._rebuild_icons()
        self.refresh_status()

    def apply_styles(self, t: dict):
        p = self._p
        self.setStyleSheet(build_git_panel_stylesheet(t))
        self.branch_combo.setStyleSheet(p["branch_combo"])
        self.refresh_btn.setStyleSheet(p["icon_btn"])
        self.sync_btn.setStyleSheet(p["icon_btn"])
        self.new_branch_btn.setStyleSheet(p["icon_btn"])
        self.tag_btn.setStyleSheet(p["icon_btn"])
        self.tree.setStyleSheet(p["tree"])
        self.commit_input.setStyleSheet(p["commit_input"])
        self.ai_msg_btn.setStyleSheet(p["ai_msg_btn"])
        self.commit_btn.setStyleSheet(p["commit_btn"])
        self.blame_btn.setStyleSheet(p["blame_btn"])
        # Section label
        self._changes_label.setStyleSheet(p["section_label"])
        # Commit container border
        self._commit_container.setStyleSheet(f"""
            QWidget#commitContainer {{
                border: 1px solid {t['border']};
                border-radius: 4px;
                background-color: {t['bg0_hard']};
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
        layout.setContentsMargins(8, 8, 8, 0)
        layout.setSpacing(6)

        # ── Branch selector ───────────────────────────────────────────────
        self.branch_combo = QComboBox()
        self.branch_combo.setToolTip("Current branch — select to switch")
        self.branch_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.branch_combo.setMinimumWidth(80)
        self.branch_combo.activated.connect(self._on_branch_selected)
        layout.addWidget(self.branch_combo)

        # ── Action row: refresh | sync | + branch | tag ───────────────────
        action_row = QHBoxLayout()
        action_row.setSpacing(4)
        action_row.setContentsMargins(0, 0, 0, 0)

        self.refresh_btn = QPushButton(self._ICON_REFRESH)
        self.refresh_btn.setToolTip("Refresh status")
        self.refresh_btn.setFixedWidth(32)
        self.refresh_btn.clicked.connect(self.refresh_status)

        self.sync_btn = QPushButton(self._ICON_SYNC)
        self.sync_btn.setToolTip("Sync (push / pull)")
        self.sync_btn.setFixedWidth(32)
        self.sync_btn.clicked.connect(self._sync)

        self.new_branch_btn = QPushButton(self._ICON_BRANCH)
        self.new_branch_btn.setToolTip("Create a new branch")
        self.new_branch_btn.clicked.connect(self._create_branch)

        self.tag_btn = QPushButton(self._ICON_TAG)
        self.tag_btn.setToolTip("Create a tag at HEAD")
        self.tag_btn.clicked.connect(self._create_tag)

        action_row.addWidget(self.refresh_btn)
        action_row.addWidget(self.sync_btn)
        action_row.addWidget(self.new_branch_btn)
        action_row.addWidget(self.tag_btn)
        layout.addLayout(action_row)

        # ── Changes section label ─────────────────────────────────────────
        self._changes_label = QLabel("CHANGES")
        layout.addWidget(self._changes_label)

        # ── File tree ─────────────────────────────────────────────────────
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(12)
        self.tree.setRootIsDecorated(False)
        self.tree.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)
        layout.addWidget(self.tree, 1)

        # ── Commit area (grouped container) ───────────────────────────────
        self._commit_container = QWidget()
        self._commit_container.setObjectName("commitContainer")
        self._commit_container.setAttribute(
            Qt.WidgetAttribute.WA_StyledBackground, True
        )
        commit_layout = QVBoxLayout(self._commit_container)
        commit_layout.setContentsMargins(0, 0, 0, 0)
        commit_layout.setSpacing(0)

        # Commit message input
        self.commit_input = QLineEdit()
        self.commit_input.setPlaceholderText("Commit message…")
        self.commit_input.returnPressed.connect(self.commit_changes)
        commit_layout.addWidget(self.commit_input)

        # AI + Commit buttons joined to the input
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(0)

        self.ai_msg_btn = QPushButton(self._ICON_AI)
        self.ai_msg_btn.clicked.connect(self.generate_ai_commit_message)
        self.ai_msg_btn.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )

        self.commit_btn = QPushButton(self._ICON_COMMIT)
        self.commit_btn.clicked.connect(self.commit_changes)
        self.commit_btn.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )

        btn_row.addWidget(self.ai_msg_btn)
        btn_row.addWidget(self.commit_btn)
        commit_layout.addLayout(btn_row)

        layout.addWidget(self._commit_container)

        # ── Blame toggle (full-width subtle strip at bottom) ──────────────
        self.blame_btn = QPushButton(self._ICON_BLAME)
        self.blame_btn.setToolTip("Toggle git blame annotations in the editor gutter")
        self.blame_btn.setCheckable(True)
        self.blame_btn.clicked.connect(self._toggle_blame)
        layout.addWidget(self.blame_btn)

        layout.addSpacing(4)
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

        # Check whether we have a remote to determine sync direction
        ok2, remotes = self.run_git_command(['git', 'remote'])
        self._has_remote = ok2 and bool(remotes.strip())
        self.sync_btn.setToolTip(
            "Push to remote" if self._has_remote else "No remote configured"
        )
        self.sync_btn.setEnabled(self._has_remote)

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
                    f"Switched to '{name}'", 3000
                )

    def _create_branch(self):
        name, ok = QInputDialog.getText(self, "New Branch", "Branch name:")
        if not ok or not name.strip():
            return
        name = name.strip().replace(' ', '-')

        reply = QMessageBox.question(
            self, "Switch to Branch",
            f"Create '{name}' and switch to it now?",
            QMessageBox.StandardButton.Yes |
            QMessageBox.StandardButton.No |
            QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Cancel:
            return

        cmd = ['git', 'checkout', '-b', name] if reply == QMessageBox.StandardButton.Yes \
              else ['git', 'branch', name]
        ok2, err = self.run_git_command(cmd)
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
            f"Tag '{name}' created. Push to remote?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            ok3, err2 = self.run_git_command(['git', 'push', 'origin', name])
            if not ok3:
                QMessageBox.critical(self, "Push Tag Failed", err2)
            elif self.parent_window:
                self.parent_window.statusBar().showMessage(
                    f"Tag '{name}' pushed", 3000
                )

    # ── Sync (push / pull) ────────────────────────────────────────────────

    def _sync(self):
        """Push if we're ahead, pull if we're behind, fetch if unknown."""
        self.sync_btn.setText("…")
        self.sync_btn.setEnabled(False)
        QApplication.processEvents()

        # Check ahead/behind
        ok, ab = self.run_git_command(
            ['git', 'rev-list', '--left-right', '--count', 'HEAD...@{u}']
        )
        ahead = behind = 0
        if ok and ab.strip():
            parts = ab.strip().split()
            if len(parts) == 2:
                try:
                    ahead, behind = int(parts[0]), int(parts[1])
                except ValueError:
                    pass

        if behind > 0 and ahead == 0:
            # Pure pull
            ok2, err = self.run_git_command(['git', 'pull'])
            msg = f"Pulled {behind} commit(s)" if ok2 else err
        else:
            # Push (or push+pull diverged — just push, let git report)
            ok2, err = self.run_git_command(['git', 'push'])
            msg = "Pushed successfully" if ok2 else err

        self.sync_btn.setText(self._ICON_SYNC)
        self.sync_btn.setEnabled(True)

        if not ok2:
            QMessageBox.critical(self, "Sync Failed", err)
        else:
            self.refresh_status()
            if hasattr(self.parent_window, 'update_git_branch'):
                self.parent_window.update_git_branch()
            if self.parent_window:
                self.parent_window.statusBar().showMessage(msg, 3000)

    # ── Git blame ─────────────────────────────────────────────────────────

    def _toggle_blame(self):
        editor = self.parent_window.current_editor() if self.parent_window else None
        if not editor or not hasattr(editor, 'toggle_blame'):
            self.blame_btn.setChecked(False)
            return
        editor.toggle_blame()
        self.blame_btn.setChecked(editor._blame_visible)
        self.blame_btn.setText(
            "Hide blame" if editor._blame_visible else self._ICON_BLAME
        )

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
            return False, "Git not found in PATH."
        except Exception as e:
            return False, str(e)

    def get_current_diff(self, cap: int = 3000) -> str:
        """
        Return a compact diff of current working tree changes.
        Used by the chat context engine — no UI state required.
        Tries unstaged first, then staged, then HEAD.
        """
        for args in (
            ['git', 'diff'],
            ['git', 'diff', '--cached'],
            ['git', 'diff', 'HEAD'],
        ):
            ok, diff = self.run_git_command(args)
            if ok and diff.strip():
                return diff[:cap] + (
                    "\n...(truncated)..." if len(diff) > cap else ""
                )
        return ""

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
        return diff[:CAP] + ("\n...(truncated)..." if len(diff) > CAP else "")

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
            QMessageBox.information(self, "No Changes",
                "No staged or unstaged changes found.")
            return

        _, log = self.run_git_command(['git', 'log', '--oneline', '-10'])

        prompt = f"""Generate a concise git commit message for the following diff.

Rules:
- Imperative mood ("Add feature" not "Added feature")
- Under 72 characters
- Single line only, no bullet points
- No quotes
- Match the style of recent history if provided

Recent commits:
{log or "No history"}

Diff:
{diff}

Respond with ONLY the commit message."""

        self.ai_msg_btn.setText("Thinking…")
        self.ai_msg_btn.setEnabled(False)
        self.commit_input.clear()
        self.commit_input.setPlaceholderText("Generating…")

        thread = QThread()
        worker = AIWorker(
            prompt=prompt, editor_text="", cursor_pos=0, is_chat=True,
            model=self.parent_window.settings_manager.get_active_model(),
            api_url=self.parent_window.settings_manager.get_llm_url(),
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
            self.commit_input.setText(lines[0] if lines else "")
            self.commit_input.setPlaceholderText("Commit message…")
            self.ai_msg_btn.setText(self._ICON_AI)
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

        success, output = self.run_git_command(
            ['git', 'status', '--porcelain', '-u']
        )
        if not success:
            item = QTreeWidgetItem(["Not a git repo"])
            item.setForeground(0, QColor(p['fg4']))
            self.tree.addTopLevelItem(item)
            return

        if not output:
            item = QTreeWidgetItem(["✓  Clean working tree"])
            item.setForeground(0, QColor(p['fg4']))
            self.tree.addTopLevelItem(item)
            return

        for line in output.split('\n'):
            if len(line) < 3:
                continue
            status    = line[:2]
            file_path = line[2:].strip().strip('"')
            filename  = os.path.basename(file_path)

            # Build row widget: checkbox area handled by tree, filename + badge
            file_item = QTreeWidgetItem()
            file_item.setText(0, filename)
            file_item.setToolTip(0, file_path)

            lower = filename.lower()
            if lower.endswith('.py'):
                file_item.setIcon(0, self.py_icon)
            elif lower.endswith(('.html', '.htm')):
                file_item.setIcon(0, self.html_icon)
            else:
                file_item.setIcon(0, self.file_icon)

            # Status color on filename
            if 'M' in status:
                fg = p['status_modified']
            elif '?' in status or 'A' in status:
                fg = p['status_added']
            elif 'D' in status:
                fg = p['status_deleted']
            else:
                fg = p['status_default']
            file_item.setForeground(0, QColor(fg))

            # Status badge as column 1
            badge_letter = ('M' if 'M' in status else
                            'A' if ('A' in status or '?' in status) else
                            'D' if 'D' in status else '?')
            file_item.setText(1, badge_letter)
            file_item.setForeground(1, QColor(fg))
            file_item.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            file_item.setData(0, Qt.ItemDataRole.UserRole, file_path)
            file_item.setFlags(file_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            file_item.setCheckState(0, Qt.CheckState.Unchecked)
            self.tree.addTopLevelItem(file_item)

        self.tree.setColumnCount(2)
        self.tree.setColumnWidth(0, self.tree.width() - 28)
        self.tree.setColumnWidth(1, 20)
        self.tree.header().setStretchLastSection(False)

    def show_context_menu(self, position):
        item = self.tree.itemAt(position)
        if not item:
            return
        rel_path = item.data(0, Qt.ItemDataRole.UserRole)
        if not rel_path:
            return

        menu = QMenu()
        menu.setStyleSheet(self._p["context_menu"])
        diff_action    = menu.addAction("View Diff")
        blame_action   = menu.addAction("Blame This File")
        menu.addSeparator()
        discard_action = menu.addAction("Discard Changes")

        action = menu.exec(self.tree.viewport().mapToGlobal(position))

        if action == diff_action:
            DiffViewerDialog(rel_path, self.repo_path, self).exec()
        elif action == blame_action:
            if self.parent_window:
                base = self.repo_path or QDir.currentPath()
                self.parent_window.open_file_in_tab(os.path.join(base, rel_path))
                editor = self.parent_window.current_editor()
                if editor and hasattr(editor, 'toggle_blame') and not editor._blame_visible:
                    editor.toggle_blame()
                    self.blame_btn.setChecked(True)
                    self.blame_btn.setText("Hide blame")
        elif action == discard_action:
            reply = QMessageBox.question(
                self, "Discard Changes",
                f"Permanently discard changes to:\n{rel_path}?\n\nThis cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.run_git_command(['git', 'checkout', '--', rel_path])
                self.run_git_command(['git', 'clean', '-fd', rel_path])
                self.refresh_status()

    def commit_changes(self):
        message = self.commit_input.text().strip()
        if not message:
            QMessageBox.warning(self, "Commit", "Please enter a commit message.")
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
            QMessageBox.information(self, "Nothing Selected",
                "Check the files you want to commit.")
            return

        ok, err = self.run_git_command(['git', 'add'] + files_to_add)
        if not ok:
            QMessageBox.critical(self, "Git Add Failed", err)
            return

        ok, err = self.run_git_command(['git', 'commit', '-m', message])
        if not ok:
            QMessageBox.critical(self, "Git Commit Failed", err)
            return

        self.commit_input.clear()
        self.refresh_status()
        self.commit_btn.setText("✓ Committed!")
        threading.Timer(2.0, lambda: self.commit_btn.setText(self._ICON_COMMIT)).start()

        if hasattr(self.parent_window, 'update_git_branch'):
            self.parent_window.update_git_branch()

    def on_item_double_clicked(self, item, column):
        rel_path = item.data(0, Qt.ItemDataRole.UserRole)
        if rel_path:
            base = self.repo_path or QDir.currentPath()
            self.file_double_clicked.emit(os.path.join(base, rel_path))

    def push_changes(self):
        """Kept for backwards compatibility — now delegates to _sync."""
        self._sync()

    def closeEvent(self, event):
        try:
            theme_signals.theme_changed.disconnect(self._on_theme_changed)
        except RuntimeError:
            pass
        super().closeEvent(event)