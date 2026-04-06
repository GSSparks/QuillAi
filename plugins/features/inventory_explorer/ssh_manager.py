"""
ssh_manager.py

Builds SSH commands from Ansible inventory host vars and
executes them in QuillAI's terminal.

Handles:
  - ansible_host, ansible_user, ansible_port
  - ansible_ssh_private_key_file (with Jinja2 var resolution prompt)
  - ssh_proxy_enable + ssh_proxy_inventory_hostname (ProxyJump)
"""

import os
import re
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QLabel, QPushButton, QDialogButtonBox,
    QCheckBox, QWidget,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from ui.theme import get_theme, theme_signals


# ── Stylesheet ────────────────────────────────────────────────────────────────

def _build_stylesheet(t: dict) -> str:
    return f"""
        QDialog, QWidget {{
            background: {t['bg1']};
            color: {t['fg1']};
        }}
        QLabel {{
            background: {t['bg1']};
            color: {t['fg4']};
            font-size: 9pt;
        }}
        QLabel#title {{
            background: {t['bg1']};
            color: {t['yellow']};
            font-size: 11pt;
            font-weight: bold;
            padding: 4px 0;
        }}
        QLabel#preview {{
            background: {t['bg0']};
            color: {t['aqua']};
            font-family: monospace;
            font-size: 9pt;
            padding: 6px 8px;
            border: 1px solid {t['bg3']};
            border-radius: 3px;
        }}
        QLabel#section {{
            color: {t['green']};
            font-size: 9pt;
            font-weight: bold;
            padding-top: 4px;
        }}
        QLineEdit {{
            background: {t['bg2']};
            color: {t['fg1']};
            border: 1px solid {t['bg3']};
            border-radius: 3px;
            padding: 3px 6px;
            font-size: 9pt;
            font-family: monospace;
        }}
        QLineEdit:focus {{
            border-color: {t['yellow']};
        }}
        QCheckBox {{
            background: {t['bg1']};
            color: {t['fg1']};
            font-size: 9pt;
        }}
        QCheckBox::indicator {{
            width: 14px;
            height: 14px;
            border: 1px solid {t['bg3']};
            border-radius: 2px;
            background: {t['bg2']};
        }}
        QCheckBox::indicator:checked {{
            background: {t['yellow']};
            border-color: {t['yellow']};
        }}
        QPushButton {{
            background: {t['bg2']};
            color: {t['fg1']};
            border: 1px solid {t['bg3']};
            border-radius: 3px;
            padding: 4px 16px;
            font-size: 9pt;
            min-width: 64px;
        }}
        QPushButton:hover {{
            background: {t['bg3']};
            border-color: {t['fg4']};
        }}
        QPushButton:default {{
            border-color: {t['yellow']};
            color: {t['yellow']};
        }}
    """


# ── Jinja2 variable resolver ──────────────────────────────────────────────────

_RE_JINJA_SIMPLE  = re.compile(r'\{\{\s*([\w_]+)\s*\}\}')
_RE_JINJA_COMPLEX = re.compile(r'\{\{.*?\}\}')


def _has_unresolved_vars(value: str) -> bool:
    return bool(_RE_JINJA_COMPLEX.search(value))


def _is_complex_jinja(value: str) -> bool:
    """True if value contains Jinja2 that can't be resolved by simple substitution."""
    for m in _RE_JINJA_COMPLEX.finditer(value):
        expr = m.group(0)
        # Simple variable reference — we can handle this
        if _RE_JINJA_SIMPLE.fullmatch(expr.strip()):
            continue
        # Anything else — lookup, filters, arithmetic, strings
        return True
    return False


def _resolve_vars(value: str, known: dict) -> str:
    """
    Replace simple {{ var }} with known values.
    Leaves complex Jinja2 expressions as empty string
    so they get caught by the unresolved var prompt.
    """
    def replace(m):
        full_expr = m.group(0)
        # Simple variable — substitute if known
        simple = _RE_JINJA_SIMPLE.fullmatch(full_expr.strip())
        if simple:
            var_name = simple.group(1)
            return known.get(var_name, full_expr)
        # Complex expression — return empty so caller knows it's unresolved
        return ''
    return _RE_JINJA_COMPLEX.sub(replace, value)


# ── SSH command builder ───────────────────────────────────────────────────────

def build_ssh_command(host, inventory, extra_vars: dict = None) -> str:
    from plugins.features.inventory_explorer.parser import resolve_host_vars

    eff   = resolve_host_vars(host, inventory)
    extra = extra_vars or {}
    eff.update(extra)

    address = _resolve_vars(eff.get('ansible_host', host.name), eff)

    # Support both ansible_user (modern) and ansible_ssh_user (legacy)
    user = _resolve_vars(
        eff.get('ansible_user') or eff.get('ansible_ssh_user', ''), eff
    )

    port     = _resolve_vars(str(eff.get('ansible_port', '22')), eff)
    key_file = _resolve_vars(
        eff.get('ansible_ssh_private_key_file', ''), eff
    )

    if not key_file and 'ansible_ssh_private_key_file' in extra:
        key_file = extra['ansible_ssh_private_key_file']

    if not address or _has_unresolved_vars(address):
        address = extra.get('ansible_host', host.name)
    if user and _has_unresolved_vars(user):
        user = extra.get('ansible_user') or extra.get('ansible_ssh_user', '')

    proxy_host = _get_proxy_host(host, inventory, eff, extra)

    parts = ['ssh']

    if port and port != '22':
        parts += ['-p', port]

    if key_file and not _has_unresolved_vars(key_file):
        key_file = os.path.expanduser(key_file)
        parts += ['-i', key_file]

    if proxy_host:
        parts += ['-J', proxy_host]

    parts += ['-o', 'StrictHostKeyChecking=accept-new']

    # Only add user if explicitly set — never fall back to system user
    target = f"{user}@{address}" if user else address
    parts.append(target)

    return ' '.join(parts)

def _get_proxy_host(host, inventory, eff: dict,
                    extra: dict) -> str:
    """
    Build the ProxyJump string if ssh_proxy_enable=True.
    Returns empty string if no proxy needed.
    """
    proxy_enable = eff.get('ssh_proxy_enable', 'False')
    if str(proxy_enable).lower() not in ('true', '1', 'yes'):
        return ''

    proxy_hostname = eff.get('ssh_proxy_inventory_hostname', '')
    if not proxy_hostname:
        return ''

    # Look up the proxy host in inventory
    proxy_host = inventory.hosts.get(proxy_hostname)
    if not proxy_host:
        return proxy_hostname  # use as-is if not in inventory

    from plugins.features.inventory_explorer.parser import resolve_host_vars
    proxy_eff = resolve_host_vars(proxy_host, inventory)
    proxy_eff.update(extra)

    proxy_addr = _resolve_vars(
        proxy_eff.get('ansible_host', proxy_hostname), proxy_eff
    )
    proxy_user = _resolve_vars(
        proxy_eff.get('ansible_user') or
        proxy_eff.get('ansible_ssh_user', ''), proxy_eff
    )
    proxy_key  = _resolve_vars(
        proxy_eff.get('ansible_ssh_private_key_file', ''), proxy_eff
    )

    if proxy_user:
        jump = f"{proxy_user}@{proxy_addr}"
    else:
        jump = proxy_addr

    # If proxy also needs a key, include it
    if proxy_key and not _has_unresolved_vars(proxy_key):
        proxy_key = os.path.expanduser(proxy_key)
        # SSH -J doesn't support -i per jump host directly
        # Use ssh_config style or just the key for the proxy
        jump = f"-i {proxy_key} {jump}"

    return jump


def collect_unresolved_vars(host, inventory) -> list[str]:
    from plugins.features.inventory_explorer.parser import resolve_host_vars

    eff = resolve_host_vars(host, inventory)

    unresolved = set()

    for key in ['ansible_host', 'ansible_user', 'ansible_ssh_user',
                'ansible_port', 'ansible_ssh_private_key_file',
                'ssh_proxy_inventory_hostname']:
        val = str(eff.get(key, ''))
        if not val:
            continue

        for m in _RE_JINJA_SIMPLE.finditer(val):
            var_name = m.group(1)
            if var_name not in eff:
                unresolved.add(var_name)

        if _is_complex_jinja(val):
            unresolved.add(key)

    return sorted(unresolved)

# ── Prompt dialog ─────────────────────────────────────────────────────────────

class SSHConnectDialog(QDialog):
    """
    Shown when a host has unresolved Jinja2 variables.
    Lets the user supply values before connecting.
    """

    connect_requested = pyqtSignal(str)   # final ssh command

    def __init__(self, host, inventory, parent=None):
        super().__init__(parent)
        self._host      = host
        self._inventory = inventory
        self._inputs    = {}   # var_name → QLineEdit

        self.setWindowTitle(f"Connect to {host.name}")
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.FramelessWindowHint
        )
        self.setModal(True)
        self.setMinimumWidth(440)

        self._unresolved = collect_unresolved_vars(host, inventory)

        self._build_ui()
        self._update_preview()
        self.setStyleSheet(_build_stylesheet(get_theme()))
        theme_signals.theme_changed.connect(
            lambda t: self.setStyleSheet(_build_stylesheet(t))
        )

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # Title
        from plugins.features.inventory_explorer.parser import resolve_host_vars
        eff     = resolve_host_vars(self._host, self._inventory)
        address = eff.get('ansible_host', self._host.name)
        user    = eff.get('ansible_user', '')
        display = f"{user}@{address}" if user else address

        title = QLabel(f"  🔗  {self._host.name}")
        title.setObjectName("title")
        layout.addWidget(title)

        sub = QLabel(f"  {display}")
        sub.setStyleSheet(f"color: {get_theme().get('fg4', '#a89984')};"
                          f"font-size: 9pt; padding-bottom: 4px;")
        layout.addWidget(sub)

        # Unresolved vars — show form to fill them in
        if self._unresolved:
            needs_label = QLabel("Missing variables:")
            needs_label.setObjectName("section")
            layout.addWidget(needs_label)

            form = QFormLayout()
            form.setSpacing(6)
            form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
            form.setFieldGrowthPolicy(
                QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
            )

            for var in self._unresolved:
                inp = QLineEdit()
            
                # Is this a full key name (complex Jinja2) or a var name?
                if var in ('ansible_ssh_private_key_file',
                           'ansible_host', 'ansible_user',
                           'ansible_port', 'ssh_proxy_inventory_hostname'):
                    # The whole value was a complex expression
                    friendly = {
                        'ansible_ssh_private_key_file': 'SSH Key Path',
                        'ansible_host':                 'Host Address',
                        'ansible_user':                 'SSH User',
                        'ansible_port':                 'SSH Port',
                        'ssh_proxy_inventory_hostname': 'Proxy Host',
                    }.get(var, var)
                    inp.setPlaceholderText(
                        f"e.g. ~/.ssh/my_key  (was complex Jinja2)"
                    )
                else:
                    friendly = var.replace('_', ' ').title()
                    inp.setPlaceholderText(f"Value for {var}")
            
                inp.textChanged.connect(self._update_preview)
                self._inputs[var] = inp
                form.addRow(f"{friendly}:", inp)

            layout.addLayout(form)
        else:
            ok_label = QLabel("✓  All variables resolved")
            ok_label.setStyleSheet(
                f"color: {get_theme().get('green', '#98971a')};"
                f"font-size: 9pt;"
            )
            layout.addWidget(ok_label)

        # SSH command preview
        preview_label = QLabel("Command:")
        preview_label.setObjectName("section")
        layout.addWidget(preview_label)

        self._preview = QLabel("")
        self._preview.setObjectName("preview")
        self._preview.setWordWrap(True)
        self._preview.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self._preview)

        # Extra SSH args
        extra_label = QLabel("Extra SSH args (optional):")
        extra_label.setObjectName("section")
        layout.addWidget(extra_label)

        self._extra_args = QLineEdit()
        self._extra_args.setPlaceholderText(
            "e.g. -L 8080:localhost:8080"
        )
        self._extra_args.textChanged.connect(self._update_preview)
        layout.addWidget(self._extra_args)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        connect_btn = QPushButton("Connect")
        connect_btn.setDefault(True)
        connect_btn.clicked.connect(self._on_connect)
        btn_layout.addWidget(connect_btn)

        layout.addLayout(btn_layout)

    def _extra_vars(self) -> dict:
        return {k: v.text().strip()
                for k, v in self._inputs.items()
                if v.text().strip()}

    def _update_preview(self):
        try:
            cmd = build_ssh_command(
                self._host, self._inventory,
                extra_vars=self._extra_vars()
            )
            extra = self._extra_args.text().strip() if hasattr(
                self, '_extra_args') else ''
            if extra:
                cmd += f" {extra}"
            self._preview.setText(cmd)
        except Exception as e:
            self._preview.setText(f"Error: {e}")

    def _on_connect(self):
        cmd = build_ssh_command(
            self._host, self._inventory,
            extra_vars=self._extra_vars()
        )
        extra = self._extra_args.text().strip()
        if extra:
            cmd += f" {extra}"
        self.connect_requested.emit(cmd)
        self.accept()

    def closeEvent(self, event):
        try:
            theme_signals.theme_changed.disconnect()
        except (RuntimeError, TypeError):
            pass
        super().closeEvent(event)


# ── Direct connect (no unresolved vars) ──────────────────────────────────────

def connect_to_host(host, inventory, parent_widget=None) -> str | None:
    """
    Build SSH command for a host. If there are unresolved Jinja2 vars,
    show the prompt dialog. Otherwise return the command immediately.
    Returns the ssh command string, or None if cancelled.
    """
    unresolved = collect_unresolved_vars(host, inventory)

    if unresolved:
        result = [None]
        dlg    = SSHConnectDialog(host, inventory, parent_widget)
        dlg.connect_requested.connect(lambda cmd: result.__setitem__(0, cmd))
        dlg.exec()
        return result[0]
    else:
        return build_ssh_command(host, inventory)