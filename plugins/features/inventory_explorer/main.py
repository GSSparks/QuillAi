"""
plugins/features/inventory_explorer/main.py

Inventory Explorer plugin — parses Ansible inventory files and
shows a tree of groups → hosts with vars and jump-to-file support.
"""

from PyQt6.QtCore import Qt
from core.plugin_base import FeaturePlugin
from core.events import EVT_PROJECT_OPENED, EVT_FILE_SAVED
from plugins.features.inventory_explorer.parser import load_inventory
from plugins.features.inventory_explorer.panel import InventoryExplorerPanel


class InventoryExplorerPlugin(FeaturePlugin):
    name        = "inventory_explorer"
    description = "Ansible inventory browser — groups, hosts, vars"
    enabled     = True

    def activate(self):
        self._panel = InventoryExplorerPanel(self.app)
        self.app.inventory_explorer_dock = self._panel
        self.app.addDockWidget(
            Qt.DockWidgetArea.LeftDockWidgetArea, self._panel
        )

        # Tabify with sidebar
        if hasattr(self.app, 'sidebar_dock'):
            self.app.tabifyDockWidget(self.app.sidebar_dock, self._panel)

        self._panel.hide()
        self.app.plugin_manager.register_dock(
            "Inventory", "inventory_explorer_dock"
        )

        self._panel.jump_requested.connect(self._on_jump_requested)
        self.on(EVT_PROJECT_OPENED, self._on_project_opened)
        self.on(EVT_FILE_SAVED,     self._on_file_saved)

    # ── Events ────────────────────────────────────────────────────────────

    def _on_project_opened(self, project_root: str = None, **kwargs):
        if not project_root:
            return
        self._panel.set_project_root(project_root)
        self._load(project_root)

    def _on_file_saved(self, path: str = None, **kwargs):
        """Reload inventory when an inventory file is saved."""
        if not path:
            return
        name = path.split('/')[-1]
        # Reload if it looks like an inventory file or group/host vars
        if any(x in path for x in ('inventory', 'hosts', 'group_vars',
                                    'host_vars')):
            root = getattr(self._panel, '_project_root', None)
            if root:
                self._load(root)

    # ── Load ──────────────────────────────────────────────────────────────

    def _load(self, project_root: str):
        inventory = load_inventory(project_root)
        if inventory.hosts or inventory.groups:
            self._panel.load_inventory(inventory)
            self._panel.show()
            self._panel.raise_()

    # ── Jump ──────────────────────────────────────────────────────────────

    def _on_jump_requested(self, file_path: str, line_num: int):
        self.app.open_file_in_tab(file_path, line_number=line_num)

    def deactivate(self):
        self._panel.close()
        self.app.inventory_explorer_dock = None