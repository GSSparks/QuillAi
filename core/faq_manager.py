"""
core/faq_manager.py

Per-project FAQ knowledge layer — sits between the wiki (file summaries)
and memory (facts). Stores how-to answers derived from conversations,
manual saves, and wiki page analysis.

Storage: ~/.config/quillai/faq/<project_name>_<hash>.json

Each entry:
{
    "id":           "uuid4[:8]",
    "question":     "How do I add a new plugin?",
    "answer":       "Create a folder under plugins/features/...",
    "type":         "howto|concept|decision|gotcha",
    "tags":         ["plugin", "architecture"],
    "source":       "conversation|manual|wiki",
    "source_files": ["plugins/features/context_debugger/main.py"],
    "source_commit": "a3f2c1d",
    "created":      "2026-04-09",
    "updated":      "2026-04-09",
    "use_count":    3,
    "confidence":   1.0,
    "stale":        false
}

Entry types
-----------
howto      "How do I add/create/implement X?"
concept    "How does X work?" / "What is X?"
decision   "Why does X work this way?"
gotcha     "Watch out for X" / common traps and non-obvious constraints

Staleness
---------
When a source file changes (detected by WikiIndexer), all FAQ entries
that reference that file are re-evaluated against the new wiki page.
Entries that are no longer accurate get confidence lowered; entries
below 0.3 confidence are pruned on next save. Manual entries are
never auto-pruned.

Pruning priority (when over MAX_FAQ)
-------------------------------------
1. stale=True, source != manual
2. confidence < 0.5, source != manual
3. lowest use_count
4. oldest updated date
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import threading
import uuid
from datetime import date
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal as _pyqtSignal


FAQ_DIR = os.path.join(os.path.expanduser("~"), ".config", "quillai", "faq")
MAX_FAQ  = 500   # higher cap — smart pruning handles quality control

# Entry types
ENTRY_TYPES = ("howto", "concept", "decision", "gotcha")

# Confidence thresholds
CONF_PRUNE    = 0.25   # entries below this get pruned on next save
CONF_STALE    = 0.45   # entries below this get marked stale
CONF_DECAY    = 0.20   # how much confidence drops when source file changes


# ── Signals ───────────────────────────────────────────────────────────────────

class _FAQSignals(QObject):
    faq_changed = _pyqtSignal()

    _instance = None

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


faq_signals = _FAQSignals.instance()


# ── LLM prompts ───────────────────────────────────────────────────────────────

_EXTRACT_FAQ_PROMPT = """\
Analyze this conversation exchange and determine if it contains knowledge
worth saving as a FAQ entry for this specific codebase.

Entry types:
- "howto"    : procedural — "How do I add/create/implement X?"
- "concept"  : architectural — "How does X work?" / "What is X?"
- "decision" : rationale — "Why does X work this way?"
- "gotcha"   : trap or non-obvious constraint — "Watch out for X"

Rules:
- Only extract if there is a CLEAR, REUSABLE question AND a substantive answer
- The answer must be SPECIFIC TO THIS CODEBASE, not generic programming advice
- Phrase the question as a developer would naturally ask it
- Keep the answer concise but complete (2-10 sentences or steps)
- Extract 1-4 lowercase keyword tags
- List specific source FILES the answer is about (relative file paths like "plugins/languages/python_plugin.py", not directories, or [] if none)
- If nothing is worth saving, return null

Return ONLY valid JSON, no markdown, no explanation:
{{"question": "...", "answer": "...", "type": "howto|concept|decision|gotcha", \
"tags": ["tag1"], "source_files": ["path/to/file.py"]}}
OR: null

USER: {user_text}
ASSISTANT: {ai_response}
"""

_WIKI_FAQ_PROMPT = """\
Analyze this wiki page for a source file and extract FAQ-worthy knowledge
that a developer working on this codebase would find useful.

Entry types:
- "howto"    : how to extend, modify, or use this component
- "concept"  : how this component works, its design, its role
- "decision" : why design choices were made
- "gotcha"   : non-obvious constraints, traps, required patterns

Rules:
- Only extract genuinely useful, NON-OBVIOUS knowledge
- Skip things that are obvious from reading the code
- Phrase as natural questions a developer would ask
- Keep answers concise (2-8 sentences)
- Extract 1-4 lowercase tags per entry
- source_files should always include the file this wiki page documents
- Return empty list [] if nothing worth saving

Return ONLY valid JSON array, no markdown:
[{{"question": "...", "answer": "...", "type": "howto|concept|decision|gotcha", \
"tags": ["tag1"], "source_files": ["{source_rel}"]}}]
"""

_DEDUP_PROMPT = """\
A new FAQ entry candidate needs to be checked against existing entries.

Candidate:
  Type: {entry_type}
  Q: {question}
  A: {answer}

Existing entries (index: question | first 150 chars of answer):
{existing}

Determine:
- "keep"      : genuinely new knowledge not covered by any existing entry
- "duplicate" : an existing entry already covers this well enough
- "update:N"  : the candidate is more accurate/complete than entry N — replace it

Be strict: only mark "duplicate" if the existing entry would answer the same
question equally well. If the candidate has meaningfully different or more
specific information, choose "keep" or "update".

Return ONLY valid JSON, no markdown:
{{"action": "keep|duplicate|update", "index": null_or_integer}}
"""

_STALENESS_PROMPT = """\
A source file has been updated. Review this FAQ entry and determine if it
is still accurate given the new wiki page for that file.

FAQ Entry:
  Q: {question}
  A: {answer}

Updated wiki page for {source_file}:
{wiki_text}

Determine:
- "valid"    : the answer is still accurate
- "outdated" : the answer is no longer accurate or misleading
- "update"   : the answer is mostly right but needs updating — provide new answer

Return ONLY valid JSON, no markdown:
{{"status": "valid|outdated|update", "new_answer": null_or_string}}
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _git_commit(project_path: str) -> str:
    """Return short HEAD commit hash, or empty string if not a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def _smart_prune(entries: list[dict], limit: int) -> list[dict]:
    """
    Prune entries down to `limit` using priority order:
    1. Remove stale non-manual entries first
    2. Remove low-confidence non-manual entries
    3. Remove lowest use_count
    4. Remove oldest updated
    Manual entries are never auto-pruned.
    """
    if len(entries) <= limit:
        return entries

    def sort_key(e):
        is_manual   = e.get("source") == "manual"
        is_stale    = e.get("stale", False)
        confidence  = e.get("confidence", 1.0)
        use_count   = e.get("use_count", 0)
        updated     = e.get("updated", "2000-01-01")
        # Manual entries score highest (never pruned)
        # Others: stale=bad, low confidence=bad, low use=bad, old=bad
        return (
            is_manual,        # True sorts last (kept)
            not is_stale,     # stale=True sorts first (pruned first)
            confidence,       # low confidence pruned before high
            use_count,        # low use_count pruned before high
            updated,          # old entries pruned before recent
        )

    entries.sort(key=sort_key)
    # Keep the top `limit` entries (highest scores)
    return entries[-limit:]


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
                    raw = json.load(f)
                self._entries = [self._migrate_entry(e) for e in raw]
            except Exception:
                self._entries = []

    def _migrate_entry(self, e: dict) -> dict:
        """Ensure older entries have all new fields with safe defaults."""
        e.setdefault("type",         "howto")
        e.setdefault("source_files", [])
        e.setdefault("source_commit","")
        e.setdefault("confidence",   1.0)
        e.setdefault("stale",        False)
        e.setdefault("use_count",    0)
        return e

    def _save(self):
        path = self._faq_file()
        if not path:
            return
        with self._lock:
            # Prune before saving
            self._entries = _smart_prune(self._entries, MAX_FAQ)
            # Remove entries below confidence threshold (non-manual only)
            self._entries = [
                e for e in self._entries
                if e.get("source") == "manual"
                or e.get("confidence", 1.0) >= CONF_PRUNE
            ]
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(self._entries, f, indent=2)
            except Exception as ex:
                print(f"[FAQManager] save failed: {ex}")

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
        except Exception:
            return ""

    def _parse_json(self, text: str):
        text = re.sub(r"^```[a-z]*\n?", "", text.strip())
        text = re.sub(r"\n?```$",       "", text.strip())
        try:
            return json.loads(text)
        except Exception:
            return None

    # ── Deduplication ─────────────────────────────────────────────────────

    def _deduplicate(self, question: str, answer: str,
                     entry_type: str = "howto") -> tuple[str, int]:
        """Returns ('keep'|'duplicate'|'update', index)."""
        if not self._entries or not self.llm_fn:
            return "keep", -1

        # Build richer comparison: question + answer preview
        existing = "\n".join(
            f"  [{i}] {e.get('type','?')} | {e['question'][:80]} | "
            f"{e['answer'][:150]}"
            for i, e in enumerate(self._entries[:30])
        )
        prompt = _DEDUP_PROMPT.format(
            entry_type=entry_type,
            question=question,
            answer=answer,
            existing=existing,
        )
        raw  = self._call_llm(prompt)
        data = self._parse_json(raw)
        if not isinstance(data, dict):
            return "keep", -1

        action = data.get("action", "keep")
        idx    = data.get("index")
        # Normalise "update:N" style responses
        if isinstance(action, str) and action.startswith("update"):
            parts = action.split(":")
            if len(parts) == 2 and parts[1].isdigit():
                idx = int(parts[1])
            action = "update"
        return action, (idx if isinstance(idx, int) else -1)

    # ── Public API ────────────────────────────────────────────────────────

    def add_entry(
        self,
        question:     str,
        answer:       str,
        tags:         list        = None,
        source:       str         = "manual",
        entry_type:   str         = "howto",
        source_files: list        = None,
        deduplicate:  bool        = True,
    ) -> bool:
        """
        Add a FAQ entry. Runs deduplication if llm_fn is set.
        Returns True if entry was added/updated.
        """
        question = question.strip()
        answer   = answer.strip()
        if not question or not answer:
            return False
        if entry_type not in ENTRY_TYPES:
            entry_type = "howto"

        commit = _git_commit(self.project_path) if self.project_path else ""

        if deduplicate:
            action, idx = self._deduplicate(question, answer, entry_type)
            if action == "duplicate":
                return False
            if action == "update" and 0 <= idx < len(self._entries):
                self._entries[idx].update({
                    "question":      question,
                    "answer":        answer,
                    "tags":          tags or [],
                    "type":          entry_type,
                    "updated":       date.today().isoformat(),
                    "source":        source,
                    "source_files":  source_files or [],
                    "source_commit": commit,
                    "confidence":    1.0,
                    "stale":         False,
                })
                self._save()
                faq_signals.faq_changed.emit()
                return True

        entry = {
            "id":            str(uuid.uuid4())[:8],
            "question":      question,
            "answer":        answer,
            "type":          entry_type,
            "tags":          tags or [],
            "source":        source,
            "source_files":  source_files or [],
            "source_commit": commit,
            "created":       date.today().isoformat(),
            "updated":       date.today().isoformat(),
            "use_count":     0,
            "confidence":    1.0,
            "stale":         False,
        }
        self._entries.append(entry)
        self._save()
        faq_signals.faq_changed.emit()
        return True

    def remove_entry(self, entry_id: str):
        self._entries = [e for e in self._entries if e.get("id") != entry_id]
        self._save()
        faq_signals.faq_changed.emit()

    def update_entry(self, entry_id: str, question: str = None,
                     answer: str = None, tags: list = None,
                     entry_type: str = None):
        for e in self._entries:
            if e.get("id") == entry_id:
                if question:    e["question"]  = question.strip()
                if answer:      e["answer"]    = answer.strip()
                if tags is not None:  e["tags"] = tags
                if entry_type:  e["type"]      = entry_type
                e["updated"]    = date.today().isoformat()
                e["stale"]      = False
                e["confidence"] = 1.0
                break
        self._save()
        faq_signals.faq_changed.emit()

    def get_all(self) -> list[dict]:
        return list(self._entries)

    def search(self, query: str, limit: int = 5) -> list[dict]:
        """Return entries matching query by keyword overlap, weighted by confidence."""
        q_words = set(re.findall(r"\w+", query.lower()))
        if not q_words:
            return []

        scored = []
        for entry in self._entries:
            if entry.get("stale") and entry.get("confidence", 1.0) < CONF_STALE:
                continue   # skip low-confidence stale entries from context
            text  = (
                entry["question"] + " " +
                entry["answer"]   + " " +
                " ".join(entry.get("tags", []))
            ).lower()
            score = sum(1 for w in q_words if w in text)
            score *= entry.get("confidence", 1.0)   # weight by confidence
            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = [e for _, e in scored[:limit]]

        # Increment use_count
        ids = {e["id"] for e in results}
        for entry in self._entries:
            if entry.get("id") in ids:
                entry["use_count"] = entry.get("use_count", 0) + 1
        if results:
            self._save()

        return results

    def build_context(self, query: str, max_chars: int = 2000) -> str:
        """Build a context string of relevant FAQ entries for injection."""
        matches = self.search(query, limit=5)
        if not matches:
            return ""

        parts = ["[FAQ — Codebase Knowledge]"]
        used  = 0
        for entry in matches:
            block = f"Q: {entry['question']}\nA: {entry['answer']}"
            if used + len(block) > max_chars:
                break
            parts.append(block)
            used += len(block)

        return "\n\n".join(parts) if len(parts) > 1 else ""

    # ── Staleness review ──────────────────────────────────────────────────

    def review_faq_for_file(self, source_rel: str, wiki_text: str):
        """
        Called by WikiIndexer after a file's wiki page is updated.
        Re-evaluates all FAQ entries that reference source_rel.
        Runs synchronously (called from WikiIndexer's background thread).
        """
        affected = [
            e for e in self._entries
            if source_rel in e.get("source_files", [])
            and e.get("source") != "manual"
        ]
        if not affected:
            return

        for entry in affected:
            self._review_single_entry(entry, source_rel, wiki_text)

        self._save()
        faq_signals.faq_changed.emit()

    def _review_single_entry(self, entry: dict, source_file: str,
                              wiki_text: str):
        """Re-evaluate one entry against an updated wiki page."""
        if not self.llm_fn:
            # No LLM — just decay confidence and mark stale
            entry["confidence"] = max(0.0, entry.get("confidence", 1.0) - CONF_DECAY)
            entry["stale"]      = entry["confidence"] < CONF_STALE
            return

        prompt = _STALENESS_PROMPT.format(
            question=entry["question"],
            answer=entry["answer"],
            source_file=source_file,
            wiki_text=wiki_text[:3000],
        )
        raw  = self._call_llm(prompt)
        data = self._parse_json(raw)
        if not isinstance(data, dict):
            return

        status     = data.get("status", "valid")
        new_answer = data.get("new_answer")

        if status == "valid":
            # Reinforce confidence slightly
            entry["confidence"] = min(1.0, entry.get("confidence", 1.0) + 0.05)
            entry["stale"]      = False

        elif status == "outdated":
            entry["confidence"] = max(0.0, entry.get("confidence", 1.0) - CONF_DECAY)
            entry["stale"]      = True
            entry["updated"]    = date.today().isoformat()

        elif status == "update" and new_answer:
            entry["answer"]        = new_answer.strip()
            entry["confidence"]    = 0.85   # slightly below 1.0 — LLM-updated
            entry["stale"]         = False
            entry["updated"]       = date.today().isoformat()
            entry["source_commit"] = _git_commit(self.project_path or "")

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
        if not raw or raw.lower().strip() == "null":
            return
        data = self._parse_json(raw)
        if not isinstance(data, dict):
            return
        q  = data.get("question",     "").strip()
        a  = data.get("answer",       "").strip()
        t  = data.get("tags",         [])
        et = data.get("type",         "howto")
        sf = data.get("source_files", [])
        if q and a:
            self.add_entry(q, a, tags=t, source="conversation",
                           entry_type=et, source_files=sf)

    # ── Async extraction from wiki pages ─────────────────────────────────

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
        prompt = _WIKI_FAQ_PROMPT.replace("{source_rel}", source_rel)
        prompt += f"\n\nSOURCE: {source_rel}\n\n{wiki_text[:4000]}"
        raw  = self._call_llm(prompt)
        data = self._parse_json(raw)
        if not isinstance(data, list):
            return
        for item in data:
            if not isinstance(item, dict):
                continue
            q  = item.get("question",     "").strip()
            a  = item.get("answer",       "").strip()
            t  = item.get("tags",         [])
            et = item.get("type",         "howto")
            sf = item.get("source_files", [source_rel])
            if q and a:
                self.add_entry(q, a, tags=t, source="wiki",
                               entry_type=et, source_files=sf)

    # ── Markdown export ───────────────────────────────────────────────────

    def export_markdown(self, output_path: str = None) -> str:
        """
        Export all non-stale FAQ entries as a Markdown document.
        Groups entries by type. Returns the markdown string and
        optionally writes to output_path.
        """
        today    = date.today().isoformat()
        project  = os.path.basename(
            (self.project_path or "").rstrip("/\\")
        ) or "Project"

        sections = {
            "howto":    ("🛠️ How-To", []),
            "concept":  ("🧠 Concepts & Architecture", []),
            "decision": ("🤔 Design Decisions", []),
            "gotcha":   ("⚠️ Gotchas & Traps", []),
        }

        for entry in sorted(self._entries,
                            key=lambda e: e.get("use_count", 0), reverse=True):
            if entry.get("stale") and entry.get("confidence", 1.0) < CONF_STALE:
                continue  # skip low-confidence stale entries from docs
            et = entry.get("type", "howto")
            if et in sections:
                sections[et][1].append(entry)

        lines = [
            f"# {project} — Developer FAQ",
            f"",
            f"> Auto-generated by QuillAI on {today}.  ",
            f"> Entries are extracted from conversations, wiki pages, and manual saves.",
            f"",
            f"---",
            f"",
        ]

        # Table of contents
        lines.append("## Contents\n")
        for et, (heading, entries) in sections.items():
            if entries:
                anchor = heading.lower()
                anchor = re.sub(r"[^\w\s-]", "", anchor)
                anchor = re.sub(r"\s+", "-", anchor.strip())
                lines.append(f"- [{heading}](#{anchor}) ({len(entries)} entries)")
        lines.append("")
        lines.append("---")
        lines.append("")

        for et, (heading, entries) in sections.items():
            if not entries:
                continue

            lines.append(f"## {heading}")
            lines.append("")

            for entry in entries:
                lines.append(f"### {entry['question']}")
                lines.append("")
                lines.append(entry["answer"])
                lines.append("")

                # Metadata footer
                meta = []
                if entry.get("tags"):
                    meta.append("**Tags:** " + ", ".join(
                        f"`{t}`" for t in entry["tags"]
                    ))
                if entry.get("source_files"):
                    files = ", ".join(
                        f"`{f}`" for f in entry["source_files"]
                    )
                    meta.append(f"**Source:** {files}")
                conf = entry.get("confidence", 1.0)
                if conf < 0.9:
                    meta.append(f"**Confidence:** {conf:.0%}")
                if entry.get("stale"):
                    meta.append("⚠️ *may be outdated*")

                if meta:
                    lines.append("  \n".join(meta))
                    lines.append("")

                lines.append("---")
                lines.append("")

        md = "\n".join(lines)

        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_text(md, encoding="utf-8")
            print(f"[FAQManager] exported {len(self._entries)} entries → {output_path}")

        return md

    def export_markdown_default(self) -> Optional[str]:
        """Export to ~/.config/quillai/faq/<project>_faq.md"""
        if not self.project_path:
            return None
        name = os.path.basename(self.project_path.rstrip("/\\"))
        h    = hashlib.md5(self.project_path.encode()).hexdigest()[:8]
        path = os.path.join(FAQ_DIR, f"{name}_{h}_faq.md")
        return self.export_markdown(path)