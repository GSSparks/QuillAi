"""
core/faq_manager.py

Per-project FAQ knowledge layer — sits between the wiki (file summaries)
and memory (facts). Stores how-to answers derived from conversations,
manual saves, and wiki page analysis.

Storage: ~/.config/quillai/faq/<project_name>_<hash>.json

Each entry:
{
    "id":        "uuid4",
    "question":  "How do I add a new plugin?",
    "answer":    "Create a folder under plugins/features/...",
    "tags":      ["plugin", "architecture"],
    "source":    "conversation|manual|wiki",
    "created":   "2026-04-09",
    "updated":   "2026-04-09",
    "use_count": 3
}
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import uuid
from datetime import date
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal as _pyqtSignal


FAQ_DIR = os.path.join(os.path.expanduser("~"), ".config", "quillai", "faq")
MAX_FAQ  = 200


# ── Signals ───────────────────────────────────────────────────────────────────

class _FAQSignals(QObject):
    faq_changed = _pyqtSignal()   # any entry added/removed/updated

    _instance = None

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


faq_signals = _FAQSignals.instance()


# ── LLM prompts ───────────────────────────────────────────────────────────────

_EXTRACT_FAQ_PROMPT = """\
Analyze this conversation exchange and determine if it contains a clear
how-to answer worth saving as a FAQ entry for this codebase.

A good FAQ entry answers questions like:
- "How do I add/create/implement X?"
- "Why does X work this way?"
- "What is the pattern for X?"
- "Where does X live in the codebase?"

Rules:
- Only extract if there is a clear, reusable question AND a substantive answer
- The answer must be specific to THIS codebase, not generic programming advice
- Phrase the question as someone would naturally ask it
- Keep the answer concise but complete (2-10 sentences or steps)
- Extract tags (1-4 keywords) describing the topic
- If nothing is worth saving, return null

Return ONLY valid JSON, no markdown, no explanation:
{{"question": "...", "answer": "...", "tags": ["tag1", "tag2"]}}
OR: null

USER: {user_text}
ASSISTANT: {ai_response}
"""

_WIKI_FAQ_PROMPT = """\
Analyze this wiki page for a source file and extract any FAQ-worthy
how-to knowledge that a developer working with this codebase would find useful.

Focus on:
- Non-obvious patterns or conventions used in this file
- How to extend or modify this component
- Common pitfalls or design decisions worth knowing
- Integration points with other parts of the system

Rules:
- Only extract genuinely useful, non-obvious knowledge
- Phrase as natural questions a developer would ask
- Keep answers concise (2-8 sentences)
- Extract 1-4 tags per entry
- Return empty list if nothing worth saving

Return ONLY valid JSON array, no markdown:
[{{"question": "...", "answer": "...", "tags": ["tag1"]}}]
"""

_DEDUP_PROMPT = """\
A new FAQ entry candidate needs to be checked against existing entries.

Candidate:
  Q: {question}
  A: {answer}

Existing entries:
{existing}

Decide:
- "keep"      : genuinely new, not covered by any existing entry
- "duplicate" : an existing entry already covers this
- "update:N"  : the candidate is better/more complete than entry N — replace it

Return ONLY valid JSON:
{{"action": "keep|duplicate|update", "index": null}}
"""


# ── FAQManager ────────────────────────────────────────────────────────────────

class FAQManager:
    def __init__(self, project_path: str = None, llm_fn=None):
        os.makedirs(FAQ_DIR, exist_ok=True)
        self.project_path = project_path
        self.llm_fn       = llm_fn
        self._entries: list[dict] = []
        self._lock = threading.Lock()
        if project_path:
            self._load()

    # ── Persistence ───────────────────────────────────────────────────────

    def _faq_file(self) -> Optional[str]:
        if not self.project_path:
            return None
        h    = hashlib.md5(self.project_path.encode()).hexdigest()[:12]
        name = os.path.basename(self.project_path.rstrip("/\\"))
        return os.path.join(FAQ_DIR, f"{name}_{h}.json")

    def _load(self):
        path = self._faq_file()
        if path and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self._entries = json.load(f)
            except Exception:
                self._entries = []

    def _save(self):
        path = self._faq_file()
        if not path:
            return
        with self._lock:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(self._entries, f, indent=2)
            except Exception as e:
                print(f"[FAQManager] save failed: {e}")

    def set_project(self, project_path: str):
        self.project_path = project_path
        self._entries     = []
        self._load()
        faq_signals.faq_changed.emit()

    # ── LLM helpers ───────────────────────────────────────────────────────

    def _call_llm(self, prompt: str) -> str:
        if not self.llm_fn:
            return ""
        try:
            return self.llm_fn(prompt).strip()
        except Exception as e:
            print(f"[FAQManager] LLM call failed: {e}")
            return ""

    def _parse_json(self, text: str):
        text = re.sub(r"^```[a-z]*\n?", "", text.strip())
        text = re.sub(r"\n?```$",       "", text.strip())
        try:
            return json.loads(text)
        except Exception:
            return None

    # ── Deduplication ─────────────────────────────────────────────────────

    def _deduplicate(self, question: str, answer: str) -> tuple[str, int]:
        """Returns ('keep'|'duplicate'|'update', index)."""
        if not self._entries or not self.llm_fn:
            return "keep", -1

        existing = "\n".join(
            f"  [{i}] Q: {e['question'][:80]}"
            for i, e in enumerate(self._entries[:20])
        )
        prompt = _DEDUP_PROMPT.format(
            question=question, answer=answer, existing=existing
        )
        raw  = self._call_llm(prompt)
        data = self._parse_json(raw)
        if not isinstance(data, dict):
            return "keep", -1

        action = data.get("action", "keep")
        idx    = data.get("index")
        return action, (idx if isinstance(idx, int) else -1)

    # ── Public API ────────────────────────────────────────────────────────

    def add_entry(self, question: str, answer: str,
                  tags: list = None, source: str = "manual",
                  deduplicate: bool = True) -> bool:
        """
        Add a FAQ entry. Runs deduplication if llm_fn is set.
        Returns True if entry was added/updated.
        """
        question = question.strip()
        answer   = answer.strip()
        if not question or not answer:
            return False

        if deduplicate:
            action, idx = self._deduplicate(question, answer)
            if action == "duplicate":
                print(f"[FAQ] duplicate skipped: {question[:50]}")
                return False
            if action == "update" and idx >= 0 and idx < len(self._entries):
                self._entries[idx].update({
                    "question": question,
                    "answer":   answer,
                    "tags":     tags or [],
                    "updated":  date.today().isoformat(),
                    "source":   source,
                })
                self._save()
                faq_signals.faq_changed.emit()
                print(f"[FAQ] updated entry [{idx}]: {question[:50]}")
                return True

        entry = {
            "id":        str(uuid.uuid4())[:8],
            "question":  question,
            "answer":    answer,
            "tags":      tags or [],
            "source":    source,
            "created":   date.today().isoformat(),
            "updated":   date.today().isoformat(),
            "use_count": 0,
        }
        self._entries.append(entry)

        # Prune if over limit
        if len(self._entries) > MAX_FAQ:
            # Keep highest use_count entries
            self._entries.sort(key=lambda e: e.get("use_count", 0), reverse=True)
            self._entries = self._entries[:MAX_FAQ]

        self._save()
        faq_signals.faq_changed.emit()
        print(f"[FAQ] new entry: {question[:50]}")
        return True

    def remove_entry(self, entry_id: str):
        self._entries = [e for e in self._entries if e.get("id") != entry_id]
        self._save()
        faq_signals.faq_changed.emit()

    def update_entry(self, entry_id: str, question: str = None,
                     answer: str = None, tags: list = None):
        for e in self._entries:
            if e.get("id") == entry_id:
                if question: e["question"] = question.strip()
                if answer:   e["answer"]   = answer.strip()
                if tags is not None: e["tags"] = tags
                e["updated"] = date.today().isoformat()
                break
        self._save()
        faq_signals.faq_changed.emit()

    def get_all(self) -> list[dict]:
        return list(self._entries)

    def search(self, query: str, limit: int = 5) -> list[dict]:
        """Return entries matching query by keyword overlap."""
        q_words = set(re.findall(r"\w+", query.lower()))
        if not q_words:
            return []

        scored = []
        for entry in self._entries:
            text  = (entry["question"] + " " + entry["answer"] + " " +
                     " ".join(entry.get("tags", []))).lower()
            score = sum(1 for w in q_words if w in text)
            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = [e for _, e in scored[:limit]]

        # Increment use_count for returned entries
        ids = {e["id"] for e in results}
        for entry in self._entries:
            if entry.get("id") in ids:
                entry["use_count"] = entry.get("use_count", 0) + 1
        if results:
            self._save()

        return results

    def build_context(self, query: str, max_chars: int = 2000) -> str:
        """Build a context string of relevant FAQ entries for injection."""
        matches = self.search(query, limit=3)
        if not matches:
            return ""

        parts = ["[FAQ — Codebase Knowledge]"]
        used  = 0
        for entry in matches:
            block = (
                f"Q: {entry['question']}\n"
                f"A: {entry['answer']}"
            )
            if used + len(block) > max_chars:
                break
            parts.append(block)
            used += len(block)

        return "\n\n".join(parts) if len(parts) > 1 else ""

    # ── Async extraction from conversations ──────────────────────────────

    def process_exchange_async(self, user_text: str, ai_response: str):
        """Fire-and-forget: extract FAQ from a conversation exchange."""
        if not self.llm_fn or not user_text.strip() or not ai_response.strip():
            return
        threading.Thread(
            target=self._extract_from_conversation,
            args=(user_text, ai_response),
            daemon=True,
        ).start()

    def _extract_from_conversation(self, user_text: str, ai_response: str):
        prompt = _EXTRACT_FAQ_PROMPT.format(
            user_text=user_text[:2000],
            ai_response=ai_response[:3000],
        )
        raw  = self._call_llm(prompt)
        if not raw or raw.lower() == "null":
            return
        data = self._parse_json(raw)
        if not isinstance(data, dict):
            return
        q = data.get("question", "").strip()
        a = data.get("answer",   "").strip()
        t = data.get("tags",     [])
        if q and a:
            self.add_entry(q, a, tags=t, source="conversation")

    # ── Extraction from wiki pages ────────────────────────────────────────

    def process_wiki_page_async(self, source_rel: str, wiki_text: str):
        """Extract FAQ entries from a newly generated wiki page."""
        if not self.llm_fn or not wiki_text.strip():
            return
        threading.Thread(
            target=self._extract_from_wiki,
            args=(source_rel, wiki_text),
            daemon=True,
        ).start()

    def _extract_from_wiki(self, source_rel: str, wiki_text: str):
        # Only process files with substantial Notes or architectural content
        if "## Notes" not in wiki_text and "## Architecture" not in wiki_text:
            return

        prompt = _WIKI_FAQ_PROMPT + f"\n\nSOURCE: {source_rel}\n\n{wiki_text[:4000]}"
        raw  = self._call_llm(prompt)
        data = self._parse_json(raw)
        if not isinstance(data, list):
            return
        for item in data:
            if not isinstance(item, dict):
                continue
            q = item.get("question", "").strip()
            a = item.get("answer",   "").strip()
            t = item.get("tags",     [])
            if q and a:
                self.add_entry(q, a, tags=t, source="wiki")