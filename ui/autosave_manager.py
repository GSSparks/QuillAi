"""
ui/autosave_manager.py

Periodic autosave and crash recovery for QuillAI.

Autosave:
    Every 2 minutes, any editor with unsaved changes writes its content
    to ~/.config/quillai/autosave/<hash>.json. The file records the
    original path, content, and cursor position.

Recovery:
    On startup, check for autosave files newer than the last clean save
    of each file. Restore silently — no dialogs. A status bar message
    lists what was recovered.

Cleanup:
    On clean save or clean close, the autosave file is deleted.
    On app exit without crash, all autosave files are cleared.
"""

import hashlib
import json
import os
import time
from datetime import datetime

AUTOSAVE_DIR = os.path.join(
    os.path.expanduser("~"), ".config", "quillai", "autosave"
)
AUTOSAVE_INTERVAL_MS = 2 * 60 * 1000   # 2 minutes


def _autosave_path(file_path: str) -> str:
    """Stable autosave filename for a given source file path."""
    h = hashlib.md5(file_path.encode()).hexdigest()[:16]
    name = os.path.basename(file_path).replace(".", "_")
    return os.path.join(AUTOSAVE_DIR, f"{name}_{h}.json")


def _untitled_autosave_path(tab_index: int) -> str:
    """Autosave path for an unsaved (Untitled) tab."""
    return os.path.join(AUTOSAVE_DIR, f"untitled_{tab_index}.json")


class AutosaveManager:
    """
    Owned by CodeEditor. Drives periodic autosave and startup recovery.
    """

    def __init__(self, get_editors_fn, status_fn):
        """
        get_editors_fn: callable() → list of (index, editor) pairs
        status_fn:      callable(message, timeout_ms) — shows status bar msg
        """
        os.makedirs(AUTOSAVE_DIR, exist_ok=True)
        self._get_editors = get_editors_fn
        self._show_status = status_fn

    # ─────────────────────────────────────────────────────────────
    # Autosave
    # ─────────────────────────────────────────────────────────────

    def save_all(self):
        """
        Write autosave entries for every editor with unsaved changes.
        Called by the QTimer every 2 minutes.
        """
        for index, editor in self._get_editors():
            if not hasattr(editor, "is_dirty"):
                continue
            if not editor.is_dirty():
                continue

            content    = editor.toPlainText()
            file_path  = getattr(editor, "file_path", None)
            cursor_pos = editor.textCursor().position()

            if file_path:
                path = _autosave_path(file_path)
            else:
                path = _untitled_autosave_path(index)

            entry = {
                "file_path":  file_path,
                "content":    content,
                "cursor_pos": cursor_pos,
                "ts":         time.time(),
                "saved_at":   datetime.now().isoformat(),
            }
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(entry, f, indent=2)
            except Exception as e:
                print(f"[autosave] write error: {e}")

    def clear(self, file_path: str):
        """
        Delete the autosave entry for a file.
        Call after a successful clean save or tab close.
        """
        if not file_path:
            return
        path = _autosave_path(file_path)
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass

    def clear_untitled(self, tab_index: int):
        """Delete autosave for an untitled tab."""
        path = _untitled_autosave_path(tab_index)
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass

    def clear_all(self):
        """
        Remove all autosave files — call on clean app exit.
        On crash this is never called, so files persist for recovery.
        """
        try:
            for fname in os.listdir(AUTOSAVE_DIR):
                if fname.endswith(".json"):
                    os.remove(os.path.join(AUTOSAVE_DIR, fname))
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────────
    # Recovery
    # ─────────────────────────────────────────────────────────────

    def find_recoverable(self) -> list[dict]:
        """
        Return a list of autosave entries that should be restored.

        An entry is recoverable if:
          - Its autosave file exists
          - The autosaved content differs from the file on disk
            (or the file no longer exists — deleted after crash)
          - The autosave is newer than the file's last modification time

        Returns list of entry dicts with an added "autosave_path" key.
        """
        recoverable = []
        try:
            files = os.listdir(AUTOSAVE_DIR)
        except Exception:
            return []

        for fname in files:
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(AUTOSAVE_DIR, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    entry = json.load(f)
            except Exception:
                continue

            entry["autosave_path"] = fpath
            file_path = entry.get("file_path")

            if file_path:
                # Named file — check if autosave is newer and different
                if os.path.exists(file_path):
                    file_mtime = os.path.getmtime(file_path)
                    if entry.get("ts", 0) <= file_mtime:
                        # File was saved after autosave — not a crash recovery
                        continue
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            disk_content = f.read()
                        if disk_content == entry.get("content", ""):
                            continue   # content matches, nothing to recover
                    except Exception:
                        pass
                # File doesn't exist or autosave is newer → recoverable
                recoverable.append(entry)
            else:
                # Untitled tab — always recoverable if content is non-empty
                if entry.get("content", "").strip():
                    recoverable.append(entry)

        return recoverable

    def restore(self, open_tab_fn) -> int:
        """
        Silently restore all recoverable autosave entries.

        open_tab_fn: callable(name, content, path, cursor_pos)
                     Opens a tab and positions the cursor.

        Returns the number of tabs restored.
        """
        entries = self.find_recoverable()
        if not entries:
            return 0

        restored = []
        for entry in entries:
            file_path  = entry.get("file_path")
            content    = entry.get("content", "")
            cursor_pos = entry.get("cursor_pos", 0)

            if file_path:
                name = os.path.basename(file_path) + " ↩"  # ↩ marks recovered
            else:
                name = "Untitled (recovered)"

            try:
                open_tab_fn(name, content, file_path, cursor_pos)
                restored.append(name)
            except Exception as e:
                print(f"[autosave] restore error: {e}")

        if restored:
            names = ", ".join(restored)
            self._show_status(
                f"↩  Recovered {len(restored)} file(s): {names}", 8000
            )

        return len(restored)