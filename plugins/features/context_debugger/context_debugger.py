# plugins/features/context_debugger/context_debugger.py

import json
from PyQt6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTabWidget,
    QTreeWidget, QTreeWidgetItem, QPlainTextEdit
)
from PyQt6.QtCore import Qt
from ui.theme import get_theme, theme_signals, FONT_UI


class ContextDebuggerDock(QDockWidget):

    def __init__(self, parent=None):
        super().__init__("Context Debugger", parent)
        self.setObjectName("context_debugger_dock")

        self._t = get_theme()
        self._history = []
        self._current_index = -1

        self._build_ui()
        theme_signals.theme_changed.connect(self._apply_theme)

    # ─────────────────────────────────────────────────────────────
    # UI
    # ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Toolbar ──
        toolbar = QWidget()
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(6, 4, 6, 4)

        self._title = QLabel("Context Debugger")
        self._title.setStyleSheet(f"font-family: '{FONT_UI}'; font-size: 9pt;")

        self.prev_btn = QPushButton("◀")
        self.next_btn = QPushButton("▶")
        self.copy_btn = QPushButton("Copy")

        self.prev_btn.clicked.connect(self._prev)
        self.next_btn.clicked.connect(self._next)
        self.copy_btn.clicked.connect(self._copy_prompt)

        tb.addWidget(self._title)
        tb.addStretch()
        tb.addWidget(self.prev_btn)
        tb.addWidget(self.next_btn)
        tb.addWidget(self.copy_btn)

        layout.addWidget(toolbar)
        
        self.tools_view = QPlainTextEdit()
        self.tools_view.setReadOnly(True)        

        # ── Tabs ──
        self.tabs = QTabWidget()

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Key", "Value"])

        self.prompt_view = QPlainTextEdit()
        self.prompt_view.setReadOnly(True)

        self.raw_view = QPlainTextEdit()
        self.raw_view.setReadOnly(True)

        self.tabs.addTab(self.tree, "Context")
        self.tabs.addTab(self.prompt_view, "Prompt")
        self.tabs.addTab(self.raw_view, "Raw")
        self.tabs.addTab(self.tools_view, "Tools")

        layout.addWidget(self.tabs)

        self.setWidget(container)
        self._apply_theme(self._t)

    # ─────────────────────────────────────────────────────────────
    # THEME
    # ─────────────────────────────────────────────────────────────

    def _apply_theme(self, t):
        self.setStyleSheet(f"""
            QDockWidget {{
                background: {t['bg1']};
                color: {t['fg1']};
            }}
            QTreeWidget, QPlainTextEdit {{
                background: {t['bg0_hard']};
                border: 1px solid {t['border']};
                font-family: monospace;
            }}
            QPushButton {{
                background: {t['bg2']};
                border: 1px solid {t['border']};
                padding: 2px 6px;
            }}
        """)

    # ─────────────────────────────────────────────────────────────
    # PUBLIC API
    # ─────────────────────────────────────────────────────────────

    def update_context(self, context: dict, prompt: str):
        entry = {
            "context": context,
            "prompt": prompt,
            "tools": []
        }

        self._history.append(entry)
        self._current_index = len(self._history) - 1

        self._render(entry)

    # ─────────────────────────────────────────────────────────────
    # RENDER
    # ─────────────────────────────────────────────────────────────

    def _render(self, entry):
        context = entry["context"]
        prompt = entry["prompt"]

        self._populate_tree(context)
        self.prompt_view.setPlainText(prompt)
        self.raw_view.setPlainText(json.dumps(context, indent=2))

        self._title.setText(
            f"Context Debugger ({self._current_index + 1}/{len(self._history)})"
        )
        tools_text = ""

        for t in entry.get("tools", []):
            if t["type"] == "call":
                tools_text += f"\n🔧 CALL {t['tool']}:\n{json.dumps(t['args'], indent=2)}\n"
            else:
                tools_text += f"\n📄 RESULT {t['tool']}:\n{t['result'][:500]}\n"
    
        self.tools_view.setPlainText(tools_text.strip())

    def _populate_tree(self, context):
        self.tree.clear()

        important = [
            ("Model", context.get("model")),
            ("Backend", context.get("backend")),
            ("Mode", "chat" if context.get("is_chat") else "inline"),
            ("Editor Length", context.get("editor_text_len")),
            ("Cursor", context.get("cursor_pos")),
            ("Wiki Length", context.get("wiki_context_len")),
        ]

        for k, v in important:
            self.tree.addTopLevelItem(QTreeWidgetItem([k, str(v)]))

        raw_root = QTreeWidgetItem(["Raw Context", ""])
        for k, v in context.items():
            raw_root.addChild(QTreeWidgetItem([k, self._preview(v)]))

        self.tree.addTopLevelItem(raw_root)
        self.tree.expandAll()

    def _preview(self, v):
        s = str(v)
        return s[:120] + "…" if len(s) > 120 else s
        
    # ─────────────────────────────────────────────────────────────
    # NAVIGATION
    # ─────────────────────────────────────────────────────────────

    def _prev(self):
        if self._current_index > 0:
            self._current_index -= 1
            self._render(self._history[self._current_index])

    def _next(self):
        if self._current_index < len(self._history) - 1:
            self._current_index += 1
            self._render(self._history[self._current_index])

    # ─────────────────────────────────────────────────────────────
    # ACTIONS
    # ─────────────────────────────────────────────────────────────

    def _copy_prompt(self):
        if self._current_index < 0:
            return

        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(
            self._history[self._current_index]["prompt"]
        )
        
    def update_tool_call(self, tool, args):
        if self._current_index >= 0:
            entry = self._history[self._current_index]
            if "tools" not in entry:
                entry["tools"] = []
            entry["tools"].append({
                "type": "call",
                "tool": tool,
                "args": args
            })
            self._render(entry)
    
    def update_tool_result(self, tool, result):
        if self._current_index >= 0:
            entry = self._history[self._current_index]
            if "tools" not in entry:
                entry["tools"] = []
            entry["tools"].append({
                "type": "result",
                "tool": tool,
                "result": result
            })
            self._render(entry)
