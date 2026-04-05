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
    
        # Backgrounds: shift towards grays with subtle blue-green tint
        "bg0_hard":   "#1b2227",  # darker grayish blue-black
        "bg0":        "#262c30",  # dark gray
        "bg1":        "#2f3539",  # medium dark gray
        "bg2":        "#4a5055",  # gray for selections
        "bg3":        "#5f656a",  # inactive tab gray
        "bg4":        "#7a8085",  # muted gray
    
        # Foregrounds: softer, more gray than yellow-beige
        "fg0":        "#d7d9db",  # light gray
        "fg1":        "#c8cacd",
        "fg2":        "#9ea1a4",
        "fg3":        "#8a8e91",
        "fg4":        "#73777a",
    
        # Accent colors: slightly muted and grayish versions
        "red":        "#dc322f",
        "green":      "#6e7b48",  # muted olive green
        "yellow":     "#b58900",
        "blue":       "#4a6b82",  # muted grayish blue
        "purple":     "#6c71c4",
        "aqua":       "#5a7e77",  # muted grayish teal
        "orange":     "#cb4b16",
    
        # Dim accent colors
        "red_dim":    "#a32422",
        "green_dim":  "#505a36",
        "yellow_dim": "#896800",
        "blue_dim":   "#395369",
        "purple_dim": "#4f5491",
        "aqua_dim":   "#43645e",
        "orange_dim": "#9a380f",
    
        # Semantic mappings
        "accent":           "#4a6b82",  # use muted blue for accent
        "accent_alt":       "#5a7e77",  # muted aqua
        "highlight":        "#2f3539",
        "border":           "#2f3539",
        "border_focus":     "#4a6b82",
        "status_bar":       "#2f3539",
        "tab_active_bar":   "#4a6b82",
        "scrollbar":        "#4a5055",
        "scrollbar_hover":  "#5f656a",
        "chat_user_bubble": "#4a6b82",
        "chat_ai_label":    "#6c71c4",
        "ghost_text":       "#4a5055",
        "error":            "#dc322f",
        "warning":          "#b58900",
        "success":          "#6e7b48",
        "added_line":       "#6e7b48",
        "modified_line":    "#b58900",
    },
    
    "one_dark": {
        "name": "One Dark",

        "bg0_hard":   "#21252b",
        "bg0":        "#282c34",
        "bg1":        "#2c313c",
        "bg2":        "#3a3f4b",
        "bg3":        "#4b5060",
        "bg4":        "#5c6370",

        "fg0":        "#ffffff",
        "fg1":        "#abb2bf",
        "fg2":        "#828997",
        "fg3":        "#5c6370",
        "fg4":        "#3e4452",

        "red":        "#e06c75",
        "green":      "#98c379",
        "yellow":     "#e5c07b",
        "blue":       "#61afef",
        "purple":     "#c678dd",
        "aqua":       "#56b6c2",
        "orange":     "#d19a66",

        "red_dim":    "#be5046",
        "green_dim":  "#7fba00",
        "yellow_dim": "#d19a66",
        "blue_dim":   "#3b8eea",
        "purple_dim": "#a074c4",
        "aqua_dim":   "#2aa198",
        "orange_dim": "#d1843a",

        "accent":           "#61afef",
        "accent_alt":       "#56b6c2",
        "highlight":        "#3e4452",
        "border":           "#2c313c",
        "border_focus":     "#61afef",
        "status_bar":       "#21252b",
        "tab_active_bar":   "#61afef",
        "scrollbar":        "#3a3f4b",
        "scrollbar_hover":  "#4b5060",
        "chat_user_bubble": "#61afef",
        "chat_ai_label":    "#c678dd",
        "ghost_text":       "#5c6370",
        "error":            "#e06c75",
        "warning":          "#e5c07b",
        "success":          "#98c379",
        "added_line":       "#98c379",
        "modified_line":    "#e5c07b",
    },

    "dracula": {
        "name": "Dracula",

        "bg0_hard":   "#282a36",
        "bg0":        "#44475a",
        "bg1":        "#373844",
        "bg2":        "#6272a4",
        "bg3":        "#6272a4",
        "bg4":        "#bd93f9",

        "fg0":        "#f8f8f2",
        "fg1":        "#f8f8f2",
        "fg2":        "#f1fa8c",
        "fg3":        "#50fa7b",
        "fg4":        "#8be9fd",

        "red":        "#ff5555",
        "green":      "#50fa7b",
        "yellow":     "#f1fa8c",
        "blue":       "#6272a4",
        "purple":     "#bd93f9",
        "aqua":       "#8be9fd",
        "orange":     "#ffb86c",

        "red_dim":    "#ff6e6e",
        "green_dim":  "#69ff94",
        "yellow_dim": "#ffffa5",
        "blue_dim":   "#7f8cdb",
        "purple_dim": "#d6acff",
        "aqua_dim":   "#9aedfe",
        "orange_dim": "#ffcb6b",

        "accent":           "#ff79c6",
        "accent_alt":       "#8be9fd",
        "highlight":        "#44475a",
        "border":           "#373844",
        "border_focus":     "#ff79c6",
        "status_bar":       "#282a36",
        "tab_active_bar":   "#ff79c6",
        "scrollbar":        "#373844",
        "scrollbar_hover":  "#6272a4",
        "chat_user_bubble": "#8be9fd",
        "chat_ai_label":    "#bd93f9",
        "ghost_text":       "#6272a4",
        "error":            "#ff5555",
        "warning":          "#f1fa8c",
        "success":          "#50fa7b",
        "added_line":       "#50fa7b",
        "modified_line":    "#f1fa8c",
    },
    
    "solarized_light": {
        "name": "Solarized Light",
    
        # Changed from #fdf6e3 and #eee8d5 to light grays
        "bg0_hard":   "#e0e0e0",  # light gray, instead of bright cream
        "bg0":        "#e0e0e0",
        "bg1":        "#cfcfcf",  # slightly darker gray for panels, sidebars
        "bg2":        "#a8a8a8",  # selection, hover
        "bg3":        "#8c8c8c",  # inactive tabs
        "bg4":        "#707070",  # comments, muted borders
    
        # Foregrounds can stay similar for readability on gray backgrounds
        "fg0":        "#073642",
        "fg1":        "#586e75",
        "fg2":        "#657b83",
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
        "highlight":        "#cfcfcf",   # lighter gray highlight instead of bright cream
        "border":           "#a8a8a8",
        "border_focus":     "#268bd2",
        "status_bar":       "#e0e0e0",
        "tab_active_bar":   "#268bd2",
        "scrollbar":        "#8c8c8c",
        "scrollbar_hover":  "#707070",
        "chat_user_bubble": "#268bd2",
        "chat_ai_label":    "#6c71c4",
        "ghost_text":       "#a8a8a8",
        "error":            "#dc322f",
        "warning":          "#b58900",
        "success":          "#859900",
        "added_line":       "#859900",
        "modified_line":    "#b58900",
    },

    "nord": {
        "name": "Nord",

        "bg0_hard":   "#2e3440",
        "bg0":        "#3b4252",
        "bg1":        "#434c5e",
        "bg2":        "#4c566a",
        "bg3":        "#616e88",
        "bg4":        "#81a1c1",

        "fg0":        "#eceff4",
        "fg1":        "#d8dee9",
        "fg2":        "#e5e9f0",
        "fg3":        "#8fbcbb",
        "fg4":        "#88c0d0",

        "red":        "#bf616a",
        "green":      "#a3be8c",
        "yellow":     "#ebcb8b",
        "blue":       "#81a1c1",
        "purple":     "#b48ead",
        "aqua":       "#88c0d0",
        "orange":     "#d08770",

        "red_dim":    "#a54242",
        "green_dim":  "#8fbcbb",
        "yellow_dim": "#d7af87",
        "blue_dim":   "#5e81ac",
        "purple_dim": "#946ea3",
        "aqua_dim":   "#5e81ac",
        "orange_dim": "#b0725a",

        "accent":           "#81a1c1",
        "accent_alt":       "#88c0d0",
        "highlight":        "#434c5e",
        "border":           "#4c566a",
        "border_focus":     "#81a1c1",
        "status_bar":       "#2e3440",
        "tab_active_bar":   "#81a1c1",
        "scrollbar":        "#434c5e",
        "scrollbar_hover":  "#616e88",
        "chat_user_bubble": "#81a1c1",
        "chat_ai_label":    "#b48ead",
        "ghost_text":       "#616e88",
        "error":            "#bf616a",
        "warning":          "#ebcb8b",
        "success":          "#a3be8c",
        "added_line":       "#a3be8c",
        "modified_line":    "#ebcb8b",
    },

    "palenight": {
        "name": "Palenight",

        "bg0_hard":   "#292d3e",
        "bg0":        "#292d3e",
        "bg1":        "#323550",
        "bg2":        "#3f415e",
        "bg3":        "#5c5f77",
        "bg4":        "#676c7f",

        "fg0":        "#e6e1cf",
        "fg1":        "#a6accd",
        "fg2":        "#bfbfef",
        "fg3":        "#828bb8",
        "fg4":        "#5c5f77",

        "red":        "#ff5370",
        "green":      "#c3e88d",
        "yellow":     "#ffcb6b",
        "blue":       "#82aaff",
        "purple":     "#c792ea",
        "aqua":       "#89ddff",
        "orange":     "#f78c6c",

        "red_dim":    "#e53950",
        "green_dim":  "#8fbcbb",
        "yellow_dim": "#f2b642",
        "blue_dim":   "#6b9afc",
        "purple_dim": "#ab47bc",
        "aqua_dim":   "#66c2ff",
        "orange_dim": "#e57373",

        "accent":           "#82aaff",
        "accent_alt":       "#89ddff",
        "highlight":        "#3f415e",
        "border":           "#323550",
        "border_focus":     "#82aaff",
        "status_bar":       "#292d3e",
        "tab_active_bar":   "#82aaff",
        "scrollbar":        "#3f415e",
        "scrollbar_hover":  "#5c5f77",
        "chat_user_bubble": "#82aaff",
        "chat_ai_label":    "#c792ea",
        "ghost_text":       "#5c5f77",
        "error":            "#ff5370",
        "warning":          "#ffcb6b",
        "success":          "#c3e88d",
        "added_line":       "#c3e88d",
        "modified_line":    "#ffcb6b",
    },
    
    "quillai": {
        "name": "QuillAi",
    
        # Base backgrounds (warm, soft grays and light browns)
        "bg0_hard":   "#2b2a28",  # editor background - dark but warm
        "bg0":        "#3c3b38",  # main background
        "bg1":        "#4e4c49",  # panels, sidebars
        "bg2":        "#65625f",  # selection, hover
        "bg3":        "#7e7b77",  # inactive tabs
        "bg4":        "#9a9793",  # comments, muted borders
    
        # Foregrounds (soft off-whites and light grays)
        "fg0":        "#f0ebe3",  # brightest text
        "fg1":        "#ded9d0",  # main text
        "fg2":        "#c6c1b8",  # secondary text
        "fg3":        "#aaa59f",  # muted text
        "fg4":        "#8f8b87",  # very muted
    
        # Accent colors (pastel, low saturation)
        "red":        "#e07a78",
        "green":      "#98bb98",
        "yellow":     "#d9c99b",
        "blue":       "#8ca6db",
        "purple":     "#b39ddb",
        "aqua":       "#7fbfc0",
        "orange":     "#eab07a",
    
        # Accent colors (dimmed variants)
        "red_dim":    "#b45e5c",
        "green_dim":  "#6f8b6f",
        "yellow_dim": "#b3a87a",
        "blue_dim":   "#6b85b0",
        "purple_dim": "#8f74b0",
        "aqua_dim":   "#5f8d8e",
        "orange_dim": "#b37b52",
    
        # Semantic mappings
        "accent":           "#8ca6db",  # calm pastel blue as primary accent
        "accent_alt":       "#7fbfc0",  # pastel aqua as secondary accent
        "highlight":        "#65625f",  # subtle selection highlight
        "border":           "#4e4c49",
        "border_focus":     "#8ca6db",
        "status_bar":       "#3c3b38",
        "tab_active_bar":   "#8ca6db",
        "scrollbar":        "#4e4c49",
        "scrollbar_hover":  "#65625f",
        "chat_user_bubble": "#7fbfc0",
        "chat_ai_label":    "#b39ddb",
        "ghost_text":       "#9a9793",
        "error":            "#e07a78",
        "warning":          "#d9c99b",
        "success":          "#98bb98",
        "added_line":       "#98bb98",
        "modified_line":    "#d9c99b",
    }

}

# Default theme
DEFAULT_THEME = "quillai"

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
    Per-widget stylesheet strings for InlineChatWidget.
    Unified aesthetic matching the git panel — flat surfaces, subtle borders,
    bg0_hard inputs, grouped button rows.
    """
    # Shared button base used for all footer buttons
    _footer_btn = f"""
        QPushButton {{
            background-color: {t['bg1']};
            color: {t['fg2']};
            border: 1px solid {t['border']};
            border-radius: 4px;
            padding: 3px 10px;
            font-family: {FONT_UI};
            font-size: 9pt;
        }}
        QPushButton:hover {{
            background-color: {t['bg2']};
            color: {t['fg0']};
            border-color: {t['border_focus']};
        }}
    """
    return {
        "panel": f"""
            QWidget#inlineChat {{
                background-color: {t['bg1']};
                border: 1px solid {t['border']};
                border-radius: 6px;
            }}
        """,
        "header": (
            f"background-color: {t['bg0_hard']}; "
            f"border-bottom: 1px solid {t['border']}; "
            f"border-radius: 6px 6px 0 0;"
        ),
        "title_label": (
            f"color: {t['fg2']}; font-weight: bold; font-size: 9pt;"
            f" font-family: {FONT_UI}; background: transparent;"
        ),
        "context_label": (
            f"color: {t['fg4']}; font-size: 8pt;"
            f" font-family: {FONT_UI}; background: transparent;"
        ),
        "close_btn": f"""
            QPushButton {{
                background: transparent; color: {t['fg4']};
                border: none; font-size: 9pt; padding: 0;
            }}
            QPushButton:hover {{ color: {t['fg1']}; }}
        """,
        "input_container": (
            f"background: {t['bg0_hard']};"
        ),
        "input": f"""
            QLineEdit {{
                background: transparent;
                border: none;
                color: {t['fg0']};
                font-family: {FONT_UI};
                font-size: 10pt;
                padding: 0;
            }}
        """,
        "send_btn": f"""
            QPushButton {{
                background-color: transparent;
                color: {t['fg4']};
                border: none;
                font-size: 10pt;
                padding: 0 4px;
            }}
            QPushButton:hover {{ color: {t['fg0']}; }}
        """,
        "response_area": f"""
            QTextEdit {{
                background-color: {t['bg0_hard']};
                color: {t['fg1']};
                border: none;
                border-top: 1px solid {t['border']};
                font-family: {FONT_UI};
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
                background-color: {t['blue_dim']};
                color: {t['fg0']};
                border: 1px solid {t['border']};
                border-radius: 4px;
                padding: 3px 10px;
                font-family: {FONT_UI};
                font-size: 9pt;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {t['blue']}; }}
        """,
        "chat_btn":  _footer_btn,
        "clear_btn": f"""
            QPushButton {{
                background-color: transparent;
                color: {t['fg4']};
                border: none;
                padding: 3px 8px;
                font-family: {FONT_UI};
                font-size: 9pt;
            }}
            QPushButton:hover {{ color: {t['fg2']}; }}
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
    """Stylesheet for SnippetPalette — unified aesthetic matching git panel."""
    return f"""
        QDialog {{ background-color: transparent; }}
        QWidget#snippetFrame {{
            background-color: {t['bg1']};
            border: 1px solid {t['border_focus']};
            border-radius: 8px;
        }}
        QLineEdit {{
            background-color: {t['bg0_hard']};
            color: {t['fg0']};
            border: none;
            border-bottom: 1px solid {t['border']};
            border-radius: 8px 8px 0 0;
            padding: 10px 14px;
            font-family: {FONT_UI};
            font-size: 11pt;
        }}
        QLineEdit:focus {{ border-bottom: 1px solid {t['border_focus']}; }}
        QListWidget {{
            background-color: {t['bg1']};
            color: {t['fg1']};
            border: none;
            outline: none;
            font-family: {FONT_UI};
            font-size: 10pt;
        }}
        QListWidget::item {{ padding: 5px 12px; }}
        QListWidget::item:selected {{
            background-color: {t['bg2']};
            color: {t['fg0']};
        }}
        QListWidget::item:hover:!selected {{ background-color: {t['bg1']}; }}
        QPlainTextEdit {{
            background-color: {t['bg0_hard']};
            color: {t['fg1']};
            border: none;
            font-family: {FONT_CODE};
            font-size: 10pt;
            padding: 10px;
        }}
        QPushButton {{
            background-color: {t['bg1']};
            color: {t['fg2']};
            border: 1px solid {t['border']};
            border-radius: 4px;
            padding: 4px 14px;
            font-family: {FONT_UI};
            font-size: 9pt;
        }}
        QPushButton:hover {{
            background-color: {t['bg2']};
            color: {t['fg0']};
            border-color: {t['border_focus']};
        }}
        QLabel {{
            color: {t['fg4']};
            font-family: {FONT_UI};
            font-size: 9pt;
        }}
    """


def build_snippet_palette_parts(t: dict) -> dict:
    """Per-widget styles for SnippetPalette children."""
    return {
        "splitter_handle": (
            f"QSplitter::handle {{ background-color: {t['border']}; width: 1px; }}"
        ),
        "preview_container": f"background-color: {t['bg0_hard']};",
        "preview_header": f"""
            QLabel {{
                color: {t['fg2']};
                background-color: {t['bg1']};
                border-bottom: 1px solid {t['border']};
                font-family: {FONT_UI};
                font-size: 9pt;
                padding: 5px 12px;
            }}
        """,
        "footer": (
            f"background-color: {t['bg1']}; border-top: 1px solid {t['border']};"
        ),
        "hint": (
            f"color: {t['fg4']}; font-family: {FONT_UI}; font-size: 9pt; padding: 0;"
        ),
        "cancel_btn": f"""
            QPushButton {{
                background-color: {t['bg1']};
                color: {t['fg2']};
                border: 1px solid {t['border']};
                border-radius: 4px;
                padding: 4px 14px;
                font-family: {FONT_UI};
                font-size: 9pt;
            }}
            QPushButton:hover {{
                background-color: {t['bg2']};
                color: {t['fg0']};
                border-color: {t['border_focus']};
            }}
        """,
        "insert_btn": f"""
            QPushButton {{
                background-color: {t['blue_dim']};
                color: {t['fg0']};
                border: 1px solid {t['border']};
                border-radius: 4px;
                padding: 4px 14px;
                font-family: {FONT_UI};
                font-size: 9pt;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {t['blue']}; }}
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
    """Settings dialog styled like git panel — flat, layered, minimal."""
    return f"""
        /* ── Dialog Base ───────────────────────────────────────────── */
        QDialog {{
            background-color: {t['bg1']};
            color: {t['fg1']};
        }}

        /* ── Labels ───────────────────────────────────────────────── */
        QLabel {{
            color: {t['fg2']};
            font-size: 9pt;
            background: transparent;
        }}

        /* Section titles (QGroupBox title) */
        QGroupBox {{
            color: {t['fg4']};
            font-weight: bold;
            font-size: 9pt;
            border: 1px solid {t['border']};
            border-radius: 6px;
            margin-top: 12px;
            padding: 10px;
            background-color: {t['bg1']};
        }}

        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 6px;
            left: 10px;
            color: {t['fg4']};
        }}

        /* ── Inputs (Git panel style) ─────────────────────────────── */
        QLineEdit {{
            background-color: {t['bg0_hard']};
            color: {t['fg0']};
            border: 1px solid {t['border']};
            border-radius: 4px;
            padding: 6px 10px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 10pt;
        }}

        QLineEdit:focus {{
            border: 1px solid {t['border_focus']};
        }}

        QComboBox {{
            background-color: {t['bg0_hard']};
            color: {t['fg0']};
            border: 1px solid {t['border']};
            border-radius: 4px;
            padding: 6px 10px;
            font-size: 10pt;
        }}

        QComboBox:focus {{
            border: 1px solid {t['border_focus']};
        }}

        QComboBox::drop-down {{
            border: none;
        }}

        QComboBox QAbstractItemView {{
            background-color: {t['bg1']};
            color: {t['fg1']};
            selection-background-color: {t['highlight']};
            border: 1px solid {t['border']};
        }}

        /* ── Buttons (Git panel style hierarchy) ──────────────────── */

        /* Primary action */
        QPushButton#saveBtn {{
            background-color: {t['accent']};
            color: {t['bg0_hard']};
            border: none;
            border-radius: 4px;
            padding: 6px 18px;
            font-weight: bold;
        }}

        QPushButton#saveBtn:hover {{
            background-color: {t['yellow']};
        }}

        /* Secondary buttons */
        QPushButton {{
            background-color: {t['bg2']};
            color: {t['fg1']};
            border: 1px solid {t['border']};
            border-radius: 4px;
            padding: 6px 14px;
            font-weight: normal;
        }}

        QPushButton:hover {{
            background-color: {t['bg3']};
            border-color: {t['border_focus']};
        }}

        /* Cancel = subtle */
        QPushButton#cancelBtn {{
            background-color: transparent;
            color: {t['fg4']};
            border: none;
            padding: 6px 10px;
        }}

        QPushButton#cancelBtn:hover {{
            color: {t['fg2']};
        }}

        /* ── Checkboxes ───────────────────────────────────────────── */
        QCheckBox {{
            color: {t['fg1']};
            spacing: 8px;
        }}

        QCheckBox::indicator {{
            width: 14px;
            height: 14px;
            border-radius: 3px;
            border: 1px solid {t['border']};
            background-color: {t['bg0_hard']};
        }}

        QCheckBox::indicator:checked {{
            background-color: {t['accent']};
            border-color: {t['accent']};
        }}
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
    # Compact icon button — refresh, branch, tag, blame
    icon_btn = f"""
        QPushButton {{
            background-color: {t['bg1']};
            color: {t['fg2']};
            border: 1px solid {t['border']};
            border-radius: 4px;
            padding: 4px 8px;
            font-size: 9pt;
        }}
        QPushButton:hover {{
            background-color: {t['bg2']};
            color: {t['fg0']};
            border-color: {t['border_focus']};
        }}
        QPushButton:checked {{
            background-color: {t['bg2']};
            color: {t['accent']};
            border-color: {t['accent']};
        }}
    """
    return {
        "icon_btn": icon_btn,
        "branch_combo": f"""
            QComboBox {{
                background-color: {t['bg1']};
                color: {t['fg1']};
                border: 1px solid {t['border']};
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 9pt;
                font-weight: bold;
            }}
            QComboBox:hover {{ border-color: {t['border_focus']}; }}
            QComboBox::drop-down {{ border: none; width: 18px; }}
            QComboBox QAbstractItemView {{
                background-color: {t['bg1']};
                color: {t['fg1']};
                selection-background-color: {t['highlight']};
                border: 1px solid {t['border']};
            }}
        """,
        "tree": f"""
            QTreeWidget {{
                background-color: {t['bg0_hard']};
                color: {t['fg1']};
                border: none;
                font-family: {FONT_UI};
                font-size: 10pt;
            }}
            QTreeWidget::item {{ padding: 3px 4px; border-radius: 3px; }}
            QTreeWidget::item:selected {{
                background-color: {t['bg2']};
                color: {t['fg0']};
            }}
            QTreeWidget::item:hover:!selected {{ background-color: {t['bg1']}; }}
            QTreeWidget::branch {{ background-color: transparent; }}
            QTreeWidget::indicator:unchecked {{
                border: 1px solid {t['border']};
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
        "section_label": f"""
            QLabel {{
                color: {t['fg4']};
                font-family: {FONT_UI};
                font-size: 8pt;
                font-weight: bold;
                padding: 4px 4px 2px 4px;
            }}
        """,
        "commit_input": f"""
            QLineEdit {{
                background-color: {t['bg0_hard']};
                color: {t['fg1']};
                border: 1px solid {t['border']};
                border-radius: 4px 4px 0 0;
                border-bottom: none;
                padding: 7px 10px;
                font-family: {FONT_UI};
                font-size: 10pt;
            }}
            QLineEdit:focus {{ border: 1px solid {t['border_focus']}; border-bottom: none; }}
        """,
        "ai_msg_btn": f"""
            QPushButton {{
                background-color: {t['bg1']};
                color: {t['fg2']};
                border: 1px solid {t['border']};
                border-radius: 0;
                border-top: none;
                border-right: 1px solid {t['border']};
                padding: 5px 8px;
                font-size: 9pt;
            }}
            QPushButton:hover {{ background-color: {t['bg2']}; color: {t['fg0']}; }}
            QPushButton:disabled {{ color: {t['fg4']}; }}
        """,
        "commit_btn": f"""
            QPushButton {{
                background-color: {t['blue_dim']};
                color: {t['fg0']};
                border: 1px solid {t['border']};
                border-top: none;
                border-left: none;
                border-radius: 0 0 4px 0;
                padding: 5px 10px;
                font-size: 9pt;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {t['blue']}; }}
        """,
        "blame_btn": f"""
            QPushButton {{
                background-color: transparent;
                color: {t['fg4']};
                border: none;
                border-top: 1px solid {t['border']};
                border-radius: 0;
                padding: 5px;
                font-size: 9pt;
            }}
            QPushButton:hover {{ color: {t['fg1']}; background-color: {t['bg1']}; }}
            QPushButton:checked {{ color: {t['accent']}; }}
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
        # Status badge colors
        "status_modified":    t['yellow'],
        "status_modified_bg": t['yellow_dim'],
        "status_added":       t['green'],
        "status_added_bg":    t['green_dim'],
        "status_deleted":     t['red'],
        "status_deleted_bg":  t['red_dim'],
        "status_default":     t['fg1'],
        # Raw theme values needed by the panel
        "bg0_hard":   t['bg0_hard'],
        "bg1":        t['bg1'],
        "border":     t['border'],
        "accent":     t['accent'],
        "fg1":        t['fg1'],
        "fg4":        t['fg4'],
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

def build_symbol_outline_stylesheet(t: dict) -> str:
    """Stylesheet for the Symbol Outline dock panel."""
    bg     = t.get("bg0_hard", "#1d2021")
    bg1    = t.get("bg1",      "#3c3836")
    bg2    = t.get("bg2",      "#504945")
    fg     = t.get("fg1",      "#ebdbb2")
    fg_dim = t.get("fg4",      "#a89984")
    border = t.get("border",   "#504945")

    return f"""
        QWidget#outlineContainer {{
            background-color: {bg};
        }}
        QWidget#outlineHeader {{
            background-color: {bg1};
            border-bottom: 1px solid {border};
        }}
        QLabel#outlineFileLabel {{
            color: {fg_dim};
            font-family: {FONT_UI};
            font-size: 8.5pt;
            background: transparent;
        }}
        QPushButton#outlineRefreshBtn {{
            background: transparent;
            color: {fg_dim};
            border: none;
            font-size: 11pt;
            padding: 0;
        }}
        QPushButton#outlineRefreshBtn:hover {{
            color: {fg};
        }}
        QTreeWidget#outlineTree {{
            background-color: {bg};
            color: {fg};
            border: none;
            font-family: {FONT_UI};
            font-size: 9.5pt;
        }}
        QTreeWidget#outlineTree::item {{
            padding: 2px 4px;
            border-radius: 3px;
        }}
        QTreeWidget#outlineTree::item:selected {{
            background-color: {bg2};
            color: {fg};
        }}
        QTreeWidget#outlineTree::item:hover:!selected {{
            background-color: {bg1};
        }}
        QTreeWidget#outlineTree::branch {{
            background: transparent;
            border: none;
        }}
    """
    
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
# Font Constants
# These are the canonical font stacks used throughout the UI.  Import them
# anywhere a font string is needed so there is one place to change them.
# ─────────────────────────────────────────────────────────────────────────────

FONT_UI   = "'Inter', 'SF Pro Text', 'Segoe UI', sans-serif"
FONT_CODE = "'JetBrains Mono', 'Hack', 'Courier New', monospace"

# QFont family names — used when constructing QFont() objects directly.
# Qt will fall back to the system monospace / sans-serif if the preferred
# font is not installed.
QFONT_CODE = "JetBrains Mono"
QFONT_UI   = "Inter"


def build_chat_styles(t: dict) -> dict:
 
    prose_font  = f"font-family: '{FONT_UI}', 'Inter', system-ui, sans-serif;"
    code_font   = f"font-family: '{FONT_CODE}', 'JetBrains Mono', monospace;"
    prose_size  = "font-size: 10.5pt;"
    code_size   = "font-size: 9.5pt;"
    prose_lh    = "line-height: 1.6;"
    code_lh     = "line-height: 1.5;"
 
    bg_code     = t.get("bg0_hard",  "#1d2021")
    bg_user     = t.get("bg2",       "#504945")
    fg_prose    = t.get("fg1",       "#ebdbb2")
    fg_dim      = t.get("fg4",       "#a89984")
    fg_label    = t.get("fg3",       "#bdae93")
    accent      = t.get("accent",    "#fabd2f")
    accent_dim  = t.get("yellow_dim", t.get("accent", "#fabd2f"))
    border      = t.get("border",    "#3c3836")
    border_code = t.get("bg2",       "#504945")
    bg1         = t.get("bg1",       "#3c3836")
    link_color  = t.get("blue",      "#83a598")
 
    return {
 
        # ── User bubble ───────────────────────────────────────────
        # <td> carries background — reliable in Qt
        "user_bubble_td": (
            f"background-color: {bg_user}; "
            f"color: {fg_prose}; "
            f"padding: 9px 14px; "
            f"{prose_font} {prose_size} {prose_lh}"
        ),
 
        # "You" label cell — right-aligned, small, dim
        "user_label_td": (
            f"color: {fg_dim}; "
            f"font-size: 8pt; "
            f"padding: 2px 6px 0 0; "
            f"{prose_font}"
        ),
 
        # ── QuillAI label ─────────────────────────────────────────
        "ai_label_td": (
            f"color: {accent_dim}; "
            f"font-size: 8pt; "
            f"font-weight: 600; "
            f"padding: 0 0 4px 6px; "
            f"{prose_font}"
        ),
 
        # ── Response content cell ─────────────────────────────────
        # Outer <td> that wraps all response prose/code
        "response_td": (
            f"color: {fg_prose}; "
            f"padding: 0 8px 0 8px; "
            f"{prose_font} {prose_size} {prose_lh}"
        ),
 
        # ── Prose ─────────────────────────────────────────────────
        "prose_p": (
            f"margin: 0 0 8px 0; padding: 0; "
            f"color: {fg_prose}; {prose_font} {prose_size} {prose_lh}"
        ),
        "ul": (
            f"margin: 0 0 8px 0; padding: 0 0 0 20px; "
            f"color: {fg_prose}; {prose_font} {prose_size}"
        ),
        "ol": (
            f"margin: 0 0 8px 0; padding: 0 0 0 20px; "
            f"color: {fg_prose}; {prose_font} {prose_size}"
        ),
        "prose_li": (
            f"margin: 2px 0; padding: 0; "
            f"color: {fg_prose}; {prose_font} {prose_size} {prose_lh}"
        ),
        "heading_1": (
            f"margin: 12px 0 6px 0; padding: 0; "
            f"color: {accent}; font-size: 13pt; font-weight: 700; {prose_font}"
        ),
        "heading_2": (
            f"margin: 10px 0 5px 0; padding: 0; "
            f"color: {accent}; font-size: 12pt; font-weight: 600; {prose_font}"
        ),
        "heading_3": (
            f"margin: 8px 0 4px 0; padding: 0; "
            f"color: {fg_label}; font-size: 11pt; font-weight: 600; {prose_font}"
        ),
        "strong": f"color: {fg_prose}; font-weight: 700;",
        "em":     f"color: {fg_prose}; font-style: italic;",
        "hr":     f"border: none; border-top: 1px solid {border}; margin: 12px 0;",
 
        # ── Inline code ───────────────────────────────────────────
        "inline_code": (
            f"background-color: {bg_code}; "
            f"color: {t.get('orange', '#fe8019')}; "
            f"border: 1px solid {border_code}; "
            f"border-radius: 3px; "
            f"padding: 1px 5px; "
            f"{code_font} font-size: 9pt;"
        ),
 
        # ── Code block — header and body same bg ──────────────────
        "code_header_td": (
            f"background-color: {bg_code}; "
            f"color: {fg_dim}; "
            f"border: 1px solid {border_code}; "
            f"border-bottom: 1px solid {border}; "
            f"padding: 5px 12px; "
            f"{prose_font} font-size: 8.5pt;"
        ),
        "lang_label": (
            f"color: {fg_label}; font-weight: 600; font-size: 8.5pt; "
            f"{prose_font} letter-spacing: 0.04em;"
        ),
        "copy_link": (
            f"color: {link_color}; text-decoration: none; font-size: 8.5pt; "
            f"{prose_font}"
        ),
        "code_body_td": (
            f"background-color: {bg_code}; "
            f"border: 1px solid {border_code}; "
            f"border-top: none; "
            f"padding: 12px 14px;"
        ),
        "code_pre": (
            f"{code_font} {code_size} {code_lh} "
            f"margin: 0; padding: 0; white-space: pre; color: {fg_prose};"
        ),
 
        # ── Markdown tables ───────────────────────────────────────
        "md_table": (
            f"border: 1px solid {border}; "
            f"margin: 4px 0 10px 0;"
        ),
        "md_th": (
            f"background-color: {bg1}; "
            f"color: {fg_label}; "
            f"font-weight: 600; "
            f"border-bottom: 1px solid {border}; "
            f"border-right: 1px solid {border}; "
            f"padding: 6px 10px; "
            f"{prose_font} {prose_size}"
        ),
        "md_td": (
            f"color: {fg_prose}; "
            f"border-bottom: 1px solid {border}; "
            f"border-right: 1px solid {border}; "
            f"padding: 5px 10px; "
            f"{prose_font} {prose_size}"
        ),
        "md_tr": "",  # row-level styling handled via td
 
        # ── Legacy keys (kept for compatibility) ──────────────────
        "user_bubble": (
            f"background-color: {bg_user}; color: {fg_prose}; "
            f"padding: 9px 14px; {prose_font} {prose_size}"
        ),
        "user_row_p":  f"margin: 4px 8px 2px 48px; padding: 0; text-align: right;",
        "user_label_p": (
            f"margin: 2px 12px 12px 0; padding: 0; text-align: right; "
            f"color: {fg_dim}; font-size: 8pt; {prose_font}"
        ),
        "ai_label_p": (
            f"margin: 4px 0 6px 8px; padding: 0; "
            f"color: {accent_dim}; font-size: 8pt; font-weight: 600; {prose_font}"
        ),
        "response_wrapper": (
            f"margin: 0 8px 4px 8px; padding: 0; "
            f"color: {fg_prose}; {prose_font} {prose_size} {prose_lh}"
        ),
        "code_header_span": (
            f"background-color: {bg_code}; color: {fg_dim}; "
            f"border: 1px solid {border_code}; padding: 5px 12px; "
            f"{prose_font} font-size: 8.5pt;"
        ),
        "code_block": (
            f"background-color: {bg_code}; color: {fg_prose}; "
            f"border: 1px solid {border_code}; padding: 12px 14px; "
            f"{code_font} {code_size} {code_lh} white-space: pre;"
        ),
        "user_label": f"color: {fg_dim}; font-size: 8pt; {prose_font}",
        "code_body_td_legacy": (
            f"background-color: {bg_code}; "
            f"border: 1px solid {border_code}; border-top: none; "
            f"border-radius: 0 0 6px 6px; padding: 12px 14px;"
        ),
        "code_pre_legacy": (
            f"{code_font} {code_size} {code_lh} "
            f"margin: 0; padding: 0; white-space: pre; color: {fg_prose};"
        ),
    }

def build_menu_stylesheet(t: dict) -> str:
    """Themed QMenu stylesheet — used for the Recent Projects menu and context menus."""
    return f"""
        QMenu {{
            background-color: {t['bg1']};
            color: {t['fg1']};
            border: 1px solid {t['border']};
            font-family: {FONT_UI};
            font-size: 10pt;
        }}
        QMenu::item {{ padding: 6px 24px 6px 12px; }}
        QMenu::item:selected {{
            background-color: {t['highlight']};
            color: {t['fg0']};
        }}
        QMenu::item:disabled {{ color: {t['fg4']}; }}
        QMenu::separator {{
            height: 1px;
            background-color: {t['border']};
            margin: 4px 0;
        }}
    """


def build_file_dialog_stylesheet(t: dict) -> str:
    """Stylesheet for QFileDialog when DontUseNativeDialog is set."""
    return f"""
        QFileDialog, QMessageBox {{
            background-color: {t['bg0']};
            color: {t['fg1']};
            font-family: {FONT_UI};
        }}
        QWidget {{
            background-color: {t['bg0']};
            color: {t['fg1']};
        }}
        QLineEdit, QTreeView, QListView {{
            background-color: {t['bg1']};
            border: 1px solid {t['border']};
            border-radius: 4px;
            color: {t['fg1']};
            padding: 2px;
        }}
        QPushButton {{
            background-color: {t['accent']};
            color: {t['bg0_hard']};
            border: none;
            padding: 6px 12px;
            border-radius: 4px;
            font-weight: bold;
        }}
        QPushButton:hover {{ background-color: {t['yellow']}; }}
    """


def build_find_in_files_parts(t: dict) -> dict:
    """Per-widget styles and colors for FindInFilesWidget."""
    return {
        "search_btn": f"""
            QPushButton {{
                background-color: {t['accent']};
                color: {t['bg0_hard']};
                border: none; border-radius: 4px;
                padding: 5px 16px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {t['yellow']}; }}
        """,
        "inputs": f"""
            QLineEdit {{
                background-color: {t['bg0_hard']};
                color: {t['fg0']};
                border: 1px solid {t['border']};
                border-radius: 4px;
                padding: 4px 8px;
            }}
            QLineEdit:focus {{ border: 1px solid {t['border_focus']}; }}
        """,
        "results_tree": f"""
            QTreeWidget {{
                background-color: {t['bg0_hard']};
                color: {t['fg1']};
                border: 1px solid {t['border']};
                border-radius: 4px;
            }}
            QTreeWidget::item {{ padding: 2px 4px; }}
            QTreeWidget::item:selected {{
                background-color: {t['bg2']};
                color: {t['fg0']};
            }}
            QTreeWidget::item:hover:!selected {{
                background-color: {t['bg1']};
            }}
        """,
        "status_default": f"color: {t['fg4']};",
        "status_found":   f"color: {t['green']};",
        "status_empty":   f"color: {t['red']};",
        # Raw colors for QTreeWidgetItem.setForeground
        "file_node_fg":   t['blue'],
        "line_node_fg":   t['fg1'],
    }


def build_command_palette_stylesheet(t: dict) -> str:
    """Outer shell for the command palette dialog."""
    return f"""
        QDialog {{ background-color: transparent; }}
        QWidget#paletteFrame {{
            background-color: {t['bg1']};
            border: 1px solid {t['border_focus']};
            border-radius: 8px;
        }}
        QLineEdit {{
            background-color: {t['bg0_hard']};
            color: {t['fg0']};
            border: none;
            border-bottom: 1px solid {t['border']};
            border-radius: 8px 8px 0 0;
            padding: 10px 14px;
            font-family: {FONT_UI};
            font-size: 11pt;
        }}
        QLineEdit:focus {{ border-bottom: 1px solid {t['border_focus']}; }}
        QListWidget {{
            background-color: {t['bg1']};
            color: {t['fg1']};
            border: none;
            border-radius: 0 0 8px 8px;
            outline: none;
            font-family: {FONT_UI};
            font-size: 10pt;
        }}
        QListWidget::item {{ padding: 5px 12px; }}
        QListWidget::item:selected {{
            background-color: {t['bg2']};
            color: {t['fg0']};
        }}
        QListWidget::item:hover:!selected {{ background-color: {t['bg2']}; }}
    """


def build_command_palette_parts(t: dict) -> dict:
    return {
        "icon_color":  t['accent'],
        "hint_color":  t['fg4'],
        "label_color": t['fg1'],
        "selected_bg": t['bg2'],
        "selected_fg": t['fg0'],
    }


def build_terminal_stylesheet(t: dict) -> str:
    """Stylesheet for the terminal dock container and fallback widget."""
    return f"""
        QWidget#terminalContainer {{
            background-color: {t['bg0_hard']};
        }}
        QPlainTextEdit {{
            background-color: {t['bg0_hard']};
            color: {t['fg1']};
            font-family: {FONT_CODE};
            font-size: 10pt;
            border: none;
            padding: 4px;
        }}
        QLineEdit {{
            background-color: {t['bg0_hard']};
            color: {t['fg0']};
            border: none;
            border-top: 1px solid {t['border']};
            font-family: {FONT_CODE};
            font-size: 10pt;
            padding: 4px 8px;
        }}
    """


def build_hover_popup_stylesheet(t: dict) -> str:
    """Floating hover doc popup shown on Ctrl+hover / cursor pause."""
    return f"""
        QWidget#hoverPopup {{
            background-color: {t['bg1']};
            border: 1px solid {t['border']};
            border-radius: 6px;
        }}
        QLabel {{
            color: {t['fg1']};
            font-family: {FONT_UI};
            font-size: 10pt;
            background: transparent;
            padding: 8px 12px;
        }}
        QTextEdit {{
            background-color: {t['bg1']};
            color: {t['fg1']};
            border: none;
            font-family: {FONT_UI};
            font-size: 10pt;
            padding: 8px 12px;
        }}
    """


def build_completion_popup_stylesheet(t: dict) -> str:
    """Autocomplete dropdown popup — list + detail bar."""
    bg      = t.get("bg1",      "#3c3836")
    bg2     = t.get("bg2",      "#504945")
    bg_hard = t.get("bg0_hard", "#1d2021")
    fg      = t.get("fg1",      "#ebdbb2")
    fg_dim  = t.get("fg4",      "#a89984")
    border  = t.get("border",   "#504945")
    blue    = t.get("blue",     "#83a598")
    sel     = t.get("bg3",      "#665c54")

    return f"""
        QFrame#CompletionPopup {{
            background-color: {bg};
            border: 1px solid {border};
        }}
        QListWidget {{
            background-color: {bg};
            color: {fg};
            border: none;
            outline: none;
            font-family: {FONT_CODE};
            font-size: 9pt;
        }}
        QListWidget::item {{
            padding: 2px 8px;
            border: none;
        }}
        QListWidget::item:selected {{
            background-color: {sel};
            color: {fg};
        }}
        QListWidget::item:hover {{
            background-color: {bg2};
        }}
        QFrame#detailBar {{
            background-color: {bg_hard};
            border-top: 1px solid {border};
        }}
        QLabel#detailLabel {{
            color: {blue};
            font-family: {FONT_CODE};
            font-size: 8pt;
            font-weight: 600;
            background: transparent;
        }}
        QLabel#docLabel {{
            color: {fg_dim};
            font-family: {FONT_UI};
            font-size: 8pt;
            background: transparent;
        }}
        QScrollBar:vertical {{
            background: {bg};
            width: 6px;
            border: none;
        }}
        QScrollBar::handle:vertical {{
            background: {sel};
            border-radius: 3px;
            min-height: 20px;
        }}
        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical {{ height: 0; }}
    """


def build_rename_dialog_stylesheet(t: dict) -> str:
    """Inline rename symbol dialog."""
    return f"""
        QWidget#RenamePopup {{
            background-color: {t['bg1']};
            border: 1px solid {t['border_focus']};
            border-radius: 6px;
        }}
        QLabel#renameLabel {{
            color: {t['fg2']};
            font-family: {FONT_UI};
            font-size: 9pt;
            background-color: {t['bg1']};
            padding: 0 4px;
        }}
        QLabel#renameHint {{
            color: {t['fg4']};
            font-family: {FONT_UI};
            font-size: 8pt;
            background-color: {t['bg1']};
            padding: 0 4px;
        }}
        QLineEdit#renameInput {{
            background-color: {t['bg0_hard']};
            color: {t['fg0']};
            border: 1px solid {t['border']};
            border-radius: 4px;
            font-family: {FONT_CODE};
            font-size: 10pt;
            padding: 4px 8px;
        }}
        QLineEdit#renameInput:focus {{
            border: 1px solid {t['border_focus']};
        }}
    """


def build_terminal_stylesheet(t: dict) -> str:
    """Stylesheet for the terminal dock container and fallback widget."""
    return f"""
        QWidget#terminalContainer {{
            background-color: {t['bg0_hard']};
        }}
        QPlainTextEdit {{
            background-color: {t['bg0_hard']};
            color: {t['fg1']};
            font-family: {FONT_CODE};
            font-size: 10pt;
            border: none;
            padding: 4px;
        }}
        QLineEdit {{
            background-color: {t['bg0_hard']};
            color: {t['fg0']};
            border: none;
            border-top: 1px solid {t['border']};
            font-family: {FONT_CODE};
            font-size: 10pt;
            padding: 4px 8px;
        }}
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