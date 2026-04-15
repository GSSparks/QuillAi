"""
ui/menu.py

All application menus for QuillAI.

Menus:
  File  — new, open, recent projects, save
  Edit  — settings
  View  — panels (checkable), split editor, themes
  Run   — run script, stop
  Wiki  — update wiki, rebuild all, show status
  Help  — about
"""

import os
from PyQt6.QtWidgets import QFileDialog, QMessageBox, QMenu
from PyQt6.QtGui import QKeySequence, QAction
from PyQt6.QtCore import QProcess

from ui.theme import (get_theme, theme_signals, theme_names,
                      build_menu_stylesheet, build_file_dialog_stylesheet)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _dialog_style() -> str:
    return build_file_dialog_stylesheet(get_theme())


def _menu_style() -> str:
    return build_menu_stylesheet(get_theme())


# ── Recent projects ───────────────────────────────────────────────────────────

def _new_project(window):
    from ui.new_project_dialog import NewProjectDialog
    dialog = NewProjectDialog(window)
    if dialog.exec() and dialog.result_path:
        folder_path = dialog.result_path
        open_file   = dialog.result_open_file

        if hasattr(window, '_save_current_session'):
            window._save_current_session()

        window._close_all_tabs_for_switch()

        if hasattr(window, 'tree_view') and hasattr(window, 'file_model'):
            window.file_model.setRootPath(folder_path)
            window.tree_view.setRootIndex(window.file_model.index(folder_path))

        if hasattr(window, 'git_dock'):
            window.git_dock.repo_path = folder_path
            window.git_dock.refresh_status()

        if hasattr(window, 'memory_manager'):
            window.memory_manager.set_project(folder_path)
        if hasattr(window, 'memory_panel'):
            window.memory_panel.refresh()
        if hasattr(window, 'update_git_branch'):
            window.update_git_branch()
        if hasattr(window, 'update_status_bar'):
            window.update_status_bar()
        if hasattr(window, 'load_project_chat'):
            window.load_project_chat()
        if hasattr(window, 'terminal_dock'):
            window.terminal_dock.set_cwd(folder_path)
        if hasattr(window, '_init_wiki'): 
            window._init_wiki(folder_path) 

        if open_file and os.path.exists(open_file):
            window.open_file_in_tab(open_file)
        else:
            window.add_new_tab("Untitled", "")

        window.statusBar().showMessage(
            f"Project '{os.path.basename(folder_path)}' created.", 4000
        )


def _open_recent_project(folder_path, window):
    if not os.path.isdir(folder_path):
        QMessageBox.warning(window, "Project Not Found",
                            f"The folder no longer exists:\n{folder_path}")
        return

    if hasattr(window, '_save_current_session'):
        window._save_current_session()

    window._close_all_tabs_for_switch()

    if hasattr(window, 'tree_view') and hasattr(window, 'file_model'):
        window.file_model.setRootPath(folder_path)
        window.tree_view.setRootIndex(window.file_model.index(folder_path))

    if hasattr(window, 'git_dock'):
        window.git_dock.repo_path = folder_path
        window.git_dock.refresh_status()

    if hasattr(window, 'memory_manager'):
        window.memory_manager.set_project(folder_path)
    if hasattr(window, 'memory_panel'):
        window.memory_panel.refresh()
    if hasattr(window, 'load_project_chat'):
        window.load_project_chat()
    if hasattr(window, 'update_git_branch'):
        window.update_git_branch()
    if hasattr(window, 'update_status_bar'):
        window.update_status_bar()
    if hasattr(window, 'terminal_dock'):
        window.terminal_dock.set_cwd(folder_path)
    if hasattr(window, '_restore_session'):
        window._restore_session(project_path=folder_path)
    if hasattr(window, '_init_wiki'):     
        window._init_wiki(folder_path)     


def _populate_recent_projects(menu, window):
    from ui.session_manager import list_project_sessions
    menu.clear()
    menu.setStyleSheet(_menu_style())

    sessions = list_project_sessions()
    if not sessions:
        empty = QAction("No recent projects", window)
        empty.setEnabled(False)
        menu.addAction(empty)
        return

    sessions.sort(key=lambda s: os.path.getmtime(s["file"]), reverse=True)

    for session in sessions[:10]:
        project_path = session["project_path"]
        tab_count    = session["tab_count"]
        name         = os.path.basename(project_path.rstrip('/'))
        label        = f"{name}  ({tab_count} tab{'s' if tab_count != 1 else ''})"

        action = QAction(label, window)
        action.setToolTip(project_path)
        action.setStatusTip(project_path)

        def make_handler(path):
            def handler():
                _open_recent_project(path, window)
            return handler

        action.triggered.connect(make_handler(project_path))
        menu.addAction(action)

    menu.addSeparator()
    clear_action = QAction("Clear Recent Projects", window)
    clear_action.triggered.connect(lambda: _clear_recent_projects(menu, window))
    menu.addAction(clear_action)


def _clear_recent_projects(menu, window):
    from ui.session_manager import list_project_sessions
    reply = QMessageBox.question(
        window, "Clear Recent Projects",
        "Remove all recent project history?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    if reply == QMessageBox.StandardButton.Yes:
        for s in list_project_sessions():
            try:
                os.remove(s["file"])
            except Exception:
                pass
        menu.clear()
        menu.setStyleSheet(_menu_style())
        empty = QAction("No recent projects", window)
        empty.setEnabled(False)
        menu.addAction(empty)


# ── Panel toggle helper ───────────────────────────────────────────────────────

def _make_panel_action(label: str, dock_attr: str, window,
                       shortcut: str = None) -> QAction:
    """
    Create a checkable QAction that mirrors the visibility of a dock widget.
    dock_attr is the attribute name on window (e.g. 'sidebar_dock').
    """
    action = QAction(label, window)
    action.setCheckable(True)

    dock = getattr(window, dock_attr, None)
    if dock:
        action.setChecked(dock.isVisible())

    if shortcut:
        action.setShortcut(QKeySequence(shortcut))

    def _toggle(checked):
        dock = getattr(window, dock_attr, None)
        if dock is None:
            return
        if checked:
            dock.show()
            dock.raise_()
        else:
            dock.hide()

    def _sync():
        dock = getattr(window, dock_attr, None)
        if dock:
            action.setChecked(dock.isVisible())

    action.triggered.connect(_toggle)

    # Keep checkbox in sync when dock is closed via its X button
    dock = getattr(window, dock_attr, None)
    if dock:
        dock.visibilityChanged.connect(lambda visible: action.setChecked(visible))

    return action


# ══════════════════════════════════════════════════════════════════════════════
# Main entry point
# ══════════════════════════════════════════════════════════════════════════════

def setup_menus(window):
    """
    Build all menus and attach them to window.menuBar().
    Call once from CodeEditor.__init__() replacing the individual setup_*_menu calls.
    """
    _setup_file_menu(window)
    _setup_edit_menu(window)
    _setup_view_menu(window)
    _setup_run_menu(window)
    _setup_wiki_menu(window)
    _setup_help_menu(window)


# Keep backwards-compatible entry point used by existing main.py
def setup_file_menu(window):
    _setup_file_menu(window)


# ── File ──────────────────────────────────────────────────────────────────────

def _setup_file_menu(window):
    file_menu = window.menuBar().addMenu("File")

    # ── New ──────────────────────────────────────────────────────────────
    new_file_action = QAction("New File", window)
    new_file_action.setShortcut(QKeySequence("Ctrl+N"))
    new_file_action.triggered.connect(lambda: window.add_new_tab("Untitled", ""))
    file_menu.addAction(new_file_action)

    new_project_action = QAction("New Project…", window)
    new_project_action.setShortcut(QKeySequence("Ctrl+Shift+N"))
    new_project_action.triggered.connect(lambda: _new_project(window))
    file_menu.addAction(new_project_action)

    file_menu.addSeparator()

    # ── Open ─────────────────────────────────────────────────────────────
    open_action = QAction("Open File…", window)
    open_action.setShortcut(QKeySequence("Ctrl+O"))
    open_action.triggered.connect(lambda: _open_file(window))
    file_menu.addAction(open_action)

    open_folder_action = QAction("Open Folder (Project)…", window)
    open_folder_action.triggered.connect(lambda: _open_folder(window))
    file_menu.addAction(open_folder_action)

    # Recent Projects submenu
    recent_menu = QMenu("Recent Projects", window)
    recent_menu.setStyleSheet(_menu_style())
    recent_menu.aboutToShow.connect(
        lambda: _populate_recent_projects(recent_menu, window)
    )
    file_menu.addMenu(recent_menu)

    file_menu.addSeparator()

    # ── Save ─────────────────────────────────────────────────────────────
    save_action = QAction("Save", window)
    save_action.setShortcut(QKeySequence("Ctrl+S"))
    save_action.triggered.connect(window.save_file)
    file_menu.addAction(save_action)

    save_as_action = QAction("Save As…", window)
    save_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
    save_as_action.triggered.connect(lambda: _save_as(window))
    file_menu.addAction(save_as_action)

    # Keep theme in sync on menu open
    theme_signals.theme_changed.connect(
        lambda t: recent_menu.setStyleSheet(_menu_style())
    )


def _open_file(window):
    from PyQt6.QtCore import QDir
    start_dir = (window.git_dock.repo_path
                 if hasattr(window, 'git_dock') and window.git_dock.repo_path
                 else QDir.currentPath())
    dialog = QFileDialog(window, "Open File", start_dir)
    dialog.setStyleSheet(_dialog_style())
    dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
    if dialog.exec():
        selected = dialog.selectedFiles()
        if selected:
            window.open_file_in_tab(selected[0])


def _open_folder(window):
    dialog = QFileDialog(window, "Open Project Folder")
    dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
    dialog.setFileMode(QFileDialog.FileMode.Directory)
    dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
    dialog.setStyleSheet(_dialog_style())
    if dialog.exec():
        selected = dialog.selectedFiles()
        if selected and os.path.isdir(selected[0]):
            _open_recent_project(selected[0], window)


def _save_as(window):
    from PyQt6.QtCore import QDir
    editor = window.current_editor()
    if not editor:
        return
    start_dir = (window.git_dock.repo_path
                 if hasattr(window, 'git_dock') and window.git_dock.repo_path
                 else QDir.currentPath())
    path, _ = QFileDialog.getSaveFileName(
        window, "Save File As", start_dir, "All Files (*)"
    )
    if path:
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(editor.toPlainText())
            editor.file_path = path
            index = window.tabs.indexOf(editor)
            window.tabs.setTabText(index, os.path.basename(path))
            if hasattr(editor, 'set_original_state'):
                editor.set_original_state(editor.toPlainText())
            if hasattr(window, 'git_dock'):
                window.git_dock.refresh_status()
            window.statusBar().showMessage(f"Saved as: {path}", 3000)
        except Exception as e:
            QMessageBox.critical(window, "Save Error", f"Could not save: {e}")


# ── Edit ──────────────────────────────────────────────────────────────────────

def _setup_edit_menu(window):
    edit_menu = window.menuBar().addMenu("Edit")

    settings_action = QAction("⚙  Settings…", window)
    settings_action.setShortcut(QKeySequence("Ctrl+,"))
    settings_action.triggered.connect(window.show_settings_dialog)
    edit_menu.addAction(settings_action)


# ── View ──────────────────────────────────────────────────────────────────────

def _setup_view_menu(window):
    view_menu = window.menuBar().addMenu("View")
    
    # Command palette
    palette_action = QAction("Command Palette", window)
    palette_action.setShortcut(QKeySequence("Ctrl+P"))
    palette_action.triggered.connect(
        lambda: window.command_palette.show_palette()
        if hasattr(window, 'command_palette') else None
    )
    view_menu.addAction(palette_action)

    view_menu.addSeparator()

    # ── Panels ───────────────────────────────────────────────────────────
    panels_menu = view_menu.addMenu("Panels")

    # Shell-owned panels — always present
    static_panels = [
        ("Explorer",       "sidebar_dock",    None),
        ("Source Control", "git_dock",        None),
        ("Outline",        "symbol_dock",     None),
        ("Find in Files",  "search_dock",     None),
        ("Output",         "output_dock",     None),
    ]
    for label, attr, shortcut in static_panels:
        action = _make_panel_action(label, attr, window, shortcut)
        # Sync initial checked state properly
        dock = getattr(window, attr, None)
        if dock:
            action.setChecked(dock.isVisible())
        panels_menu.addAction(action)

    # Plugin-owned panels — added dynamically when menu opens
    def _add_plugin_panels():
        for action in getattr(panels_menu, '_plugin_actions', []):
            panels_menu.removeAction(action)
        panels_menu._plugin_actions = []

        pm = getattr(window, 'plugin_manager', None)
        if not pm:
            return

        # Only show plugins that are currently active
        active_names = {p.name for p in pm._plugins}

        plugin_actions = []
        for label, (dock_attr, shortcut) in pm.docks.items():
            # Derive plugin name from dock_attr — strip trailing _dock
            plugin_name = dock_attr.replace('_dock', '')
            # Skip if plugin is disabled (not in active list)
            # Allow through if we can't match a name (static/core docks)
            matched_plugin = next(
                (p for p in pm._plugins
                 if getattr(window, dock_attr, None) is not None
                 and any(
                     getattr(p, attr, None) is getattr(window, dock_attr, None)
                     for attr in ('dock', '_panel', '_dock')
                 )),
                None
            )
            if matched_plugin is None and dock_attr not in (
                attr for _, attr, _ in static_panels
            ):
                # Can't confirm it's active — skip
                continue
            action = _make_panel_action(label, dock_attr, window, shortcut)
            plugin_actions.append(action)

        if plugin_actions:
            sep = panels_menu.addSeparator()
            panels_menu._plugin_actions.append(sep)
            for action in plugin_actions:
                panels_menu.addAction(action)
                panels_menu._plugin_actions.append(action)

    panels_menu.aboutToShow.connect(_add_plugin_panels)
    
    view_menu.addSeparator()

    # ── Split editor ──────────────────────────────────────────────────────
    split_h_action = QAction("Split Editor ↔", window)
    split_h_action.setShortcut(QKeySequence("Ctrl+\\"))
    split_h_action.triggered.connect(
        lambda: window._split_active(
            __import__('PyQt6.QtCore', fromlist=['Qt']).Qt.Orientation.Horizontal
        )
    )
    view_menu.addAction(split_h_action)

    split_v_action = QAction("Split Editor ↕", window)
    split_v_action.setShortcut(QKeySequence("Ctrl+Shift+\\"))
    split_v_action.triggered.connect(
        lambda: window._split_active(
            __import__('PyQt6.QtCore', fromlist=['Qt']).Qt.Orientation.Vertical
        )
    )
    view_menu.addAction(split_v_action)

    view_menu.addSeparator()

    # ── Themes ────────────────────────────────────────────────────────────
    theme_menu = view_menu.addMenu("Theme")

    def _apply_theme_action(key):
        from ui.theme import apply_theme
        from PyQt6.QtWidgets import QApplication
        apply_theme(QApplication.instance(), key,
                    settings_manager=getattr(window, 'settings_manager', None))

    def _build_theme_menu():
        theme_menu.clear()
        current = getattr(
            __import__('ui.theme', fromlist=['_current_theme_name']),
            '_current_theme_name', 'gruvbox_dark'
        )
        for key, display_name in theme_names():
            action = QAction(display_name, window)
            action.setCheckable(True)
            action.setChecked(key == current)

            def make_handler(k):
                def handler():
                    _apply_theme_action(k)
                    _build_theme_menu()   # refresh checks
                return handler

            action.triggered.connect(make_handler(key))
            theme_menu.addAction(action)

    theme_menu.aboutToShow.connect(_build_theme_menu)


# ── Run ───────────────────────────────────────────────────────────────────────

def _setup_run_menu(window):
    run_menu = window.menuBar().addMenu("Run")

    run_action = QAction("▶  Run Script", window)
    run_action.setShortcut(QKeySequence("F5"))
    run_action.triggered.connect(
        lambda: window.run_script() if hasattr(window, 'run_script') else None
    )
    run_menu.addAction(run_action)

    stop_action = QAction("■  Stop", window)
    stop_action.setShortcut(QKeySequence("Shift+F5"))
    stop_action.triggered.connect(lambda: _stop_script(window))
    run_menu.addAction(stop_action)


def _stop_script(window):
    if hasattr(window, 'process'):
        if window.process.state() == QProcess.ProcessState.Running:
            window.process.kill()
            window.statusBar().showMessage("Process stopped.", 3000)
            if hasattr(window, 'output_editor'):
                window.output_editor.appendPlainText("\n>>> Stopped by user.")


# ── Wiki ──────────────────────────────────────────────────────────────────────

def _setup_wiki_menu(window):
    wiki_menu = window.menuBar().addMenu("Wiki")

    # ── Update stale pages ────────────────────────────────────────────────
    update_action = QAction("Update Stale Pages", window)
    update_action.setShortcut(QKeySequence("Ctrl+Shift+U"))
    update_action.triggered.connect(lambda: _wiki_update(window))
    wiki_menu.addAction(update_action)

    # ── Rebuild everything ────────────────────────────────────────────────
    rebuild_action = QAction("Rebuild All Pages…", window)
    rebuild_action.triggered.connect(lambda: _wiki_rebuild_all(window))
    wiki_menu.addAction(rebuild_action)

    wiki_menu.addSeparator()

    export_faq_action = QAction("Export FAQ → Markdown", window)
    export_faq_action.triggered.connect(lambda: _faq_export(window))
    wiki_menu.addAction(export_faq_action)

    wiki_menu.addSeparator()

    # ── Status — populated dynamically on open ────────────────────────────
    def _populate_status():
        # Remove old dynamic actions
        for action in getattr(wiki_menu, '_status_actions', []):
            wiki_menu.removeAction(action)
        wiki_menu._status_actions = []

        wm = getattr(window, 'wiki_manager', None)
        if not wm or not wm.enabled:
            a = QAction("Wiki not available for this project", window)
            a.setEnabled(False)
            wiki_menu.addAction(a)
            wiki_menu._status_actions = [a]
            return

        stale = wm.stale_files()
        total = len(list(wm._wiki_dir.rglob("*.md")))
        project = wm.repo_root.name

        summary = QAction(
            f"📁 {project}  —  {total} pages, {len(stale)} stale", window
        )
        summary.setEnabled(False)
        wiki_menu.addAction(summary)
        wiki_menu._status_actions = [summary]

        if stale:
            wiki_menu.addSeparator()
            header = QAction("Stale files:", window)
            header.setEnabled(False)
            wiki_menu.addAction(header)
            wiki_menu._status_actions += [header]

            for rel in stale[:10]:
                a = QAction(f"  · {rel}", window)
                a.setEnabled(False)
                wiki_menu.addAction(a)
                wiki_menu._status_actions.append(a)

            if len(stale) > 10:
                more = QAction(f"  … and {len(stale) - 10} more", window)
                more.setEnabled(False)
                wiki_menu.addAction(more)
                wiki_menu._status_actions.append(more)

    wiki_menu.aboutToShow.connect(_populate_status)


def _wiki_update(window):
    wi = getattr(window, 'wiki_indexer', None)
    wm = getattr(window, 'wiki_manager', None)
    if not wm or not wm.enabled:
        window.statusBar().showMessage("Wiki not available for this project.", 3000)
        return
    if not wi:
        window.statusBar().showMessage("Wiki indexer not running.", 3000)
        return
    wi.restart()
    window.statusBar().showMessage("Wiki: scanning for stale pages…", 3000)


def _wiki_rebuild_all(window):
    wm = getattr(window, 'wiki_manager', None)
    wi = getattr(window, 'wiki_indexer', None)
    if not wm or not wm.enabled:
        window.statusBar().showMessage("Wiki not available for this project.", 3000)
        return

    reply = QMessageBox.question(
        window, "Rebuild Wiki",
        f"Regenerate all wiki pages for '{wm.repo_root.name}'?\n\n"
        f"This will make one API call per source file and may take a while.",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    if reply != QMessageBox.StandardButton.Yes:
        return

    if not wi:
        window.statusBar().showMessage("Wiki indexer not running.", 3000)
        return

    # Clear meta so every file is treated as stale
    wm._meta.clear()
    wm._save_meta()

    # Restart the indexer — it will pick up all stale files automatically
    wi.restart()

    from core.wiki_manager import _collect_source_files
    count = len(_collect_source_files(wm.repo_root))
    window.statusBar().showMessage(f"Wiki: rebuilding {count} pages…", 5000)


# ── Help ──────────────────────────────────────────────────────────────────────

def _faq_export(window):
    fm = getattr(window, 'faq_manager', None)
    if not fm:
        window.statusBar().showMessage("FAQ manager not available.", 3000)
        return
    import os
    path = fm.export_markdown_default()
    if path and os.path.exists(path):
        window.statusBar().showMessage(f"FAQ exported → {path}", 5000)
        # Offer to open in editor
        from PyQt6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            window, "FAQ Exported",
            f"FAQ exported to:\n{path}\n\nOpen in editor?",
        )
        if reply == QMessageBox.StandardButton.Yes:
            window.open_file(path)
    else:
        window.statusBar().showMessage("FAQ export failed — no entries?", 3000)


def _setup_help_menu(window):
    help_menu = window.menuBar().addMenu("Help")

    about_action = QAction("About QuillAI", window)
    about_action.triggered.connect(
        lambda: window._show_about() if hasattr(window, '_show_about') else None
    )
    help_menu.addAction(about_action)