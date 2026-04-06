"""
parser.py

Parses Ansible inventory files (INI and YAML formats) into a unified
data model. Handles groups, hosts, vars, children, and group_vars/host_vars
directories.
"""

import os
import re
from dataclasses import dataclass, field

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class AnsibleHost:
    name:      str
    address:   str = ""          # ansible_host value
    user:      str = ""          # ansible_user value
    port:      int = 22
    vars:      dict = field(default_factory=dict)
    groups:    list = field(default_factory=list)
    file_path: str = ""          # inventory file where defined
    line_num:  int = 0


@dataclass
class AnsibleGroup:
    name:      str
    hosts:     list = field(default_factory=list)   # host names
    children:  list = field(default_factory=list)   # child group names
    vars:      dict = field(default_factory=dict)
    file_path: str = ""
    line_num:  int = 0


@dataclass
class Inventory:
    hosts:      dict = field(default_factory=dict)   # name → AnsibleHost
    groups:     dict = field(default_factory=dict)   # name → AnsibleGroup
    files:      list = field(default_factory=list)   # all parsed files
    errors:     list = field(default_factory=list)


# ── INI parser ────────────────────────────────────────────────────────────────

_RE_HOST_LINE = re.compile(
    r'^(\S+)'                          # hostname
    r'(?:\s+(.*))?$'                   # optional key=value pairs
)
_RE_KV = re.compile(r'(\w+)=(\S+)')
_RE_GROUP_HEADER = re.compile(
    r'^\[([^\]]+)\]'                   # [group_name] or [group_name:vars] etc
)


def _parse_kv(s: str) -> dict:
    """Parse 'key=val key2=val2' into a dict. Handles Jinja2 values."""
    result = {}
    # Use a smarter split that respects {{ }} blocks
    pos = 0
    s   = s.strip()
    while pos < len(s):
        # Find next key=
        m = re.search(r'(\w+)=', s[pos:])
        if not m:
            break
        key   = m.group(1)
        start = pos + m.end()
        # Find end of value — next key= or end of string
        next_key = re.search(r'\s+\w+=', s[start:])
        if next_key:
            val = s[start:start + next_key.start()]
            pos = start + next_key.start() + 1
        else:
            val = s[start:]
            pos = len(s)
        result[key] = val.strip()
    return result


def parse_ini(content: str, file_path: str = "",
              inventory: Inventory = None) -> Inventory:
    if inventory is None:
        inventory = Inventory()

    current_group    = None
    current_section  = None   # 'hosts' | 'vars' | 'children'

    for line_num, raw_line in enumerate(content.splitlines(), 1):
        line = raw_line.strip()

        # Skip blank lines and comments
        if not line or line.startswith('#') or line.startswith(';'):
            continue

        # Group header
        m = _RE_GROUP_HEADER.match(line)
        if m:
            header = m.group(1)
            if ':' in header:
                parts           = header.split(':', 1)
                current_group   = parts[0].strip()
                current_section = parts[1].strip()   # 'vars' or 'children'
            else:
                current_group   = header.strip()
                current_section = 'hosts'

            if current_group not in inventory.groups:
                inventory.groups[current_group] = AnsibleGroup(
                    name      = current_group,
                    file_path = file_path,
                    line_num  = line_num,
                )
            continue

        if current_group is None:
            # Lines before any group header — treat as 'all' group
            current_group   = 'all'
            current_section = 'hosts'
            if 'all' not in inventory.groups:
                inventory.groups['all'] = AnsibleGroup(
                    name='all', file_path=file_path)

        group = inventory.groups[current_group]

        if current_section == 'children':
            child = line.strip()
            if child not in group.children:
                group.children.append(child)
            # Ensure child group exists
            if child not in inventory.groups:
                inventory.groups[child] = AnsibleGroup(
                    name=child, file_path=file_path)

        elif current_section == 'vars':
            kv = _parse_kv(line)
            group.vars.update(kv)

        else:  # hosts
            m = _RE_HOST_LINE.match(line)
            if not m:
                continue
            hostname = m.group(1)
            kv_str   = m.group(2) or ''
            kv       = _parse_kv(kv_str)

            if hostname not in inventory.hosts:
                host = AnsibleHost(
                    name      = hostname,
                    address   = kv.get('ansible_host', ''),
                    user      = kv.get('ansible_user', ''),
                    vars      = kv,
                    file_path = file_path,
                    line_num  = line_num,
                )
                try:
                    host.port = int(kv.get('ansible_port', 22))
                except ValueError:
                    host.port = 22
                inventory.hosts[hostname] = host

            host = inventory.hosts[hostname]
            if current_group not in host.groups:
                host.groups.append(current_group)
            if hostname not in group.hosts:
                group.hosts.append(hostname)

    if file_path not in inventory.files:
        inventory.files.append(file_path)

    return inventory


# ── YAML inventory parser ─────────────────────────────────────────────────────

def parse_yaml_inventory(content: str, file_path: str = "",
                          inventory: Inventory = None) -> Inventory:
    if not HAS_YAML:
        return inventory or Inventory()
    if inventory is None:
        inventory = Inventory()

    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        inv = inventory or Inventory()
        inv.errors.append(f"{file_path}: {e}")
        return inv

    if not isinstance(data, dict):
        return inventory

    def _walk_group(group_name: str, group_data: dict):
        if group_name not in inventory.groups:
            inventory.groups[group_name] = AnsibleGroup(
                name=group_name, file_path=file_path)
        group = inventory.groups[group_name]

        if not isinstance(group_data, dict):
            return

        # Hosts
        hosts = group_data.get('hosts', {}) or {}
        for hname, hvars in hosts.items():
            hvars = hvars or {}
            if hname not in inventory.hosts:
                inventory.hosts[hname] = AnsibleHost(
                    name      = str(hname),
                    address   = str(hvars.get('ansible_host', '')),
                    user      = str(hvars.get('ansible_user', '')),
                    vars      = {k: str(v) for k, v in hvars.items()},
                    file_path = file_path,
                )
            host = inventory.hosts[str(hname)]
            if group_name not in host.groups:
                host.groups.append(group_name)
            if str(hname) not in group.hosts:
                group.hosts.append(str(hname))

        # Vars
        gvars = group_data.get('vars', {}) or {}
        group.vars.update({k: str(v) for k, v in gvars.items()})

        # Children
        children = group_data.get('children', {}) or {}
        for child_name, child_data in children.items():
            if child_name not in group.children:
                group.children.append(child_name)
            _walk_group(child_name, child_data or {})

    for group_name, group_data in data.items():
        _walk_group(group_name, group_data or {})

    if file_path not in inventory.files:
        inventory.files.append(file_path)

    return inventory


# ── group_vars / host_vars loader ─────────────────────────────────────────────

def load_group_vars(project_root: str, inventory: Inventory) -> Inventory:
    """
    Load group_vars/ and host_vars/ directories and merge into inventory.
    Supports both flat files (group_vars/webservers.yml) and
    directories (group_vars/webservers/main.yml).
    """
    for var_dir in ('group_vars', 'host_vars'):
        base = os.path.join(project_root, var_dir)
        if not os.path.isdir(base):
            continue

        for entry in os.listdir(base):
            entry_path = os.path.join(base, entry)
            name = entry

            # Strip extension for flat files
            if os.path.isfile(entry_path):
                name = os.path.splitext(entry)[0]
                files = [entry_path]
            elif os.path.isdir(entry_path):
                files = [
                    os.path.join(entry_path, f)
                    for f in os.listdir(entry_path)
                    if f.endswith(('.yml', '.yaml'))
                ]
            else:
                continue

            combined_vars = {}
            for fpath in files:
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    if HAS_YAML:
                        data = yaml.safe_load(content) or {}
                        if isinstance(data, dict):
                            combined_vars.update(
                                {k: str(v) for k, v in data.items()}
                            )
                except Exception:
                    pass

            if var_dir == 'group_vars':
                if name not in inventory.groups:
                    inventory.groups[name] = AnsibleGroup(name=name)
                inventory.groups[name].vars.update(combined_vars)
            else:  # host_vars
                if name not in inventory.hosts:
                    inventory.hosts[name] = AnsibleHost(name=name)
                inventory.hosts[name].vars.update(combined_vars)

    return inventory


# ── Auto-detect and parse ─────────────────────────────────────────────────────

def _is_yaml_inventory(content: str) -> bool:
    """Heuristic — YAML inventories start with a mapping key at column 0."""
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        return not stripped.startswith('[')
    return False


def parse_inventory_file(file_path: str,
                          inventory: Inventory = None) -> Inventory:
    """Parse a single inventory file, auto-detecting format."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        inv = inventory or Inventory()
        inv.errors.append(f"Could not read {file_path}: {e}")
        return inv

    if _is_yaml_inventory(content):
        return parse_yaml_inventory(content, file_path, inventory)
    else:
        return parse_ini(content, file_path, inventory)


def load_inventory(project_root: str) -> Inventory:
    """
    Find and load all inventory files in a project.

    Detection strategy (in order):
    1. Look for ansible.cfg and read [defaults] inventory= setting
    2. Walk the project tree looking for directories named 'inventory'
       or 'inventories' at any depth (up to 4 levels)
    3. Look for common flat inventory filenames at any depth
    4. Load group_vars/ and host_vars/ relative to each inventory found
    """
    inventory = Inventory()
    found_roots = []  # inventory root dirs/files we've found

    # ── Strategy 1: ansible.cfg ───────────────────────────────────────────
    cfg_inventory = _read_ansible_cfg(project_root)
    if cfg_inventory:
        full = cfg_inventory if os.path.isabs(cfg_inventory) \
               else os.path.join(project_root, cfg_inventory)
        full = os.path.normpath(full)
        if os.path.exists(full):
            found_roots.append(full)

    # ── Strategy 2: walk for inventory directories ────────────────────────
    _INV_DIR_NAMES = {'inventory', 'inventories', 'inv'}
    _INV_FILE_NAMES = {'hosts', 'hosts.ini', 'hosts.yml', 'hosts.yaml',
                       'inventory', 'inventory.ini', 'inventory.yml',
                       'inventory.yaml', 'site.hosts'}
    _SKIP_DIRS = {'.git', '__pycache__', 'node_modules', '.tox',
                  'venv', '.venv', '.mypy_cache', 'dist', 'build',
                  'roles', 'tasks', 'handlers', 'templates', 'files',
                  'vars', 'defaults', 'meta', 'library', 'filter_plugins'}

    for dirpath, dirnames, filenames in os.walk(project_root):
        # Limit depth
        depth = dirpath.replace(project_root, '').count(os.sep)
        if depth > 5:
            dirnames.clear()
            continue

        dirnames[:] = [d for d in dirnames
                       if d not in _SKIP_DIRS
                       and not d.startswith('.')]

        # Check if this directory IS an inventory directory
        basename = os.path.basename(dirpath)
        if basename.lower() in _INV_DIR_NAMES and dirpath != project_root:
            if dirpath not in found_roots:
                found_roots.append(dirpath)

        # Check for flat inventory files
        for fn in filenames:
            if fn in _INV_FILE_NAMES:
                fp = os.path.join(dirpath, fn)
                if fp not in found_roots:
                    found_roots.append(fp)

    # ── Strategy 3: content sniffing if nothing found ─────────────────────
    # If we still found nothing, look for any .ini/.yml that looks like
    # an inventory by scanning content
    if not found_roots:
        for dirpath, dirnames, filenames in os.walk(project_root):
            depth = dirpath.replace(project_root, '').count(os.sep)
            if depth > 3:
                dirnames.clear()
                continue
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            for fn in filenames:
                if not fn.endswith(('.ini', '.yml', '.yaml')):
                    continue
                fp = os.path.join(dirpath, fn)
                try:
                    with open(fp, 'r', encoding='utf-8') as f:
                        head = f.read(512)
                    if _looks_like_inventory(head):
                        found_roots.append(fp)
                except Exception:
                    pass

    # ── Parse everything found ────────────────────────────────────────────
    for root in found_roots:
        if os.path.isfile(root):
            parse_inventory_file(root, inventory)
            # Look for group_vars/host_vars next to the file
            _load_group_vars_relative(
                os.path.dirname(root), inventory
            )
        elif os.path.isdir(root):
            # Parse all files in the inventory directory
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [
                    d for d in dirnames
                    if not d.startswith('.')
                    and d not in ('group_vars', 'host_vars')
                ]
                for fn in sorted(filenames):
                    if fn.startswith('.') or fn.endswith(
                            ('.py', '.pyc', '.sh', '.md', '.rst')):
                        continue
                    parse_inventory_file(
                        os.path.join(dirpath, fn), inventory
                    )
            # group_vars/host_vars inside the inventory dir
            _load_group_vars_relative(root, inventory)
            # Also check one level up (e.g. playbooks/group_vars/)
            parent = os.path.dirname(root)
            if parent != project_root:
                _load_group_vars_relative(parent, inventory)

    # Always check project root group_vars/host_vars
    _load_group_vars_relative(project_root, inventory)

    return inventory


def _read_ansible_cfg(project_root: str) -> str:
    """
    Read ansible.cfg and return the inventory= value if set.
    Searches project root and parent directories (up to 3 levels up).
    """
    import configparser
    search_dirs = [project_root]
    parent = project_root
    for _ in range(3):
        parent = os.path.dirname(parent)
        if parent and parent != project_root:
            search_dirs.append(parent)

    for d in search_dirs:
        cfg_path = os.path.join(d, 'ansible.cfg')
        if not os.path.exists(cfg_path):
            continue
        try:
            cfg = configparser.ConfigParser()
            cfg.read(cfg_path)
            inv = cfg.get('defaults', 'inventory', fallback='')
            if inv:
                # Make relative to the cfg file's directory
                if not os.path.isabs(inv):
                    inv = os.path.join(d, inv)
                return os.path.normpath(inv)
        except Exception:
            pass
    return ''


def _looks_like_inventory(content: str) -> bool:
    """Heuristic — does this file look like an Ansible inventory?"""
    indicators = [
        '[', 'ansible_host=', 'ansible_user=',
        ':children]', ':vars]', 'ansible_connection=',
    ]
    return sum(1 for i in indicators if i in content) >= 2


def _load_group_vars_relative(base_dir: str, inventory: Inventory):
    """Load group_vars/ and host_vars/ relative to base_dir."""
    for var_dir in ('group_vars', 'host_vars'):
        full = os.path.join(base_dir, var_dir)
        if os.path.isdir(full):
            load_group_vars(base_dir, inventory)
            break


# ── Effective vars resolver ───────────────────────────────────────────────────

def resolve_host_vars(host: AnsibleHost,
                      inventory: Inventory) -> dict:
    """
    Resolve the effective vars for a host by merging group vars
    in Ansible precedence order:
    all → parent groups → child groups → host vars
    """
    merged = {}

    # Start with 'all' group vars
    all_group = inventory.groups.get('all')
    if all_group:
        merged.update(all_group.vars)

    # Walk groups from least to most specific
    def _collect_group_vars(group_name: str, depth: int = 0):
        if depth > 10:  # prevent infinite recursion
            return
        group = inventory.groups.get(group_name)
        if not group:
            return
        # Recurse into parent groups first
        for parent_name, parent in inventory.groups.items():
            if group_name in parent.children:
                _collect_group_vars(parent_name, depth + 1)
        merged.update(group.vars)

    for group_name in host.groups:
        if group_name != 'all':
            _collect_group_vars(group_name)

    # Host vars win
    merged.update(host.vars)
    return merged