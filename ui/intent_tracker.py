import re
import os
from datetime import datetime


class IntentTracker:
    """
    Tracks session-level intent signals and builds a compact context
    prefix that gets prepended to every inline completion prompt.
    Caches the result until sources change.
    """

    MAX_CHAT_EXCHANGES = 3    # how many recent chat exchanges to include
    MAX_FACTS = 8             # how many memory facts to include
    MAX_SYMBOLS = 10          # how many recently visited symbols to track
    MAX_FILES = 5             # how many recently edited files to track

    def __init__(self, memory_manager=None):
        self.memory_manager = memory_manager

        # Session state
        self._recent_chat = []        # list of (user, ai) tuples
        self._recent_files = []       # recently edited file paths
        self._recent_symbols = []     # recently visited function/class names

        # Cache
        self._cache = None
        self._cache_key = None

    # ── Signal collectors ─────────────────────────────────────────────────

    def record_chat_exchange(self, user_text: str, ai_text: str):
        """Call this after each completed chat exchange."""
        self._recent_chat.append((
            user_text[:200].strip(),
            ai_text[:300].strip(),
        ))
        # Keep only the last N exchanges
        self._recent_chat = self._recent_chat[-self.MAX_CHAT_EXCHANGES:]
        self._invalidate_cache()

    def record_file_edit(self, file_path: str):
        """Call this when the user switches tabs or saves."""
        if not file_path:
            return
        # Move to front, deduplicate
        self._recent_files = [f for f in self._recent_files if f != file_path]
        self._recent_files.insert(0, file_path)
        self._recent_files = self._recent_files[:self.MAX_FILES]
        self._invalidate_cache()

    def record_cursor_symbol(self, symbol_name: str):
        """Call this when cursor enters a function or class definition."""
        if not symbol_name or len(symbol_name) < 2:
            return
        self._recent_symbols = [s for s in self._recent_symbols if s != symbol_name]
        self._recent_symbols.insert(0, symbol_name)
        self._recent_symbols = self._recent_symbols[:self.MAX_SYMBOLS]
        self._invalidate_cache()

    def _invalidate_cache(self):
        self._cache = None
        self._cache_key = None

    # ── Cache key ─────────────────────────────────────────────────────────

    def _compute_cache_key(self):
        facts = self.memory_manager.get_facts() if self.memory_manager else []
        return (
            tuple(u[:50] for u, _ in self._recent_chat),
            tuple(self._recent_files),
            tuple(self._recent_symbols),
            tuple(facts[:self.MAX_FACTS]),
        )

    # ── Context builder ───────────────────────────────────────────────────

    def build_intent_context(self, current_file_path: str = "", language: str = "") -> str:
        """
        Returns a compact intent prefix string.
        Uses cache if nothing has changed since last call.
        """
        key = self._compute_cache_key()
        if self._cache is not None and key == self._cache_key:
            return self._cache

        parts = []

        # 1. Language + current file
        if language and language != "code":
            parts.append(f"Language: {language}")

        if current_file_path:
            fname = os.path.basename(current_file_path)
            parts.append(f"Current file: {fname}")

        # 2. Memory facts (preferences and project knowledge)
        facts = []
        if self.memory_manager:
            facts = self.memory_manager.get_facts()[:self.MAX_FACTS]
        if facts:
            facts_str = "; ".join(facts)
            parts.append(f"Developer preferences: {facts_str}")

        # 3. Recent files edited this session
        recent_file_names = [
            os.path.basename(f) for f in self._recent_files
            if f != current_file_path
        ][:3]
        if recent_file_names:
            parts.append(f"Recently edited: {', '.join(recent_file_names)}")

        # 4. Recently visited symbols (functions/classes)
        if self._recent_symbols:
            parts.append(f"Recently working in: {', '.join(self._recent_symbols[:5])}")

        # 5. Recent chat context — most valuable for intent
        if self._recent_chat:
            chat_lines = []
            for user, ai in self._recent_chat[-2:]:  # last 2 exchanges
                # Truncate aggressively — just enough to convey topic
                user_short = user[:120].replace('\n', ' ')
                ai_short = ai[:120].replace('\n', ' ')
                chat_lines.append(f"  Q: {user_short}")
                chat_lines.append(f"  A: {ai_short}")
            parts.append("Recent discussion:\n" + "\n".join(chat_lines))

        if not parts:
            self._cache = ""
            self._cache_key = key
            return ""

        result = "[Session context]\n" + "\n".join(parts) + "\n"
        self._cache = result
        self._cache_key = key
        return result

    def get_current_symbol(self, editor_text: str, cursor_pos: int) -> str:
        """
        Infer which function or class the cursor is currently inside.
        Used to auto-record the symbol without AST parsing overhead.
        """
        text_before = editor_text[:cursor_pos]
        lines = text_before.split('\n')

        for line in reversed(lines):
            stripped = line.strip()
            # Match def or class at any indent level
            m = re.match(r'^(def|class|async def)\s+(\w+)', stripped)
            if m:
                return m.group(2)
        return ""