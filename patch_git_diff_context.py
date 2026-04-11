#!/usr/bin/env python3
"""
patch_git_diff_context.py
=========================
Injects recent git diff into AI chat context automatically when
the query looks like a debug/review/change question.

Run from the project root:
    python3 patch_git_diff_context.py

Files changed:
  - ui/git_panel.py  — add get_current_diff() public method
  - main.py          — inject diff block in _launch context assembly
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent


def patch(path, old, new, description):
    if not path.exists():
        print("  -  " + description + "  (file not found, skipping)")
        return False
    text = path.read_text(encoding="utf-8")
    if old not in text:
        print("  x  " + description + "  (marker not found -- already patched?)")
        return False
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("  ok " + description)
    return True


GP = ROOT / "ui" / "git_panel.py"
MP = ROOT / "main.py"


# ── 1. Add get_current_diff() to GitDockWidget ────────────────────────────────
# Insert right before _get_diff_for_ai so they sit together

patch(
    GP,
    "    def _get_diff_for_ai(self) -> str:",
    (
        "    def get_current_diff(self, cap: int = 3000) -> str:\n"
        "        \"\"\"\n"
        "        Return a compact diff of current working tree changes.\n"
        "        Used by the chat context engine — no UI state required.\n"
        "        Tries unstaged first, then staged, then HEAD.\n"
        "        \"\"\"\n"
        "        for args in (\n"
        "            ['git', 'diff'],\n"
        "            ['git', 'diff', '--cached'],\n"
        "            ['git', 'diff', 'HEAD'],\n"
        "        ):\n"
        "            ok, diff = self.run_git_command(args)\n"
        "            if ok and diff.strip():\n"
        "                return diff[:cap] + (\n"
        "                    \"\\n...(truncated)...\" if len(diff) > cap else \"\"\n"
        "                )\n"
        "        return \"\"\n"
        "\n"
        "    def _get_diff_for_ai(self) -> str:"
    ),
    "Add get_current_diff() to GitDockWidget",
)


# ── 2. Inject diff context in main.py _launch ────────────────────────────────
# Slot it in right after gitlab_block, before prompt_with_context assembly

patch(
    MP,
    (
        "            faq_block    = (f\"\\n\\n{faq_ctx}\"    if faq_ctx    else \"\")\n"
        "            gitlab_block = (f\"\\n\\n{gitlab_ctx}\"  if gitlab_ctx else \"\")\n"
        "            symbol_block = (symbol_ctx + '\\n\\n'   if symbol_ctx else '')\n"
        "            prompt_with_context = f\"{user_text}\\n\\n{symbol_block}{context}{faq_block}{gitlab_block}\""
    ),
    (
        "            faq_block    = (f\"\\n\\n{faq_ctx}\"    if faq_ctx    else \"\")\n"
        "            gitlab_block = (f\"\\n\\n{gitlab_ctx}\"  if gitlab_ctx else \"\")\n"
        "            symbol_block = (symbol_ctx + '\\n\\n'   if symbol_ctx else '')\n"
        "\n"
        "            # Git diff context — inject when query is debug/change related\n"
        "            diff_block = \"\"\n"
        "            if (hasattr(self, 'git_dock') and self.git_dock\n"
        "                    and self.git_dock.repo_path\n"
        "                    and _query_wants_diff(user_text)):\n"
        "                diff = self.git_dock.get_current_diff(cap=3000)\n"
        "                if diff:\n"
        "                    diff_block = (\n"
        "                        f\"\\n\\n[Recent Changes]\\n\"\n"
        "                        f\"```diff\\n{diff}\\n```\"\n"
        "                    )\n"
        "\n"
        "            prompt_with_context = f\"{user_text}\\n\\n{symbol_block}{context}{faq_block}{gitlab_block}{diff_block}\""
    ),
    "Inject git diff block in _launch context assembly",
)


# ── 3. Add _query_wants_diff() helper near top of main.py ────────────────────

patch(
    MP,
    "MAX_FILE_SIZE = 6000  # characters",
    (
        "MAX_FILE_SIZE = 6000  # characters\n"
        "\n"
        "\n"
        "def _query_wants_diff(text: str) -> bool:\n"
        "    \"\"\"\n"
        "    Return True if the user query is likely about recent changes,\n"
        "    bugs introduced by edits, or code review — i.e. git diff is useful.\n"
        "    \"\"\"\n"
        "    text = text.lower()\n"
        "    triggers = [\n"
        "        'what did i change', 'what have i changed', 'my changes',\n"
        "        'recent changes', 'what changed', 'diff',\n"
        "        'why did i break', 'why is it broken', 'what broke',\n"
        "        'review my', 'review the change', 'look at my change',\n"
        "        'bug i introduced', 'regression', 'since my last',\n"
        "        'what i modified', 'what was modified', 'uncommitted',\n"
        "        'staged', 'unstaged', 'working tree',\n"
        "    ]\n"
        "    return any(t in text for t in triggers)"
    ),
    "Add _query_wants_diff() helper",
)


print("")
print("Patch complete. Restart QuillAI to test.")
print("")
print("The AI will now automatically include your recent git diff when")
print("you ask questions like:")
print("  'why is this broken?'")
print("  'review my changes'")
print("  'what did I change?'")
print("  'what broke since my last edit?'")