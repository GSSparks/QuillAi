from PyQt6.QtCore import QObject, pyqtSignal

class ThemeSignals(QObject):
    theme_changed = pyqtSignal(dict)

theme_signals = ThemeSignals()

"""
QuillAI Theme System
====================
To add a new theme:
  1. Add a new dictionary to THEMES following the same key structure.
  2. It will automatically appear in Settings.

To switch themes at runtime, call:
  from ui.theme import apply_theme
  apply_theme(app, "gruvbox_dark")

Widget authors
--------------
- Call get_theme() once in __init__ to get the current palette.
- Connect to theme_signals.theme_changed to stay in sync if the dialog
  can remain open while the user switches themes.
- Never call get_theme() with a hardcoded name; always use the no-arg form
  so you always get the live current theme.
- Never build stylesheet strings inline inside widgets.  Use the builders
  provided here (build_app_stylesheet, build_dialog_stylesheet, etc.).
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
        "accent":           "#fabd2f",   # primary accent (yellow)
        "accent_alt":       "#83a598",   # secondary accent (blue)
        "highlight":        "#458588",   # selection highlight
        "border":           "#504945",   # default border
        "border_focus":     "#fabd2f",   # focused border
        "status_bar":       "#3c3836",   # status bar background
        "tab_active_bar":   "#fabd2f",   # top border on active tab
        "scrollbar":        "#504945",   # scrollbar handle
        "scrollbar_hover":  "#665c54",
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

        "accent":           "#0e639c",
        "accent_alt":       "#4ec9b0",
        "highlight":        "#264f78",
        "border":           "#3e3e42",
        "border_focus":     "#007acc",
        "status_bar":       "#007acc",
        "tab_active_bar":   "#0e639c",
        "scrollbar":        "#424242",
        "scrollbar_hover":  "#4f4f4f",
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

        "accent":           "#f92672",
        "accent_alt":       "#a6e22e",
        "highlight":        "#49483e",
        "border":           "#3e3d32",
        "border_focus":     "#f92672",
        "status_bar":       "#2d2e27",
        "tab_active_bar":   "#f92672",
        "scrollbar":        "#49483e",
        "scrollbar_hover":  "#75715e",
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

        "accent":           "#268bd2",
        "accent_alt":       "#2aa198",
        "highlight":        "#073642",
        "border":           "#073642",
        "border_focus":     "#268bd2",
        "status_bar":       "#073642",
        "tab_active_bar":   "#268bd2",
        "scrollbar":        "#586e75",
        "scrollbar_hover":  "#657b83",
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

# Tracks whichever theme is currently active so get_theme() with no args
# always returns the live palette rather than always falling back to the default.
_current_theme_name: str = DEFAULT_THEME


# ─────────────────────────────────────────────────────────────────────────────
# Theme Access
# ─────────────────────────────────────────────────────────────────────────────

def get_theme(name: str = None) -> dict:
    """Return the theme dict for *name*, or the currently active theme."""
    return THEMES.get(name or _current_theme_name, THEMES[DEFAULT_THEME])


def theme_names() -> list:
    """Return list of (key, display_name) tuples for all available themes."""
    return [(k, v["name"]) for k, v in THEMES.items()]


def get(key: str, theme_name: str = None) -> str:
    """Shortcut: return a single color from the current (or named) theme."""
    return get_theme(theme_name).get(key, "#ff00ff")  # magenta = missing key


# ─────────────────────────────────────────────────────────────────────────────
# Stylesheet Builders
# All stylesheet strings live here — never inside individual widget files.
# ─────────────────────────────────────────────────────────────────────────────

def build_app_stylesheet(t: dict) -> str:
    """
    Global Qt stylesheet applied once to QApplication.
    Covers all standard widgets that haven't been given a more specific sheet.
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


def build_dialog_stylesheet(t: dict) -> str:
    """
    Base stylesheet for modal dialogs (QDialog subclasses).
    Overrides the app-level button style so dialog buttons use a more
    subdued look that fits a secondary-surface context.
    """
    return f"""
        QDialog {{
            background-color: {t['bg1']};
            color: {t['fg1']};
        }}
        QPushButton {{
            background-color: {t['bg2']};
            color: {t['fg1']};
            border: none; border-radius: 4px;
            padding: 6px 16px;
            font-family: 'Inter', sans-serif;
            font-weight: bold;
        }}
        QPushButton:hover  {{ background-color: {t['bg3']}; }}
        QPushButton:pressed {{ background-color: {t['bg4']}; }}
        QPushButton:disabled {{
            background-color: {t['bg1']};
            color: {t['fg4']};
        }}
        QTextEdit {{
            background-color: {t['bg0_hard']};
            color: {t['fg1']};
            border: 1px solid {t['border']};
            border-radius: 4px;
            padding: 5px;
        }}
        QLineEdit {{
            background-color: {t['bg0_hard']};
            color: {t['fg1']};
            border: 1px solid {t['border']};
            border-radius: 4px;
            padding: 5px 8px;
            selection-background-color: {t['highlight']};
        }}
        QLineEdit:focus {{
            border: 1px solid {t['border_focus']};
        }}
        QLabel {{
            background: transparent;
            color: {t['fg1']};
        }}
    """


def build_minimap_stylesheet(t: dict) -> str:
    return f"""
        QPlainTextEdit {{
            background-color: {t['bg0_hard']};
            color: {t['fg4']};
            border-left: 1px solid {t['border']};
            border-right: none;
            border-top: none;
            border-bottom: none;
        }}
    """


def build_jump_bar_stylesheet(t: dict) -> str:
    return f"""
        QLineEdit {{
            background-color: {t['bg1']};
            color: {t['fg0']};
            border: none;
            border-top: 1px solid {t['border_focus']};
            font-family: 'JetBrains Mono', monospace;
            font-size: 11pt;
            padding: 4px 10px;
        }}
    """


def build_color_swatch_stylesheet(hex_color: str, text_color: str) -> str:
    """Stylesheet for the floating hex color swatch in the editor."""
    return f"""
        QLabel {{
            background-color: {hex_color};
            border: 1px solid rgba(0, 0, 0, 0.4);
            border-radius: 4px;
            color: {text_color};
            font-family: 'Hack', monospace;
            font-size: 8pt;
            padding: 0 4px;
        }}
    """


def build_inline_chat_stylesheet(t: dict) -> dict:
    """
    Returns a dict of per-widget stylesheet strings for InlineChatWidget.
    Keeping them separate (rather than one giant sheet) lets the widget
    call setStyleSheet on each child directly, which is both more precise
    and avoids selector-specificity fights with the app-level sheet.

    Keys match the widget attribute names in InlineChatWidget.
    """
    return {
        "panel": f"""
            QWidget#inlineChat {{
                background-color: {t['bg1']};
                border: 1px solid {t['accent']};
                border-radius: 6px;
            }}
        """,
        "header": (
            f"background-color: {t['bg0_hard']}; border-radius: 6px 6px 0 0;"
        ),
        "title_label": (
            f"color: {t['aqua']}; font-weight: bold; font-size: 9pt;"
            f" background: transparent;"
        ),
        "context_label": (
            f"color: {t['fg4']}; font-size: 8pt; background: transparent;"
        ),
        "close_btn": f"""
            QPushButton {{
                background: transparent; color: {t['fg4']};
                border: none; font-size: 9pt; padding: 0;
            }}
            QPushButton:hover {{ color: {t['red']}; }}
        """,
        "input_container": (
            f"background: {t['bg0_hard']}; border-top: 1px solid {t['border']};"
        ),
        "input": f"""
            QLineEdit {{
                background: transparent;
                border: none;
                color: {t['fg0']};
                font-family: 'Inter', 'Segoe UI', sans-serif;
                font-size: 10pt;
            }}
        """,
        "send_btn": f"""
            QPushButton {{
                background-color: {t['accent']};
                color: {t['bg0_hard']};
                border: none; border-radius: 4px; font-size: 10pt;
            }}
            QPushButton:hover {{ background-color: {t['yellow']}; }}
        """,
        "response_area": f"""
            QTextEdit {{
                background-color: {t['bg0_hard']};
                color: {t['fg1']};
                border: none;
                border-top: 1px solid {t['border']};
                font-family: 'Inter', 'Segoe UI', sans-serif;
                font-size: 10pt;
                padding: 8px;
            }}
        """,
        "footer": (
            f"background: {t['bg1']}; border-top: 1px solid {t['border']};"
            f" border-radius: 0 0 6px 6px;"
        ),
        "insert_btn": f"""
            QPushButton {{
                background-color: {t['accent']};
                color: {t['bg0_hard']};
                border: none; border-radius: 3px;
                padding: 3px 10px; font-size: 9pt; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {t['yellow']}; }}
        """,
        "chat_btn": f"""
            QPushButton {{
                background-color: {t['bg2']};
                color: {t['fg1']};
                border: none; border-radius: 3px;
                padding: 3px 10px; font-size: 9pt;
            }}
            QPushButton:hover {{ background-color: {t['bg3']}; }}
        """,
        "clear_btn": f"""
            QPushButton {{
                background-color: transparent;
                color: {t['fg4']};
                border: none; border-radius: 3px;
                padding: 3px 8px; font-size: 9pt;
            }}
            QPushButton:hover {{ color: {t['red']}; }}
        """,
    }


def build_new_project_dialog_stylesheet(t: dict) -> str:
    """Stylesheet for NewProjectDialog."""
    return f"""
        QDialog {{
            background-color: {t['bg0']};
            color: {t['fg1']};
        }}
        QLabel {{
            color: {t['fg1']};
            font-size: 10pt;
        }}
        QLineEdit {{
            background-color: {t['bg1']};
            color: {t['fg0']};
            border: 1px solid {t['border']};
            border-radius: 4px;
            padding: 6px 10px;
            font-size: 10pt;
        }}
        QLineEdit:focus {{
            border: 1px solid {t['border_focus']};
        }}
        QComboBox {{
            background-color: {t['bg1']};
            color: {t['fg0']};
            border: 1px solid {t['border']};
            border-radius: 4px;
            padding: 6px 10px;
            font-size: 10pt;
        }}
        QComboBox::drop-down {{ border: none; }}
        QComboBox QAbstractItemView {{
            background-color: {t['bg1']};
            color: {t['fg0']};
            selection-background-color: {t['highlight']};
            border: 1px solid {t['border']};
        }}
        QPushButton {{
            background-color: {t['accent']};
            color: {t['bg0_hard']};
            border: none;
            border-radius: 4px;
            padding: 8px 18px;
            font-size: 10pt;
            font-weight: bold;
        }}
        QPushButton:hover  {{ background-color: {t['yellow']}; }}
        QPushButton:pressed {{ background-color: {t['yellow_dim']}; }}
        QPushButton#cancel {{
            background-color: {t['bg2']};
            color: {t['fg1']};
        }}
        QPushButton#cancel:hover  {{ background-color: {t['bg3']}; }}
        QCheckBox {{
            color: {t['fg1']};
            font-size: 10pt;
            spacing: 8px;
        }}
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


def build_snippet_palette_stylesheet(t: dict) -> str:
    """Main stylesheet for SnippetPalette — covers the dialog and all standard child widgets."""
    return f"""
        QDialog {{
            background-color: {t['bg1']};
            border: 1px solid {t['border']};
            border-radius: 8px;
        }}
        QLineEdit {{
            background-color: {t['bg0_hard']};
            color: {t['fg0']};
            border: none;
            border-bottom: 1px solid {t['border']};
            border-radius: 0;
            padding: 10px 14px;
            font-family: 'Inter', 'Segoe UI', sans-serif;
            font-size: 13pt;
        }}
        QListWidget {{
            background-color: {t['bg1']};
            color: {t['fg1']};
            border: none;
            outline: none;
            font-family: 'Inter', 'Segoe UI', sans-serif;
            font-size: 10pt;
        }}
        QListWidget::item {{
            padding: 6px 12px;
            border-radius: 0;
        }}
        QListWidget::item:selected {{
            background-color: {t['bg2']};
            color: {t['fg0']};
        }}
        QListWidget::item:hover:!selected {{
            background-color: {t['bg1']};
        }}
        QPlainTextEdit {{
            background-color: {t['bg0_hard']};
            color: {t['fg1']};
            border: none;
            font-family: 'JetBrains Mono', 'Hack', monospace;
            font-size: 10pt;
            padding: 10px;
        }}
        QPushButton {{
            border-radius: 4px;
            padding: 5px 16px;
            font-family: 'Inter', 'Segoe UI', sans-serif;
            font-weight: bold;
            font-size: 10pt;
            border: none;
        }}
        QLabel {{
            color: {t['fg4']};
            font-family: 'Inter', 'Segoe UI', sans-serif;
            font-size: 9pt;
            padding: 4px 12px;
        }}
    """


def build_snippet_palette_parts(t: dict) -> dict:
    """
    Per-widget stylesheet strings for the parts of SnippetPalette that
    can't be cleanly reached by the main dialog-level sheet.
    """
    return {
        "splitter_handle": (
            f"QSplitter::handle {{ background-color: {t['border']}; }}"
        ),
        "preview_container": f"background-color: {t['bg0_hard']};",
        "preview_header": f"""
            QLabel {{
                color: {t['fg1']};
                background-color: {t['bg1']};
                border-bottom: 1px solid {t['border']};
                font-weight: bold;
                font-size: 10pt;
                padding: 6px 12px;
            }}
        """,
        "footer": (
            f"background-color: {t['bg1']}; border-top: 1px solid {t['border']};"
        ),
        "hint": f"color: {t['fg4']}; font-size: 9pt; padding: 0;",
        "cancel_btn": f"""
            QPushButton {{ background-color: {t['bg2']}; color: {t['fg1']}; }}
            QPushButton:hover {{ background-color: {t['bg3']}; }}
        """,
        "insert_btn": f"""
            QPushButton {{ background-color: {t['accent']}; color: {t['bg0_hard']}; }}
            QPushButton:hover {{ background-color: {t['yellow']}; }}
        """,
    }


def build_about_dialog_stylesheet(t: dict) -> str:
    """Base stylesheet for AboutDialog — covers standard widget types."""
    return f"""
        QDialog {{
            background-color: {t['bg0']};
            color: {t['fg1']};
        }}
        QLabel {{
            color: {t['fg1']};
            background: transparent;
        }}
        QPushButton {{
            background-color: {t['accent']};
            color: {t['bg0_hard']};
            border: none; border-radius: 4px;
            padding: 8px 20px;
            font-size: 10pt; font-weight: bold;
        }}
        QPushButton:hover  {{ background-color: {t['yellow']}; }}
        QPushButton#close {{
            background-color: {t['bg2']};
            color: {t['fg1']};
        }}
        QPushButton#close:hover {{ background-color: {t['bg3']}; }}
        QFrame#divider {{ background-color: {t['border']}; }}
    """


def build_about_dialog_parts(t: dict) -> dict:
    """
    Per-widget styles for AboutDialog children that live outside the
    normal cascade (background panels, scroll area, inline-styled labels).
    """
    return {
        "header":          f"background-color: {t['bg0_hard']};",
        "logo_fallback":   f"font-size: 64pt; color: {t['blue']};",
        "name_label":      f"color: {t['fg0']}; font-size: 20pt;",
        "version_label":   f"color: {t['fg4']}; font-size: 10pt;",
        "desc_label":      f"color: {t['fg2']}; font-size: 10pt;",
        "content":         f"background-color: {t['bg0']};",
        "deps_title":      f"color: {t['blue']}; font-size: 10pt; font-weight: bold;",
        "deps_scroll": f"""
            QScrollArea {{
                background-color: {t['bg1']};
                border: 1px solid {t['border']};
                border-radius: 6px;
            }}
            QScrollArea > QWidget > QWidget {{ background-color: {t['bg1']}; }}
            QScrollBar:vertical {{
                border: none; background: {t['bg1']};
                width: 8px; margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {t['scrollbar']};
                min-height: 20px; border-radius: 4px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {t['scrollbar_hover']}; }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{ height: 0px; }}
        """,
        "deps_widget":     f"background-color: {t['bg1']};",
        "dep_name":        f"color: {t['fg1']}; font-size: 11pt;",
        "dep_ok":          f"color: {t['green']}; font-size: 11pt;",
        "dep_missing":     f"color: {t['red']}; font-size: 11pt;",
        "github_btn": f"""
            QPushButton {{
                background-color: {t['bg1']};
                color: {t['aqua']};
                border: 1px solid {t['border']};
                border-radius: 4px;
                padding: 10px 16px;
                font-size: 10pt; font-weight: normal;
            }}
            QPushButton:hover {{
                background-color: {t['bg2']};
                border-color: {t['aqua']};
            }}
        """,
    }


def build_settings_dialog_stylesheet(t: dict) -> str:
    """Stylesheet for SettingsDialog."""
    return f"""
        QDialog {{
            background-color: {t['bg1']};
            color: {t['fg1']};
        }}
        QLabel {{
            color: {t['fg1']};
            font-size: 10pt;
        }}
        QLineEdit {{
            background-color: {t['bg0_hard']};
            color: {t['fg1']};
            border: 1px solid {t['border']};
            border-radius: 4px;
            padding: 5px 8px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 10pt;
        }}
        QLineEdit:focus {{
            border: 1px solid {t['border_focus']};
        }}
        QGroupBox {{
            color: {t['fg4']};
            font-weight: bold;
            font-size: 9pt;
            border: 1px solid {t['border']};
            border-radius: 6px;
            margin-top: 10px;
            padding-top: 8px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 4px;
        }}
        QComboBox {{
            background-color: {t['bg0_hard']};
            color: {t['fg1']};
            border: 1px solid {t['border']};
            border-radius: 4px;
            padding: 5px 8px;
            font-size: 10pt;
        }}
        QComboBox:focus {{ border: 1px solid {t['border_focus']}; }}
        QComboBox QAbstractItemView {{
            background-color: {t['bg1']};
            color: {t['fg1']};
            selection-background-color: {t['highlight']};
            border: 1px solid {t['border']};
        }}
        QPushButton {{
            background-color: {t['accent']};
            color: {t['bg0_hard']};
            border: none; border-radius: 4px;
            padding: 6px 16px; font-weight: bold;
        }}
        QPushButton:hover  {{ background-color: {t['yellow']}; }}
        QPushButton#cancelBtn {{
            background-color: {t['bg2']};
            color: {t['fg1']};
        }}
        QPushButton#cancelBtn:hover {{ background-color: {t['bg3']}; }}
    """


def build_hint_label_stylesheet(t: dict) -> str:
    """Shared style for small hint/helper labels inside dialogs."""
    return f"color: {t['fg4']}; font-size: 9pt;"


def build_markdown_browser_stylesheet(t: dict) -> str:
    """Qt stylesheet for the QTextBrowser widget in MarkdownPreviewDock."""
    return f"""
        QTextBrowser {{
            background-color: {t['bg0_hard']};
            color: {t['fg1']};
            border: none;
            font-family: 'Inter', 'Segoe UI', sans-serif;
            font-size: 11pt;
            padding: 16px;
            line-height: 1.7;
        }}
    """


def build_markdown_html_css(t: dict) -> str:
    """
    Full HTML/CSS stylesheet injected into the rendered markdown document.
    Returned as a plain string for embedding inside a <style> tag.
    """
    return f"""
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    background-color: {t['bg0_hard']};
    color: {t['fg1']};
    font-family: 'Inter', 'Segoe UI', 'Helvetica Neue', sans-serif;
    font-size: 15px;
    line-height: 1.8;
    padding: 24px 32px;
    max-width: 860px;
  }}

  h1, h2, h3, h4, h5, h6 {{
    color: {t['fg0']};
    font-weight: 600;
    line-height: 1.3;
    margin: 1.4em 0 0.5em 0;
  }}
  h1 {{ font-size: 2em; border-bottom: 1px solid {t['border']}; padding-bottom: 0.3em; }}
  h2 {{ font-size: 1.5em; border-bottom: 1px solid {t['border']}; padding-bottom: 0.2em; }}
  h3 {{ font-size: 1.25em; color: {t['fg2']}; }}
  h4 {{ font-size: 1.1em; color: {t['fg3']}; }}

  p {{ margin: 0.8em 0; }}

  a {{ color: {t['aqua']}; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}

  strong {{ color: {t['fg0']}; font-weight: 600; }}
  em {{ color: {t['orange']}; font-style: italic; }}

  code {{
    background-color: {t['bg2']};
    color: {t['orange']};
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.9em;
    padding: 2px 6px;
    border-radius: 4px;
  }}

  pre {{
    background-color: {t['bg1']};
    border: 1px solid {t['border']};
    border-radius: 8px;
    padding: 16px 20px;
    overflow-x: auto;
    margin: 1em 0;
  }}
  pre code {{
    background: none;
    color: {t['fg1']};
    padding: 0;
    font-size: 0.9em;
    line-height: 1.6;
  }}

  blockquote {{
    border-left: 3px solid {t['blue']};
    margin: 1em 0;
    padding: 8px 16px;
    background-color: {t['bg1']};
    border-radius: 0 6px 6px 0;
    color: {t['fg3']};
    font-style: italic;
  }}

  ul, ol {{ padding-left: 1.5em; margin: 0.8em 0; }}
  li {{ margin: 0.3em 0; line-height: 1.7; }}
  li > p {{ margin: 0.2em 0; }}

  table {{
    border-collapse: collapse;
    width: 100%;
    margin: 1em 0;
    font-size: 0.95em;
  }}
  th {{
    background-color: {t['bg2']};
    color: {t['fg0']};
    font-weight: 600;
    text-align: left;
    padding: 8px 12px;
    border: 1px solid {t['border']};
  }}
  td {{
    padding: 7px 12px;
    border: 1px solid {t['border']};
    color: {t['fg2']};
  }}
  tr:nth-child(even) td {{ background-color: {t['bg1']}; }}
  tr:hover td {{ background-color: {t['bg2']}; }}

  hr {{
    border: none;
    border-top: 1px solid {t['border']};
    margin: 1.5em 0;
  }}

  img {{ max-width: 100%; border-radius: 6px; }}

  .toc {{
    background-color: {t['bg1']};
    border: 1px solid {t['border']};
    border-radius: 6px;
    padding: 12px 16px;
    margin: 1em 0;
    font-size: 0.9em;
  }}
  .toc ul {{ margin: 0.3em 0; }}

  .admonition {{
    border-left: 4px solid {t['blue']};
    background-color: {t['bg1']};
    padding: 10px 16px;
    border-radius: 0 6px 6px 0;
    margin: 1em 0;
  }}
  .admonition-title {{ font-weight: bold; color: {t['blue']}; margin-bottom: 4px; }}
  .warning {{ border-left-color: {t['yellow']}; }}
  .warning .admonition-title {{ color: {t['yellow']}; }}
  .danger, .error {{ border-left-color: {t['red']}; }}
  .danger .admonition-title, .error .admonition-title {{ color: {t['red']}; }}
  .tip, .hint {{ border-left-color: {t['green']}; }}
  .tip .admonition-title, .hint .admonition-title {{ color: {t['green']}; }}

  dl dt {{ font-weight: bold; color: {t['fg2']}; margin-top: 0.8em; }}
  dl dd  {{ margin-left: 1.5em; color: {t['fg3']}; }}

  .footnote {{
    font-size: 0.85em;
    color: {t['fg4']};
    border-top: 1px solid {t['border']};
    margin-top: 2em;
    padding-top: 0.5em;
  }}
"""


def build_find_replace_stylesheet(t: dict) -> str:
    """Main stylesheet for FindReplaceWidget."""
    return f"""
        QWidget {{
            background-color: {t['bg1']};
            color: {t['fg1']};
            font-family: 'Inter', 'SF Pro Text', 'Segoe UI', sans-serif;
            font-size: 10pt;
        }}
        QLineEdit {{
            background-color: {t['bg0_hard']};
            color: {t['fg0']};
            border: 1px solid {t['border']};
            border-radius: 4px;
            padding: 4px 8px;
        }}
        QLineEdit:focus {{ border: 1px solid {t['border_focus']}; }}
        QLineEdit[state="match"] {{
            background-color: {t['bg0_hard']};
            border: 1px solid {t['green']};
            color: {t['fg0']};
        }}
        QLineEdit[state="no_match"] {{
            background-color: {t['bg0_hard']};
            border: 1px solid {t['red']};
            color: {t['fg0']};
        }}
        QPushButton {{
            background-color: {t['bg2']};
            color: {t['fg1']};
            border-radius: 4px;
            padding: 4px 12px;
            border: none;
        }}
        QPushButton:hover   {{ background-color: {t['bg3']}; }}
        QPushButton:pressed {{ background-color: {t['accent']}; color: {t['bg0_hard']}; }}
        QPushButton#closeBtn {{
            background-color: transparent;
            font-weight: bold;
            padding: 4px 8px;
        }}
        QPushButton#closeBtn:hover {{
            background-color: {t['red']};
            color: {t['bg0_hard']};
        }}
        QCheckBox {{
            color: {t['fg2']};
            spacing: 4px;
        }}
    """


def build_match_label_stylesheet(t: dict, state: str) -> str:
    """
    Stylesheet for the match-count label in FindReplaceWidget.
    state: 'match' | 'no_match' | '' (neutral)
    """
    color = t['green'] if state == 'match' else t['red'] if state == 'no_match' else t['fg4']
    return (
        f"QPushButton {{ color: {color}; background: transparent; "
        f"border: none; padding: 0 4px; min-width: 60px; }}"
    )


def build_sliding_panel_stylesheet(t: dict) -> str:
    """Outer panel shell — just the background and left border."""
    return f"""
        QWidget#slidingPanel {{
            background-color: {t['bg1']};
            border-left: 1px solid {t['border']};
        }}
    """


def build_sliding_panel_parts(t: dict) -> dict:
    """
    Per-widget styles for SlidingPanel children that need individual sheets.
    """
    return {
        "arrow_label": (
            f"color: {t['fg4']}; font-size: 11pt; background: transparent;"
        ),
        "content": f"background-color: {t['bg1']};",
        "tab_bar": (
            f"background-color: {t['bg0_hard']}; "
            f"border-bottom: 1px solid {t['border']};"
        ),
        "tab_btn": f"""
            QPushButton {{
                background: transparent;
                color: {t['fg4']};
                border: none;
                border-bottom: 2px solid transparent;
                padding: 6px 12px;
                font-family: Inter, sans-serif;
                font-size: 9pt;
                font-weight: bold;
            }}
            QPushButton:checked {{
                color: {t['fg0']};
                border-bottom: 2px solid {t['tab_active_bar']};
            }}
            QPushButton:hover:!checked {{ color: {t['fg2']}; }}
        """,
        "pin_btn": f"""
            QPushButton {{
                background: transparent;
                color: {t['fg4']};
                border: none;
                font-size: 12pt;
                padding: 0;
            }}
            QPushButton:checked {{ color: {t['accent']}; }}
            QPushButton:hover   {{ color: {t['fg2']}; }}
        """,
        "chat_history": f"""
            QTextBrowser {{
                background-color: {t['bg0_hard']};
                color: {t['fg1']};
                border: 1px solid {t['border']};
                border-radius: 6px;
                padding: 8px;
            }}
        """,
        "chat_input": f"""
            QTextEdit {{
                background-color: {t['bg1']};
                color: {t['fg0']};
                border: 1px solid {t['border']};
                border-radius: 6px;
                padding: 8px;
                font-family: Inter, sans-serif;
                font-size: 10pt;
            }}
            QTextEdit:focus {{ border: 1px solid {t['border_focus']}; }}
        """,
        "send_btn": f"""
            QPushButton {{
                background-color: {t['accent']};
                color: {t['bg0_hard']};
                border: none;
                border-radius: 6px;
                font-size: 14pt;
            }}
            QPushButton:hover {{ background-color: {t['yellow']}; }}
        """,
        "resize_grip_hover": f"background-color: {t['accent']};",
    }


def build_git_panel_stylesheet(t: dict) -> str:
    """QDockWidget title bar style for GitDockWidget."""
    return f"""
        QDockWidget {{
            color: {t['fg2']};
            font-family: 'Inter', 'SF Pro Text', 'Segoe UI', sans-serif;
            font-weight: bold;
            font-size: 10pt;
        }}
        QDockWidget::title {{
            background-color: {t['bg1']};
            padding: 6px 10px;
        }}
    """


def build_git_panel_parts(t: dict) -> dict:
    """Per-widget styles for GitDockWidget children."""
    action_btn = f"""
        QPushButton {{
            background-color: {t['bg2']};
            color: {t['fg1']};
            border-radius: 4px;
            padding: 4px 8px;
        }}
        QPushButton:hover {{ background-color: {t['bg3']}; }}
    """
    return {
        "action_btn": action_btn,   # refresh + push share this style
        "tree": f"""
            QTreeWidget {{
                background-color: {t['bg0_hard']};
                color: {t['fg1']};
                border: none;
                font-family: 'Inter', 'SF Pro Text', 'Segoe UI', sans-serif;
                font-size: 11pt;
            }}
            QTreeWidget::item {{ padding: 4px; }}
            QTreeWidget::item:selected {{
                background-color: {t['bg2']};
                color: {t['fg0']};
                border-radius: 4px;
            }}
            QTreeWidget::item:hover:!selected {{
                background-color: {t['bg1']};
                border-radius: 4px;
            }}
            QTreeWidget::branch {{ background-color: transparent; }}
            QTreeWidget::indicator:unchecked {{
                border: 1px solid {t['fg4']};
                background-color: {t['bg0_hard']};
                border-radius: 2px;
                width: 12px; height: 12px;
            }}
            QTreeWidget::indicator:checked {{
                background-color: {t['accent']};
                border: 1px solid {t['accent']};
                border-radius: 2px;
                width: 12px; height: 12px;
            }}
        """,
        "commit_input": f"""
            QLineEdit {{
                background-color: {t['bg1']};
                color: {t['fg1']};
                border: 1px solid {t['border']};
                border-radius: 4px;
                padding: 6px;
                font-family: 'Inter', 'SF Pro Text', 'Segoe UI', sans-serif;
            }}
            QLineEdit:focus {{ border: 1px solid {t['border_focus']}; }}
        """,
        "ai_msg_btn": f"""
            QPushButton {{
                background-color: {t['purple']};
                color: {t['bg0_hard']};
                border-radius: 4px;
                padding: 6px 10px;
                font-weight: bold;
                font-size: 9pt;
            }}
            QPushButton:hover    {{ background-color: {t['purple_dim']}; }}
            QPushButton:disabled {{
                background-color: {t['bg2']};
                color: {t['fg4']};
            }}
        """,
        "commit_btn": f"""
            QPushButton {{
                background-color: {t['accent']};
                color: {t['bg0_hard']};
                border-radius: 4px;
                padding: 6px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {t['yellow']}; }}
        """,
        "context_menu": f"""
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
        """,
        # Colors used to tint file-status rows in the tree
        "status_modified": t['yellow'],
        "status_added":    t['green'],
        "status_deleted":  t['red'],
        "status_default":  t['fg1'],
    }


def build_diff_apply_dialog_stylesheet(t: dict) -> str:
    """Base stylesheet for DiffApplyDialog."""
    return f"""
        QDialog {{
            background-color: {t['bg0']};
            color: {t['fg1']};
        }}
        QLabel {{
            color: {t['fg4']};
            font-family: 'Inter', sans-serif;
            font-size: 9pt;
            padding: 4px 8px;
            background-color: {t['bg1']};
        }}
        QPushButton {{
            border-radius: 4px;
            padding: 6px 20px;
            font-weight: bold;
            font-family: 'Inter', sans-serif;
            border: none;
        }}
    """


def build_diff_apply_parts(t: dict) -> dict:
    """Per-widget styles and raw colors for DiffApplyDialog."""
    return {
        "splitter_handle": (
            f"QSplitter::handle {{ background-color: {t['border']}; }}"
        ),
        "left_label": (
            f"background-color: {t['bg1']}; color: {t['red']}; font-weight: bold;"
        ),
        "right_label": (
            f"background-color: {t['bg1']}; color: {t['green']}; font-weight: bold;"
        ),
        "text_view": f"""
            QTextEdit {{
                background-color: {t['bg0_hard']};
                color: {t['fg1']};
                border: none;
                padding: 8px;
            }}
        """,
        "hint": f"color: {t['fg4']}; font-size: 9pt; background: transparent;",
        "discard_btn": f"""
            QPushButton {{
                background-color: {t['bg2']};
                color: {t['fg1']};
            }}
            QPushButton:hover {{
                background-color: {t['red']};
                color: {t['bg0_hard']};
            }}
        """,
        "accept_btn": f"""
            QPushButton {{
                background-color: {t['accent']};
                color: {t['bg0_hard']};
            }}
            QPushButton:hover {{ background-color: {t['yellow']}; }}
        """,
        # Raw hex values for QTextCharFormat coloring in populate()
        "diff_removed": t['red'],
        "diff_added":   t['green'],
        "diff_neutral": t['fg1'],
    }


def build_memory_panel_stylesheet(t: dict) -> str:
    """Outer widget background for MemoryPanel."""
    return f"background-color: {t['bg1']};"


def build_memory_panel_parts(t: dict) -> dict:
    """Per-widget styles and raw colors for MemoryPanel."""
    list_style = f"""
        QListWidget {{
            background-color: {t['bg0_hard']};
            color: {t['fg1']};
            border: 1px solid {t['border']};
            border-radius: 4px;
            font-size: 9pt;
        }}
        QListWidget::item {{ padding: 4px 8px; }}
        QListWidget::item:selected {{
            background-color: {t['bg2']};
            color: {t['fg0']};
        }}
        QListWidget::item:hover:!selected {{
            background-color: {t['bg1']};
        }}
    """
    input_style = f"""
        QLineEdit {{
            background-color: {t['bg0_hard']};
            color: {t['fg0']};
            border: 1px solid {t['border']};
            border-radius: 4px;
            padding: 4px 8px;
            font-size: 9pt;
        }}
        QLineEdit:focus {{ border: 1px solid {t['border_focus']}; }}
    """
    return {
        "label":          f"color: {t['fg4']}; font-size: 9pt; font-weight: bold;",
        "facts_tabs": f"""
            QTabWidget::pane {{
                border: 1px solid {t['border']};
                background: {t['bg0_hard']};
            }}
            QTabBar::tab {{
                background: {t['bg1']};
                color: {t['fg4']};
                padding: 4px 10px;
                font-size: 9pt;
            }}
            QTabBar::tab:selected {{
                background: {t['bg0_hard']};
                color: {t['fg0']};
                border-top: 1px solid {t['tab_active_bar']};
            }}
        """,
        "list":           list_style,
        "conv_list": f"""
            QListWidget {{
                background-color: {t['bg0_hard']};
                color: {t['fg1']};
                border: 1px solid {t['border']};
                border-radius: 4px;
                font-size: 9pt;
            }}
            QListWidget::item {{
                padding: 6px 8px;
                border-bottom: 1px solid {t['bg1']};
            }}
            QListWidget::item:selected {{
                background-color: {t['bg2']};
                color: {t['fg0']};
            }}
            QListWidget::item:hover:!selected {{
                background-color: {t['bg1']};
            }}
        """,
        "input":          input_style,
        "scope_check":    f"color: {t['fg4']}; font-size: 9pt;",
        "add_btn": f"""
            QPushButton {{
                background-color: {t['accent']};
                color: {t['bg0_hard']};
                border: none; border-radius: 4px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {t['yellow']}; }}
        """,
        "del_btn": f"""
            QPushButton {{
                background-color: {t['bg2']};
                color: {t['fg1']};
                border: none; border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {t['red']};
                color: {t['bg0_hard']};
            }}
        """,
        "clear_btn": f"""
            QPushButton {{
                background-color: {t['bg2']};
                color: {t['fg1']};
                border: none; border-radius: 4px;
                padding: 4px 10px; font-size: 9pt;
            }}
            QPushButton:hover {{ background-color: {t['bg3']}; }}
        """,
        "clear_all_btn": f"""
            QPushButton {{
                background-color: {t['bg2']};
                color: {t['fg1']};
                border: none; border-radius: 4px;
                padding: 4px 10px; font-size: 9pt;
            }}
            QPushButton:hover {{
                background-color: {t['red']};
                color: {t['bg0_hard']};
            }}
        """,
        # Raw color for QListWidgetItem.setForeground in _filter_conversations
        "conv_item_fg": t['fg3'],
    }


def build_dock_stylesheet(t: dict) -> str:
    """Shared QDockWidget title bar style used by all docks in CodeEditor."""
    return f"""
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
    """


def build_tab_widget_stylesheet(t: dict) -> str:
    """Stylesheet for the main QTabWidget in CodeEditor."""
    return f"""
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
    """


def build_output_panel_stylesheet(t: dict) -> str:
    """Stylesheet for the output QPlainTextEdit."""
    return f"""
        QPlainTextEdit {{
            background-color: {t['bg0_hard']};
            color: {t['fg1']};
            font-family: 'JetBrains Mono', monospace;
            font-size: 10pt;
            border: none;
        }}
    """


def build_explain_error_btn_stylesheet(t: dict) -> str:
    """Stylesheet for the 'Explain Error' button in the output panel."""
    return f"""
        QPushButton {{
            background-color: {t['purple']};
            color: {t['bg0_hard']};
            border: none;
            padding: 6px 12px;
            border-radius: 4px;
            font-family: 'Inter', 'SF Pro Text', 'Segoe UI', sans-serif;
            font-weight: bold;
        }}
        QPushButton:hover {{ background-color: {t['purple_dim']}; }}
    """


def build_tree_view_stylesheet(t: dict) -> str:
    """Stylesheet for the file explorer QTreeView."""
    return f"""
        QTreeView {{
            background-color: {t['bg0_hard']};
            color: {t['fg1']};
            border: none;
            font-family: 'Inter', 'SF Pro Text', 'Segoe UI', sans-serif;
            font-size: 11pt;
        }}
        QTreeView::item {{ padding: 4px; }}
        QTreeView::item:selected {{
            background-color: {t['bg2']};
            color: {t['fg0']};
            border-radius: 4px;
        }}
        QTreeView::item:hover:!selected {{
            background-color: {t['bg1']};
            border-radius: 4px;
        }}
        QTreeView::branch {{ background-color: transparent; }}
    """


# ─────────────────────────────────────────────────────────────────────────────
# Runtime Theme Application
# ─────────────────────────────────────────────────────────────────────────────

def apply_theme(app, theme_name: str, settings_manager=None):
    global _current_theme_name
    _current_theme_name = theme_name

    t = get_theme(theme_name)
    app.setStyleSheet(build_app_stylesheet(t))

    try:
        from editor.highlighter import registry
        registry.on_theme_changed(t)
    except Exception:
        pass

    if settings_manager:
        settings_manager.set('theme', theme_name)

    # Broadcast the new palette to any connected widget
    theme_signals.theme_changed.emit(t)

    return t