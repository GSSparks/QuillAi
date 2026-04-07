"""
panel.py

Inventory Explorer panel — shows groups → hosts tree with vars,
host details, and jump-to-file support.
"""

import os
from PyQt6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QTreeWidget, QTreeWidgetItem, QLabel, QPushButton,
    QSizePolicy, QSplitter, QTextEdit, QLineEdit,
    QFrame, QMenu
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QFont, QIcon, QCursor

from ui.theme import get_theme, theme_signals, build_dock_stylesheet
from plugins.features.inventory_explorer.parser import (
    Inventory, AnsibleHost, AnsibleGroup, resolve_host_vars
)


class InventoryExplorerPanel(QDockWidget):

    jump_requested = pyqtSignal(str, int)   # file_path, line_num
    ssh_connect_requested = pyqtSignal(str)       # ssh command

    def __init__(self, parent=None):
        super().__init__("Inventory", parent)
        self.setObjectName("inventory_explorer_dock")
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable  |
            QDockWidget.DockWidgetFeature.DockWidgetMovable   |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )

        self._inventory: Inventory | None = None
        self._t = get_theme()

        self._build_ui()
        self._apply_theme(self._t)
        theme_signals.theme_changed.connect(self._apply_theme)

    # ── UI ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        container = QWidget()
        layout    = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setFixedHeight(32)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(8, 0, 4, 0)

        self._status = QLabel("No inventory loaded")
        self._status.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        hl.addWidget(self._status)

        refresh_btn = QPushButton("↻")
        refresh_btn.setFixedSize(24, 22)
        refresh_btn.setToolTip("Reload inventory")
        refresh_btn.clicked.connect(self._refresh)
        hl.addWidget(refresh_btn)

        layout.addWidget(header)

        # Search box
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter hosts…")
        self._search.textChanged.connect(self._filter)
        self._search.setFixedHeight(26)
        layout.addWidget(self._search)

        # Splitter — tree top, detail bottom
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Tree
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setIndentation(16)
        self._tree.setAnimated(True)
        self._tree.itemClicked.connect(self._on_item_clicked)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        splitter.addWidget(self._tree)

        self._tree.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self._tree.customContextMenuRequested.connect(
            self._on_context_menu
        )

        # Detail panel
        self._detail = QTextEdit()
        self._detail.setReadOnly(True)
        self._detail.setMaximumHeight(200)
        self._detail.setPlaceholderText("Click a host to see details…")
        splitter.addWidget(self._detail)

        splitter.setSizes([400, 200])
        layout.addWidget(splitter)

        self.setWidget(container)

    # ── Load ──────────────────────────────────────────────────────────────

    def load_inventory(self, inventory: Inventory):
        self._inventory = inventory
        self._populate_tree(inventory)

        host_count  = len(inventory.hosts)
        group_count = len(inventory.groups)
        file_count  = len(inventory.files)
        self._status.setText(
            f"{host_count} hosts  ·  {group_count} groups  ·  "
            f"{file_count} file{'s' if file_count != 1 else ''}"
        )

        if inventory.errors:
            self._detail.setPlainText(
                "Parse warnings:\n" + "\n".join(inventory.errors[:5])
            )

    def _populate_tree(self, inventory: Inventory):
        self._tree.clear()
        t = self._t

        # Color palette
        group_color = QColor(t.get('yellow',  '#d79921'))
        host_color  = QColor(t.get('fg1',     '#ebdbb2'))
        addr_color  = QColor(t.get('fg4',     '#a89984'))
        empty_color = QColor(t.get('bg3',     '#665c54'))
        child_color = QColor(t.get('aqua',    '#689d6a'))
        deploy_color= QColor(t.get('blue',    '#458588'))

        def _make_group_item(group_name: str,
                             visited: set = None) -> QTreeWidgetItem:
            if visited is None:
                visited = set()
            if group_name in visited:
                return None
            visited.add(group_name)

            group = inventory.groups.get(group_name)
            item  = QTreeWidgetItem()

            host_count = _count_hosts(group_name, inventory, set())
            label = f"  {group_name}"
            if host_count:
                label += f"  ({host_count})"

            item.setText(0, label)
            item.setData(0, Qt.ItemDataRole.UserRole,
                         ('group', group_name))

            if group and (group.hosts or group.children):
                item.setForeground(0, group_color)
            else:
                item.setForeground(0, empty_color)
                item.setToolTip(0, "Empty group")

            # Host children
            if group:
                for hname in group.hosts:
                    host = inventory.hosts.get(hname)
                    hitem = QTreeWidgetItem()
                    addr  = host.address if host else ''
                    label = f"  {hname}"
                    if addr:
                        label += f"  {addr}"
                    hitem.setText(0, label)
                    hitem.setForeground(0, host_color if addr else addr_color)
                    hitem.setData(0, Qt.ItemDataRole.UserRole,
                                  ('host', hname))
                    if host and host.user:
                        hitem.setToolTip(
                            0, f"{host.user}@{addr or hname}"
                        )
                    item.addChild(hitem)

                # Child group references
                for child_name in group.children:
                    citem = QTreeWidgetItem()
                    citem.setText(0, f"  ⤷ {child_name}")
                    citem.setForeground(0, child_color)
                    citem.setData(0, Qt.ItemDataRole.UserRole,
                                  ('group_ref', child_name))
                    item.addChild(citem)

            return item

        # Build top-level groups — find roots (not children of anything)
        all_children = set()
        for g in inventory.groups.values():
            for c in g.children:
                all_children.add(c)

        top_level = [
            name for name in inventory.groups
            if name not in all_children
        ]

        # Always put 'all' first if it exists
        if 'all' in top_level:
            top_level.remove('all')
            top_level.insert(0, 'all')

        for group_name in sorted(top_level):
            item = _make_group_item(group_name)
            if item:
                self._tree.addTopLevelItem(item)

        # Ungrouped hosts
        ungrouped = [
            h for h in inventory.hosts.values()
            if not h.groups
        ]
        if ungrouped:
            ug_item = QTreeWidgetItem()
            ug_item.setText(0, "  (ungrouped)")
            ug_item.setForeground(0, QColor(t.get('bg3', '#665c54')))
            for host in ungrouped:
                hitem = QTreeWidgetItem()
                hitem.setText(0, f"  {host.name}  {host.address}")
                hitem.setForeground(0, QColor(t.get('fg4', '#a89984')))
                hitem.setData(0, Qt.ItemDataRole.UserRole,
                              ('host', host.name))
                ug_item.addChild(hitem)
            self._tree.addTopLevelItem(ug_item)
            
    def _on_context_menu(self, pos):
        item = self._tree.itemAt(pos)
        if not item:
            return
    
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        kind, name = data
    
        print(f"[inventory] context menu: data={data}")
    
        menu = QMenu(self)
        t    = self._t
        menu.setStyleSheet(f"""
            QMenu {{
                background: {t['bg1']};
                color: {t['fg1']};
                border: 1px solid {t['bg3']};
                padding: 4px;
            }}
            QMenu::item {{
                padding: 4px 24px 4px 12px;
                font-size: 9pt;
            }}
            QMenu::item:selected {{
                background: {t['bg2']};
                color: {t['fg1']};
            }}
            QMenu::separator {{
                height: 1px;
                background: {t['bg3']};
                margin: 3px 0;
            }}
        """)
    
        if kind == 'host':
            host = self._inventory.hosts.get(name) if self._inventory else None
            if host:
                ssh_action = menu.addAction(f"🔗  SSH into {name}")
                ssh_action.triggered.connect(
                    lambda checked=False, h=name: self._ssh_connect(h)
                )
                menu.addSeparator()
            jump_action = menu.addAction("↗  Jump to definition")
            jump_action.triggered.connect(
                lambda: self._on_item_double_clicked(item, 0)
            )
    
        elif kind in ('group', 'group_ref'):
            # Collect all reachable hosts recursively
            hosts = self._collect_hosts(name)
    
            if hosts:
                if len(hosts) == 1:
                    # Single host — connect directly
                    hname = hosts[0]
                    ssh_action = menu.addAction(f"🔗  SSH into {hname}")
                    ssh_action.triggered.connect(
                        lambda checked=False, h=hname: self._ssh_connect(h)
                    )
                else:
                    # Multiple hosts — submenu
                    ssh_menu = menu.addMenu(f"🔗  SSH into…")
                    ssh_menu.setStyleSheet(menu.styleSheet())
                    for hname in hosts[:12]:
                        a = ssh_menu.addAction(hname)
                        a.triggered.connect(
                            lambda checked=False, h=hname: self._ssh_connect(h)
                        )
                    if len(hosts) > 12:
                        ssh_menu.addSeparator()
                        ssh_menu.addAction(
                            f"… +{len(hosts) - 12} more hosts"
                        ).setEnabled(False)
    
                menu.addSeparator()
    
            jump_action = menu.addAction("↗  Jump to definition")
            jump_action.triggered.connect(
                lambda: self._on_item_double_clicked(item, 0)
            )
    
        if not menu.isEmpty():
            menu.exec(QCursor.pos())
            
    def _collect_hosts(self, group_name: str,
                       visited: set = None) -> list[str]:
        """
        Recursively collect all host names reachable from a group,
        including hosts in child groups.
        """
        if visited is None:
            visited = set()
        if not self._inventory or group_name in visited:
            return []
        visited.add(group_name)
    
        group = self._inventory.groups.get(group_name)
        if not group:
            return []
    
        hosts = list(group.hosts)  # direct hosts
    
        for child in group.children:
            hosts += self._collect_hosts(child, visited)
    
        # Deduplicate while preserving order
        seen  = set()
        dedup = []
        for h in hosts:
            if h not in seen:
                seen.add(h)
                dedup.append(h)
    
        return dedup
    
    def _ssh_connect(self, host_name: str):
        if not self._inventory:
            return
        host = self._inventory.hosts.get(host_name)
        if not host:
            return
    
        from plugins.features.inventory_explorer.parser import resolve_host_vars
        eff = resolve_host_vars(host, self._inventory)
        print(f"[ssh] {host_name}")
        print(f"[ssh] host.user = {repr(host.user)}")
        print(f"[ssh] eff ansible_user = {repr(eff.get('ansible_user', 'NOT SET'))}")
        print(f"[ssh] eff keys with user = {[k for k in eff if 'user' in k.lower()]}")
    
        from plugins.features.inventory_explorer.ssh_manager import connect_to_host
        cmd = connect_to_host(host, self._inventory, self,
                              project_root=getattr(self, '_project_root', None))
        if cmd:
            self.ssh_connect_requested.emit(cmd)

    # ── Filter ────────────────────────────────────────────────────────────

    def _filter(self, text: str):
        text = text.lower().strip()

        def _walk(item: QTreeWidgetItem) -> bool:
            """Returns True if item or any child matches."""
            label   = item.text(0).lower()
            matches = text in label

            child_matches = False
            for i in range(item.childCount()):
                if _walk(item.child(i)):
                    child_matches = True

            visible = matches or child_matches or not text
            item.setHidden(not visible)
            if child_matches and text:
                item.setExpanded(True)
            return visible

        for i in range(self._tree.topLevelItemCount()):
            _walk(self._tree.topLevelItem(i))

    # ── Selection ─────────────────────────────────────────────────────────

    def _on_item_clicked(self, item: QTreeWidgetItem, col: int):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        kind, name = data

        if kind == 'host':
            self._show_host_detail(name)
        elif kind in ('group', 'group_ref'):
            self._show_group_detail(name)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, col: int):
        """Jump to the definition in the inventory file."""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data or not self._inventory:
            return
        kind, name = data

        if kind == 'host':
            host = self._inventory.hosts.get(name)
            if host and host.file_path:
                self.jump_requested.emit(host.file_path, host.line_num)
        elif kind in ('group', 'group_ref'):
            group = self._inventory.groups.get(name)
            if group and group.file_path:
                self.jump_requested.emit(group.file_path, group.line_num)

    def _show_host_detail(self, host_name: str):
        if not self._inventory:
            return
        host = self._inventory.hosts.get(host_name)
        if not host:
            return

        t     = self._t
        fg    = t.get('fg1',    '#ebdbb2')
        fg4   = t.get('fg4',    '#a89984')
        yellow= t.get('yellow', '#d79921')
        aqua  = t.get('aqua',   '#689d6a')
        green = t.get('green',  '#98971a')

        eff_vars = resolve_host_vars(host, self._inventory)

        lines = [
            f"<b style='color:{yellow};font-size:10pt'>{host.name}</b>",
        ]

        if host.address:
            lines.append(
                f"<span style='color:{aqua}'>Address:</span> "
                f"<code>{host.address}</code>"
            )
        user = eff_vars.get('ansible_user', host.user)
        if user:
            lines.append(
                f"<span style='color:{aqua}'>User:</span> "
                f"<code>{user}</code>"
            )
        port = eff_vars.get('ansible_port', str(host.port))
        if port and port != '22':
            lines.append(
                f"<span style='color:{aqua}'>Port:</span> "
                f"<code>{port}</code>"
            )
        if host.groups:
            lines.append(
                f"<span style='color:{aqua}'>Groups:</span> "
                f"{', '.join(host.groups)}"
            )

        # SSH key (truncated)
        key = eff_vars.get('ansible_ssh_private_key_file', '')
        if key:
            display = key if len(key) < 50 else '…' + key[-40:]
            lines.append(
                f"<span style='color:{aqua}'>SSH Key:</span> "
                f"<code style='font-size:8pt'>{display}</code>"
            )

        # Custom vars (non-ansible_ prefix)
        custom = {k: v for k, v in eff_vars.items()
                  if not k.startswith('ansible_')}
        if custom:
            lines.append(f"<br><span style='color:{green}'>Vars:</span>")
            for k, v in sorted(custom.items())[:15]:
                display_v = v if len(str(v)) < 60 else str(v)[:57] + '…'
                lines.append(
                    f"&nbsp;&nbsp;<span style='color:{fg4}'>{k}</span>"
                    f" = <code>{display_v}</code>"
                )
            if len(custom) > 15:
                lines.append(
                    f"&nbsp;&nbsp;<span style='color:{fg4}'>"
                    f"… +{len(custom)-15} more</span>"
                )

        if host.file_path:
            lines.append(
                f"<br><span style='color:{fg4};font-size:8pt'>"
                f"Defined in: {os.path.basename(host.file_path)}"
                f" line {host.line_num}</span>"
            )

        self._detail.setHtml(
            f"<div style='font-family:monospace;font-size:9pt;"
            f"color:{fg};padding:8px'>"
            + "<br>".join(lines) + "</div>"
        )

    def _show_group_detail(self, group_name: str):
        if not self._inventory:
            return
        group = self._inventory.groups.get(group_name)
        if not group:
            return

        t      = self._t
        fg     = t.get('fg1',    '#ebdbb2')
        fg4    = t.get('fg4',    '#a89984')
        yellow = t.get('yellow', '#d79921')
        aqua   = t.get('aqua',   '#689d6a')
        green  = t.get('green',  '#98971a')

        host_count = _count_hosts(group_name, self._inventory, set())
        lines = [
            f"<b style='color:{yellow};font-size:10pt'>"
            f"[{group_name}]</b>",
            f"<span style='color:{fg4}'>"
            f"{len(group.hosts)} direct host{'s' if len(group.hosts)!=1 else ''}"
            f"  ·  {host_count} total</span>",
        ]

        if group.children:
            lines.append(
                f"<span style='color:{aqua}'>Children:</span> "
                f"{', '.join(group.children)}"
            )

        if group.vars:
            lines.append(f"<br><span style='color:{green}'>Group vars:</span>")
            for k, v in sorted(group.vars.items())[:15]:
                display_v = v if len(str(v)) < 60 else str(v)[:57] + '…'
                lines.append(
                    f"&nbsp;&nbsp;<span style='color:{fg4}'>{k}</span>"
                    f" = <code>{display_v}</code>"
                )

        if group.file_path:
            lines.append(
                f"<br><span style='color:{fg4};font-size:8pt'>"
                f"Defined in: {os.path.basename(group.file_path)}"
                f" line {group.line_num}</span>"
            )

        self._detail.setHtml(
            f"<div style='font-family:monospace;font-size:9pt;"
            f"color:{fg};padding:8px'>"
            + "<br>".join(lines) + "</div>"
        )

    # ── Refresh ───────────────────────────────────────────────────────────

    def _refresh(self):
        if hasattr(self, '_project_root') and self._project_root:
            from plugins.features.inventory_explorer.parser import load_inventory
            inv = load_inventory(self._project_root)
            self.load_inventory(inv)

    def set_project_root(self, root: str):
        self._project_root = root

    # ── Theme ─────────────────────────────────────────────────────────────

    def _apply_theme(self, t: dict):
        self._t = t
        self.setStyleSheet(build_dock_stylesheet(t))
        bg  = t.get('bg0', '#282828')
        fg  = t.get('fg1', '#ebdbb2')
        fg4 = t.get('fg4', '#a89984')
        bg1 = t.get('bg1', '#3c3836')
        bg2 = t.get('bg2', '#504945')

        self._tree.setStyleSheet(f"""
            QTreeWidget {{
                background: {bg};
                color: {fg};
                border: none;
                outline: none;
            }}
            QTreeWidget::item {{
                padding: 2px 0;
            }}
            QTreeWidget::item:selected {{
                background: {bg2};
            }}
            QTreeWidget::item:hover {{
                background: {bg1};
            }}
        """)
        self._search.setStyleSheet(f"""
            QLineEdit {{
                background: {bg1};
                color: {fg};
                border: none;
                border-bottom: 1px solid {t.get('bg3', '#665c54')};
                padding: 4px 8px;
                font-family: monospace;
                font-size: 9pt;
            }}
        """)
        self._detail.setStyleSheet(f"""
            QTextEdit {{
                background: {bg};
                color: {fg};
                border: none;
                border-top: 1px solid {t.get('bg3', '#665c54')};
            }}
        """)

        # Repopulate with new theme colors
        if self._inventory:
            self._populate_tree(self._inventory)

    def closeEvent(self, event):
        try:
            theme_signals.theme_changed.disconnect(self._apply_theme)
        except (RuntimeError, TypeError):
            pass
        super().closeEvent(event)


# ── Helper ────────────────────────────────────────────────────────────────────

def _count_hosts(group_name: str, inventory: Inventory,
                 visited: set) -> int:
    """Recursively count all hosts in a group including children."""
    if group_name in visited:
        return 0
    visited.add(group_name)
    group = inventory.groups.get(group_name)
    if not group:
        return 0
    count = len(group.hosts)
    for child in group.children:
        count += _count_hosts(child, inventory, visited)
    return count