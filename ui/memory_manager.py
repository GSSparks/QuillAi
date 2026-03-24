import json
import os
from datetime import datetime


MEMORY_FILE = os.path.join(os.path.expanduser("~"), ".config", "quillai", "memory.json")

MAX_CONVERSATIONS = 20   # how many past conversation summaries to keep
MAX_FACTS = 50           # how many codebase/preference facts to keep


class MemoryManager:
    def __init__(self):
        self.memory = self._load()

    def _load(self):
        if os.path.exists(MEMORY_FILE):
            try:
                with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "facts": [],           # persistent facts about the project/user
            "conversations": [],   # summaries of past chats
        }

    def _save(self):
        os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(self.memory, f, indent=2)

    # ── Facts ────────────────────────────────────────────────────────────
    def add_fact(self, fact: str):
        """Add a persistent fact. Avoids exact duplicates."""
        fact = fact.strip()
        if fact and fact not in self.memory["facts"]:
            self.memory["facts"].append(fact)
            # Trim to limit
            if len(self.memory["facts"]) > MAX_FACTS:
                self.memory["facts"] = self.memory["facts"][-MAX_FACTS:]
            self._save()

    def remove_fact(self, index: int):
        if 0 <= index < len(self.memory["facts"]):
            self.memory["facts"].pop(index)
            self._save()

    def get_facts(self) -> list:
        return self.memory["facts"]

    # ── Conversations ─────────────────────────────────────────────────────
    def add_conversation(self, summary: str, tags: list = None):
        """Store a summary of a completed conversation."""
        entry = {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "summary": summary.strip(),
            "tags": tags or [],
        }
        self.memory["conversations"].append(entry)
        if len(self.memory["conversations"]) > MAX_CONVERSATIONS:
            self.memory["conversations"] = self.memory["conversations"][-MAX_CONVERSATIONS:]
        self._save()

    def get_conversations(self) -> list:
        return self.memory["conversations"]

    def clear_conversations(self):
        self.memory["conversations"] = []
        self._save()

    def clear_all(self):
        self.memory = {"facts": [], "conversations": []}
        self._save()

    # ── Context Builder ───────────────────────────────────────────────────
    def build_memory_context(self) -> str:
        """Returns a formatted memory block to inject into prompts."""
        parts = []

        if self.memory["facts"]:
            facts_text = "\n".join(f"- {f}" for f in self.memory["facts"])
            parts.append(f"[Things I know about this project and your preferences]\n{facts_text}")

        if self.memory["conversations"]:
            recent = self.memory["conversations"][-5:]  # last 5 conversations
            conv_lines = []
            for c in recent:
                tags = f" [{', '.join(c['tags'])}]" if c.get("tags") else ""
                conv_lines.append(f"- {c['date']}{tags}: {c['summary']}")
            conv_text = "\n".join(conv_lines)
            parts.append(f"[Recent conversation history]\n{conv_text}")

        if not parts:
            return ""

        return "[Memory]\n" + "\n\n".join(parts)