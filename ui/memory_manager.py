import json
import os
import re
from datetime import datetime


MEMORY_DIR = os.path.join(os.path.expanduser("~"), ".config", "quillai", "memory")
GLOBAL_MEMORY_FILE = os.path.join(MEMORY_DIR, "global.json")

MAX_CONVERSATIONS = 50
MAX_FACTS = 100


class MemoryManager:
    def __init__(self, project_path=None):
        os.makedirs(MEMORY_DIR, exist_ok=True)
        self.project_path = project_path
        self.global_memory = self._load(GLOBAL_MEMORY_FILE)
        self.project_memory = self._load(self._project_file()) if project_path else None

    def _project_file(self):
        if not self.project_path:
            return None
        # Use a hash of the path as the filename so it's safe for all OSes
        import hashlib
        path_hash = hashlib.md5(self.project_path.encode()).hexdigest()[:12]
        name = os.path.basename(self.project_path)
        return os.path.join(MEMORY_DIR, f"{name}_{path_hash}.json")

    def set_project(self, project_path):
        """Call this when the user opens a folder."""
        self.project_path = project_path
        self.project_memory = self._load(self._project_file())

    def _load(self, path):
        if path and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"facts": [], "conversations": []}

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

    # ── Facts ─────────────────────────────────────────────────────────────
    def add_fact(self, fact: str, project_scoped=False):
        fact = fact.strip()
        if not fact:
            return
        target = self.project_memory if (project_scoped and self.project_memory is not None) else self.global_memory
        if fact not in target["facts"]:
            target["facts"].append(fact)
            if len(target["facts"]) > MAX_FACTS:
                target["facts"] = target["facts"][-MAX_FACTS:]
            if project_scoped and self.project_memory is not None:
                self._save_project()
            else:
                self._save_global()

    def remove_fact(self, index: int, project_scoped=False):
        target = self.project_memory if (project_scoped and self.project_memory is not None) else self.global_memory
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

    def get_global_facts(self):
        return self.global_memory["facts"]

    def get_project_facts(self):
        if self.project_memory:
            return self.project_memory["facts"]
        return []

    # ── Conversations ──────────────────────────────────────────────────────
    def add_conversation(self, summary: str, user_message: str = "",
                         ai_response: str = "", tags: list = None):
        entry = {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "summary": summary.strip(),
            "user_message": user_message.strip(),
            "ai_response": ai_response.strip(),
            "tags": tags or [],
        }
        if self.project_path and self.project_memory is not None:
            self.project_memory["conversations"].append(entry)
            if len(self.project_memory["conversations"]) > MAX_CONVERSATIONS:
                self.project_memory["conversations"] = \
                    self.project_memory["conversations"][-MAX_CONVERSATIONS:]
            self._save_project()
        else:
            self.global_memory["conversations"].append(entry)
            if len(self.global_memory["conversations"]) > MAX_CONVERSATIONS:
                self.global_memory["conversations"] = \
                    self.global_memory["conversations"][-MAX_CONVERSATIONS:]
            self._save_global()
    
    def get_chat_history_file(self) -> str:
        """Returns the path to the project-scoped chat history file."""
        if self.project_path:
            import hashlib
            path_hash = hashlib.md5(self.project_path.encode()).hexdigest()[:12]
            name = os.path.basename(self.project_path.rstrip('/'))
            return os.path.join(MEMORY_DIR, f"chat_{name}_{path_hash}.txt")
        return os.path.join(MEMORY_DIR, "chat_global.txt")
    
    def save_chat_history(self, text: str):
        """Save chat history scoped to the current project."""
        os.makedirs(MEMORY_DIR, exist_ok=True)
        try:
            with open(self.get_chat_history_file(), "w", encoding="utf-8") as f:
                f.write(text)
        except Exception as e:
            print(f"Could not save chat history: {e}")
    
    def load_chat_history(self) -> str:
        """Load chat history for the current project."""
        path = self.get_chat_history_file()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception:
                pass
        return ""
            
    def get_conversations(self) -> list:
        convs = list(self.global_memory["conversations"])
        if self.project_path and self.project_memory:
            convs += self.project_memory["conversations"]
        convs.sort(key=lambda x: x.get("date", ""), reverse=True)
        return convs

    def search_conversations(self, query: str, limit=5) -> list:
        """Find the most relevant past conversations for a query."""
        query_words = set(re.findall(r'\w+', query.lower()))
        scored = []
        for conv in self.get_conversations():
            summary_words = set(re.findall(r'\w+', conv["summary"].lower()))
            # Score = number of overlapping words
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
        self.global_memory = {"facts": [], "conversations": []}
        if self.project_memory is not None:
            self.project_memory = {"facts": [], "conversations": []}
        self._save_global()
        self._save_project()

    # ── Auto-extraction ────────────────────────────────────────────────────
    def extract_facts_from_exchange(self, user_text: str, ai_response: str) -> list:
        """
        Heuristically extract facts from a conversation exchange.
        Returns a list of fact strings to add.
        """
        facts = []
        combined = f"{user_text} {ai_response}".lower()

        # Preference patterns
        preference_patterns = [
            (r"i (always|prefer|like to|want to|use)\s+([^.!?\n]{5,60})", user_text),
            (r"i('m| am) using\s+([^.!?\n]{5,60})", user_text),
            (r"we (always|prefer|use)\s+([^.!?\n]{5,60})", user_text),
            (r"this project (uses|is built with|requires)\s+([^.!?\n]{5,60})", user_text),
        ]

        for pattern, source in preference_patterns:
            for match in re.finditer(pattern, source.lower()):
                # Grab the full sentence around the match
                start = max(0, match.start() - 10)
                end = min(len(source), match.end() + 20)
                snippet = source[start:end].strip().capitalize()
                if len(snippet) > 10:
                    facts.append(snippet)

        return facts[:3]  # cap at 3 facts per exchange to avoid noise

    # ── Context Builder ────────────────────────────────────────────────────
    def build_memory_context(self, query: str = "") -> str:
        parts = []

        all_facts = self.get_facts()
        if all_facts:
            # Separate global and project facts
            global_facts = self.get_global_facts()
            project_facts = self.get_project_facts()

            if global_facts:
                facts_text = "\n".join(f"- {f}" for f in global_facts)
                parts.append(f"[User preferences and general knowledge]\n{facts_text}")

            if project_facts:
                facts_text = "\n".join(f"- {f}" for f in project_facts)
                project_name = os.path.basename(self.project_path) if self.project_path else "this project"
                parts.append(f"[Facts about {project_name}]\n{facts_text}")

        # Use relevant conversations if query provided, otherwise use recent
        if query:
            relevant = self.search_conversations(query, limit=5)
        else:
            relevant = self.get_conversations()[:5]

        if relevant:
            conv_lines = []
            for c in relevant:
                tags = f" [{', '.join(c['tags'])}]" if c.get("tags") else ""
                conv_lines.append(f"- {c['date']}{tags}: {c['summary']}")
            parts.append(f"[Relevant past conversations]\n" + "\n".join(conv_lines))

        if not parts:
            return ""

        return "[Memory]\n" + "\n\n".join(parts)