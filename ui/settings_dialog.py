from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QFormLayout,
                             QGroupBox, QComboBox, QApplication,
                             QWidget, QScrollArea, QCheckBox)
from PyQt6.QtCore import Qt

from ui.theme import (theme_names, get_theme, apply_theme, theme_signals,
                      build_settings_dialog_stylesheet,
                      build_hint_label_stylesheet)


class SettingsDialog(QDialog):
    def __init__(self, settings_manager, parent=None):
        super().__init__(parent)
        self.sm = settings_manager
        self.setWindowTitle("QuillAI Settings")
        self.resize(520, 560)

        self._original_theme = self.sm.get('theme') or 'gruvbox_dark'

        self._setup_ui()
        self.apply_styles(get_theme())

        theme_signals.theme_changed.connect(self._on_theme_changed)

    # ── Theme ─────────────────────────────────────────────────────────────

    def _on_theme_changed(self, t: dict):
        self.apply_styles(t)

    def apply_styles(self, t: dict):
        self.setStyleSheet(build_settings_dialog_stylesheet(t))
        hint_style = build_hint_label_stylesheet(t)
        self._key_hint.setStyleSheet(hint_style)
        self._theme_hint.setStyleSheet(hint_style)

    # ── UI Setup ──────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Scrollable content (Git panel style) ──────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(14)

        scroll.setWidget(container)
        root.addWidget(scroll)

        # ── Local LLM ────────────────────────────────────────────
        local_group = QGroupBox("Local LLM  (llama.cpp)")
        local_form = QFormLayout(local_group)
        local_form.setSpacing(8)

        self.local_url = QLineEdit(self.sm.get("local_llm_url"))
        self.local_url.setPlaceholderText("http://localhost:11434/v1/chat/completions")

        self.local_model = QLineEdit(self.sm.get("active_model"))
        self.local_model.setPlaceholderText("qwen2.5-coder-7b")

        local_form.addRow("Server URL:", self.local_url)
        local_form.addRow("Model name:", self.local_model)

        # ── OpenAI ───────────────────────────────────────────────
        openai_group = QGroupBox("OpenAI  (or compatible)")
        openai_form = QFormLayout(openai_group)
        openai_form.setSpacing(8)

        self.cloud_url = QLineEdit(self.sm.get("cloud_llm_url"))
        self.cloud_url.setPlaceholderText("https://api.openai.com/v1/chat/completions")

        self.openai_key = QLineEdit(self.sm.get("cloud_api_key"))
        self.openai_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.openai_key.setPlaceholderText("sk-...")

        self.openai_model = QLineEdit(self.sm.get("chat_model"))
        self.openai_model.setPlaceholderText("gpt-4o")

        openai_form.addRow("API URL:", self.cloud_url)
        openai_form.addRow("API Key:", self.openai_key)
        openai_form.addRow("Chat model:", self.openai_model)

        # ── Anthropic ────────────────────────────────────────────
        claude_group = QGroupBox("Anthropic  (Claude)")
        claude_form = QFormLayout(claude_group)
        claude_form.setSpacing(8)

        self.anthropic_key = QLineEdit(self.sm.get("anthropic_api_key"))
        self.anthropic_key.setEchoMode(QLineEdit.EchoMode.Password)

        self.claude_chat_model = QLineEdit(
            self.sm.get("chat_model") if self.sm.get_backend() == "claude"
            else "claude-sonnet-4-6"
        )

        self.claude_inline_model = QLineEdit(
            self.sm.get("active_model") if self.sm.get_backend() == "claude"
            else "claude-haiku-4-5-20251001"
        )

        self._key_hint = QLabel("Get your key at console.anthropic.com")

        claude_form.addRow("API Key:", self.anthropic_key)
        claude_form.addRow("Chat model:", self.claude_chat_model)
        claude_form.addRow("Inline model:", self.claude_inline_model)
        claude_form.addRow("", self._key_hint)

        # ── Terminal ──────────────────────────────────────────────
        terminal_group = QGroupBox("Terminal")
        terminal_form = QFormLayout(terminal_group)
        terminal_form.setSpacing(8)

        self.terminal_clean_shell = QCheckBox("Clean shell  (skip .bashrc / .zshrc)")
        self.terminal_clean_shell.setChecked(
            bool(self.sm.get("terminal_clean_shell"))
        )

        terminal_form.addRow("", self.terminal_clean_shell)

        # ── Appearance ────────────────────────────────────────────
        theme_group = QGroupBox("Appearance")
        theme_form = QFormLayout(theme_group)
        theme_form.setSpacing(8)

        self.theme_combo = QComboBox()
        current_theme = self.sm.get('theme') or 'gruvbox_dark'

        for key, name in theme_names():
            self.theme_combo.addItem(name, key)
            if key == current_theme:
                self.theme_combo.setCurrentText(name)

        self.theme_combo.currentIndexChanged.connect(self._preview_theme)

        self._theme_hint = QLabel("Theme change previews live; Cancel reverts.")

        theme_form.addRow("Theme:", self.theme_combo)
        theme_form.addRow("", self._theme_hint)

        # ── Add sections ──────────────────────────────────────────
        layout.addWidget(local_group)
        layout.addWidget(openai_group)
        layout.addWidget(claude_group)
        layout.addWidget(terminal_group)
        layout.addWidget(theme_group)
        layout.addStretch()

        # ── Footer (Git panel style) ──────────────────────────────
        self.footer = QWidget()
        footer_layout = QHBoxLayout(self.footer)
        footer_layout.setContentsMargins(12, 8, 12, 8)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: gray;")

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("cancelBtn")
        cancel_btn.clicked.connect(self._on_cancel)

        save_btn = QPushButton("Save")
        save_btn.setObjectName("saveBtn")
        save_btn.clicked.connect(self.save_and_close)

        footer_layout.addWidget(self.status_label)
        footer_layout.addStretch()
        footer_layout.addWidget(cancel_btn)
        footer_layout.addWidget(save_btn)

        root.addWidget(self.footer)

    # ── Actions ───────────────────────────────────────────────────────────

    def _preview_theme(self):
        selected = self.theme_combo.currentData()
        apply_theme(QApplication.instance(), selected)

    def _on_cancel(self):
        if self.theme_combo.currentData() != self._original_theme:
            apply_theme(QApplication.instance(), self._original_theme)
        self.reject()

    def save_and_close(self):
        self.sm.set("local_llm_url", self.local_url.text().strip())
        self.sm.set("active_model", self.local_model.text().strip())
        self.sm.set("cloud_llm_url", self.cloud_url.text().strip())
        self.sm.set("cloud_api_key", self.openai_key.text().strip())
        self.sm.set("chat_model", self.openai_model.text().strip())
        self.sm.set("anthropic_api_key", self.anthropic_key.text().strip())
        self.sm.set("terminal_clean_shell", self.terminal_clean_shell.isChecked())

        if self.sm.get_backend() == "claude":
            self.sm.set("active_model", self.claude_inline_model.text().strip())
            self.sm.set("chat_model", self.claude_chat_model.text().strip())

        selected_theme = self.theme_combo.currentData()
        self.sm.set('theme', selected_theme)
        apply_theme(QApplication.instance(), selected_theme)

        self.status_label.setText("Saved ✓")
        self.accept()

    # ── Cleanup ───────────────────────────────────────────────────────────

    def closeEvent(self, event):
        try:
            theme_signals.theme_changed.disconnect(self._on_theme_changed)
        except RuntimeError:
            pass
        super().closeEvent(event)