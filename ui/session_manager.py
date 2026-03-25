import json
import os

SESSION_FILE = os.path.join(os.path.expanduser("~"), ".config", "quillai", "session.json")


def save_session(tabs, active_index, project_path=None):
    """Save the current session to disk."""
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

    os.makedirs(os.path.dirname(SESSION_FILE), exist_ok=True)
    try:
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(session, f, indent=2)
    except Exception as e:
        print(f"Could not save session: {e}")


def load_session() -> dict:
    """Load the last session. Returns empty dict if none exists."""
    if not os.path.exists(SESSION_FILE):
        return {}
    try:
        with open(SESSION_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def clear_session():
    if os.path.exists(SESSION_FILE):
        os.remove(SESSION_FILE)