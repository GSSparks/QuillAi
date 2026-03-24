from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QFormLayout,
                             QGroupBox, QSizePolicy)

FIELD_STYLE = """
    QLineEdit {
        background-color: #1E1E1E;
        color: #FFFFFF;
        border: 1px solid #3E3E42;
        border-radius: 4px;
        padding: 5px 8px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 10pt;
    }
    QLineEdit:focus { border: 1px solid #0E639C; }
"""

GROUP_STYLE = """
    QGroupBox {
        color: #888888;
        font-weight: bold;
        font-size: 9pt;
        border: 1px solid #3E3E42;
        border-radius: 6px;
        margin-top: 10px;
        padding-top: 8px;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 4px;
    }
"""


class SettingsDialog(QDialog):
    def __init__(self, settings_manager, parent=None):
        super().__init__(parent)
        self.sm = settings_manager
        self.setWindowTitle("QuillAI Settings")
        self.setFixedWidth(500)
        self.setStyleSheet("""
            QDialog { background-color: #252526; color: #CCCCCC; }
            QLabel  { color: #CCCCCC; font-size: 10pt; }
            QPushButton {
                background-color: #0E639C; color: white;
                border: none; border-radius: 4px;
                padding: 6px 16px; font-weight: bold;
            }
            QPushButton:hover { background-color: #1177BB; }
            QPushButton#cancelBtn {
                background-color: #3E3E42; color: #CCCCCC;
            }
            QPushButton#cancelBtn:hover { background-color: #4E4E52; }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # ── Local LLM ──────────────────────────────────────────
        local_group = QGroupBox("Local LLM  (llama.cpp)")
        local_group.setStyleSheet(GROUP_STYLE)
        local_form = QFormLayout(local_group)
        local_form.setSpacing(8)

        self.local_url = QLineEdit(self.sm.get("local_llm_url"))
        self.local_url.setStyleSheet(FIELD_STYLE)
        self.local_url.setPlaceholderText("http://localhost:11434/v1/chat/completions")

        self.local_model = QLineEdit(self.sm.get("active_model"))
        self.local_model.setStyleSheet(FIELD_STYLE)
        self.local_model.setPlaceholderText("qwen2.5-coder-7b")

        local_form.addRow("Server URL:", self.local_url)
        local_form.addRow("Model name:", self.local_model)

        # ── OpenAI ─────────────────────────────────────────────
        openai_group = QGroupBox("OpenAI  (or compatible)")
        openai_group.setStyleSheet(GROUP_STYLE)
        openai_form = QFormLayout(openai_group)
        openai_form.setSpacing(8)

        self.cloud_url = QLineEdit(self.sm.get("cloud_llm_url"))
        self.cloud_url.setStyleSheet(FIELD_STYLE)
        self.cloud_url.setPlaceholderText("https://api.openai.com/v1/chat/completions")

        self.openai_key = QLineEdit(self.sm.get("cloud_api_key"))
        self.openai_key.setStyleSheet(FIELD_STYLE)
        self.openai_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.openai_key.setPlaceholderText("sk-...")

        self.openai_model = QLineEdit(self.sm.get("chat_model"))
        self.openai_model.setStyleSheet(FIELD_STYLE)
        self.openai_model.setPlaceholderText("gpt-4o  (leave blank to use model name above)")

        openai_form.addRow("API URL:", self.cloud_url)
        openai_form.addRow("API Key:", self.openai_key)
        openai_form.addRow("Chat model:", self.openai_model)

        # ── Anthropic / Claude ──────────────────────────────────
        claude_group = QGroupBox("Anthropic  (Claude)")
        claude_group.setStyleSheet(GROUP_STYLE)
        claude_form = QFormLayout(claude_group)
        claude_form.setSpacing(8)

        self.anthropic_key = QLineEdit(self.sm.get("anthropic_api_key"))
        self.anthropic_key.setStyleSheet(FIELD_STYLE)
        self.anthropic_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.anthropic_key.setPlaceholderText("sk-ant-...")

        self.claude_chat_model = QLineEdit(
            self.sm.get("chat_model") if self.sm.get_backend() == "claude" else "claude-sonnet-4-6"
        )
        self.claude_chat_model.setStyleSheet(FIELD_STYLE)
        self.claude_chat_model.setPlaceholderText("claude-sonnet-4-6")

        self.claude_inline_model = QLineEdit(
            self.sm.get("active_model") if self.sm.get_backend() == "claude" else "claude-haiku-4-5-20251001"
        )
        self.claude_inline_model.setStyleSheet(FIELD_STYLE)
        self.claude_inline_model.setPlaceholderText("claude-haiku-4-5-20251001")

        key_hint = QLabel("Get your key at console.anthropic.com")
        key_hint.setStyleSheet("color: #555555; font-size: 9pt;")

        claude_form.addRow("API Key:", self.anthropic_key)
        claude_form.addRow("Chat model:", self.claude_chat_model)
        claude_form.addRow("Inline model:", self.claude_inline_model)
        claude_form.addRow("", key_hint)

        # ── Buttons ─────────────────────────────────────────────
        btns = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.save_and_close)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("cancelBtn")
        cancel_btn.clicked.connect(self.reject)

        btns.addStretch()
        btns.addWidget(cancel_btn)
        btns.addWidget(save_btn)

        layout.addWidget(local_group)
        layout.addWidget(openai_group)
        layout.addWidget(claude_group)
        layout.addLayout(btns)

    def save_and_close(self):
        self.sm.set("local_llm_url",      self.local_url.text().strip())
        self.sm.set("active_model",       self.local_model.text().strip())
        self.sm.set("cloud_llm_url",      self.cloud_url.text().strip())
        self.sm.set("cloud_api_key",      self.openai_key.text().strip())
        self.sm.set("chat_model",         self.openai_model.text().strip())
        self.sm.set("anthropic_api_key",  self.anthropic_key.text().strip())

        # If currently on Claude backend, update the models there too
        if self.sm.get_backend() == "claude":
            self.sm.set("active_model", self.claude_inline_model.text().strip())
            self.sm.set("chat_model",   self.claude_chat_model.text().strip())

        self.accept()