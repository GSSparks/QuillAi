"""
ssh_manager.py

Builds SSH commands from Ansible inventory host vars and
executes them in QuillAI's terminal.

Handles:
  - ansible_host, ansible_user, ansible_port
  - ansible_ssh_private_key_file (with Jinja2 var resolution)
  - ansible_ssh_private_key_dir  (auto-discovered from project)
  - ansible_ssh_common_args      (ProxyCommand extraction)
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


# ── Key auto-discovery ────────────────────────────────────────────────────────

# Common locations for SSH keys relative to project root
_KEY_DIR_CANDIDATES = [
    "playbooks/identities",
    "identities",
    "keys",
    "ssh",
    "ssh_keys",
    ".ssh",
    "playbooks/keys",
    "ansible/keys",
    "ansible/identities",
]


def discover_key_dir(project_root: str) -> str:
    """
    Search common locations for .pem or private key files relative to
    project_root. Returns the directory path if found, else empty string.
    """
    if not project_root:
        return ""
    for candidate in _KEY_DIR_CANDIDATES:
        full = os.path.join(project_root, candidate)
        if not os.path.isdir(full):
            continue
        # Check if it contains any .pem or key files
        try:
            entries = os.listdir(full)
            if any(
                f.endswith((".pem", ".key", ".rsa")) or
                (os.path.isfile(os.path.join(full, f)) and
                 not f.endswith((".yml", ".yaml", ".txt", ".md")))
                for f in entries
            ):
                return full
        except OSError:
            pass
    return ""


def discover_key_file(project_root: str, key_filename: str) -> str:
    """
    Given a bare filename like 'ca-central-1-sandbox.pem', search
    common key directories and return the full path if found.
    """
    if not project_root or not key_filename:
        return ""
    key_dir = discover_key_dir(project_root)
    if key_dir:
        candidate = os.path.join(key_dir, key_filename)
        if os.path.isfile(candidate):
            return candidate
    # Also try ~/.ssh
    ssh_home = os.path.expanduser("~/.ssh")
    candidate = os.path.join(ssh_home, key_filename)
    if os.path.isfile(candidate):
        return candidate
    return ""


# ── Jinja2 variable resolver ──────────────────────────────────────────────────

_RE_JINJA_SIMPLE  = re.compile(r'\{\{\s*([\w_]+)\s*\}\}')
_RE_JINJA_COMPLEX = re.compile(r'\{\{.*?\}\}')


def _has_unresolved_vars(value: str) -> bool:
    return bool(_RE_JINJA_COMPLEX.search(value))


def _is_complex_jinja(value: str) -> bool:
    for m in _RE_JINJA_COMPLEX.finditer(value):
        expr = m.group(0)
        if _RE_JINJA_SIMPLE.fullmatch(expr.strip()):
            continue
        return True
    return False


def _resolve_vars(value: str, known: dict) -> str:
    """Replace simple {{ var }} with known values."""
    def replace(m):
        full_expr = m.group(0)
        simple = _RE_JINJA_SIMPLE.fullmatch(full_expr.strip())
        if simple:
            var_name = simple.group(1)
            return known.get(var_name, full_expr)
        return ''
    return _RE_JINJA_COMPLEX.sub(replace, value)


def _auto_resolve_key_vars(eff: dict, project_root: str) -> dict:
    """
    Try to resolve ansible_ssh_private_key_dir automatically by
    discovering it from the project structure. Returns a copy of eff
    with the variable filled in if found.
    """
    resolved = dict(eff)

    # If ansible_ssh_private_key_dir is already known, nothing to do
    if resolved.get('ansible_ssh_private_key_dir'):
        return resolved

    # Check if the key file has an unresolved dir variable
    key_file = resolved.get('ansible_ssh_private_key_file', '')
    if not key_file or not _has_unresolved_vars(key_file):
        return resolved

    # Try to discover the key directory
    key_dir = discover_key_dir(project_root)
    if key_dir:
        resolved['ansible_ssh_private_key_dir'] = key_dir
        # Re-resolve the key file with the discovered dir
        resolved_key = _resolve_vars(key_file, resolved)
        if not _has_unresolved_vars(resolved_key):
            resolved['ansible_ssh_private_key_file'] = resolved_key

    return resolved


# ── ProxyCommand parser ───────────────────────────────────────────────────────

_RE_PROXY_HOST = re.compile(
    r'ProxyCommand[^"\']*["\'].*?-W\s+%h:%p.*?'
    r'(?:ec2-user@|user@|@)([^\s\'"]+)',
    re.IGNORECASE
)
_RE_PROXY_USER_HOST = re.compile(
    r'(?:ProxyCommand|ProxyJump)[^"\']*["\']?.*?'
    r'([\w\-.]+)@([\w\-\.]+)',
    re.IGNORECASE
)


def _parse_proxy_from_common_args(common_args: str) -> tuple[str, str]:
    """
    Extract (user, host) from ansible_ssh_common_args ProxyCommand.
    Returns ('', '') if not found.
    """
    if not common_args:
        return '', ''

    # Try to find user@host pattern inside the ProxyCommand
    m = _RE_PROXY_USER_HOST.search(common_args)
    if m:
        return m.group(1), m.group(2)

    # Fallback — just look for the host
    m = _RE_PROXY_HOST.search(common_args)
    if m:
        return 'ec2-user', m.group(1)

    return '', ''


# ── SSH command builder ───────────────────────────────────────────────────────

def build_ssh_command(host, inventory, extra_vars: dict = None,
                      project_root: str = None) -> str:
    from plugins.features.inventory_explorer.parser import resolve_host_vars

    eff   = resolve_host_vars(host, inventory)
    extra = extra_vars or {}
    eff.update(extra)

    # Auto-resolve ansible_ssh_private_key_dir from project structure
    if project_root:
        eff = _auto_resolve_key_vars(eff, project_root)

    address = _resolve_vars(eff.get('ansible_host', host.name), eff)
    user    = _resolve_vars(
        eff.get('ansible_user') or eff.get('ansible_ssh_user', ''), eff
    )
    port    = _resolve_vars(str(eff.get('ansible_port', '22')), eff)
    key_file = _resolve_vars(
        eff.get('ansible_ssh_private_key_file', ''), eff
    )

    if not address or _has_unresolved_vars(address):
        address = extra.get('ansible_host', host.name)
    if user and _has_unresolved_vars(user):
        user = extra.get('ansible_user') or extra.get('ansible_ssh_user', '')

    # Expand ~ in key path
    if key_file and not _has_unresolved_vars(key_file):
        key_file = os.path.expanduser(key_file)
        # If path doesn't exist yet, try discovering the file
        if not os.path.isfile(key_file) and project_root:
            basename = os.path.basename(key_file)
            discovered = discover_key_file(project_root, basename)
            if discovered:
                key_file = discovered

    proxy_jump = _get_proxy_jump(host, inventory, eff, extra, project_root)

    parts = ['ssh']

    if port and port != '22':
        parts += ['-p', port]

    if key_file and not _has_unresolved_vars(key_file):
        parts += ['-i', key_file]

    if proxy_jump:
        parts += ['-J', proxy_jump]

    parts += ['-o', 'StrictHostKeyChecking=accept-new']

    target = f"{user}@{address}" if user else address
    parts.append(target)

    return ' '.join(parts)


def _get_proxy_jump(host, inventory, eff: dict,
                    extra: dict, project_root: str = None) -> str:
    """
    Build the ProxyJump string. Checks both:
    1. ssh_proxy_enable + ssh_proxy_inventory_hostname (explicit)
    2. ansible_ssh_common_args ProxyCommand (parsed)
    Returns empty string if no proxy needed.
    """
    # ── Method 1: explicit ssh_proxy_enable ──────────────────────────────
    proxy_enable = eff.get('ssh_proxy_enable', 'False')
    if str(proxy_enable).lower() in ('true', '1', 'yes'):
        proxy_hostname = eff.get('ssh_proxy_inventory_hostname', '')
        if proxy_hostname:
            proxy_host = inventory.hosts.get(proxy_hostname)
            if proxy_host:
                from plugins.features.inventory_explorer.parser import resolve_host_vars
                proxy_eff = resolve_host_vars(proxy_host, inventory)
                proxy_eff.update(extra)
                if project_root:
                    proxy_eff = _auto_resolve_key_vars(proxy_eff, project_root)

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
                if proxy_key and not _has_unresolved_vars(proxy_key):
                    proxy_key = os.path.expanduser(proxy_key)
                    if not os.path.isfile(proxy_key) and project_root:
                        discovered = discover_key_file(
                            project_root, os.path.basename(proxy_key)
                        )
                        if discovered:
                            proxy_key = discovered

                jump = f"{proxy_user}@{proxy_addr}" if proxy_user else proxy_addr
                return jump
            else:
                return proxy_hostname

    # ── Method 2: parse ansible_ssh_common_args ───────────────────────────
    common_args = eff.get('ansible_ssh_common_args', '')
    if common_args:
        proxy_user, proxy_host_addr = _parse_proxy_from_common_args(common_args)
        if proxy_host_addr:
            return f"{proxy_user}@{proxy_host_addr}" if proxy_user else proxy_host_addr

    return ''


def collect_unresolved_vars(host, inventory,
                             project_root: str = None) -> list[str]:
    from plugins.features.inventory_explorer.parser import resolve_host_vars

    eff = resolve_host_vars(host, inventory)

    # Try auto-resolution before flagging anything as unresolved
    if project_root:
        eff = _auto_resolve_key_vars(eff, project_root)

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
    connect_requested = pyqtSignal(str)

    def __init__(self, host, inventory, parent=None, project_root: str = None):
        super().__init__(parent)
        self._host         = host
        self._inventory    = inventory
        self._project_root = project_root
        self._inputs       = {}

        self.setWindowTitle(f"Connect to {host.name}")
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.FramelessWindowHint
        )
        self.setModal(True)
        self.setMinimumWidth(480)

        self._unresolved = collect_unresolved_vars(
            host, inventory, project_root
        )
        self._prefill    = self._compute_prefill()

        self._build_ui()
        self._update_preview()
        self.setStyleSheet(_build_stylesheet(get_theme()))
        theme_signals.theme_changed.connect(
            lambda t: self.setStyleSheet(_build_stylesheet(t))
        )

    def _compute_prefill(self) -> dict:
        """
        Pre-fill dialog fields with auto-discovered values where possible.
        """
        prefill = {}
        if not self._project_root:
            return prefill

        # If ansible_ssh_private_key_dir is unresolved, discover it
        if 'ansible_ssh_private_key_dir' in self._unresolved:
            key_dir = discover_key_dir(self._project_root)
            if key_dir:
                prefill['ansible_ssh_private_key_dir'] = key_dir

        # If the whole key file is unresolved, try to find the .pem
        if 'ansible_ssh_private_key_file' in self._unresolved:
            from plugins.features.inventory_explorer.parser import resolve_host_vars
            eff      = resolve_host_vars(self._host, self._inventory)
            key_tmpl = eff.get('ansible_ssh_private_key_file', '')
            # Extract filename from the template
            # e.g. "{{ dir }}/ca-central-1-sandbox.pem" → "ca-central-1-sandbox.pem"
            basename = re.sub(_RE_JINJA_COMPLEX, '', key_tmpl).strip().lstrip('/')
            basename = os.path.basename(basename)
            if basename:
                found = discover_key_file(self._project_root, basename)
                if found:
                    prefill['ansible_ssh_private_key_file'] = found

        return prefill

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
        sub.setStyleSheet(
            f"color: {get_theme().get('fg4', '#a89984')};"
            f"font-size: 9pt; padding-bottom: 4px;"
        )
        layout.addWidget(sub)

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

            _friendly = {
                'ansible_ssh_private_key_file': 'SSH Key Path',
                'ansible_ssh_private_key_dir':  'SSH Key Directory',
                'ansible_host':                 'Host Address',
                'ansible_user':                 'SSH User',
                'ansible_port':                 'SSH Port',
                'ssh_proxy_inventory_hostname': 'Proxy Host',
            }

            for var in self._unresolved:
                inp = QLineEdit()
                # Pre-fill if auto-discovered
                if var in self._prefill:
                    inp.setText(self._prefill[var])
                    inp.setStyleSheet(
                        inp.styleSheet() +
                        f"border-color: {get_theme().get('green', '#98971a')};"
                    )
                else:
                    inp.setPlaceholderText(f"Value for {var}")

                inp.textChanged.connect(self._update_preview)
                self._inputs[var] = inp
                friendly = _friendly.get(var, var.replace('_', ' ').title())
                form.addRow(f"{friendly}:", inp)

            layout.addLayout(form)

            # Show discovery hint if key dir was found
            if 'ansible_ssh_private_key_dir' in self._prefill or \
               'ansible_ssh_private_key_file' in self._prefill:
                hint = QLabel(
                    f"✓ Key auto-discovered from project structure"
                )
                hint.setStyleSheet(
                    f"color: {get_theme().get('green', '#98971a')};"
                    f"font-size: 8pt; padding: 2px 0;"
                )
                layout.addWidget(hint)
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
        self._extra_args.setPlaceholderText("e.g. -L 8080:localhost:8080")
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
                extra_vars=self._extra_vars(),
                project_root=self._project_root,
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
            extra_vars=self._extra_vars(),
            project_root=self._project_root,
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


# ── Direct connect ────────────────────────────────────────────────────────────

def connect_to_host(host, inventory, parent_widget=None,
                    project_root: str = None) -> str | None:
    """
    Build SSH command for a host. If there are unresolved Jinja2 vars
    after auto-resolution, show the prompt dialog.
    Returns the ssh command string, or None if cancelled.
    """
    unresolved = collect_unresolved_vars(host, inventory, project_root)

    if unresolved:
        result = [None]
        dlg    = SSHConnectDialog(
            host, inventory, parent_widget,
            project_root=project_root
        )
        dlg.connect_requested.connect(lambda cmd: result.__setitem__(0, cmd))
        dlg.exec()
        return result[0]
    else:
        return build_ssh_command(
            host, inventory, project_root=project_root
        )