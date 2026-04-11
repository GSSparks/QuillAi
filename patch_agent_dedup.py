#!/usr/bin/env python3
"""
patch_agent_dedup.py
====================
Fixes double-render of agent final answer and status panel.

Run from the project root:
    python3 patch_agent_dedup.py
"""

from pathlib import Path

ROOT = Path(__file__).parent


def patch(path, old, new, description):
    if not path.exists():
        print(f"  -  {description}  (file not found)")
        return False
    text = path.read_text(encoding="utf-8")
    if old not in text:
        print(f"  x  {description}  (marker not found)")
        return False
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"  ok {description}")
    return True


MP = ROOT / "main.py"
CR = ROOT / "ui" / "chat_renderer.py"


# ── 1. Set _skip_stream_finished flag when agent finishes ─────────────────────

patch(
    MP,
    (
        "                self.chat_worker.tool_status.connect(self.append_agent_status)\n"
        "                self.chat_worker.write_ops.connect(self._on_agent_write_ops)\n"
    ),
    (
        "                self.chat_worker.tool_status.connect(self.append_agent_status)\n"
        "                self.chat_worker.write_ops.connect(self._on_agent_write_ops)\n"
        "                self.chat_worker.finished.connect(\n"
        "                    lambda: setattr(self, '_skip_stream_finished', True)\n"
        "                )\n"
    ),
    "Set _skip_stream_finished on agent finish",
)


# ── 2. Skip re-render in chat_stream_finished for agent mode ──────────────────

patch(
    CR,
    (
        "    def chat_stream_finished(self):\n"
        "        print(f\"[stream_finished] full_response tail: {self.current_ai_raw_text[-200:]!r}\")\n"
        "        from PyQt6.QtGui import QTextCursor\n"
        "        full_response = self.current_ai_raw_text"
    ),
    (
        "    def chat_stream_finished(self):\n"
        "        # Agent mode — final answer already rendered, just clean up\n"
        "        if getattr(self, '_skip_stream_finished', False):\n"
        "            self._skip_stream_finished = False\n"
        "            self.current_ai_raw_text = \"\"\n"
        "            self._stream_buffer      = \"\"\n"
        "            self._stream_start_pos   = 0\n"
        "            self.memory_manager.save_chat_history(self.chat_history.toHtml())\n"
        "            return\n"
        "\n"
        "        from PyQt6.QtGui import QTextCursor\n"
        "        full_response = self.current_ai_raw_text"
    ),
    "Skip re-render in chat_stream_finished for agent mode",
)


# ── 3. Remove stale debug print ───────────────────────────────────────────────

patch(
    CR,
    "        print(f\"[stream_finished] full_response tail: {self.current_ai_raw_text[-200:]!r}\")\n",
    "",
    "Remove debug print from chat_stream_finished",
)

print("")
print("Done. Restart QuillAI — agent answers should no longer appear twice.")