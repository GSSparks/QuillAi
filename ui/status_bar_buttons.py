"""
ui/status_bar_buttons.py

Interactive status bar buttons for QuillAI.
Each button shows the current state and opens a popup menu or toggles on click.
"""

from PyQt6.QtWidgets import QPushButton, QMenu
from PyQt6.QtGui import QAction
from PyQt6.QtCore import Qt


def _make_status_btn(parent, width=90):
    """Create a flat status bar button matching the ai_mode_btn style."""
    btn = QPushButton("", parent)
    btn.setFlat(True)
    btn.setFixedWidth(width)
    btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return btn


def _popup_menu(btn, items, current, callback, parent):
    """
    Show a small popup menu anchored to btn.
    items: list of str labels
    current: currently selected label (gets a checkmark)
    callback: callable(label)
    """
    from ui.theme import get_theme, build_menu_stylesheet
    menu = QMenu(parent)
    menu.setStyleSheet(build_menu_stylesheet(get_theme()))
    for item in items:
        action = QAction(("✓  " if item == current else "    ") + item, parent)
        action.triggered.connect(lambda checked=False, v=item: callback(v))
        menu.addAction(action)
    menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))


# ── Insert / Overwrite ────────────────────────────────────────────────────────

def setup_ins_ovr_btn(main_window):
    """INS / OVR toggle button."""
    btn = _make_status_btn(main_window, width=44)
    btn.setText("INS")
    btn.setToolTip("Insert mode — click or press Insert to toggle")

    def _toggle():
        editor = main_window.current_editor()
        if not editor:
            return
        editor._insert_mode = not getattr(editor, '_insert_mode', False)
        _refresh(editor)

    def _refresh(editor):
        if editor is None:
            btn.setText("INS")
            return
        mode = getattr(editor, '_insert_mode', False)
        btn.setText("OVR" if mode else "INS")
        btn.setToolTip("Overwrite mode — click or press Insert to toggle"
                       if mode else
                       "Insert mode — click or press Insert to toggle")

    btn.clicked.connect(_toggle)
    btn._refresh = _refresh
    return btn


# ── Indentation ───────────────────────────────────────────────────────────────

def setup_indent_btn(main_window):
    """Spaces: N / Tabs button."""
    btn = _make_status_btn(main_window, width=80)
    btn.setText("Spaces: 4")
    btn.setToolTip("Indentation style — click to change")

    def _on_click():
        editor = main_window.current_editor()
        if not editor:
            return
        current = btn.text()

        def _apply(choice):
            btn.setText(choice)
            _convert_indentation(editor, choice)

        _popup_menu(btn, ["Spaces: 2", "Spaces: 4", "Tabs"], current, _apply, main_window)

    btn.clicked.connect(_on_click)
    return btn


def _convert_indentation(editor, choice):
    """Convert all indentation in the document to the chosen style."""
    from PyQt6.QtGui import QTextCursor
    text = editor.toPlainText()
    lines = text.split('\n')
    result = []

    if choice == "Tabs":
        for line in lines:
            stripped = line.lstrip(' ')
            spaces = len(line) - len(stripped)
            tabs = spaces // 4
            remainder = spaces % 4
            result.append('\t' * tabs + ' ' * remainder + stripped)
    elif choice == "Spaces: 2":
        for line in lines:
            stripped = line.lstrip('\t ')
            indent = line[:len(line) - len(stripped)]
            # Normalize tabs → 4 spaces, then halve
            spaces = indent.replace('\t', '    ')
            count = len(spaces) // 2
            result.append('  ' * count + stripped)
    else:  # Spaces: 4
        for line in lines:
            stripped = line.lstrip('\t ')
            indent = line[:len(line) - len(stripped)]
            spaces = indent.replace('\t', '    ')
            count = len(spaces) // 4
            result.append('    ' * count + stripped)

    new_text = '\n'.join(result)
    if new_text != text:
        cursor = editor.textCursor()
        pos = cursor.position()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.insertText(new_text)
        cursor.setPosition(min(pos, len(new_text)))
        editor.setTextCursor(cursor)

    # Update tab stop distance
    from PyQt6.QtGui import QFontMetrics
    if choice == "Spaces: 2":
        editor.setTabStopDistance(2 * QFontMetrics(editor.font()).horizontalAdvance(' '))
    else:
        editor.setTabStopDistance(4 * QFontMetrics(editor.font()).horizontalAdvance(' '))


# ── Encoding ──────────────────────────────────────────────────────────────────

def setup_encoding_btn(main_window):
    """Encoding button — UTF-8, UTF-8 BOM, Latin-1."""
    btn = _make_status_btn(main_window, width=80)
    btn.setText("UTF-8")
    btn.setToolTip("File encoding — click to change and re-save")

    _ENCODINGS = ["UTF-8", "UTF-8 BOM", "Latin-1"]

    def _on_click():
        editor = main_window.current_editor()
        if not editor or not getattr(editor, 'file_path', None):
            return
        current = btn.text()

        def _apply(choice):
            btn.setText(choice)
            _convert_encoding(editor, choice)

        _popup_menu(btn, _ENCODINGS, current, _apply, main_window)

    btn.clicked.connect(_on_click)
    return btn


def _convert_encoding(editor, choice):
    """Re-save the file with the chosen encoding."""
    import os
    file_path = getattr(editor, 'file_path', None)
    if not file_path:
        return
    text = editor.toPlainText()
    enc_map = {
        "UTF-8":     ("utf-8",       False),
        "UTF-8 BOM": ("utf-8-sig",   True),
        "Latin-1":   ("latin-1",     False),
    }
    codec, _ = enc_map.get(choice, ("utf-8", False))
    try:
        with open(file_path, 'w', encoding=codec) as f:
            f.write(text)
    except (UnicodeEncodeError, OSError) as e:
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.warning(None, "Encoding Error",
                            f"Could not save with {choice}:\n{e}")


# ── Line endings ──────────────────────────────────────────────────────────────

def setup_lineending_btn(main_window):
    """LF / CRLF / CR button."""
    btn = _make_status_btn(main_window, width=50)
    btn.setText("LF")
    btn.setToolTip("Line endings — click to change")

    def _on_click():
        editor = main_window.current_editor()
        if not editor:
            return
        current = btn.text()

        def _apply(choice):
            btn.setText(choice)
            _convert_line_endings(editor, choice)

        _popup_menu(btn, ["LF", "CRLF", "CR"], current, _apply, main_window)

    btn.clicked.connect(_on_click)
    return btn


def _convert_line_endings(editor, choice):
    """Convert all line endings in the document."""
    from PyQt6.QtGui import QTextCursor
    text = editor.toPlainText()

    # Normalize first
    text = text.replace('\r\n', '\n').replace('\r', '\n')

    if choice == "CRLF":
        text = text.replace('\n', '\r\n')
    elif choice == "CR":
        text = text.replace('\n', '\r')
    # LF — already normalized

    cursor = editor.textCursor()
    pos = cursor.position()
    cursor.select(QTextCursor.SelectionType.Document)
    cursor.insertText(text)
    cursor.setPosition(min(pos, len(text)))
    editor.setTextCursor(cursor)


# ── File type / Language ──────────────────────────────────────────────────────

_LANGUAGE_MAP = {
    'Python': '.py', 'JavaScript': '.js', 'TypeScript': '.ts',
    'HTML': '.html', 'CSS': '.css', 'SCSS': '.scss',
    'JSON': '.json', 'YAML': '.yml', 'TOML': '.toml', 'XML': '.xml',
    'Markdown': '.md', 'Bash': '.sh', 'Zsh': '.zsh', 'Fish': '.fish',
    'Nix': '.nix', 'Rust': '.rs', 'Go': '.go',
    'C': '.c', 'C++': '.cpp', 'Java': '.java',
    'Kotlin': '.kt', 'Swift': '.swift', 'Lua': '.lua',
    'Ruby': '.rb', 'PHP': '.php', 'Perl': '.pl',
    'SQL': '.sql', 'Terraform': '.tf', 'HCL': '.hcl',
    'reStructuredText': '.rst', 'LaTeX': '.tex', 'Text': '.txt',
    'Plain Text': '',
}


def setup_filetype_btn(main_window):
    """Language / file type button."""
    btn = _make_status_btn(main_window, width=100)
    btn.setText("Plain Text")
    btn.setToolTip("Language mode — click to change syntax highlighting")

    def _on_click():
        editor = main_window.current_editor()
        if not editor:
            return
        current = btn.text()

        def _apply(choice):
            btn.setText(choice)
            _change_language(editor, choice, main_window)

        _popup_menu(btn, sorted(_LANGUAGE_MAP.keys()), current, _apply, main_window)

    btn.clicked.connect(_on_click)
    return btn


def _change_language(editor, language, main_window):
    """Apply a language highlighter to the editor."""
    from editor.highlighter import registry
    ext = _LANGUAGE_MAP.get(language, '')
    editor.highlighter = registry.get_highlighter(editor.document(), ext)
    editor._detected_ext = ext
    # Update status bar so cursor label etc stay in sync
    if hasattr(main_window, 'update_status_bar'):
        main_window.update_status_bar()