import hashlib
import json
import os
import re
import threading
from datetime import datetime


MEMORY_DIR = os.path.join(os.path.expanduser("~"), ".config", "quillai", "memory")
GLOBAL_MEMORY_FILE = os.path.join(MEMORY_DIR, "global.json")

MAX_CONVERSATIONS   = 50
MAX_FACTS           = 100
MAX_TURNS           = 20
RECENT_TURNS_IN_CTX = 6
COMPRESS_THRESHOLD  = 20


# ---------------------------------------------------------------------------
# LLM prompts
# ---------------------------------------------------------------------------

_FACT_EXTRACTION_PROMPT = """\
Analyze this conversation exchange and extract any facts worth remembering.

For each fact decide its scope:
- "global"  : about the user's preferences, habits, tools, or skills that apply across ALL projects
- "project" : specific to THIS codebase — its language, architecture, libraries, conventions, or goals
- "none"    : not worth remembering (casual chat, questions, one-off requests, test messages)

Rules:
- Extract ONLY genuinely useful, durable facts — not questions, not one-off requests
- Phrase each fact as a clear statement, not a raw quote
- If nothing is worth remembering, return an empty list
- Return ONLY valid JSON, no markdown, no explanation

Return format:
[{{"fact": "...", "scope": "global|project|none"}}, ...]

USER: {user_text}
ASSISTANT: {ai_response}
"""

_CONVERSATION_SCORE_PROMPT = """\
Decide if this conversation exchange is worth saving as a long-term memory summary.

Save it if it:
- Resolved a non-trivial bug or architectural question
- Established a pattern, convention, or decision for the codebase
- Revealed something important about how the project works
- Produced significant code that was accepted

Skip it if it:
- Was a simple factual question
- Was casual chat or a test message
- Was a one-liner that didn't resolve anything

Return ONLY valid JSON, no markdown, no explanation:
{{"save": true|false, "summary": "2-3 sentence summary if save=true, else null"}}

USER: {user_text}
ASSISTANT: {ai_response}
"""


class MemoryManager:
    def __init__(self, project_path=None, llm_fn=None):
        """
        llm_fn: optional callable(prompt: str) -> str
                Used for LLM-based fact extraction and conversation scoring.
                Falls back to heuristics if not provided.
        """
        os.makedirs(MEMORY_DIR, exist_ok=True)
        self.project_path   = project_path
        self.llm_fn         = llm_fn
        self.global_memory  = self._load(GLOBAL_MEMORY_FILE)
        self.project_memory = self._load(self._project_file()) if project_path else None

        self._ensure_turns_key(self.global_memory)
        if self.project_memory is not None:
            self._ensure_turns_key(self.project_memory)

    # ─────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────

    def _ensure_turns_key(self, memory: dict):
        if "turns" not in memory:
            memory["turns"] = []

    def _project_file(self):
        if not self.project_path:
            return None
        path_hash = hashlib.md5(self.project_path.encode()).hexdigest()[:12]
        name = os.path.basename(self.project_path.rstrip("/\\"))
        return os.path.join(MEMORY_DIR, f"{name}_{path_hash}.json")

    def _active_memory(self):
        if self.project_path and self.project_memory is not None:
            return self.project_memory
        return self.global_memory

    def _save_active(self):
        if self.project_path and self.project_memory is not None:
            self._save(self.project_memory, self._project_file())
        else:
            self._save(self.global_memory, GLOBAL_MEMORY_FILE)

    def set_project(self, project_path):
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

    def _call_llm(self, prompt: str) -> str:
        """Call llm_fn safely, returning empty string on any failure."""
        if not self.llm_fn:
            return ""
        try:
            return self.llm_fn(prompt).strip()
        except Exception as e:
            print(f"[MemoryManager] LLM call failed: {e}")
            return ""

    def _parse_json(self, text: str):
        """Strip markdown fences and parse JSON, returning None on failure."""
        text = re.sub(r"^```[a-z]*\n?", "", text.strip())
        text = re.sub(r"\n?```$", "", text.strip())
        try:
            return json.loads(text)
        except Exception:
            return None

    # ─────────────────────────────────────────────────────────────
    # Turn Buffer
    # ─────────────────────────────────────────────────────────────

    def add_turn(self, role: str, content: str):
        mem = self._active_memory()
        mem["turns"].append({
            "role":    role,
            "content": content.strip(),
            "ts":      datetime.now().isoformat(),
        })
        if len(mem["turns"]) > MAX_TURNS:
            mem["turns"] = mem["turns"][-MAX_TURNS:]
        self._save_active()
        self.maybe_compress()

    def get_recent_turns(self, n: int = RECENT_TURNS_IN_CTX) -> list:
        return self._active_memory()["turns"][-n:]

    def clear_turns(self):
        self._active_memory()["turns"] = []
        self._save_active()

    # ─────────────────────────────────────────────────────────────
    # Compression
    # ─────────────────────────────────────────────────────────────

    def maybe_compress(self):
        mem   = self._active_memory()
        turns = mem["turns"]
        if len(turns) < COMPRESS_THRESHOLD:
            return
        mid          = len(turns) // 2
        to_compress  = turns[:mid]
        mem["turns"] = turns[mid:]

        summary = self._summarize_turns(to_compress)
        if summary:
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
        block = "\n".join(
            f"{t['role'].upper()}: {t['content']}" for t in turns
        )
        if self.llm_fn:
            prompt = (
                "Summarize the following coding assistant conversation concisely "
                "(2-3 sentences). Focus on: decisions made, code changed, "
                "problems solved, open questions.\n\n" + block
            )
            result = self._call_llm(prompt)
            if result:
                return result

        # Heuristic fallback
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
    # Smart extraction  (LLM-based, runs async)
    # ─────────────────────────────────────────────────────────────

    def process_exchange_async(self, user_text: str, ai_response: str):
        """
        Fire-and-forget: extract facts and score the conversation in a
        background thread. Safe to call from the Qt main thread after
        each completed AI response.
        """
        if not user_text.strip() or not ai_response.strip():
            return
        t = threading.Thread(
            target=self._process_exchange,
            args=(user_text, ai_response),
            daemon=True,
        )
        t.start()

    def _process_exchange(self, user_text: str, ai_response: str):
        """Background thread: extract facts then score conversation."""
        self._extract_and_store_facts(user_text, ai_response)
        self._score_and_store_conversation(user_text, ai_response)

    def _extract_and_store_facts(self, user_text: str, ai_response: str):
        """
        Ask the LLM to extract facts from the exchange and classify each
        as global, project, or none. Falls back to heuristic extraction
        if no LLM is available.
        """
        if self.llm_fn:
            prompt = _FACT_EXTRACTION_PROMPT.format(
                user_text=user_text[:2000],
                ai_response=ai_response[:2000],
            )
            raw = self._call_llm(prompt)
            data = self._parse_json(raw)

            if isinstance(data, list):
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    fact  = item.get("fact", "").strip()
                    scope = item.get("scope", "none").lower()
                    if not fact or scope == "none":
                        continue
                    project_scoped = (
                        scope == "project"
                        and self.project_path
                        and self.project_memory is not None
                    )
                    self.add_fact(fact, project_scoped=project_scoped)
                return

        # Heuristic fallback — only if no LLM
        for fact in self._heuristic_facts(user_text):
            self.add_fact(fact, project_scoped=False)

    def _score_and_store_conversation(self, user_text: str, ai_response: str):
        """
        Ask the LLM whether this exchange is worth saving as a long-term
        conversation summary. Skips trivial exchanges automatically.
        """
        if not self.llm_fn:
            # Without LLM, use a simple length heuristic —
            # only save if both sides said something substantial
            if len(user_text) > 80 and len(ai_response) > 200:
                self.add_conversation(
                    summary      = user_text[:120].strip(),
                    user_message = user_text,
                    ai_response  = ai_response,
                )
            return

        prompt = _CONVERSATION_SCORE_PROMPT.format(
            user_text=user_text[:2000],
            ai_response=ai_response[:2000],
        )
        raw  = self._call_llm(prompt)
        data = self._parse_json(raw)

        if not isinstance(data, dict):
            return
        if not data.get("save"):
            return

        summary = (data.get("summary") or "").strip()
        if not summary:
            return

        self.add_conversation(
            summary      = summary,
            user_message = user_text,
            ai_response  = ai_response,
        )

    def _heuristic_facts(self, user_text: str) -> list:
        """Regex fallback when no LLM is available."""
        facts    = []
        patterns = [
            r"i (always|prefer|like to|want to)\s+([^.!?\n]{5,60})",
            r"i('m| am) using\s+([^.!?\n]{5,60})",
            r"we (always|prefer|use)\s+([^.!?\n]{5,60})",
            r"this project (uses|is built with|requires)\s+([^.!?\n]{5,60})",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, user_text.lower()):
                start   = max(0, match.start() - 10)
                end     = min(len(user_text), match.end() + 20)
                snippet = user_text[start:end].strip().capitalize()
                if len(snippet) > 10:
                    facts.append(snippet)
        return facts[:3]

    # ─────────────────────────────────────────────────────────────
    # Chat history HTML
    # ─────────────────────────────────────────────────────────────

    def get_chat_history_file(self) -> str:
        if self.project_path:
            path_hash = hashlib.md5(self.project_path.encode()).hexdigest()[:12]
            name      = os.path.basename(self.project_path.rstrip("/\\"))
            return os.path.join(MEMORY_DIR, f"chat_{name}_{path_hash}.html")
        return os.path.join(MEMORY_DIR, "chat_global.html")

    def save_chat_history(self, html: str):
        os.makedirs(MEMORY_DIR, exist_ok=True)
        try:
            with open(self.get_chat_history_file(), "w", encoding="utf-8") as f:
                f.write(html)
        except Exception as e:
            print(f"Could not save chat history: {e}")

    def load_chat_history(self) -> str:
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
    # Conversations
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
    # Context Builder
    # ─────────────────────────────────────────────────────────────

    def build_memory_context(self, query: str = "") -> str:
        """
        Assembles memory into a context block for the LLM prompt.

        Layer 1 — Facts (always included, cheap tokens)
        Layer 2 — Recent turns verbatim (short-term chat coherence)
        Layer 3 — Relevant past conversation summaries (long-term recall)
        """
        parts = []

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

        recent = self.get_recent_turns(RECENT_TURNS_IN_CTX)
        if recent:
            lines = "\n".join(
                f"{t['role'].upper()}: {t['content']}" for t in recent
            )
            parts.append(f"[Recent conversation]\n{lines}")

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