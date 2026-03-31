import hashlib
import json
import os
import re
from datetime import datetime


MEMORY_DIR = os.path.join(os.path.expanduser("~"), ".config", "quillai", "memory")
GLOBAL_MEMORY_FILE = os.path.join(MEMORY_DIR, "global.json")

MAX_CONVERSATIONS  = 50
MAX_FACTS          = 100
MAX_TURNS          = 20   # raw turns kept in the turn buffer before compression
RECENT_TURNS_IN_CTX = 6   # how many recent turns are always injected verbatim
COMPRESS_THRESHOLD  = 20  # compress oldest half when buffer exceeds this


class MemoryManager:
    def __init__(self, project_path=None, llm_fn=None):
        """
        llm_fn: optional callable(prompt: str) -> str
                Used for LLM-based compression of old turns into summaries.
                Falls back to a simple heuristic summary if not provided.
        """
        os.makedirs(MEMORY_DIR, exist_ok=True)
        self.project_path = project_path
        self.llm_fn       = llm_fn
        self.global_memory  = self._load(GLOBAL_MEMORY_FILE)
        self.project_memory = self._load(self._project_file()) if project_path else None

        # Ensure turn buffer key exists in loaded data
        self._ensure_turns_key(self.global_memory)
        if self.project_memory is not None:
            self._ensure_turns_key(self.project_memory)

    # ─────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────

    def _ensure_turns_key(self, memory: dict):
        """Back-compat: add 'turns' key if loading an older memory file."""
        if "turns" not in memory:
            memory["turns"] = []

    def _project_file(self):
        if not self.project_path:
            return None
        path_hash = hashlib.md5(self.project_path.encode()).hexdigest()[:12]
        name = os.path.basename(self.project_path.rstrip("/\\"))
        return os.path.join(MEMORY_DIR, f"{name}_{path_hash}.json")

    def _active_memory(self):
        """Return the memory dict that should receive new turns/conversations."""
        if self.project_path and self.project_memory is not None:
            return self.project_memory
        return self.global_memory

    def _save_active(self):
        if self.project_path and self.project_memory is not None:
            self._save(self.project_memory, self._project_file())
        else:
            self._save(self.global_memory, GLOBAL_MEMORY_FILE)

    def set_project(self, project_path):
        """Call this when the user opens a folder."""
        self.project_path   = project_path
        self.project_memory = self._load(self._project_file())
        self._ensure_turns_key(self.project_memory)

    def _load(self, path):
        if path and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"facts": [], "conversations": [], "turns": []}

    def _save(self, memory, path):
        if not path:
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(memory, f, indent=2)

    def _save_global(self):
        self._save(self.global_memory, GLOBAL_MEMORY_FILE)

    def _save_project(self):
        if self.project_memory is not None:
            self._save(self.project_memory, self._project_file())

    # ─────────────────────────────────────────────────────────────
    # Turn Buffer  (replaces chat_history_store.py)
    # ─────────────────────────────────────────────────────────────

    def add_turn(self, role: str, content: str):
        """
        Record a single message turn (role: 'user' or 'assistant').
        Automatically compresses old turns once the buffer grows large.
        Call this after every user message and every assistant response.
        """
        mem = self._active_memory()
        mem["turns"].append({
            "role":    role,
            "content": content.strip(),
            "ts":      datetime.now().isoformat(),
        })

        # Hard cap — trim to MAX_TURNS before compression check
        if len(mem["turns"]) > MAX_TURNS:
            mem["turns"] = mem["turns"][-MAX_TURNS:]

        self._save_active()
        self.maybe_compress()

    def get_recent_turns(self, n: int = RECENT_TURNS_IN_CTX) -> list:
        """Return the last n turns from the active memory store."""
        return self._active_memory()["turns"][-n:]

    def clear_turns(self):
        """Clear the turn buffer for the active scope (new session)."""
        self._active_memory()["turns"] = []
        self._save_active()

    # ─────────────────────────────────────────────────────────────
    # Compression  (turns → conversation summaries)
    # ─────────────────────────────────────────────────────────────

    def maybe_compress(self):
        """
        When the turn buffer exceeds COMPRESS_THRESHOLD, compress the
        oldest half into a conversation summary and prune those turns.
        Uses the LLM if available, otherwise falls back to a heuristic.
        """
        mem   = self._active_memory()
        turns = mem["turns"]

        if len(turns) < COMPRESS_THRESHOLD:
            return

        mid         = len(turns) // 2
        to_compress = turns[:mid]
        mem["turns"] = turns[mid:]   # keep the recent half

        summary = self._summarize_turns(to_compress)
        if summary:
            # Reuse existing add_conversation — stores to the right scope
            user_msgs = [t["content"] for t in to_compress if t["role"] == "user"]
            ai_msgs   = [t["content"] for t in to_compress if t["role"] == "assistant"]
            self.add_conversation(
                summary      = summary,
                user_message = user_msgs[-1] if user_msgs else "",
                ai_response  = ai_msgs[-1]   if ai_msgs   else "",
                tags         = ["auto-compressed"],
            )

        self._save_active()

    def _summarize_turns(self, turns: list) -> str:
        """
        Summarize a list of turn dicts into a single string.
        Uses LLM if available, otherwise extracts the first user message
        and first assistant sentence as a heuristic summary.
        """
        block = "\n".join(
            f"{t['role'].upper()}: {t['content']}" for t in turns
        )

        if self.llm_fn:
            prompt = (
                "Summarize the following coding assistant conversation concisely "
                "(2-3 sentences). Focus on: decisions made, code changed, "
                "problems solved, open questions.\n\n" + block
            )
            try:
                return self.llm_fn(prompt).strip()
            except Exception:
                pass

        # Heuristic fallback — first user message + first assistant sentence
        user_line = next(
            (t["content"][:120] for t in turns if t["role"] == "user"), ""
        )
        ai_line = next(
            (t["content"].split(".")[0][:120] for t in turns if t["role"] == "assistant"), ""
        )
        if user_line:
            return f"User asked: {user_line}" + (f". Assistant: {ai_line}" if ai_line else "")
        return ""

    # ─────────────────────────────────────────────────────────────
    # Chat history HTML  (project-scoped, replaces chat_history_store.py)
    # ─────────────────────────────────────────────────────────────

    def get_chat_history_file(self) -> str:
        if self.project_path:
            path_hash = hashlib.md5(self.project_path.encode()).hexdigest()[:12]
            name      = os.path.basename(self.project_path.rstrip("/\\"))
            return os.path.join(MEMORY_DIR, f"chat_{name}_{path_hash}.html")
        return os.path.join(MEMORY_DIR, "chat_global.html")

    def save_chat_history(self, html: str):
        """Persist chat panel HTML for the current project."""
        os.makedirs(MEMORY_DIR, exist_ok=True)
        try:
            with open(self.get_chat_history_file(), "w", encoding="utf-8") as f:
                f.write(html)
        except Exception as e:
            print(f"Could not save chat history: {e}")

    def load_chat_history(self) -> str:
        """Load chat panel HTML for the current project."""
        path = self.get_chat_history_file()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception:
                pass
        return ""

    # ─────────────────────────────────────────────────────────────
    # Facts
    # ─────────────────────────────────────────────────────────────

    def add_fact(self, fact: str, project_scoped=False):
        fact   = fact.strip()
        target = (
            self.project_memory
            if (project_scoped and self.project_memory is not None)
            else self.global_memory
        )
        if fact and fact not in target["facts"]:
            target["facts"].append(fact)
            if len(target["facts"]) > MAX_FACTS:
                target["facts"] = target["facts"][-MAX_FACTS:]
            if project_scoped and self.project_memory is not None:
                self._save_project()
            else:
                self._save_global()

    def remove_fact(self, index: int, project_scoped=False):
        target = (
            self.project_memory
            if (project_scoped and self.project_memory is not None)
            else self.global_memory
        )
        if 0 <= index < len(target["facts"]):
            target["facts"].pop(index)
            if project_scoped:
                self._save_project()
            else:
                self._save_global()

    def get_facts(self, include_project=True) -> list:
        facts = list(self.global_memory["facts"])
        if include_project and self.project_memory:
            for f in self.project_memory["facts"]:
                if f not in facts:
                    facts.append(f)
        return facts

    def get_global_facts(self) -> list:
        return self.global_memory["facts"]

    def get_project_facts(self) -> list:
        return self.project_memory["facts"] if self.project_memory else []

    # ─────────────────────────────────────────────────────────────
    # Conversations (summaries of past exchanges)
    # ─────────────────────────────────────────────────────────────

    def add_conversation(self, summary: str, user_message: str = "",
                         ai_response: str = "", tags: list = None):
        entry = {
            "date":         datetime.now().strftime("%Y-%m-%d %H:%M"),
            "summary":      summary.strip(),
            "user_message": user_message.strip(),
            "ai_response":  ai_response.strip(),
            "tags":         tags or [],
        }
        target = self._active_memory()
        target["conversations"].append(entry)
        if len(target["conversations"]) > MAX_CONVERSATIONS:
            target["conversations"] = target["conversations"][-MAX_CONVERSATIONS:]
        self._save_active()

    def get_conversations(self) -> list:
        convs = list(self.global_memory["conversations"])
        if self.project_path and self.project_memory:
            convs += self.project_memory["conversations"]
        convs.sort(key=lambda x: x.get("date", ""), reverse=True)
        return convs

    def search_conversations(self, query: str, limit=5) -> list:
        query_words = set(re.findall(r"\w+", query.lower()))
        scored = []
        for conv in self.get_conversations():
            summary_words = set(re.findall(r"\w+", conv["summary"].lower()))
            score = len(query_words & summary_words)
            if score > 0:
                scored.append((score, conv))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored[:limit]]

    def clear_conversations(self):
        self.global_memory["conversations"] = []
        if self.project_memory:
            self.project_memory["conversations"] = []
        self._save_global()
        self._save_project()

    def clear_all(self):
        self.global_memory  = {"facts": [], "conversations": [], "turns": []}
        if self.project_memory is not None:
            self.project_memory = {"facts": [], "conversations": [], "turns": []}
        self._save_global()
        self._save_project()

    # ─────────────────────────────────────────────────────────────
    # Auto-extraction  (heuristic fact mining from exchanges)
    # ─────────────────────────────────────────────────────────────

    def extract_facts_from_exchange(self, user_text: str, ai_response: str) -> list:
        facts    = []
        patterns = [
            (r"i (always|prefer|like to|want to|use)\s+([^.!?\n]{5,60})", user_text),
            (r"i('m| am) using\s+([^.!?\n]{5,60})",                        user_text),
            (r"we (always|prefer|use)\s+([^.!?\n]{5,60})",                 user_text),
            (r"this project (uses|is built with|requires)\s+([^.!?\n]{5,60})", user_text),
        ]
        for pattern, source in patterns:
            for match in re.finditer(pattern, source.lower()):
                start   = max(0, match.start() - 10)
                end     = min(len(source), match.end() + 20)
                snippet = source[start:end].strip().capitalize()
                if len(snippet) > 10:
                    facts.append(snippet)
        return facts[:3]

    # ─────────────────────────────────────────────────────────────
    # Context Builder  (called by ContextEngine)
    # ─────────────────────────────────────────────────────────────

    def build_memory_context(self, query: str = "") -> str:
        """
        Assembles memory into a context block for the LLM prompt.

        Layer 1 — Facts (always included, cheap tokens)
        Layer 2 — Recent turns verbatim (short-term chat coherence)
        Layer 3 — Relevant past conversation summaries (long-term recall)
        """
        parts = []

        # ── Layer 1: Facts ─────────────────────────────────────────
        global_facts  = self.get_global_facts()
        project_facts = self.get_project_facts()

        if global_facts:
            parts.append(
                "[User preferences]\n"
                + "\n".join(f"- {f}" for f in global_facts)
            )

        if project_facts:
            name = os.path.basename(self.project_path) if self.project_path else "this project"
            parts.append(
                f"[Facts about {name}]\n"
                + "\n".join(f"- {f}" for f in project_facts)
            )

        # ── Layer 2: Recent turns (verbatim) ───────────────────────
        recent = self.get_recent_turns(RECENT_TURNS_IN_CTX)
        if recent:
            lines = "\n".join(
                f"{t['role'].upper()}: {t['content']}" for t in recent
            )
            parts.append(f"[Recent conversation]\n{lines}")

        # ── Layer 3: Relevant past summaries ───────────────────────
        relevant = (
            self.search_conversations(query, limit=3)
            if query
            else self.get_conversations()[:3]
        )
        if relevant:
            lines = "\n".join(
                "- {}{}: {}".format(
                    c["date"],
                    f" [{', '.join(c['tags'])}]" if c.get("tags") else "",
                    c["summary"],
                )
                for c in relevant
            )
            parts.append(f"[Relevant past conversations]\n{lines}")

        return ("[Memory]\n" + "\n\n".join(parts)) if parts else ""