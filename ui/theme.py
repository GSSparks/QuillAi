"""
QuillAI Theme System
====================
To add a new theme:
  1. Add a new dictionary to ./plugins/themes following the same key structure.
  2. It will automatically appear in Settings and the View → Theme menu.

To switch themes at runtime:
  from ui.theme import apply_theme
  apply_theme(app, "gruvbox_dark")

Widget authors
--------------
- Call get_theme() once in __init__ to get the current palette.
- Connect to theme_signals.theme_changed to stay in sync.
- Never call get_theme() with a hardcoded name; use the no-arg form.
- Never build stylesheet strings inline. Use the builders provided here.
"""

from PyQt6.QtCore import QObject, pyqtSignal
import os
import importlib.util


# ─────────────────────────────────────────────────────────────────────────────
# Signals
# ─────────────────────────────────────────────────────────────────────────────

class ThemeSignals(QObject):
    theme_changed = pyqtSignal(dict)

theme_signals = ThemeSignals()


# ─────────────────────────────────────────────────────────────────────────────
# Font Constants  (defined first — used by all builders below)
# ─────────────────────────────────────────────────────────────────────────────

FONT_UI   = "'Inter', 'SF Pro Text', 'Segoe UI', sans-serif"
FONT_CODE = "'JetBrains Mono', 'Hack', 'Courier New', monospace"

# QFont family names for constructing QFont() objects directly
QFONT_CODE = "JetBrains Mono"
QFONT_UI   = "Inter"


# ─────────────────────────────────────────────────────────────────────────────
# Theme Registry  (auto-populated from plugins/themes/*.py)
# ─────────────────────────────────────────────────────────────────────────────
 
THEMES: dict = {}
 
DEFAULT_THEME = "quillai"
 
 
def _load_themes():
    """
    Discover and register all theme plugin files.
 
    Each file in plugins/themes/ must define:
        THEME_KEY  — str, the internal key (e.g. "gruvbox_dark")
        THEME_DATA — dict, the full palette
 
    Files that are missing either attribute are silently skipped.
    Import errors are printed but don't prevent other themes from loading.
    """
    themes_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),  # project root
        "plugins", "themes"
    )
 
    if not os.path.isdir(themes_dir):
        return
 
    for filename in sorted(os.listdir(themes_dir)):
        if not filename.endswith(".py") or filename.startswith("_"):
            continue
 
        filepath = os.path.join(themes_dir, filename)
        module_name = f"plugins.themes.{filename[:-3]}"
 
        try:
            spec   = importlib.util.spec_from_file_location(module_name, filepath)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
 
            key  = getattr(module, "THEME_KEY",  None)
            data = getattr(module, "THEME_DATA", None)
 
            if key and isinstance(data, dict):
                THEMES[key] = data
            else:
                print(f"[theme] skipped {filename} — missing THEME_KEY or THEME_DATA")
 
        except Exception as e:
            print(f"[theme] failed to load {filename}: {e}")
 
 
_load_themes()
 
# Fallback — if no themes loaded (e.g. plugins/ missing), define a minimal one
if not THEMES:
    THEMES["default"] = {
        "name": "Default",
        "bg0_hard": "#1d2021", "bg0": "#282828", "bg1": "#3c3836",
        "bg2": "#504945", "bg3": "#665c54", "bg4": "#7c6f64",
        "fg0": "#fbf1c7", "fg1": "#ebdbb2", "fg2": "#d5c4a1",
        "fg3": "#bdae93", "fg4": "#a89984",
        "red": "#fb4934", "green": "#b8bb26", "yellow": "#fabd2f",
        "blue": "#83a598", "purple": "#d3869b", "aqua": "#8ec07c",
        "orange": "#fe8019",
        "red_dim": "#cc241d", "green_dim": "#98971a", "yellow_dim": "#d79921",
        "blue_dim": "#458588", "purple_dim": "#b16286", "aqua_dim": "#689d6a",
        "orange_dim": "#d65d0e",
        "accent": "#fabd2f", "accent_alt": "#83a598", "accent_hover": "#ffd966",
        "highlight": "#458588", "border": "#504945", "border_focus": "#fabd2f",
        "status_bar": "#1d2021", "tab_active_bar": "#fabd2f",
        "scrollbar": "#504945", "scrollbar_hover": "#665c54",
        "chat_user_bubble": "#458588", "chat_ai_label": "#d3869b",
        "ghost_text": "#7c6f64", "error": "#fb4934", "warning": "#fabd2f",
        "success": "#b8bb26", "added_line": "#b8bb26", "modified_line": "#fabd2f",
        "is_dark": True,
    }
    DEFAULT_THEME = "default"


# ─────────────────────────────────────────────────────────────────────────────
# Theme Access
# ─────────────────────────────────────────────────────────────────────────────

def get_theme(name: str = None) -> dict:
    return THEMES.get(name or _current_theme_name, THEMES[DEFAULT_THEME])

def theme_names() -> list:
    return [(k, v["name"]) for k, v in THEMES.items()]

def get(key: str, theme_name: str = None) -> str:
    return get_theme(theme_name).get(key, "#ff00ff")


# ─────────────────────────────────────────────────────────────────────────────
# Helper — text color that contrasts well on a given bg
# ─────────────────────────────────────────────────────────────────────────────

def _contrast_text(t: dict) -> str:
    """Return fg0 for dark themes, bg0_hard for light themes."""
    return t.get("fg0", "#ffffff") if t.get("is_dark", True) else t.get("bg0_hard", "#1d2021")


# ─────────────────────────────────────────────────────────────────────────────
# Stylesheet Builders
# ─────────────────────────────────────────────────────────────────────────────

def build_app_stylesheet(t: dict) -> str:
    ct = _contrast_text(t)
    return f"""
        QWidget {{
            background-color: {t['bg0']};
            color: {t['fg1']};
            font-family: {FONT_UI};
        }}

        /* ── Splitters ── */
        QSplitter::handle {{
            background-color: {t['border']};
        }}
        QSplitter::handle:horizontal {{ width: 1px; }}
        QSplitter::handle:vertical   {{ height: 1px; }}
        QSplitter::handle:hover      {{ background-color: {t['accent']}; }}

        /* ── Scrollbars ── */
        QScrollBar:vertical {{
            border: none; background: transparent;
            width: 8px; margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: {t['scrollbar']};
            min-height: 30px; border-radius: 4px;
        }}
        QScrollBar::handle:vertical:hover {{ background: {t['scrollbar_hover']}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
        QScrollBar:horizontal {{
            border: none; background: transparent;
            height: 8px; margin: 0;
        }}
        QScrollBar::handle:horizontal {{
            background: {t['scrollbar']};
            min-width: 30px; border-radius: 4px;
        }}
        QScrollBar::handle:horizontal:hover {{ background: {t['scrollbar_hover']}; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}

        /* ── Inputs ── */
        QLineEdit, QTextEdit {{
            background-color: {t['bg1']};
            border: 1px solid {t['border']};
            border-radius: 5px;
            padding: 5px 8px;
            color: {t['fg1']};
            selection-background-color: {t['highlight']};
            font-family: {FONT_UI};
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
            color: {ct};
            border: none; border-radius: 5px;
            padding: 6px 14px;
            font-weight: 600;
            font-family: {FONT_UI};
        }}
        QPushButton:hover  {{ background-color: {t['accent_hover']}; }}
        QPushButton:pressed {{ background-color: {t['border_focus']}; }}
        QPushButton:disabled {{
            background-color: {t['bg2']};
            color: {t['fg4']};
        }}

        /* ── Menus ── */
        QMenu {{
            background-color: {t['bg1']};
            color: {t['fg1']};
            border: 1px solid {t['border']};
            border-radius: 6px;
            padding: 4px 0;
            font-family: {FONT_UI};
            font-size: 10pt;
        }}
        QMenu::item {{
            padding: 6px 24px 6px 14px;
            border-radius: 3px;
            margin: 1px 4px;
        }}
        QMenu::item:selected {{
            background-color: {t['bg2']};
            color: {t['fg0']};
        }}
        QMenu::item:disabled {{ color: {t['fg4']}; }}
        QMenu::separator {{
            height: 1px;
            background-color: {t['border']};
            margin: 4px 8px;
        }}
        QMenu::indicator {{
            width: 14px; height: 14px;
            left: 6px;
        }}
        QMenu::indicator:checked {{
            background-color: {t['accent']};
            border-radius: 3px;
        }}

        /* ── Menu Bar ── */
        QMenuBar {{
            background-color: {t['bg0']};
            color: {t['fg2']};
            font-family: {FONT_UI};
            font-size: 10pt;
            border-bottom: 1px solid {t['border']};
            padding: 2px 0;
        }}
        QMenuBar::item {{
            padding: 4px 10px;
            border-radius: 4px;
        }}
        QMenuBar::item:selected {{
            background-color: {t['bg2']};
            color: {t['fg0']};
        }}

        /* ── Tab Widget ── */
        QTabWidget::pane {{
            border: none;
            background-color: {t['bg0_hard']};
        }}
        QTabBar::tab {{
            background-color: {t['bg0']};
            color: {t['fg4']};
            padding: 7px 16px;
            border-right: 1px solid {t['border']};
            border-bottom: 2px solid transparent;
            font-family: {FONT_UI};
            font-size: 9.5pt;
        }}
        QTabBar::tab:selected {{
            background-color: {t['bg0_hard']};
            color: {t['fg0']};
            border-bottom: 2px solid {t['tab_active_bar']};
        }}
        QTabBar::tab:hover:!selected {{
            background-color: {t['bg1']};
            color: {t['fg2']};
        }}

        /* ── Dock Widgets ── */
        QDockWidget {{
            color: {t['fg2']};
            font-family: {FONT_UI};
            font-weight: 600;
            font-size: 9.5pt;
            titlebar-close-icon: none;
            titlebar-normal-icon: none;
        }}
        QDockWidget::title {{
            background-color: {t['bg0']};
            text-align: left;
            padding: 6px 10px;
            border-bottom: 1px solid {t['border']};
        }}
        QDockWidget::close-button, QDockWidget::float-button {{
            background: transparent;
            border: none;
            padding: 2px;
        }}
        QDockWidget::close-button:hover, QDockWidget::float-button:hover {{
            background-color: {t['bg2']};
            border-radius: 3px;
        }}

        /* ── Tooltips ── */
        QToolTip {{
            background-color: {t['bg0_hard']};
            color: {t['fg1']};
            border: 1px solid {t['border_focus']};
            border-radius: 4px;
            padding: 4px 8px;
            font-family: {FONT_UI};
            font-size: 9pt;
        }}

        /* ── Combo Box ── */
        QComboBox {{
            background-color: {t['bg1']};
            color: {t['fg1']};
            border: 1px solid {t['border']};
            border-radius: 5px;
            padding: 5px 10px;
            font-family: {FONT_UI};
        }}
        QComboBox:focus {{ border: 1px solid {t['border_focus']}; }}
        QComboBox::drop-down {{ border: none; width: 20px; }}
        QComboBox QAbstractItemView {{
            background-color: {t['bg1']};
            color: {t['fg1']};
            selection-background-color: {t['highlight']};
            border: 1px solid {t['border']};
            border-radius: 4px;
        }}

        /* ── Progress Bar ── */
        QProgressBar {{
            background-color: {t['bg2']};
            border: none; border-radius: 4px;
            max-height: 6px;
        }}
        QProgressBar::chunk {{
            background-color: {t['accent']};
            border-radius: 4px;
        }}

        /* ── Check Box ── */
        QCheckBox {{ color: {t['fg1']}; spacing: 8px; font-family: {FONT_UI}; }}
        QCheckBox::indicator {{
            width: 15px; height: 15px;
            border-radius: 4px;
            border: 1px solid {t['border']};
            background-color: {t['bg1']};
        }}
        QCheckBox::indicator:checked {{
            background-color: {t['accent']};
            border-color: {t['accent']};
            image: none;
        }}
        QCheckBox::indicator:hover {{
            border-color: {t['border_focus']};
        }}

        /* ── Group Box ── */
        QGroupBox {{
            color: {t['fg4']};
            font-size: 9pt; font-weight: 600;
            border: 1px solid {t['border']};
            border-radius: 6px;
            margin-top: 10px; padding-top: 10px;
            font-family: {FONT_UI};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 6px; left: 10px;
        }}
    """


def build_status_bar_stylesheet(t: dict) -> str:
    ct = _contrast_text(t)
    sep_color = "rgba(255,255,255,0.2)" if t.get("is_dark", True) else "rgba(0,0,0,0.2)"
    return f"""
        QStatusBar {{
            background-color: {t['status_bar']};
            color: {ct};
            font-family: {FONT_UI};
            font-size: 9pt;
            border-top: 1px solid {t['border']};
        }}
        QStatusBar::item {{ border: none; background: transparent; }}
        QStatusBar QLabel {{
            color: {ct};
            background: transparent;
            padding: 0 8px; font-size: 9pt;
        }}
        QStatusBar QPushButton {{
            color: {ct};
            background: transparent; border: none;
            padding: 0 8px; font-size: 9pt; font-weight: 600;
            border-radius: 3px;
        }}
        QStatusBar QPushButton:hover {{
            background-color: {sep_color};
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
            font-family: {FONT_CODE};
        }}
        QScrollBar:vertical {{
            border: none; background: transparent;
            width: 8px; margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: {t['scrollbar']};
            min-height: 30px; border-radius: 4px;
        }}
        QScrollBar::handle:vertical:hover {{ background: {t['scrollbar_hover']}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
        QScrollBar:horizontal {{
            border: none; background: transparent;
            height: 8px; margin: 0;
        }}
        QScrollBar::handle:horizontal {{
            background: {t['scrollbar']};
            min-width: 30px; border-radius: 4px;
        }}
        QScrollBar::handle:horizontal:hover {{ background: {t['scrollbar_hover']}; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}
    """


def build_dialog_stylesheet(t: dict) -> str:
    ct = _contrast_text(t)
    return f"""
        QDialog {{
            background-color: {t['bg1']};
            color: {t['fg1']};
            font-family: {FONT_UI};
        }}
        QPushButton {{
            background-color: {t['bg2']};
            color: {t['fg1']};
            border: none; border-radius: 5px;
            padding: 6px 16px;
            font-family: {FONT_UI};
            font-weight: 600;
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
            border-radius: 5px;
            padding: 5px;
            font-family: {FONT_UI};
        }}
        QLineEdit {{
            background-color: {t['bg0_hard']};
            color: {t['fg1']};
            border: 1px solid {t['border']};
            border-radius: 5px;
            padding: 5px 8px;
            selection-background-color: {t['highlight']};
            font-family: {FONT_UI};
        }}
        QLineEdit:focus {{ border: 1px solid {t['border_focus']}; }}
        QLabel {{
            background: transparent;
            color: {t['fg1']};
            font-family: {FONT_UI};
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
            border-top: 2px solid {t['border_focus']};
            font-family: {FONT_CODE};
            font-size: 11pt;
            padding: 4px 10px;
        }}
    """


def build_color_swatch_stylesheet(hex_color: str, text_color: str) -> str:
    return f"""
        QLabel {{
            background-color: {hex_color};
            border: 1px solid rgba(0,0,0,0.3);
            border-radius: 4px;
            color: {text_color};
            font-family: {FONT_CODE};
            font-size: 8pt;
            padding: 0 4px;
        }}
    """


def build_dock_stylesheet(t: dict) -> str:
    return f"""
        QDockWidget {{
            color: {t['fg2']};
            font-family: {FONT_UI};
            font-weight: 600;
            font-size: 9.5pt;
        }}
        QDockWidget::title {{
            background-color: {t['bg0']};
            text-align: left;
            padding: 6px 10px;
            border-bottom: 1px solid {t['border']};
        }}
    """


def build_tab_widget_stylesheet(t: dict) -> str:
    return f"""
        QTabWidget::pane {{
            border: none;
            background-color: {t['bg0_hard']};
        }}
        QTabBar::tab {{
            background-color: {t['bg0']};
            color: {t['fg4']};
            padding: 7px 16px;
            border-right: 1px solid {t['border']};
            border-bottom: 2px solid transparent;
            font-family: {FONT_UI};
            font-size: 9.5pt;
        }}
        QTabBar::tab:selected {{
            background-color: {t['bg0_hard']};
            color: {t['fg0']};
            border-bottom: 2px solid {t['tab_active_bar']};
        }}
        QTabBar::tab:hover:!selected {{
            background-color: {t['bg1']};
            color: {t['fg2']};
        }}
    """


def build_output_panel_stylesheet(t: dict) -> str:
    return f"""
        QPlainTextEdit {{
            background-color: {t['bg0_hard']};
            color: {t['fg1']};
            font-family: {FONT_CODE};
            font-size: 10pt;
            border: none;
        }}
    """


def build_explain_error_btn_stylesheet(t: dict) -> str:
    return f"""
        QPushButton {{
            background-color: {t['purple']};
            color: {t['bg0_hard']};
            border: none;
            padding: 5px 12px;
            border-radius: 5px;
            font-family: {FONT_UI};
            font-weight: 600;
        }}
        QPushButton:hover {{ background-color: {t['purple_dim']}; }}
    """


def build_tree_view_stylesheet(t: dict) -> str:
    return f"""
        QTreeView {{
            background-color: {t['bg0_hard']};
            color: {t['fg1']};
            border: none;
            font-family: {FONT_UI};
            font-size: 10.5pt;
        }}
        QTreeView::item {{ padding: 4px 6px; border-radius: 4px; }}
        QTreeView::item:selected {{
            background-color: {t['bg2']};
            color: {t['fg0']};
        }}
        QTreeView::item:hover:!selected {{
            background-color: {t['bg1']};
        }}
        QTreeView::branch {{ background-color: transparent; }}
    """


def build_find_replace_stylesheet(t: dict) -> str:
    return f"""
        QWidget {{
            background-color: {t['bg1']};
            color: {t['fg1']};
            font-family: {FONT_UI};
            font-size: 10pt;
        }}
        QLineEdit {{
            background-color: {t['bg0_hard']};
            color: {t['fg0']};
            border: 1px solid {t['border']};
            border-radius: 5px;
            padding: 4px 8px;
            font-family: {FONT_UI};
        }}
        QLineEdit:focus {{ border: 1px solid {t['border_focus']}; }}
        QLineEdit[state="match"] {{
            border: 1px solid {t['green']};
        }}
        QLineEdit[state="no_match"] {{
            border: 1px solid {t['red']};
        }}
        QPushButton {{
            background-color: {t['bg2']};
            color: {t['fg1']};
            border-radius: 5px;
            padding: 4px 12px;
            border: none;
            font-family: {FONT_UI};
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
            border-radius: 5px;
        }}
        QCheckBox {{ color: {t['fg2']}; spacing: 4px; font-family: {FONT_UI}; }}
    """


def build_match_label_stylesheet(t: dict, state: str) -> str:
    color = t['green'] if state == 'match' else t['red'] if state == 'no_match' else t['fg4']
    return (
        f"QPushButton {{ color: {color}; background: transparent; "
        f"border: none; padding: 0 4px; min-width: 60px; font-family: {FONT_UI}; }}"
    )


def build_symbol_outline_stylesheet(t: dict) -> str:
    bg     = t.get("bg0_hard", "#1d2021")
    bg1    = t.get("bg0",      "#282828")
    bg2    = t.get("bg2",      "#504945")
    fg     = t.get("fg1",      "#ebdbb2")
    fg_dim = t.get("fg4",      "#a89984")
    border = t.get("border",   "#504945")

    return f"""
        QWidget#outlineContainer {{ background-color: {bg}; }}
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
        QPushButton#outlineRefreshBtn:hover {{ color: {fg}; }}
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
        QTreeWidget#outlineTree::item:hover:!selected {{ background-color: {bg1}; }}
        QTreeWidget#outlineTree::branch {{ background: transparent; border: none; }}
    """


def build_completion_popup_stylesheet(t: dict) -> str:
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
            border-radius: 5px;
        }}
        QListWidget {{
            background-color: {bg};
            color: {fg};
            border: none; outline: none;
            font-family: {FONT_CODE};
            font-size: 9pt;
        }}
        QListWidget::item {{ padding: 2px 8px; border: none; }}
        QListWidget::item:selected {{ background-color: {sel}; color: {fg}; }}
        QListWidget::item:hover {{ background-color: {bg2}; }}
        QFrame#detailBar {{
            background-color: {bg_hard};
            border-top: 1px solid {border};
        }}
        QLabel#detailLabel {{
            color: {blue};
            font-family: {FONT_CODE};
            font-size: 8pt; font-weight: 600;
            background: transparent;
        }}
        QLabel#docLabel {{
            color: {fg_dim};
            font-family: {FONT_UI};
            font-size: 8pt;
            background: transparent;
        }}
        QScrollBar:vertical {{
            background: {bg}; width: 5px; border: none;
        }}
        QScrollBar::handle:vertical {{
            background: {sel}; border-radius: 2px; min-height: 20px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    """


def build_rename_dialog_stylesheet(t: dict) -> str:
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
        QLineEdit#renameInput:focus {{ border: 1px solid {t['border_focus']}; }}
    """


def build_hover_popup_stylesheet(t: dict) -> str:
    return f"""
        QWidget#hoverPopup {{
            background-color: {t['bg1']};
            border: 1px solid {t['border_focus']};
            border-radius: 6px;
        }}
        QLabel {{
            color: {t['fg1']};
            font-family: {FONT_UI};
            font-size: 10pt;
            background: transparent;
            padding: 6px 10px;
        }}
    """


def build_command_palette_stylesheet(t: dict) -> str:
    return f"""
        QDialog {{ background-color: transparent; }}
        QWidget#paletteFrame {{
            background-color: {t['bg1']};
            border: 1px solid {t['border_focus']};
            border-radius: 10px;
        }}
        QLineEdit {{
            background-color: {t['bg0_hard']};
            color: {t['fg0']};
            border: none;
            border-bottom: 1px solid {t['border']};
            border-radius: 10px 10px 0 0;
            padding: 12px 16px;
            font-family: {FONT_UI};
            font-size: 11pt;
        }}
        QLineEdit:focus {{ border-bottom: 1px solid {t['border_focus']}; }}
        QListWidget {{
            background-color: {t['bg1']};
            color: {t['fg1']};
            border: none;
            border-radius: 0 0 10px 10px;
            outline: none;
            font-family: {FONT_UI};
            font-size: 10pt;
            padding: 4px;
        }}
        QListWidget::item {{
            padding: 6px 12px;
            border-radius: 5px;
            margin: 1px 2px;
        }}
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
    return f"""
        QWidget#terminalContainer {{ background-color: {t['bg0_hard']}; }}
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


def build_menu_stylesheet(t: dict) -> str:
    return f"""
        QMenu {{
            background-color: {t['bg1']};
            color: {t['fg1']};
            border: 1px solid {t['border']};
            border-radius: 6px;
            padding: 4px 0;
            font-family: {FONT_UI};
            font-size: 10pt;
        }}
        QMenu::item {{
            padding: 6px 24px 6px 14px;
            border-radius: 3px;
            margin: 1px 4px;
        }}
        QMenu::item:selected {{
            background-color: {t['bg2']};
            color: {t['fg0']};
        }}
        QMenu::item:disabled {{ color: {t['fg4']}; }}
        QMenu::separator {{
            height: 1px;
            background-color: {t['border']};
            margin: 4px 8px;
        }}
    """


def build_file_dialog_stylesheet(t: dict) -> str:
    return f"""
        QFileDialog, QMessageBox {{
            background-color: {t['bg0']};
            color: {t['fg1']};
            font-family: {FONT_UI};
        }}
        QWidget {{
            background-color: {t['bg0']};
            color: {t['fg1']};
            font-family: {FONT_UI};
        }}
        QLineEdit, QTreeView, QListView {{
            background-color: {t['bg1']};
            border: 1px solid {t['border']};
            border-radius: 5px;
            color: {t['fg1']};
            padding: 2px;
        }}
        QPushButton {{
            background-color: {t['accent']};
            color: {t['bg0_hard']};
            border: none;
            padding: 6px 14px;
            border-radius: 5px;
            font-weight: 600;
        }}
        QPushButton:hover {{ background-color: {t['accent_hover']}; }}
    """


def build_markdown_browser_stylesheet(t: dict) -> str:
    return f"""
        QTextBrowser {{
            background-color: {t['bg0_hard']};
            color: {t['fg1']};
            border: none;
            font-family: {FONT_UI};
            font-size: 11pt;
            padding: 16px;
            line-height: 1.7;
        }}
    """


def build_sliding_panel_stylesheet(t: dict) -> str:
    return f"""
        QWidget#slidingPanel {{
            background-color: {t['bg1']};
            border-left: 1px solid {t['border']};
        }}
    """


def build_sliding_panel_parts(t: dict) -> dict:
    return {
        "arrow_label": f"color: {t['fg4']}; font-size: 11pt; background: transparent;",
        "content": f"background-color: {t['bg1']};",
        "tab_bar": (
            f"background-color: {t['bg0_hard']}; border-bottom: 1px solid {t['border']};"
        ),
        "tab_btn": f"""
            QPushButton {{
                background: transparent;
                color: {t['fg4']};
                border: none;
                border-bottom: 2px solid transparent;
                padding: 6px 14px;
                font-family: {FONT_UI};
                font-size: 9pt;
                font-weight: 600;
            }}
            QPushButton:checked {{
                color: {t['fg0']};
                border-bottom: 2px solid {t['tab_active_bar']};
            }}
            QPushButton:hover:!checked {{ color: {t['fg2']}; }}
        """,
        "pin_btn": f"""
            QPushButton {{
                background: transparent; color: {t['fg4']};
                border: none; font-size: 12pt; padding: 0;
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
                font-family: {FONT_UI};
            }}
        """,
        "chat_input": f"""
            QTextEdit {{
                background-color: {t['bg1']};
                color: {t['fg0']};
                border: 1px solid {t['border']};
                border-radius: 6px;
                padding: 8px;
                font-family: {FONT_UI};
                font-size: 10pt;
            }}
            QTextEdit:focus {{ border: 1px solid {t['border_focus']}; }}
        """,
        "send_btn": f"""
            QPushButton {{
                background-color: {t['accent']};
                color: {t['bg0_hard']};
                border: none; border-radius: 6px;
                font-size: 14pt;
            }}
            QPushButton:hover {{ background-color: {t['accent_hover']}; }}
        """,
        "resize_grip_hover": f"background-color: {t['accent']};",
    }


def build_git_panel_stylesheet(t: dict) -> str:
    return f"""
        QDockWidget {{
            color: {t['fg2']};
            font-family: {FONT_UI};
            font-weight: 600;
            font-size: 9.5pt;
        }}
        QDockWidget::title {{
            background-color: {t['bg0']};
            padding: 6px 10px;
            border-bottom: 1px solid {t['border']};
        }}
    """


def build_git_panel_parts(t: dict) -> dict:
    icon_btn = f"""
        QPushButton {{
            background-color: {t['bg1']};
            color: {t['fg2']};
            border: 1px solid {t['border']};
            border-radius: 5px;
            padding: 4px 8px;
            font-size: 9pt;
            font-family: {FONT_UI};
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
                border-radius: 5px;
                padding: 4px 10px;
                font-size: 9pt; font-weight: 600;
                font-family: {FONT_UI};
            }}
            QComboBox:hover {{ border-color: {t['border_focus']}; }}
            QComboBox::drop-down {{ border: none; width: 18px; }}
            QComboBox QAbstractItemView {{
                background-color: {t['bg1']};
                color: {t['fg1']};
                selection-background-color: {t['highlight']};
                border: 1px solid {t['border']};
                border-radius: 4px;
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
            QTreeWidget::item:selected {{ background-color: {t['bg2']}; color: {t['fg0']}; }}
            QTreeWidget::item:hover:!selected {{ background-color: {t['bg1']}; }}
            QTreeWidget::branch {{ background-color: transparent; }}
            QTreeWidget::indicator:unchecked {{
                border: 1px solid {t['border']};
                background-color: {t['bg0_hard']};
                border-radius: 3px; width: 12px; height: 12px;
            }}
            QTreeWidget::indicator:checked {{
                background-color: {t['accent']};
                border: 1px solid {t['accent']};
                border-radius: 3px; width: 12px; height: 12px;
            }}
        """,
        "section_label": f"""
            QLabel {{
                color: {t['fg4']};
                font-family: {FONT_UI};
                font-size: 8pt; font-weight: 600;
                padding: 4px 4px 2px 4px;
                letter-spacing: 0.05em;
                text-transform: uppercase;
            }}
        """,
        "commit_input": f"""
            QLineEdit {{
                background-color: {t['bg0_hard']};
                color: {t['fg1']};
                border: 1px solid {t['border']};
                border-radius: 5px 5px 0 0;
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
                font-family: {FONT_UI};
            }}
            QPushButton:hover {{ background-color: {t['bg2']}; color: {t['fg0']}; }}
            QPushButton:disabled {{ color: {t['fg4']}; }}
        """,
        "commit_btn": f"""
            QPushButton {{
                background-color: {t['blue_dim']};
                color: {t['fg0']};
                border: 1px solid {t['border']};
                border-top: none; border-left: none;
                border-radius: 0 0 5px 0;
                padding: 5px 10px;
                font-size: 9pt; font-weight: 600;
                font-family: {FONT_UI};
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
                font-family: {FONT_UI};
            }}
            QPushButton:hover {{ color: {t['fg1']}; background-color: {t['bg1']}; }}
            QPushButton:checked {{ color: {t['accent']}; }}
        """,
        "context_menu": f"""
            QMenu {{
                background-color: {t['bg1']};
                color: {t['fg1']};
                border: 1px solid {t['border']};
                border-radius: 6px;
                padding: 4px 0;
            }}
            QMenu::item {{ padding: 6px 20px; border-radius: 3px; margin: 1px 4px; }}
            QMenu::item:selected {{ background-color: {t['highlight']}; color: {t['fg0']}; }}
        """,
        "status_modified":    t['yellow'],
        "status_modified_bg": t['yellow_dim'],
        "status_added":       t['green'],
        "status_added_bg":    t['green_dim'],
        "status_deleted":     t['red'],
        "status_deleted_bg":  t['red_dim'],
        "status_default":     t['fg1'],
        "bg0_hard":   t['bg0_hard'],
        "bg1":        t['bg1'],
        "border":     t['border'],
        "accent":     t['accent'],
        "fg1":        t['fg1'],
        "fg4":        t['fg4'],
    }


def build_diff_apply_dialog_stylesheet(t: dict) -> str:
    return f"""
        QDialog {{ background-color: {t['bg0']}; color: {t['fg1']}; }}
        QLabel {{
            color: {t['fg4']};
            font-family: {FONT_UI};
            font-size: 9pt;
            padding: 4px 8px;
            background-color: {t['bg1']};
        }}
        QPushButton {{
            border-radius: 5px;
            padding: 6px 20px;
            font-weight: 600;
            font-family: {FONT_UI};
            border: none;
        }}
    """


def build_diff_apply_parts(t: dict) -> dict:
    return {
        "splitter_handle": f"QSplitter::handle {{ background-color: {t['border']}; }}",
        "left_label":  f"background-color: {t['bg1']}; color: {t['red']}; font-weight: bold;",
        "right_label": f"background-color: {t['bg1']}; color: {t['green']}; font-weight: bold;",
        "text_view": f"""
            QTextEdit {{
                background-color: {t['bg0_hard']};
                color: {t['fg1']};
                border: none; padding: 8px;
                font-family: {FONT_CODE};
            }}
        """,
        "hint": f"color: {t['fg4']}; font-size: 9pt; background: transparent; font-family: {FONT_UI};",
        "discard_btn": f"""
            QPushButton {{
                background-color: {t['bg2']}; color: {t['fg1']};
            }}
            QPushButton:hover {{ background-color: {t['red']}; color: {t['bg0_hard']}; }}
        """,
        "accept_btn": f"""
            QPushButton {{
                background-color: {t['accent']}; color: {t['bg0_hard']};
            }}
            QPushButton:hover {{ background-color: {t['accent_hover']}; }}
        """,
        "diff_removed": t['red'],
        "diff_added":   t['green'],
        "diff_neutral": t['fg1'],
    }


def build_memory_panel_stylesheet(t: dict) -> str:
    return f"background-color: {t['bg1']};"


def build_memory_panel_parts(t: dict) -> dict:
    list_style = f"""
        QListWidget {{
            background-color: {t['bg0_hard']};
            color: {t['fg1']};
            border: 1px solid {t['border']};
            border-radius: 5px;
            font-size: 9pt;
            font-family: {FONT_UI};
        }}
        QListWidget::item {{ padding: 4px 8px; }}
        QListWidget::item:selected {{ background-color: {t['bg2']}; color: {t['fg0']}; }}
        QListWidget::item:hover:!selected {{ background-color: {t['bg1']}; }}
    """
    input_style = f"""
        QLineEdit {{
            background-color: {t['bg0_hard']};
            color: {t['fg0']};
            border: 1px solid {t['border']};
            border-radius: 5px;
            padding: 4px 8px;
            font-size: 9pt;
            font-family: {FONT_UI};
        }}
        QLineEdit:focus {{ border: 1px solid {t['border_focus']}; }}
    """
    return {
        "label":     f"color: {t['fg4']}; font-size: 9pt; font-weight: 600; font-family: {FONT_UI};",
        "facts_tabs": f"""
            QTabWidget::pane {{ border: 1px solid {t['border']}; background: {t['bg0_hard']}; }}
            QTabBar::tab {{
                background: {t['bg1']}; color: {t['fg4']};
                padding: 4px 10px; font-size: 9pt; font-family: {FONT_UI};
            }}
            QTabBar::tab:selected {{
                background: {t['bg0_hard']}; color: {t['fg0']};
                border-top: 2px solid {t['tab_active_bar']};
            }}
        """,
        "list": list_style,
        "conv_list": f"""
            QListWidget {{
                background-color: {t['bg0_hard']}; color: {t['fg1']};
                border: 1px solid {t['border']}; border-radius: 5px;
                font-size: 9pt; font-family: {FONT_UI};
            }}
            QListWidget::item {{ padding: 6px 8px; border-bottom: 1px solid {t['bg1']}; }}
            QListWidget::item:selected {{ background-color: {t['bg2']}; color: {t['fg0']}; }}
            QListWidget::item:hover:!selected {{ background-color: {t['bg1']}; }}
        """,
        "input":       input_style,
        "scope_check": f"color: {t['fg4']}; font-size: 9pt; font-family: {FONT_UI};",
        "add_btn": f"""
            QPushButton {{
                background-color: {t['accent']}; color: {t['bg0_hard']};
                border: none; border-radius: 5px; font-weight: 600;
            }}
            QPushButton:hover {{ background-color: {t['accent_hover']}; }}
        """,
        "del_btn": f"""
            QPushButton {{
                background-color: {t['bg2']}; color: {t['fg1']};
                border: none; border-radius: 5px;
            }}
            QPushButton:hover {{ background-color: {t['red']}; color: {t['bg0_hard']}; }}
        """,
        "clear_btn": f"""
            QPushButton {{
                background-color: {t['bg2']}; color: {t['fg1']};
                border: none; border-radius: 5px;
                padding: 4px 10px; font-size: 9pt;
            }}
            QPushButton:hover {{ background-color: {t['bg3']}; }}
        """,
        "clear_all_btn": f"""
            QPushButton {{
                background-color: {t['bg2']}; color: {t['fg1']};
                border: none; border-radius: 5px;
                padding: 4px 10px; font-size: 9pt;
            }}
            QPushButton:hover {{ background-color: {t['red']}; color: {t['bg0_hard']}; }}
        """,
        "conv_item_fg": t['fg3'],
    }


def build_settings_dialog_stylesheet(t: dict) -> str:
    ct = _contrast_text(t)
    return f"""
        QDialog {{ background-color: {t['bg1']}; color: {t['fg1']}; font-family: {FONT_UI}; }}
        QLabel {{ color: {t['fg2']}; font-size: 9pt; background: transparent; font-family: {FONT_UI}; }}
        QGroupBox {{
            color: {t['fg4']}; font-weight: 600; font-size: 9pt;
            border: 1px solid {t['border']}; border-radius: 6px;
            margin-top: 12px; padding: 10px;
            background-color: {t['bg1']};
            font-family: {FONT_UI};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin; subcontrol-position: top left;
            padding: 0 6px; left: 10px; color: {t['fg4']};
        }}
        QLineEdit {{
            background-color: {t['bg0_hard']}; color: {t['fg0']};
            border: 1px solid {t['border']}; border-radius: 5px;
            padding: 6px 10px; font-family: {FONT_CODE}; font-size: 10pt;
        }}
        QLineEdit:focus {{ border: 1px solid {t['border_focus']}; }}
        QComboBox {{
            background-color: {t['bg0_hard']}; color: {t['fg0']};
            border: 1px solid {t['border']}; border-radius: 5px;
            padding: 6px 10px; font-size: 10pt; font-family: {FONT_UI};
        }}
        QComboBox:focus {{ border: 1px solid {t['border_focus']}; }}
        QComboBox::drop-down {{ border: none; }}
        QComboBox QAbstractItemView {{
            background-color: {t['bg1']}; color: {t['fg1']};
            selection-background-color: {t['highlight']};
            border: 1px solid {t['border']}; border-radius: 4px;
        }}
        QPushButton#saveBtn {{
            background-color: {t['accent']}; color: {ct};
            border: none; border-radius: 5px;
            padding: 6px 18px; font-weight: 600;
        }}
        QPushButton#saveBtn:hover {{ background-color: {t['accent_hover']}; }}
        QPushButton {{
            background-color: {t['bg2']}; color: {t['fg1']};
            border: 1px solid {t['border']}; border-radius: 5px;
            padding: 6px 14px;
            font-family: {FONT_UI};
        }}
        QPushButton:hover {{ background-color: {t['bg3']}; border-color: {t['border_focus']}; }}
        QPushButton#cancelBtn {{
            background-color: transparent; color: {t['fg4']};
            border: none; padding: 6px 10px;
        }}
        QPushButton#cancelBtn:hover {{ color: {t['fg2']}; }}
        QCheckBox {{ color: {t['fg1']}; spacing: 8px; font-family: {FONT_UI}; }}
        QCheckBox::indicator {{
            width: 14px; height: 14px; border-radius: 4px;
            border: 1px solid {t['border']}; background-color: {t['bg0_hard']};
        }}
        QCheckBox::indicator:checked {{
            background-color: {t['accent']}; border-color: {t['accent']};
        }}
    """


def build_hint_label_stylesheet(t: dict) -> str:
    return f"color: {t['fg4']}; font-size: 9pt; font-family: {FONT_UI};"


def build_about_dialog_stylesheet(t: dict) -> str:
    ct = _contrast_text(t)
    return f"""
        QDialog {{ background-color: {t['bg0']}; color: {t['fg1']}; }}
        QLabel {{ color: {t['fg1']}; background: transparent; font-family: {FONT_UI}; }}
        QPushButton {{
            background-color: {t['accent']}; color: {ct};
            border: none; border-radius: 5px;
            padding: 8px 20px; font-size: 10pt; font-weight: 600;
            font-family: {FONT_UI};
        }}
        QPushButton:hover {{ background-color: {t['accent_hover']}; }}
        QPushButton#close {{ background-color: {t['bg2']}; color: {t['fg1']}; }}
        QPushButton#close:hover {{ background-color: {t['bg3']}; }}
        QFrame#divider {{ background-color: {t['border']}; }}
    """


def build_about_dialog_parts(t: dict) -> dict:
    ct = _contrast_text(t)
    return {
        "header":        f"background-color: {t['bg0_hard']};",
        "logo_fallback": f"font-size: 64pt; color: {t['blue']};",
        "name_label":    f"color: {t['fg0']}; font-size: 20pt; font-family: {FONT_UI};",
        "version_label": f"color: {t['fg4']}; font-size: 10pt; font-family: {FONT_UI};",
        "desc_label":    f"color: {t['fg2']}; font-size: 10pt; font-family: {FONT_UI};",
        "content":       f"background-color: {t['bg0']};",
        "deps_title":    f"color: {t['blue']}; font-size: 10pt; font-weight: bold; font-family: {FONT_UI};",
        "deps_scroll": f"""
            QScrollArea {{
                background-color: {t['bg1']};
                border: 1px solid {t['border']}; border-radius: 6px;
            }}
            QScrollArea > QWidget > QWidget {{ background-color: {t['bg1']}; }}
            QScrollBar:vertical {{
                border: none; background: {t['bg1']}; width: 6px; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {t['scrollbar']}; min-height: 20px; border-radius: 3px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {t['scrollbar_hover']}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """,
        "deps_widget":  f"background-color: {t['bg1']};",
        "dep_name":     f"color: {t['fg1']}; font-size: 11pt; font-family: {FONT_UI};",
        "dep_ok":       f"color: {t['green']}; font-size: 11pt; font-family: {FONT_UI};",
        "dep_missing":  f"color: {t['red']}; font-size: 11pt; font-family: {FONT_UI};",
        "github_btn": f"""
            QPushButton {{
                background-color: {t['bg1']}; color: {t['aqua']};
                border: 1px solid {t['border']}; border-radius: 5px;
                padding: 10px 16px; font-size: 10pt; font-family: {FONT_UI};
            }}
            QPushButton:hover {{ background-color: {t['bg2']}; border-color: {t['aqua']}; }}
        """,
    }


def build_new_project_dialog_stylesheet(t: dict) -> str:
    ct = _contrast_text(t)
    return f"""
        QDialog {{ background-color: {t['bg0']}; color: {t['fg1']}; font-family: {FONT_UI}; }}
        QLabel {{ color: {t['fg1']}; font-size: 10pt; font-family: {FONT_UI}; }}
        QLineEdit {{
            background-color: {t['bg1']}; color: {t['fg0']};
            border: 1px solid {t['border']}; border-radius: 5px;
            padding: 6px 10px; font-size: 10pt; font-family: {FONT_UI};
        }}
        QLineEdit:focus {{ border: 1px solid {t['border_focus']}; }}
        QComboBox {{
            background-color: {t['bg1']}; color: {t['fg0']};
            border: 1px solid {t['border']}; border-radius: 5px;
            padding: 6px 10px; font-size: 10pt; font-family: {FONT_UI};
        }}
        QComboBox::drop-down {{ border: none; }}
        QComboBox QAbstractItemView {{
            background-color: {t['bg1']}; color: {t['fg0']};
            selection-background-color: {t['highlight']};
            border: 1px solid {t['border']}; border-radius: 4px;
        }}
        QPushButton {{
            background-color: {t['accent']}; color: {ct};
            border: none; border-radius: 5px;
            padding: 8px 18px; font-size: 10pt; font-weight: 600;
            font-family: {FONT_UI};
        }}
        QPushButton:hover {{ background-color: {t['accent_hover']}; }}
        QPushButton#cancel {{ background-color: {t['bg2']}; color: {t['fg1']}; }}
        QPushButton#cancel:hover {{ background-color: {t['bg3']}; }}
        QCheckBox {{ color: {t['fg1']}; font-size: 10pt; spacing: 8px; font-family: {FONT_UI}; }}
        QCheckBox::indicator {{
            width: 15px; height: 15px; border-radius: 4px;
            border: 1px solid {t['border']}; background-color: {t['bg1']};
        }}
        QCheckBox::indicator:checked {{ background-color: {t['accent']}; border-color: {t['accent']}; }}
        QGroupBox {{
            color: {t['fg4']}; font-size: 9pt; font-weight: 600;
            border: 1px solid {t['border']}; border-radius: 6px;
            margin-top: 8px; padding-top: 8px; font-family: {FONT_UI};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin; subcontrol-position: top left;
            padding: 0 6px; left: 10px;
        }}
    """


def build_snippet_palette_stylesheet(t: dict) -> str:
    return f"""
        QDialog {{ background-color: transparent; }}
        QWidget#snippetFrame {{
            background-color: {t['bg1']};
            border: 1px solid {t['border_focus']};
            border-radius: 10px;
        }}
        QLineEdit {{
            background-color: {t['bg0_hard']}; color: {t['fg0']};
            border: none; border-bottom: 1px solid {t['border']};
            border-radius: 10px 10px 0 0;
            padding: 10px 14px; font-family: {FONT_UI}; font-size: 11pt;
        }}
        QLineEdit:focus {{ border-bottom: 1px solid {t['border_focus']}; }}
        QListWidget {{
            background-color: {t['bg1']}; color: {t['fg1']};
            border: none; outline: none;
            font-family: {FONT_UI}; font-size: 10pt;
        }}
        QListWidget::item {{ padding: 5px 12px; border-radius: 4px; margin: 1px 4px; }}
        QListWidget::item:selected {{ background-color: {t['bg2']}; color: {t['fg0']}; }}
        QListWidget::item:hover:!selected {{ background-color: {t['bg1']}; }}
        QPlainTextEdit {{
            background-color: {t['bg0_hard']}; color: {t['fg1']};
            border: none; font-family: {FONT_CODE}; font-size: 10pt; padding: 10px;
        }}
        QPushButton {{
            background-color: {t['bg1']}; color: {t['fg2']};
            border: 1px solid {t['border']}; border-radius: 5px;
            padding: 4px 14px; font-family: {FONT_UI}; font-size: 9pt;
        }}
        QPushButton:hover {{
            background-color: {t['bg2']}; color: {t['fg0']};
            border-color: {t['border_focus']};
        }}
        QLabel {{ color: {t['fg4']}; font-family: {FONT_UI}; font-size: 9pt; }}
    """


def build_snippet_palette_parts(t: dict) -> dict:
    return {
        "splitter_handle": f"QSplitter::handle {{ background-color: {t['border']}; width: 1px; }}",
        "preview_container": f"background-color: {t['bg0_hard']};",
        "preview_header": f"""
            QLabel {{
                color: {t['fg2']}; background-color: {t['bg1']};
                border-bottom: 1px solid {t['border']};
                font-family: {FONT_UI}; font-size: 9pt; padding: 5px 12px;
            }}
        """,
        "footer": f"background-color: {t['bg1']}; border-top: 1px solid {t['border']};",
        "hint":   f"color: {t['fg4']}; font-family: {FONT_UI}; font-size: 9pt; padding: 0;",
        "cancel_btn": f"""
            QPushButton {{
                background-color: {t['bg1']}; color: {t['fg2']};
                border: 1px solid {t['border']}; border-radius: 5px;
                padding: 4px 14px; font-family: {FONT_UI}; font-size: 9pt;
            }}
            QPushButton:hover {{ background-color: {t['bg2']}; color: {t['fg0']}; border-color: {t['border_focus']}; }}
        """,
        "insert_btn": f"""
            QPushButton {{
                background-color: {t['blue_dim']}; color: {t['fg0']};
                border: 1px solid {t['border']}; border-radius: 5px;
                padding: 4px 14px; font-family: {FONT_UI}; font-size: 9pt; font-weight: 600;
            }}
            QPushButton:hover {{ background-color: {t['blue']}; }}
        """,
    }


def build_find_in_files_parts(t: dict) -> dict:
    ct = _contrast_text(t)
    return {
        "search_btn": f"""
            QPushButton {{
                background-color: {t['accent']}; color: {ct};
                border: none; border-radius: 5px;
                padding: 5px 16px; font-weight: 600; font-family: {FONT_UI};
            }}
            QPushButton:hover {{ background-color: {t['accent_hover']}; }}
        """,
        "inputs": f"""
            QLineEdit {{
                background-color: {t['bg0_hard']}; color: {t['fg0']};
                border: 1px solid {t['border']}; border-radius: 5px;
                padding: 4px 8px; font-family: {FONT_UI};
            }}
            QLineEdit:focus {{ border: 1px solid {t['border_focus']}; }}
        """,
        "results_tree": f"""
            QTreeWidget {{
                background-color: {t['bg0_hard']}; color: {t['fg1']};
                border: 1px solid {t['border']}; border-radius: 5px;
                font-family: {FONT_UI};
            }}
            QTreeWidget::item {{ padding: 2px 4px; }}
            QTreeWidget::item:selected {{ background-color: {t['bg2']}; color: {t['fg0']}; }}
            QTreeWidget::item:hover:!selected {{ background-color: {t['bg1']}; }}
        """,
        "status_default": f"color: {t['fg4']}; font-family: {FONT_UI};",
        "status_found":   f"color: {t['green']}; font-family: {FONT_UI};",
        "status_empty":   f"color: {t['red']}; font-family: {FONT_UI};",
        "file_node_fg":   t['blue'],
        "line_node_fg":   t['fg1'],
    }


def build_inline_chat_stylesheet(t: dict) -> dict:
    _footer_btn = f"""
        QPushButton {{
            background-color: {t['bg1']}; color: {t['fg2']};
            border: 1px solid {t['border']}; border-radius: 5px;
            padding: 3px 10px; font-family: {FONT_UI}; font-size: 9pt;
        }}
        QPushButton:hover {{
            background-color: {t['bg2']}; color: {t['fg0']};
            border-color: {t['border_focus']};
        }}
    """
    return {
        "panel": f"""
            QWidget#inlineChat {{
                background-color: {t['bg1']};
                border: 1px solid {t['border']}; border-radius: 8px;
            }}
        """,
        "header": (
            f"background-color: {t['bg0_hard']}; "
            f"border-bottom: 1px solid {t['border']}; border-radius: 8px 8px 0 0;"
        ),
        "title_label": (
            f"color: {t['fg2']}; font-weight: 600; font-size: 9pt;"
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
        "input_container": f"background: {t['bg0_hard']};",
        "input": f"""
            QLineEdit {{
                background: transparent; border: none;
                color: {t['fg0']}; font-family: {FONT_UI}; font-size: 10pt; padding: 0;
            }}
        """,
        "send_btn": f"""
            QPushButton {{
                background-color: transparent; color: {t['fg4']};
                border: none; font-size: 10pt; padding: 0 4px;
            }}
            QPushButton:hover {{ color: {t['fg0']}; }}
        """,
        "response_area": f"""
            QTextEdit {{
                background-color: {t['bg0_hard']}; color: {t['fg1']};
                border: none; border-top: 1px solid {t['border']};
                font-family: {FONT_UI}; font-size: 10pt; padding: 8px;
            }}
        """,
        "footer": (
            f"background: {t['bg1']}; border-top: 1px solid {t['border']};"
            f" border-radius: 0 0 8px 8px;"
        ),
        "insert_btn": f"""
            QPushButton {{
                background-color: {t['blue_dim']}; color: {t['fg0']};
                border: 1px solid {t['border']}; border-radius: 5px;
                padding: 3px 10px; font-family: {FONT_UI}; font-size: 9pt; font-weight: 600;
            }}
            QPushButton:hover {{ background-color: {t['blue']}; }}
        """,
        "chat_btn":  _footer_btn,
        "clear_btn": f"""
            QPushButton {{
                background-color: transparent; color: {t['fg4']};
                border: none; padding: 3px 8px;
                font-family: {FONT_UI}; font-size: 9pt;
            }}
            QPushButton:hover {{ color: {t['fg2']}; }}
        """,
    }


def build_markdown_html_css(t: dict) -> str:
    return f"""
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background-color: {t['bg0_hard']}; color: {t['fg1']};
    font-family: 'Inter', 'Segoe UI', 'Helvetica Neue', sans-serif;
    font-size: 15px; line-height: 1.8;
    padding: 24px 32px; max-width: 860px;
  }}
  h1, h2, h3, h4, h5, h6 {{
    color: {t['fg0']}; font-weight: 600; line-height: 1.3;
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
    background-color: {t['bg2']}; color: {t['orange']};
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.9em; padding: 2px 6px; border-radius: 4px;
  }}
  pre {{
    background-color: {t['bg1']}; border: 1px solid {t['border']};
    border-radius: 8px; padding: 16px 20px; overflow-x: auto; margin: 1em 0;
  }}
  pre code {{
    background: none; color: {t['fg1']}; padding: 0;
    font-size: 0.9em; line-height: 1.6;
  }}
  blockquote {{
    border-left: 3px solid {t['blue']}; margin: 1em 0;
    padding: 8px 16px; background-color: {t['bg1']};
    border-radius: 0 6px 6px 0; color: {t['fg3']}; font-style: italic;
  }}
  ul, ol {{ padding-left: 1.5em; margin: 0.8em 0; }}
  li {{ margin: 0.3em 0; line-height: 1.7; }}
  table {{
    border-collapse: collapse; width: 100%; margin: 1em 0; font-size: 0.95em;
  }}
  th {{
    background-color: {t['bg2']}; color: {t['fg0']}; font-weight: 600;
    text-align: left; padding: 8px 12px; border: 1px solid {t['border']};
  }}
  td {{ padding: 7px 12px; border: 1px solid {t['border']}; color: {t['fg2']}; }}
  tr:nth-child(even) td {{ background-color: {t['bg1']}; }}
  tr:hover td {{ background-color: {t['bg2']}; }}
  hr {{ border: none; border-top: 1px solid {t['border']}; margin: 1.5em 0; }}
  img {{ max-width: 100%; border-radius: 6px; }}
  .admonition {{
    border-left: 4px solid {t['blue']}; background-color: {t['bg1']};
    padding: 10px 16px; border-radius: 0 6px 6px 0; margin: 1em 0;
  }}
  .admonition-title {{ font-weight: bold; color: {t['blue']}; margin-bottom: 4px; }}
  .warning {{ border-left-color: {t['yellow']}; }}
  .warning .admonition-title {{ color: {t['yellow']}; }}
  .danger, .error {{ border-left-color: {t['red']}; }}
  .danger .admonition-title, .error .admonition-title {{ color: {t['red']}; }}
  .tip, .hint {{ border-left-color: {t['green']}; }}
  .tip .admonition-title, .hint .admonition-title {{ color: {t['green']}; }}
"""


def build_chat_styles(t: dict) -> dict:
    prose_font  = f"font-family: 'Inter', system-ui, sans-serif;"
    code_font   = f"font-family: 'JetBrains Mono', monospace;"
    prose_size  = "font-size: 10.5pt;"
    code_size   = "font-size: 9.5pt;"
    prose_lh    = "line-height: 1.6;"
    code_lh     = "line-height: 1.5;"
    bg_code     = t.get("bg0_hard",   "#1d2021")
    bg_user     = t.get("bg2",        "#504945")
    fg_prose    = t.get("fg1",        "#ebdbb2")
    fg_dim      = t.get("fg4",        "#a89984")
    fg_label    = t.get("fg3",        "#bdae93")
    accent      = t.get("accent",     "#fabd2f")
    accent_dim  = t.get("yellow_dim", t.get("accent", "#fabd2f"))
    border      = t.get("border",     "#3c3836")
    border_code = t.get("bg2",        "#504945")
    bg1         = t.get("bg1",        "#3c3836")
    link_color  = t.get("blue",       "#83a598")

    return {
        "user_bubble_td": (
            f"background-color: {bg_user}; color: {fg_prose}; "
            f"padding: 9px 14px; {prose_font} {prose_size} {prose_lh}"
        ),
        "user_label_td": (
            f"color: {fg_dim}; font-size: 8pt; padding: 2px 6px 0 0; {prose_font}"
        ),
        "ai_label_td": (
            f"color: {accent_dim}; font-size: 8pt; font-weight: 600; "
            f"padding: 0 0 4px 6px; {prose_font}"
        ),
        "response_td": (
            f"color: {fg_prose}; padding: 0 8px; {prose_font} {prose_size} {prose_lh}"
        ),
        "prose_p": (
            f"margin: 0 0 8px 0; padding: 0; color: {fg_prose}; {prose_font} {prose_size} {prose_lh}"
        ),
        "ul": f"margin: 0 0 8px 0; padding: 0 0 0 20px; color: {fg_prose}; {prose_font} {prose_size}",
        "ol": f"margin: 0 0 8px 0; padding: 0 0 0 20px; color: {fg_prose}; {prose_font} {prose_size}",
        "prose_li": f"margin: 2px 0; padding: 0; color: {fg_prose}; {prose_font} {prose_size} {prose_lh}",
        "heading_1": f"margin: 12px 0 6px 0; padding: 0; color: {accent}; font-size: 13pt; font-weight: 700; {prose_font}",
        "heading_2": f"margin: 10px 0 5px 0; padding: 0; color: {accent}; font-size: 12pt; font-weight: 600; {prose_font}",
        "heading_3": f"margin: 8px 0 4px 0; padding: 0; color: {fg_label}; font-size: 11pt; font-weight: 600; {prose_font}",
        "strong":    f"color: {fg_prose}; font-weight: 700;",
        "em":        f"color: {fg_prose}; font-style: italic;",
        "hr":        f"border: none; border-top: 1px solid {border}; margin: 12px 0;",
        "inline_code": (
            f"background-color: {bg_code}; color: {t.get('orange', '#fe8019')}; "
            f"border: 1px solid {border_code}; border-radius: 3px; "
            f"padding: 1px 5px; {code_font} font-size: 9pt;"
        ),
        "code_header_td": (
            f"background-color: {bg_code}; color: {fg_dim}; "
            f"border: 1px solid {border_code}; border-bottom: 1px solid {border}; "
            f"padding: 5px 12px; {prose_font} font-size: 8.5pt;"
        ),
        "lang_label": (
            f"color: {fg_label}; font-weight: 600; font-size: 8.5pt; "
            f"{prose_font} letter-spacing: 0.04em;"
        ),
        "copy_link": f"color: {link_color}; text-decoration: none; font-size: 8.5pt; {prose_font}",
        "code_body_td": (
            f"background-color: {bg_code}; border: 1px solid {border_code}; "
            f"border-top: none; padding: 12px 14px;"
        ),
        "code_pre": (
            f"{code_font} {code_size} {code_lh} "
            f"margin: 0; padding: 0; white-space: pre; color: {fg_prose};"
        ),
        "md_table":  f"border: 1px solid {border}; margin: 4px 0 10px 0;",
        "md_th": (
            f"background-color: {bg1}; color: {fg_label}; font-weight: 600; "
            f"border-bottom: 1px solid {border}; border-right: 1px solid {border}; "
            f"padding: 6px 10px; {prose_font} {prose_size}"
        ),
        "md_td": (
            f"color: {fg_prose}; border-bottom: 1px solid {border}; "
            f"border-right: 1px solid {border}; padding: 5px 10px; {prose_font} {prose_size}"
        ),
        "md_tr": "",
        # Legacy keys
        "user_bubble": f"background-color: {bg_user}; color: {fg_prose}; padding: 9px 14px; {prose_font} {prose_size}",
        "user_row_p":  "margin: 4px 8px 2px 48px; padding: 0; text-align: right;",
        "user_label_p": f"margin: 2px 12px 12px 0; padding: 0; text-align: right; color: {fg_dim}; font-size: 8pt; {prose_font}",
        "ai_label_p": f"margin: 4px 0 6px 8px; padding: 0; color: {accent_dim}; font-size: 8pt; font-weight: 600; {prose_font}",
        "response_wrapper": f"margin: 0 8px 4px 8px; padding: 0; color: {fg_prose}; {prose_font} {prose_size} {prose_lh}",
        "code_header_span": f"background-color: {bg_code}; color: {fg_dim}; border: 1px solid {border_code}; padding: 5px 12px; {prose_font} font-size: 8.5pt;",
        "code_block": f"background-color: {bg_code}; color: {fg_prose}; border: 1px solid {border_code}; padding: 12px 14px; {code_font} {code_size} {code_lh} white-space: pre;",
        "user_label": f"color: {fg_dim}; font-size: 8pt; {prose_font}",
        "code_body_td_legacy": f"background-color: {bg_code}; border: 1px solid {border_code}; border-top: none; border-radius: 0 0 6px 6px; padding: 12px 14px;",
        "code_pre_legacy": f"{code_font} {code_size} {code_lh} margin: 0; padding: 0; white-space: pre; color: {fg_prose};",
    }


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
    theme_signals.theme_changed.emit(t)
    return t