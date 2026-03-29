from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QFormLayout,
                             QGroupBox, QComboBox, QApplication)
from ui.theme import theme_names, get_theme, apply_theme


class SettingsDialog(QDialog):
    def __init__(self, settings_manager, parent=None):
        super().__init__(parent)
        self.sm = settings_manager
        self.setWindowTitle("QuillAI Settings")
        self.setFixedWidth(500)

        # Build styles from current theme
        t = get_theme(self.sm.get('theme') or 'gruvbox_dark')
        self._apply_dialog_style(t)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # ── Local LLM ──────────────────────────────────────────
        local_group = QGroupBox("Local LLM  (llama.cpp)")
        local_form = QFormLayout(local_group)
        local_form.setSpacing(8)

        self.local_url = QLineEdit(self.sm.get("local_llm_url"))
        self.local_url.setPlaceholderText("http://localhost:11434/v1/chat/completions")

        self.local_model = QLineEdit(self.sm.get("active_model"))
        self.local_model.setPlaceholderText("qwen2.5-coder-7b")

        local_form.addRow("Server URL:", self.local_url)
        local_form.addRow("Model name:", self.local_model)

        # ── OpenAI ─────────────────────────────────────────────
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

        # ── Anthropic / Claude ──────────────────────────────────
        claude_group = QGroupBox("Anthropic  (Claude)")
        claude_form = QFormLayout(claude_group)
        claude_form.setSpacing(8)

        self.anthropic_key = QLineEdit(self.sm.get("anthropic_api_key"))
        self.anthropic_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.anthropic_key.setPlaceholderText("sk-ant-...")

        self.claude_chat_model = QLineEdit(
            self.sm.get("chat_model") if self.sm.get_backend() == "claude"
            else "claude-sonnet-4-6"
        )
        self.claude_chat_model.setPlaceholderText("claude-sonnet-4-6")

        self.claude_inline_model = QLineEdit(
            self.sm.get("active_model") if self.sm.get_backend() == "claude"
            else "claude-haiku-4-5-20251001"
        )
        self.claude_inline_model.setPlaceholderText("claude-haiku-4-5-20251001")

        key_hint = QLabel("Get your key at console.anthropic.com")
        key_hint.setStyleSheet(f"color: {t['fg4']}; font-size: 9pt;")

        claude_form.addRow("API Key:", self.anthropic_key)
        claude_form.addRow("Chat model:", self.claude_chat_model)
        claude_form.addRow("Inline model:", self.claude_inline_model)
        claude_form.addRow("", key_hint)

        # ── Theme ───────────────────────────────────────────────
        theme_group = QGroupBox("Appearance")
        theme_form = QFormLayout(theme_group)
        theme_form.setSpacing(8)

        self.theme_combo = QComboBox()
        current_theme = self.sm.get('theme') or 'gruvbox_dark'
        for key, name in theme_names():
            self.theme_combo.addItem(name, key)
            if key == current_theme:
                self.theme_combo.setCurrentText(name)

        # Live preview — apply theme immediately on change
        self.theme_combo.currentIndexChanged.connect(self._preview_theme)

        theme_hint = QLabel("Theme takes effect immediately.")
        theme_hint.setStyleSheet(f"color: {t['fg4']}; font-size: 9pt;")

        theme_form.addRow("Theme:", self.theme_combo)
        theme_form.addRow("", theme_hint)

        # ── Buttons ─────────────────────────────────────────────
        btns = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.save_and_close)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("cancelBtn")
        cancel_btn.clicked.connect(self._on_cancel)

        btns.addStretch()
        btns.addWidget(cancel_btn)
        btns.addWidget(save_btn)

        layout.addWidget(local_group)
        layout.addWidget(openai_group)
        layout.addWidget(claude_group)
        layout.addWidget(theme_group)
        layout.addLayout(btns)

        # Store the original theme so we can revert on cancel
        self._original_theme = current_theme

    def _apply_dialog_style(self, t: dict):
        self.setStyleSheet(f"""
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
            QComboBox:focus {{
                border: 1px solid {t['border_focus']};
            }}
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
            QPushButton:hover {{ background-color: {t['yellow']}; }}
            QPushButton#cancelBtn {{
                background-color: {t['bg2']};
                color: {t['fg1']};
            }}
            QPushButton#cancelBtn:hover {{
                background-color: {t['bg3']};
            }}
        """)

    def _preview_theme(self):
        """Apply theme live as user changes the combo box."""
        selected = self.theme_combo.currentData()
        t = get_theme(selected)
        apply_theme(QApplication.instance(), selected)
        # Re-style the dialog itself to match
        self._apply_dialog_style(t)

    def _on_cancel(self):
        """Revert to the original theme if the user cancels."""
        if self.theme_combo.currentData() != self._original_theme:
            apply_theme(QApplication.instance(), self._original_theme)
        self.reject()

    def save_and_close(self):
        self.sm.set("local_llm_url",     self.local_url.text().strip())
        self.sm.set("active_model",      self.local_model.text().strip())
        self.sm.set("cloud_llm_url",     self.cloud_url.text().strip())
        self.sm.set("cloud_api_key",     self.openai_key.text().strip())
        self.sm.set("chat_model",        self.openai_model.text().strip())
        self.sm.set("anthropic_api_key", self.anthropic_key.text().strip())

        if self.sm.get_backend() == "claude":
            self.sm.set("active_model", self.claude_inline_model.text().strip())
            self.sm.set("chat_model",   self.claude_chat_model.text().strip())

        # Save the selected theme
        selected_theme = self.theme_combo.currentData()
        self.sm.set('theme', selected_theme)
        apply_theme(QApplication.instance(), selected_theme)

        self.accept()