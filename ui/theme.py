from PyQt6.QtCore import QObject, pyqtSignal

class ThemeSignals(QObject):
    theme_changed = pyqtSignal(dict)

theme_signals = ThemeSignals()

"""
QuillAI Theme System
====================
To add a new theme:
  1. Add a new dictionary to THEMES following the same key structure
  2. It will automatically appear in Settings

To switch themes at runtime, call:
  from ui.theme import apply_theme
  apply_theme(app, "gruvbox_dark")
"""

# ─────────────────────────────────────────────────────────────────────────────
# Palette Definitions
# ─────────────────────────────────────────────────────────────────────────────

THEMES = {

    "gruvbox_dark": {
        "name": "Gruvbox Dark",

        # Base backgrounds
        "bg0_hard":   "#1d2021",   # hardest bg — used for editor
        "bg0":        "#282828",   # main bg
        "bg1":        "#3c3836",   # lighter bg — panels, sidebars
        "bg2":        "#504945",   # selection, hover
        "bg3":        "#665c54",   # inactive tabs
        "bg4":        "#7c6f64",   # comments, muted borders

        # Foregrounds
        "fg0":        "#fbf1c7",   # brightest text
        "fg1":        "#ebdbb2",   # main text
        "fg2":        "#d5c4a1",   # secondary text
        "fg3":        "#bdae93",   # muted text
        "fg4":        "#a89984",   # very muted

        # Accent colors (bright variants)
        "red":        "#fb4934",
        "green":      "#b8bb26",
        "yellow":     "#fabd2f",
        "blue":       "#83a598",
        "purple":     "#d3869b",
        "aqua":       "#8ec07c",
        "orange":     "#fe8019",

        # Accent colors (faded variants)
        "red_dim":    "#cc241d",
        "green_dim":  "#98971a",
        "yellow_dim": "#d79921",
        "blue_dim":   "#458588",
        "purple_dim": "#b16286",
        "aqua_dim":   "#689d6a",
        "orange_dim": "#d65d0e",

        # Semantic mappings
        "accent":          "#fabd2f",   # primary accent (yellow)
        "accent_alt":      "#83a598",   # secondary accent (blue)
        "highlight":       "#458588",   # selection highlight
        "border":          "#504945",   # default border
        "border_focus":    "#fabd2f",   # focused border
        "status_bar":      "#3c3836",   # status bar background
        "tab_active_bar":  "#fabd2f",   # top border on active tab
        "scrollbar":       "#504945",   # scrollbar handle
        "scrollbar_hover": "#665c54",
        "chat_user_bubble": "#458588",
        "chat_ai_label":    "#d3869b",
        "ghost_text":       "#7c6f64",
        "error":            "#fb4934",
        "warning":          "#fabd2f",
        "success":          "#b8bb26",
        "added_line":       "#b8bb26",
        "modified_line":    "#fabd2f",
    },

    "vscode_dark": {
        "name": "VS Code Dark",

        "bg0_hard":   "#1e1e1e",
        "bg0":        "#252526",
        "bg1":        "#2d2d30",
        "bg2":        "#37373d",
        "bg3":        "#3e3e42",
        "bg4":        "#555555",

        "fg0":        "#ffffff",
        "fg1":        "#d4d4d4",
        "fg2":        "#cccccc",
        "fg3":        "#bbbbbb",
        "fg4":        "#888888",

        "red":        "#f44747",
        "green":      "#4ec9b0",
        "yellow":     "#dcdcaa",
        "blue":       "#569cd6",
        "purple":     "#c586c0",
        "aqua":       "#4ec9b0",
        "orange":     "#ce9178",

        "red_dim":    "#f44336",
        "green_dim":  "#6a9955",
        "yellow_dim": "#d7ba7d",
        "blue_dim":   "#264f78",
        "purple_dim": "#8a2be2",
        "aqua_dim":   "#4ec9b0",
        "orange_dim": "#ce9178",

        "accent":          "#0e639c",
        "accent_alt":      "#4ec9b0",
        "highlight":       "#264f78",
        "border":          "#3e3e42",
        "border_focus":    "#007acc",
        "status_bar":      "#007acc",
        "tab_active_bar":  "#0e639c",
        "scrollbar":       "#424242",
        "scrollbar_hover": "#4f4f4f",
        "chat_user_bubble": "#0e639c",
        "chat_ai_label":    "#8a2be2",
        "ghost_text":       "#787878",
        "error":            "#f44336",
        "warning":          "#f0a30a",
        "success":          "#4caf50",
        "added_line":       "#4caf50",
        "modified_line":    "#f0a30a",
    },

    "monokai": {
        "name": "Monokai",

        "bg0_hard":   "#1a1a1a",
        "bg0":        "#272822",
        "bg1":        "#2d2e27",
        "bg2":        "#3e3d32",
        "bg3":        "#49483e",
        "bg4":        "#75715e",

        "fg0":        "#f9f8f5",
        "fg1":        "#f8f8f2",
        "fg2":        "#cfcfc2",
        "fg3":        "#a59f85",
        "fg4":        "#75715e",

        "red":        "#f92672",
        "green":      "#a6e22e",
        "yellow":     "#e6db74",
        "blue":       "#66d9ef",
        "purple":     "#ae81ff",
        "aqua":       "#a1efe4",
        "orange":     "#fd971f",

        "red_dim":    "#cc2166",
        "green_dim":  "#86c120",
        "yellow_dim": "#c4bb62",
        "blue_dim":   "#4ab7cd",
        "purple_dim": "#8c5fdd",
        "aqua_dim":   "#7fcfc2",
        "orange_dim": "#db7f0d",

        "accent":          "#f92672",
        "accent_alt":      "#a6e22e",
        "highlight":       "#49483e",
        "border":          "#3e3d32",
        "border_focus":    "#f92672",
        "status_bar":      "#2d2e27",
        "tab_active_bar":  "#f92672",
        "scrollbar":       "#49483e",
        "scrollbar_hover": "#75715e",
        "chat_user_bubble": "#4ab7cd",
        "chat_ai_label":    "#ae81ff",
        "ghost_text":       "#75715e",
        "error":            "#f92672",
        "warning":          "#e6db74",
        "success":          "#a6e22e",
        "added_line":       "#a6e22e",
        "modified_line":    "#e6db74",
    },
    
    "solarized_dark": {
        "name": "Solarized Dark",
    
        "bg0_hard":   "#00212b",
        "bg0":        "#002b36",
        "bg1":        "#073642",
        "bg2":        "#586e75",
        "bg3":        "#657b83",
        "bg4":        "#839496",
    
        "fg0":        "#fdf6e3",
        "fg1":        "#eee8d5",
        "fg2":        "#93a1a1",
        "fg3":        "#839496",
        "fg4":        "#657b83",
    
        "red":        "#dc322f",
        "green":      "#859900",
        "yellow":     "#b58900",
        "blue":       "#268bd2",
        "purple":     "#6c71c4",
        "aqua":       "#2aa198",
        "orange":     "#cb4b16",
    
        "red_dim":    "#a32422",
        "green_dim":  "#647300",
        "yellow_dim": "#896800",
        "blue_dim":   "#1a6699",
        "purple_dim": "#4f5491",
        "aqua_dim":   "#1f7a72",
        "orange_dim": "#9a380f",
    
        "accent":          "#268bd2",
        "accent_alt":      "#2aa198",
        "highlight":       "#073642",
        "border":          "#073642",
        "border_focus":    "#268bd2",
        "status_bar":      "#073642",
        "tab_active_bar":  "#268bd2",
        "scrollbar":       "#586e75",
        "scrollbar_hover": "#657b83",
        "chat_user_bubble": "#268bd2",
        "chat_ai_label":    "#6c71c4",
        "ghost_text":       "#586e75",
        "error":            "#dc322f",
        "warning":          "#b58900",
        "success":          "#859900",
        "added_line":       "#859900",
        "modified_line":    "#b58900",
    },
}

# Default theme
DEFAULT_THEME = "gruvbox_dark"


# ─────────────────────────────────────────────────────────────────────────────
# Theme Access
# ─────────────────────────────────────────────────────────────────────────────

def get_theme(name: str = None) -> dict:
    """Returns the theme dict for the given name, falling back to default."""
    return THEMES.get(name or DEFAULT_THEME, THEMES[DEFAULT_THEME])


def theme_names() -> list:
    """Returns list of (key, display_name) tuples for all available themes."""
    return [(k, v["name"]) for k, v in THEMES.items()]


def get(key: str, theme_name: str = None) -> str:
    """Shortcut to get a single color from the current theme."""
    return get_theme(theme_name).get(key, "#ff00ff")  # magenta = missing key


# ─────────────────────────────────────────────────────────────────────────────
# Stylesheet Generator
# ─────────────────────────────────────────────────────────────────────────────

def build_app_stylesheet(t: dict) -> str:
    """
    Builds the global Qt stylesheet from a theme palette dict.
    Applied once to QApplication — covers all widgets.
    """
    return f"""
        QWidget {{
            background-color: {t['bg0']};
            color: {t['fg1']};
        }}

        /* ── Splitters ── */
        QSplitter::handle {{
            background-color: {t['border']};
            margin: 0px;
        }}
        QSplitter::handle:horizontal {{ width: 1px; }}
        QSplitter::handle:vertical   {{ height: 1px; }}
        QSplitter::handle:hover      {{ background-color: {t['accent']}; }}

        /* ── Scrollbars ── */
        QScrollBar:vertical {{
            border: none; background: transparent;
            width: 14px; margin: 0px;
        }}
        QScrollBar::handle:vertical {{
            background: {t['scrollbar']};
            min-height: 30px; border-radius: 7px;
            margin: 2px 3px 2px 3px;
        }}
        QScrollBar::handle:vertical:hover {{ background: {t['scrollbar_hover']}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}

        QScrollBar:horizontal {{
            border: none; background: transparent;
            height: 14px; margin: 0px;
        }}
        QScrollBar::handle:horizontal {{
            background: {t['scrollbar']};
            min-width: 30px; border-radius: 7px;
            margin: 3px 2px 3px 2px;
        }}
        QScrollBar::handle:horizontal:hover {{ background: {t['scrollbar_hover']}; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}

        /* ── Inputs ── */
        QLineEdit, QTextEdit {{
            background-color: {t['bg1']};
            border: 1px solid {t['border']};
            border-radius: 4px;
            padding: 5px 8px;
            color: {t['fg1']};
            selection-background-color: {t['highlight']};
        }}
        QLineEdit:focus, QTextEdit:focus {{
            border: 1px solid {t['border_focus']};
        }}

        /* ── Tree / List Views ── */
        QTreeView, QListView {{
            background-color: {t['bg0_hard']};
            border: none; outline: none;
        }}
        QTreeView::item, QListView::item {{
            padding: 4px; border-radius: 4px;
        }}
        QTreeView::item:selected, QListView::item:selected {{
            background-color: {t['bg2']};
            color: {t['fg0']};
        }}
        QTreeView::item:hover:!selected, QListView::item:hover:!selected {{
            background-color: {t['bg1']};
        }}

        /* ── Buttons ── */
        QPushButton {{
            background-color: {t['accent']};
            color: {t['bg0_hard']};
            border: none; border-radius: 4px;
            padding: 6px 14px; font-weight: bold;
        }}
        QPushButton:hover  {{ background-color: {t['yellow']}; }}
        QPushButton:pressed {{ background-color: {t['yellow_dim']}; }}
        QPushButton:disabled {{
            background-color: {t['bg2']};
            color: {t['fg4']};
        }}

        /* ── Menus ── */
        QMenu {{
            background-color: {t['bg1']};
            color: {t['fg1']};
            border: 1px solid {t['border']};
        }}
        QMenu::item {{ padding: 6px 20px; }}
        QMenu::item:selected {{
            background-color: {t['highlight']};
            color: {t['fg0']};
        }}
        QMenu::separator {{
            height: 1px;
            background-color: {t['border']};
        }}

        /* ── Menu Bar ── */
        QMenuBar {{
            background-color: {t['bg0']};
            color: {t['fg1']};
        }}
        QMenuBar::item:selected {{
            background-color: {t['bg2']};
        }}

        /* ── Tab Widget ── */
        QTabWidget::pane {{
            border: none;
            background-color: {t['bg0_hard']};
        }}
        QTabBar::tab {{
            background-color: {t['bg1']};
            color: {t['fg4']};
            padding: 8px 15px;
            border-right: 1px solid {t['bg0_hard']};
            font-family: 'Inter', 'SF Pro Text', 'Segoe UI', sans-serif;
            font-size: 10pt;
        }}
        QTabBar::tab:selected {{
            background-color: {t['bg0_hard']};
            color: {t['fg0']};
            border-top: 2px solid {t['tab_active_bar']};
        }}
        QTabBar::tab:hover:!selected {{
            background-color: {t['bg2']};
            color: {t['fg1']};
        }}

        /* ── Dock Widgets ── */
        QDockWidget {{
            color: {t['fg2']};
            font-family: 'Inter', 'SF Pro Text', 'Segoe UI', sans-serif;
            font-weight: bold;
            font-size: 10pt;
        }}
        QDockWidget::title {{
            background-color: {t['bg1']};
            text-align: left;
            padding-left: 10px;
            padding-top: 6px;
            padding-bottom: 6px;
        }}

        /* ── Tooltips ── */
        QToolTip {{
            background-color: {t['bg2']};
            color: {t['fg1']};
            border: 1px solid {t['border']};
            padding: 4px 8px;
        }}

        /* ── Combo Box ── */
        QComboBox {{
            background-color: {t['bg1']};
            color: {t['fg1']};
            border: 1px solid {t['border']};
            border-radius: 4px;
            padding: 6px 10px;
        }}
        QComboBox:focus {{ border: 1px solid {t['border_focus']}; }}
        QComboBox QAbstractItemView {{
            background-color: {t['bg1']};
            color: {t['fg1']};
            selection-background-color: {t['highlight']};
            border: 1px solid {t['border']};
        }}

        /* ── Progress Bar ── */
        QProgressBar {{
            background-color: {t['bg2']};
            border: none; border-radius: 6px;
            max-height: 8px;
        }}
        QProgressBar::chunk {{
            background-color: {t['accent']};
            border-radius: 6px;
        }}

        /* ── Check Box ── */
        QCheckBox {{ color: {t['fg1']}; spacing: 8px; }}
        QCheckBox::indicator {{
            width: 16px; height: 16px;
            border-radius: 3px;
            border: 1px solid {t['border']};
            background-color: {t['bg1']};
        }}
        QCheckBox::indicator:checked {{
            background-color: {t['accent']};
            border-color: {t['accent']};
        }}

        /* ── Group Box ── */
        QGroupBox {{
            color: {t['fg4']};
            font-size: 9pt; font-weight: bold;
            border: 1px solid {t['border']};
            border-radius: 4px;
            margin-top: 8px; padding-top: 8px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 6px; left: 10px;
        }}
    """


def build_status_bar_stylesheet(t: dict) -> str:
    return f"""
        QStatusBar {{
            background-color: {t['status_bar']};
            color: {t['fg0']};
            font-family: 'Inter', 'Segoe UI', sans-serif;
            font-size: 9pt;
        }}
        QStatusBar::item {{ border: none; background: transparent; }}
        QStatusBar QLabel {{
            color: {t['fg0']};
            background: transparent;
            padding: 0 8px; font-size: 9pt;
        }}
        QStatusBar QPushButton {{
            color: {t['fg0']};
            background: transparent; border: none;
            padding: 0 8px; font-size: 9pt; font-weight: bold;
        }}
        QStatusBar QPushButton:hover {{
            background-color: rgba(255,255,255,0.15);
        }}
    """


def build_editor_stylesheet(t: dict) -> str:
    return f"""
        QPlainTextEdit {{
            background-color: {t['bg0_hard']};
            color: {t['fg1']};
            border: none;
            selection-background-color: {t['highlight']};
            selection-color: {t['fg0']};
        }}
        QScrollBar:vertical {{
            border: none; background: {t['bg0_hard']};
            width: 14px; margin: 0px;
        }}
        QScrollBar::handle:vertical {{
            background: {t['scrollbar']};
            min-height: 30px; border-radius: 7px;
            margin: 2px 3px 2px 3px;
        }}
        QScrollBar::handle:vertical:hover {{ background: {t['scrollbar_hover']}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
        QScrollBar:horizontal {{
            border: none; background: {t['bg0_hard']};
            height: 14px; margin: 0px;
        }}
        QScrollBar::handle:horizontal {{
            background: {t['scrollbar']};
            min-width: 30px; border-radius: 7px;
            margin: 3px 2px 3px 2px;
        }}
        QScrollBar::handle:horizontal:hover {{ background: {t['scrollbar_hover']}; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}
    """


# ─────────────────────────────────────────────────────────────────────────────
# Runtime Theme Application
# ─────────────────────────────────────────────────────────────────────────────

def apply_theme(app, theme_name: str, settings_manager=None):
    t = get_theme(theme_name)
    app.setStyleSheet(build_app_stylesheet(t))

    try:
        from editor.highlighter import registry
        registry.on_theme_changed(t)
    except Exception:
        pass

    if settings_manager:
        settings_manager.set('theme', theme_name)

    # Notify all listeners that the theme changed
    theme_signals.theme_changed.emit(t)

    return t