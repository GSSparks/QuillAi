from editor.highlighter import LanguagePlugin, THEME
from PyQt6.QtCore import QRegularExpression


class AnsiblePlugin(LanguagePlugin):
    EXTENSIONS = ['.yml', '.yaml']

    def __init__(self):
        super().__init__()

        # ── YAML keys (name:, hosts:, tasks:, become:, etc.) ─────────────
        self.add_rule(r'\b[\w-]+\s*(?=:)', 'keyword')

        # ── Ansible module names (values after the key on their own line) ─
        # e.g. ansible.builtin.copy, ansible.builtin.command
        self.add_rule(r'\bansible\.\w+\.\w+\b', 'builtin')
        self.add_rule(r'\b(apt|yum|dnf|pip|copy|template|file|service|'
                      r'command|shell|debug|fail|assert|stat|set_fact|'
                      r'include_tasks|import_tasks|import_playbook|'
                      r'include_role|import_role|register|notify|handler|'
                      r'block|rescue|always|loop|with_items|with_dict|'
                      r'when|tags|vars|vars_files|gather_facts|become|'
                      r'become_user|ignore_errors|changed_when|failed_when|'
                      r'no_log|delegate_to|run_once|serial|strategy)\b',
                      'builtin')

        # ── YAML list dashes ─────────────────────────────────────────────
        self.add_rule(r'^\s*-\s', 'operator')

        # ── Booleans ──────────────────────────────────────────────────────
        self.add_rule(
            r'\b(true|false|yes|no|True|False|Yes|No|null|~)\b',
            'keyword'
        )

        # ── Numbers ───────────────────────────────────────────────────────
        self.add_rule(r'\b[0-9]+(\.[0-9]+)?\b', 'number')

        # ── Strings ───────────────────────────────────────────────────────
        self.add_rule(r'"[^"\\]*(\\.[^"\\]*)*"', 'string')
        self.add_rule(r"'[^'\\]*(\\.[^'\\]*)*'", 'string')

        # ── Jinja2 variables {{ var }} ────────────────────────────────────
        self.add_rule(r'\{\{.*?\}\}', 'string2')

        # ── Jinja2 blocks {% ... %} ───────────────────────────────────────
        self.add_rule(r'\{%.*?%\}', 'builtin')

        # ── Comments ──────────────────────────────────────────────────────
        self.add_rule(r'#[^\n]*', 'comment')

        # ── YAML anchors and aliases (&anchor, *alias) ────────────────────
        self.add_rule(r'&\w+', 'class_def')
        self.add_rule(r'\*\w+', 'func_def')

        # ── Multiline strings (| and > block scalars) ─────────────────────
        self.multiline_start  = QRegularExpression(r'[|>][-+]?\s*$')
        self.multiline_end    = QRegularExpression(r'^(?!\s)')
        self.multiline_format = THEME['string']