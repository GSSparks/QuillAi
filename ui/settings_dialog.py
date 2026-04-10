from PyQt6.QtWidgets import (
    QSpinBox, QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFormLayout,
    QGroupBox, QComboBox, QApplication,
    QWidget, QScrollArea, QCheckBox, QTabWidget)
from ui.secret_line_edit import SecretLineEdit
from PyQt6.QtCore import Qt

from ui.theme import (theme_names, get_theme, apply_theme, theme_signals,
                      build_settings_dialog_stylesheet,
                      build_hint_label_stylesheet)


class SettingsDialog(QDialog):
    def __init__(self, settings_manager, parent=None,
                 project_settings=None):
        super().__init__(parent)
        self.sm               = settings_manager
        self.project_settings = project_settings
        self.setWindowTitle("QuillAI Settings")
        self.resize(560, 500)

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
        # Style the tab widget
        self._tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {t.get('bg3', '#665c54')};
                background: {t.get('bg0', '#282828')};
                border-radius: 4px;
            }}
            QTabBar::tab {{
                background: {t.get('bg1', '#3c3836')};
                color: {t.get('fg4', '#a89984')};
                padding: 6px 18px;
                border: none;
                border-right: 1px solid {t.get('bg3', '#665c54')};
                font-size: 9pt;
            }}
            QTabBar::tab:selected {{
                background: {t.get('bg2', '#504945')};
                color: {t.get('yellow', '#d79921')};
                border-bottom: 2px solid {t.get('yellow', '#d79921')};
            }}
            QTabBar::tab:hover:!selected {{
                background: {t.get('bg2', '#504945')};
                color: {t.get('fg1', '#ebdbb2')};
            }}
        """)
        # Style GitLab note label if present
        if hasattr(self, '_gitlab_note'):
            self._gitlab_note.setStyleSheet(
                f"color: {t.get('fg4', '#a89984')}; font-size: 8pt;"
                " background: transparent;"
            )

    # ── UI Setup ──────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 0)
        root.setSpacing(8)

        # ── Tab widget ────────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        root.addWidget(self._tabs, stretch=1)

        self._tabs.addTab(self._build_ai_tab(),           "🤖  AI")
        self._tabs.addTab(self._build_integrations_tab(), "🔗  Integrations")
        self._tabs.addTab(self._build_editor_tab(),       "⌨  Editor")
        self._tabs.addTab(self._build_appearance_tab(),   "🎨  Appearance")

        # ── Footer ────────────────────────────────────────────────────────
        self.footer = QWidget()
        footer_layout = QHBoxLayout(self.footer)
        footer_layout.setContentsMargins(0, 8, 0, 12)

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

    # ── Tab builders ──────────────────────────────────────────────────────

    def _tab_scroll(self) -> tuple[QWidget, QVBoxLayout]:
        """Return (tab_widget, inner_layout) with scroll area."""
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(14)

        scroll.setWidget(inner)
        tab_layout.addWidget(scroll)
        return tab, layout

    def _build_ai_tab(self) -> QWidget:
        tab, layout = self._tab_scroll()

        # ── Local LLM ────────────────────────────────────────────
        local_group = QGroupBox("Local LLM  (llama.cpp)")
        local_form  = QFormLayout(local_group)
        local_form.setSpacing(8)

        self.local_url = QLineEdit(self.sm.get("local_llm_url"))
        self.local_url.setPlaceholderText(
            "http://localhost:11434/v1/chat/completions")

        self.local_model = QLineEdit(self.sm.get("active_model"))
        self.local_model.setPlaceholderText("qwen2.5-coder-7b")

        self.token_budget = QSpinBox()
        self.token_budget.setRange(2000, 128000)
        self.token_budget.setSingleStep(1000)
        self.token_budget.setValue(self.sm.get_token_budget())
        self.token_budget.setToolTip(
            "Maximum tokens sent to the model per request.\n"
            "Lower = faster responses on slow hardware.\n"
            "Recommended: 8000-16000 for local, 28000 for cloud."
        )

        local_form.addRow("Server URL:",     self.local_url)
        local_form.addRow("Model name:",     self.local_model)
        local_form.addRow("Context budget:", self.token_budget)

        # ── OpenAI ───────────────────────────────────────────────
        openai_group = QGroupBox("OpenAI  (or compatible)")
        openai_form  = QFormLayout(openai_group)
        openai_form.setSpacing(8)

        self.cloud_url = QLineEdit(self.sm.get("cloud_llm_url"))
        self.cloud_url.setPlaceholderText(
            "https://api.openai.com/v1/chat/completions")

        _oai_set = bool(self.sm.get('cloud_api_key') or
                        self.sm.get_api_key())
        self.openai_key = SecretLineEdit(
            text=self.sm.get_openai_key() if _oai_set else '',
            placeholder='● stored securely' if _oai_set else 'sk-...'
        )

        self.openai_model = QLineEdit(self.sm.get("chat_model"))
        self.openai_model.setPlaceholderText("gpt-4o")

        openai_form.addRow("API URL:",    self.cloud_url)
        openai_form.addRow("API Key:",    self.openai_key)
        openai_form.addRow("Chat model:", self.openai_model)

        # ── Anthropic ────────────────────────────────────────────
        claude_group = QGroupBox("Anthropic  (Claude)")
        claude_form  = QFormLayout(claude_group)
        claude_form.setSpacing(8)

        _ant_set = bool(self.sm.get('anthropic_api_key') or
                        self.sm.get_api_key())
        self.anthropic_key = SecretLineEdit(
            text=self.sm.get_anthropic_key() if _ant_set else '',
            placeholder='● stored securely' if _ant_set else 'sk-ant-...'
        )

        self.claude_chat_model = QLineEdit(
            self.sm.get("chat_model")
            if self.sm.get_backend() == "claude"
            else "claude-sonnet-4-6"
        )
        self.claude_inline_model = QLineEdit(
            self.sm.get("active_model")
            if self.sm.get_backend() == "claude"
            else "claude-haiku-4-5-20251001"
        )

        self._key_hint = QLabel("Get your key at console.anthropic.com")

        claude_form.addRow("API Key:",      self.anthropic_key)
        claude_form.addRow("Chat model:",   self.claude_chat_model)
        claude_form.addRow("Inline model:", self.claude_inline_model)
        claude_form.addRow("",              self._key_hint)

        layout.addWidget(local_group)
        layout.addWidget(openai_group)
        layout.addWidget(claude_group)
        layout.addStretch()
        return tab

    def _build_integrations_tab(self) -> QWidget:
        tab, layout = self._tab_scroll()

        # ── GitLab CI ────────────────────────────────────────────
        gitlab_group = QGroupBox("GitLab CI")
        gitlab_form  = QFormLayout(gitlab_group)
        gitlab_form.setSpacing(8)

        _ps = self.project_settings
        has_project = _ps and _ps.has_project()

        self.gitlab_url = QLineEdit(
            _ps.get_gitlab_url() if has_project else ''
        )
        self.gitlab_url.setPlaceholderText("https://gitlab.example.com")

        _gl_tok_set = has_project and bool(
            _ps.get_gitlab_token() if _ps else ''
        )
        self.gitlab_token = SecretLineEdit(
            text=_ps.get_gitlab_token() if _gl_tok_set else '',
            placeholder='● stored securely' if _gl_tok_set else 'glpat-xxxx'
        )

        self.gitlab_project = QLineEdit(
            _ps.get_gitlab_project_id() if has_project else ''
        )
        self.gitlab_project.setPlaceholderText("group/project  or  12345")

        if not has_project:
            for w in [self.gitlab_url, self.gitlab_token,
                      self.gitlab_project]:
                w.setEnabled(False)
                w.setPlaceholderText("Open a project first")

        gitlab_form.addRow("Instance URL:",    self.gitlab_url)
        gitlab_form.addRow("API Token:",       self.gitlab_token)
        gitlab_form.addRow("Project ID/Path:", self.gitlab_project)

        self._gitlab_note = QLabel(
            "⚠ Settings are per-project — stored in\n"
            "~/.config/quillai/projects/<project>/settings.json"
        )
        self._gitlab_note.setWordWrap(True)
        gitlab_form.addRow("", self._gitlab_note)

        layout.addWidget(gitlab_group)
        layout.addStretch()
        return tab

    def _build_editor_tab(self) -> QWidget:
        tab, layout = self._tab_scroll()

        # ── Terminal ─────────────────────────────────────────────
        terminal_group = QGroupBox("Terminal")
        terminal_form  = QFormLayout(terminal_group)
        terminal_form.setSpacing(8)

        self.terminal_clean_shell = QCheckBox(
            "Clean shell  (skip .bashrc / .zshrc)")
        self.terminal_clean_shell.setChecked(
            bool(self.sm.get("terminal_clean_shell")))

        terminal_form.addRow("", self.terminal_clean_shell)

        layout.addWidget(terminal_group)
        layout.addStretch()
        return tab

    def _build_appearance_tab(self) -> QWidget:
        tab, layout = self._tab_scroll()

        # ── Theme ────────────────────────────────────────────────
        theme_group = QGroupBox("Appearance")
        theme_form  = QFormLayout(theme_group)
        theme_form.setSpacing(8)

        self.theme_combo = QComboBox()
        current_theme = self.sm.get('theme') or 'gruvbox_dark'
        for key, name in theme_names():
            self.theme_combo.addItem(name, key)
            if key == current_theme:
                self.theme_combo.setCurrentText(name)

        self.theme_combo.currentIndexChanged.connect(self._preview_theme)

        self._theme_hint = QLabel(
            "Theme change previews live; Cancel reverts.")

        theme_form.addRow("Theme:", self.theme_combo)
        theme_form.addRow("",      self._theme_hint)

        layout.addWidget(theme_group)
        layout.addStretch()
        return tab

    # ── Actions ───────────────────────────────────────────────────────────

    def _preview_theme(self):
        selected = self.theme_combo.currentData()
        apply_theme(QApplication.instance(), selected)

    def _on_cancel(self):
        if self.theme_combo.currentData() != self._original_theme:
            apply_theme(QApplication.instance(), self._original_theme)
        self.reject()

    def save_and_close(self):
        self.sm.set("local_llm_url",  self.local_url.text().strip())
        self.sm.set("active_model",   self.local_model.text().strip())
        self.sm.set_token_budget(self.token_budget.value())
        self.sm.set("cloud_llm_url",  self.cloud_url.text().strip())
        if self.openai_key.text().strip():
            self.sm.set_api_key('openai', self.openai_key.text().strip())
        self.sm.set("chat_model",     self.openai_model.text().strip())
        if self.anthropic_key.text().strip():
            self.sm.set_api_key('anthropic', self.anthropic_key.text().strip())
        self.sm.set("terminal_clean_shell",
                    self.terminal_clean_shell.isChecked())

        if self.sm.get_backend() == "claude":
            self.sm.set("active_model", self.claude_inline_model.text().strip())
            self.sm.set("chat_model",   self.claude_chat_model.text().strip())

        if self.project_settings and self.project_settings.has_project():
            tok = self.gitlab_token.text().strip()
            # Only update token if user typed a new one
            if not tok:
                tok = self.project_settings.get_gitlab_token()
            self.project_settings.set_gitlab_settings(
                self.gitlab_url.text().strip(),
                tok,
                self.gitlab_project.text().strip(),
            )

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