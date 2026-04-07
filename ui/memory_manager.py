import hashlib
import json
import os
import re
import threading
from datetime import datetime, date


MEMORY_DIR         = os.path.join(os.path.expanduser("~"), ".config", "quillai", "memory")
GLOBAL_MEMORY_FILE = os.path.join(MEMORY_DIR, "global.json")

MAX_CONVERSATIONS    = 50
MAX_FACTS            = 100
MAX_TURNS            = 20
RECENT_TURNS_IN_CTX  = 6
COMPRESS_THRESHOLD   = 20

# Confidence thresholds
CONFIDENCE_INITIAL   = 1.0   # new fact starts here
CONFIDENCE_DECAY     = 0.15  # subtracted per 30-day period without reinforcement
CONFIDENCE_PRUNE     = 0.25  # facts below this are removed on next save
CONFIDENCE_STALE     = 0.50  # wiki review marks fact at this level when uncertain
FACT_MAX_AGE_DAYS    = 180   # hard cap — facts older than this are pruned regardless


# ---------------------------------------------------------------------------
# LLM prompts
# ---------------------------------------------------------------------------

_FACT_EXTRACTION_PROMPT = """\
Analyze this conversation exchange and extract any facts worth remembering.

For each fact decide its scope:
- "global"  : about the user's preferences, habits, tools, or skills — applies across ALL projects
- "project" : specific to THIS codebase — its language, architecture, libraries, conventions, goals
- "none"    : not worth remembering (casual chat, questions, one-off requests, test messages)

Also list which source files (relative paths) the fact was derived from, if any are evident.
If no specific files are mentioned, return an empty list for source_files.

Rules:
- Extract ONLY genuinely useful, durable facts — not questions or one-off requests
- Phrase each fact as a clear declarative statement
- If nothing is worth remembering, return an empty list
- Return ONLY valid JSON, no markdown, no explanation

Return format:
[{{"fact": "...", "scope": "global|project|none", "source_files": ["path/to/file.js", ...]}}]

USER: {user_text}
ASSISTANT: {ai_response}
"""

_DEDUP_PROMPT = """\
You are managing a memory store. A new fact candidate needs to be checked against existing facts.

New candidate:
  "{candidate}"

Existing facts:
{existing}

Decide what to do:
- "keep_new"   : the candidate is genuinely new information not covered by any existing fact
- "duplicate"  : an existing fact already covers this — discard the candidate
- "replace"    : the candidate is more specific/accurate than an existing fact — replace it
                 (include the index of the fact to replace as "replace_index")
- "contradict" : the candidate contradicts an existing fact — store new, lower confidence on old
                 (include the index of the contradicted fact as "contradict_index")

Return ONLY valid JSON, no markdown, no explanation:
{{"action": "keep_new|duplicate|replace|contradict", "replace_index": null, "contradict_index": null}}
"""

_STALENESS_PROMPT = """\
A wiki page for a source file has been regenerated. Review the facts tagged to this file
and decide if each fact is still accurate based on the updated wiki content.

Source file: {source_file}

Updated wiki page:
{wiki_text}

Facts to review:
{facts}

For each fact, return its index and verdict:
- "current"   : still accurate
- "stale"     : no longer accurate or relevant
- "uncertain" : might still be true but cannot confirm from the wiki

Return ONLY valid JSON, no markdown, no explanation:
[{{"index": 0, "verdict": "current|stale|uncertain"}}, ...]
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


# ---------------------------------------------------------------------------
# Fact helpers
# ---------------------------------------------------------------------------

def _make_fact(text: str, source_files: list = None) -> dict:
    return {
        "text":         text.strip(),
        "source_files": source_files or [],
        "added":        date.today().isoformat(),
        "last_seen":    date.today().isoformat(),
        "confidence":   CONFIDENCE_INITIAL,
    }


def _fact_text(fact) -> str:
    """Normalise — facts may be legacy strings or new dicts."""
    if isinstance(fact, dict):
        return fact.get("text", "")
    return str(fact)


def _migrate_facts(facts: list) -> list:
    """Convert bare string facts to the new dict format."""
    migrated = []
    for f in facts:
        if isinstance(f, str):
            migrated.append(_make_fact(f))
        elif isinstance(f, dict) and "text" in f:
            # Backfill missing keys
            f.setdefault("source_files", [])
            f.setdefault("added",      date.today().isoformat())
            f.setdefault("last_seen",  date.today().isoformat())
            f.setdefault("confidence", CONFIDENCE_INITIAL)
            migrated.append(f)
    return migrated


def _decay_confidence(fact: dict) -> dict:
    """Apply time-based confidence decay in place. Returns the fact."""
    try:
        last = date.fromisoformat(fact.get("last_seen", date.today().isoformat()))
        days_old = (date.today() - last).days
        periods  = days_old // 30
        if periods > 0:
            fact["confidence"] = max(
                0.0,
                fact.get("confidence", CONFIDENCE_INITIAL) - CONFIDENCE_DECAY * periods
            )
    except (ValueError, TypeError):
        pass
    return fact


def _is_prunable(fact: dict) -> bool:
    """True if the fact should be removed."""
    try:
        added = date.fromisoformat(fact.get("added", date.today().isoformat()))
        if (date.today() - added).days > FACT_MAX_AGE_DAYS:
            return True
    except (ValueError, TypeError):
        pass
    return fact.get("confidence", CONFIDENCE_INITIAL) < CONFIDENCE_PRUNE


# ---------------------------------------------------------------------------
# MemoryManager
# ---------------------------------------------------------------------------

class MemoryManager:
    def __init__(self, project_path=None, llm_fn=None):
        """
        llm_fn: optional callable(prompt: str) -> str
        """
        os.makedirs(MEMORY_DIR, exist_ok=True)
        self.project_path   = project_path
        self.llm_fn         = llm_fn
        self.global_memory  = self._load(GLOBAL_MEMORY_FILE)
        self.project_memory = self._load(self._project_file()) if project_path else None

        self._ensure_schema(self.global_memory)
        if self.project_memory is not None:
            self._ensure_schema(self.project_memory)

    # ─────────────────────────────────────────────────────────────
    # Schema / migration helpers
    # ─────────────────────────────────────────────────────────────

    def _ensure_schema(self, memory: dict):
        """Migrate old data formats and ensure all keys exist."""
        if "turns" not in memory:
            memory["turns"] = []
        # Migrate bare string facts → fact dicts
        memory["facts"] = _migrate_facts(memory.get("facts", []))

    def _prune_facts(self, memory: dict):
        """Remove low-confidence and expired facts, applying decay first."""
        memory["facts"] = [
            f for f in (_decay_confidence(f) for f in memory["facts"])
            if not _is_prunable(f)
        ]

    # ─────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────

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
        self._ensure_schema(self.project_memory)

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
        self._prune_facts(self.global_memory)
        self._save(self.global_memory, GLOBAL_MEMORY_FILE)

    def _save_project(self):
        if self.project_memory is not None:
            self._prune_facts(self.project_memory)
            self._save(self.project_memory, self._project_file())

    def _call_llm(self, prompt: str) -> str:
        if not self.llm_fn:
            return ""
        try:
            return self.llm_fn(prompt).strip()
        except Exception as e:
            print(f"[MemoryManager] LLM call failed: {e}")
            return ""

    def _parse_json(self, text: str):
        text = re.sub(r"^```[a-z]*\n?", "", text.strip())
        text = re.sub(r"\n?```$",       "", text.strip())
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
        block = "\n".join(f"{t['role'].upper()}: {t['content']}" for t in turns)
        if self.llm_fn:
            prompt = (
                "Summarize the following coding assistant conversation concisely "
                "(2-3 sentences). Focus on: decisions made, code changed, "
                "problems solved, open questions.\n\n" + block
            )
            result = self._call_llm(prompt)
            if result:
                return result
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
    # Smart extraction  (async, called after each AI response)
    # ─────────────────────────────────────────────────────────────

    def process_exchange_async(self, user_text: str, ai_response: str):
        """Fire-and-forget background processing after each AI response."""
        if not user_text.strip() or not ai_response.strip():
            return
        threading.Thread(
            target=self._process_exchange,
            args=(user_text, ai_response),
            daemon=True,
        ).start()

    def _process_exchange(self, user_text: str, ai_response: str):
        self._extract_and_store_facts(user_text, ai_response)
        self._score_and_store_conversation(user_text, ai_response)

    def _extract_and_store_facts(self, user_text: str, ai_response: str):
        if self.llm_fn:
            prompt = _FACT_EXTRACTION_PROMPT.format(
                user_text=user_text[:2000],
                ai_response=ai_response[:2000],
            )
            raw  = self._call_llm(prompt)
            data = self._parse_json(raw)

            if isinstance(data, list):
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    text   = item.get("fact", "").strip()
                    scope  = item.get("scope", "none").lower()
                    files  = item.get("source_files", [])
                    if not text or scope == "none":
                        continue
                    project_scoped = (
                        scope == "project"
                        and self.project_path
                        and self.project_memory is not None
                    )
                    self.add_fact(text, project_scoped=project_scoped, source_files=files)
                return

        # Heuristic fallback
        for fact in self._heuristic_facts(user_text):
            self.add_fact(fact, project_scoped=False)

    def _score_and_store_conversation(self, user_text: str, ai_response: str):
        if not self.llm_fn:
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
        if not isinstance(data, dict) or not data.get("save"):
            return
        summary = (data.get("summary") or "").strip()
        if summary:
            self.add_conversation(
                summary      = summary,
                user_message = user_text,
                ai_response  = ai_response,
            )

    def _heuristic_facts(self, user_text: str) -> list:
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
    # Deduplication  (LLM-based)
    # ─────────────────────────────────────────────────────────────

    def _deduplicate_fact(self, candidate: str, target: dict) -> str:
        """
        Check candidate against existing facts in target memory.

        Returns one of:
          "keep_new"   — store candidate as a new fact
          "duplicate"  — discard, already covered
          "replace:N"  — replace fact at index N with candidate
          "contradict:N" — store candidate, lower confidence on fact N
        """
        existing = target.get("facts", [])
        if not existing or not self.llm_fn:
            return "keep_new"

        existing_lines = "\n".join(
            f"  [{i}] {_fact_text(f)}"
            for i, f in enumerate(existing)
        )
        prompt = _DEDUP_PROMPT.format(
            candidate=candidate,
            existing=existing_lines,
        )
        raw  = self._call_llm(prompt)
        data = self._parse_json(raw)
        if not isinstance(data, dict):
            return "keep_new"

        action = data.get("action", "keep_new")
        if action == "replace":
            idx = data.get("replace_index")
            if idx is not None:
                return f"replace:{idx}"
        elif action == "contradict":
            idx = data.get("contradict_index")
            if idx is not None:
                return f"contradict:{idx}"
        elif action == "duplicate":
            return "duplicate"
        return "keep_new"

    # ─────────────────────────────────────────────────────────────
    # Facts  (public API)
    # ─────────────────────────────────────────────────────────────

    def add_fact(self, fact: str, project_scoped=False, source_files: list = None):
        """
        Add a fact, running LLM deduplication first.
        source_files: optional list of relative file paths this fact came from.
        """
        fact = fact.strip()
        if not fact:
            return

        target = (
            self.project_memory
            if (project_scoped and self.project_memory is not None)
            else self.global_memory
        )

        # Run dedup
        decision = self._deduplicate_fact(fact, target)

        if decision == "duplicate":
            # Reinforce confidence on the existing matching fact
            self._reinforce_similar_fact(fact, target)
            return

        new_fact = _make_fact(fact, source_files)

        if decision.startswith("replace:"):
            try:
                idx = int(decision.split(":")[1])
                if 0 <= idx < len(target["facts"]):
                    # Carry over source_files from old fact
                    old_files = target["facts"][idx].get("source_files", [])
                    new_fact["source_files"] = list(
                        set(old_files + (source_files or []))
                    )
                    target["facts"][idx] = new_fact
                    print(f"[Memory] replaced fact [{idx}]: {fact[:60]}")
                else:
                    target["facts"].append(new_fact)
            except (ValueError, IndexError):
                target["facts"].append(new_fact)

        elif decision.startswith("contradict:"):
            try:
                idx = int(decision.split(":")[1])
                if 0 <= idx < len(target["facts"]):
                    target["facts"][idx]["confidence"] = CONFIDENCE_STALE
                    print(f"[Memory] lowered confidence on fact [{idx}] (contradiction)")
            except (ValueError, IndexError):
                pass
            target["facts"].append(new_fact)

        else:
            # keep_new
            target["facts"].append(new_fact)
            print(f"[Memory] new fact: {fact[:60]}")

        if len(target["facts"]) > MAX_FACTS:
            # Prune lowest-confidence facts first
            target["facts"].sort(key=lambda f: f.get("confidence", 1.0), reverse=True)
            target["facts"] = target["facts"][:MAX_FACTS]

        if project_scoped and self.project_memory is not None:
            self._save_project()
        else:
            self._save_global()

    def _reinforce_similar_fact(self, fact_text: str, target: dict):
        """Bump last_seen and confidence on a fact that was confirmed as duplicate."""
        today = date.today().isoformat()
        for f in target["facts"]:
            if _fact_text(f).lower() == fact_text.lower():
                f["last_seen"]  = today
                f["confidence"] = min(CONFIDENCE_INITIAL, f.get("confidence", 1.0) + 0.1)
                return

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
        """Return list of fact text strings for context building."""
        facts = [_fact_text(f) for f in self.global_memory["facts"]]
        if include_project and self.project_memory:
            existing = set(facts)
            for f in self.project_memory["facts"]:
                t = _fact_text(f)
                if t not in existing:
                    facts.append(t)
        return facts

    def get_global_facts(self) -> list:
        return [_fact_text(f) for f in self.global_memory["facts"]]

    def get_project_facts(self) -> list:
        if not self.project_memory:
            return []
        return [_fact_text(f) for f in self.project_memory["facts"]]

    def get_facts_raw(self, project_scoped=False) -> list:
        """Return raw fact dicts (for memory panel display)."""
        target = (
            self.project_memory
            if (project_scoped and self.project_memory is not None)
            else self.global_memory
        )
        return target.get("facts", [])

    # ─────────────────────────────────────────────────────────────
    # Staleness review  (called by WikiIndexer after page generation)
    # ─────────────────────────────────────────────────────────────

    def review_facts_for_file(self, source_rel: str, wiki_text: str):
        """
        After a wiki page is regenerated, review any facts tagged to
        that source file and adjust confidence based on the updated content.

        Called from WikiIndexer in a background thread — safe, no Qt calls.
        """
        if not self.llm_fn:
            return

        for memory, is_project in (
            (self.global_memory,  False),
            (self.project_memory, True),
        ):
            if memory is None:
                continue

            tagged = [
                (i, f) for i, f in enumerate(memory["facts"])
                if source_rel in f.get("source_files", [])
            ]
            if not tagged:
                continue

            facts_text = "\n".join(
                f"  [{i}] {_fact_text(f)}" for i, f in tagged
            )
            prompt = _STALENESS_PROMPT.format(
                source_file=source_rel,
                wiki_text=wiki_text[:3000],
                facts=facts_text,
            )
            raw  = self._call_llm(prompt)
            data = self._parse_json(raw)
            if not isinstance(data, list):
                continue

            changed = False
            for item in data:
                if not isinstance(item, dict):
                    continue
                # item["index"] is the index within `tagged`, not `memory["facts"]`
                tagged_idx = item.get("index")
                if tagged_idx is None or tagged_idx >= len(tagged):
                    continue
                fact_idx, fact = tagged[tagged_idx]
                verdict = item.get("verdict", "current")

                if verdict == "stale":
                    fact["confidence"] = max(0.0, fact.get("confidence", 1.0) - 0.5)
                    print(f"[Memory] stale fact [{fact_idx}]: {_fact_text(fact)[:60]}")
                    changed = True
                elif verdict == "uncertain":
                    fact["confidence"] = CONFIDENCE_STALE
                    changed = True
                elif verdict == "current":
                    fact["last_seen"] = date.today().isoformat()
                    changed = True

            if changed:
                if is_project:
                    self._save_project()
                else:
                    self._save_global()

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