import json
import os
import hashlib

SESSION_DIR = os.path.join(os.path.expanduser("~"), ".config", "quillai", "sessions")


def _project_session_file(project_path: str) -> str:
    """Returns a unique session file path for a given project."""
    path_hash = hashlib.md5(project_path.encode()).hexdigest()[:12]
    name = os.path.basename(project_path.rstrip('/'))
    return os.path.join(SESSION_DIR, f"{name}_{path_hash}.json")


def _global_session_file() -> str:
    return os.path.join(SESSION_DIR, "global.json")


def save_session(tabs, active_index, project_path=None):
    """Save the current tab session, scoped to the project if one is open."""
    tab_data = []
    for path, cursor_pos in tabs:
        if path and os.path.exists(path):
            tab_data.append({
                "path": path,
                "cursor": cursor_pos,
            })

    session = {
        "tabs": tab_data,
        "active_tab": active_index,
        "project_path": project_path,
    }

    os.makedirs(SESSION_DIR, exist_ok=True)
    target = _project_session_file(project_path) if project_path else _global_session_file()

    try:
        with open(target, "w", encoding="utf-8") as f:
            json.dump(session, f, indent=2)
    except Exception as e:
        print(f"Could not save session: {e}")


def load_session(project_path=None) -> dict:
    """Load session for the given project, falling back to global."""
    candidates = []

    if project_path:
        candidates.append(_project_session_file(project_path))

    candidates.append(_global_session_file())

    for path in candidates:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                continue

    return {}


def clear_session(project_path=None):
    target = _project_session_file(project_path) if project_path else _global_session_file()
    if os.path.exists(target):
        os.remove(target)


def list_project_sessions() -> list:
    """Returns a list of all saved project sessions."""
    if not os.path.exists(SESSION_DIR):
        return []
    sessions = []
    for filename in os.listdir(SESSION_DIR):
        if filename.endswith(".json") and filename != "global.json":
            path = os.path.join(SESSION_DIR, filename)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                project_path = data.get("project_path", "")
                tab_count = len(data.get("tabs", []))
                if project_path:
                    sessions.append({
                        "project_path": project_path,
                        "tab_count": tab_count,
                        "file": path,
                    })
            except Exception:
                continue
    return sessions
    
def set(self, key: str, value):
    self._settings[key] = value
    self._save()