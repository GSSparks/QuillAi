"""
ai/ai_editor_worker.py

AIEditorWorker — streams AI-generated code directly into the editor.

Two phases:
  1. Plan call  — fast, non-streaming. Sends file content + user request,
                  model returns the best insertion line number.
  2. Stream call — streams the actual code to insert at that line.

Signals:
  chunk_ready(str, int)   — text chunk + target document position
  insertion_ready(int)    — insertion position confirmed, ready to stream
  finished()
  error(str)
"""

import json
import re
import requests

from PyQt6.QtCore import QObject, pyqtSignal, QThread, pyqtSlot


# Triggers that indicate the user wants AI to write into the editor
EDITOR_WRITE_TRIGGERS = re.compile(
    r'\b(add|write|insert|implement|create|put|generate|type)\b',
    re.IGNORECASE,
)


def wants_editor_write(text: str) -> bool:
    """Return True if the message looks like a request to write code."""
    t = text.lower().strip()
    # Must have a write verb AND some target indicator
    has_verb = bool(EDITOR_WRITE_TRIGGERS.search(t))
    has_target = any(w in t for w in [
        'here', 'function', 'method', 'class', 'docstring', 'comment',
        'import', 'above', 'below', 'after', 'before', 'at the', 'end of',
        'top of', 'bottom of', 'this file', 'the file',
    ])
    return has_verb and has_target


class AIEditorWorker(QObject):
    """
    Streams AI code directly into the editor at the best insertion point.
    """

    insertion_ready = pyqtSignal(int)   # document char position to insert at
    chunk_ready     = pyqtSignal(str)   # next text chunk to insert
    finished        = pyqtSignal()
    error           = pyqtSignal(str)

    def __init__(
        self,
        user_request: str,
        file_content: str,
        file_path: str,
        model: str,
        api_url: str,
        api_key: str,
        backend: str,
        parent=None,
    ):
        super().__init__(parent)
        self.user_request = user_request
        self.file_content = file_content
        self.file_path    = file_path
        self.model        = model
        self.api_url      = api_url.rstrip("/")
        self.api_key      = api_key
        self.backend      = backend.lower()
        self._cancelled   = False

    def cancel(self):
        self._cancelled = True

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.backend == "claude":
            h["x-api-key"]         = self.api_key.strip()
            h["anthropic-version"] = "2023-06-01"
        elif self.backend != "gemini":
            h["Authorization"] = f"Bearer {self.api_key.strip()}"
        return h

    def _plan_call(self) -> int:
        """
        Ask the model where to insert the code.
        Returns the line number (1-indexed) to insert after.

        Smart approach: grep the file for the relevant symbol first,
        send only a focused excerpt instead of the whole file.
        """
        import re as _re
        lines = self.file_content.splitlines()

        # Try to extract the target symbol from the request
        # e.g. "add docstring to jump_to_click" -> "jump_to_click"
        sym_match = _re.search(
            r'(?:to|for|in|of)\s+["\']?([\w_]+)["\']?\s*(?:function|method|class|def)?',
            self.user_request, _re.IGNORECASE
        )
        if not sym_match:
            sym_match = _re.search(r'([\w_]+)\s*(?:function|method|class)',
                                   self.user_request, _re.IGNORECASE)

        # Find the symbol in the file
        focus_start = 0
        focus_end   = min(len(lines), 100)  # default: first 100 lines

        if sym_match:
            sym = sym_match.group(1)
            for i, line in enumerate(lines):
                if _re.search(rf'\bdef\s+{_re.escape(sym)}\b|\bclass\s+{_re.escape(sym)}\b', line):
                    focus_start = max(0, i - 3)
                    focus_end   = min(len(lines), i + 20)
                    break

        excerpt = lines[focus_start:focus_end]
        numbered = "\n".join(f"{focus_start+i+1}: {l}"
                              for i, l in enumerate(excerpt))

        plan_prompt = (
            f"You are a code editor assistant. "
            f"The user wants to: {self.user_request}\n\n"
            f"Here is the relevant part of the file (lines {focus_start+1}-{focus_end}):\n"
            f"{numbered}\n\n"
            f"Reply with ONLY a JSON object like: "
            f'{{\"insert_after_line\": 42, \"reason\": \"after def line\"}}\n'
            f"Choose the best line number to insert after (from the ACTUAL line numbers shown). "
            f"For a docstring, insert after the def/class line. "
            f"Do not include any other text."
        )

        try:
            if self.backend == "claude":
                payload = {
                    "model":      self.model,
                    "max_tokens": 100,
                    "messages":   [{"role": "user", "content": plan_prompt}],
                    "stream":     False,
                }
                resp = requests.post(
                    self.api_url, json=payload,
                    headers=self._headers(), timeout=30
                )
                data = resp.json()
                text = " ".join(
                    b.get("text", "") for b in data.get("content", [])
                    if b.get("type") == "text"
                )
            elif self.backend == "gemini":
                url  = (
                    f"https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{self.model}:generateContent?key={self.api_key.strip()}"
                )
                payload = {
                    "contents": [{"role": "user", "parts": [{"text": plan_prompt}]}],
                    "generationConfig": {"maxOutputTokens": 100},
                }
                resp = requests.post(url, json=payload, timeout=30)
                data = resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
            else:
                payload = {
                    "model":      self.model,
                    "max_tokens": 100,
                    "messages":   [{"role": "user", "content": plan_prompt}],
                    "stream":     False,
                }
                resp = requests.post(
                    self.api_url, json=payload,
                    headers=self._headers(), timeout=30
                )
                data    = resp.json()
                choices = data.get("choices", [])
                text    = choices[0]["message"]["content"] if choices else ""

            # Parse JSON from response
            m = re.search(r'\{[^}]+\}', text)
            if m:
                obj = json.loads(m.group(0))
                return int(obj.get("insert_after_line", len(lines)))
        except Exception as e:
            print(f"[AIEditorWorker] plan call failed: {e}")

        # Default: insert at end of file
        return len(lines)

    def _line_to_char_pos(self, line: int) -> int:
        """Convert 1-indexed line number to document character position."""
        lines = self.file_content.splitlines(keepends=True)
        pos = sum(len(l) for l in lines[:line])
        return pos

    def _stream_code(self, insert_pos: int):
        """Stream the actual code insertion."""
        lines = self.file_content.splitlines()
        insert_after = next(
            (i+1 for i, l in enumerate(lines)
             if sum(len(x) + 1 for x in lines[:i+1]) >= insert_pos),
            len(lines)
        )

        context_before = "\n".join(lines[max(0, insert_after-10):insert_after])
        context_after  = "\n".join(lines[insert_after:insert_after+5])

        stream_prompt = (
            f"You are writing code directly into a file. "
            f"The user wants to: {self.user_request}\n\n"
            f"Code before insertion point:\n```\n{context_before}\n```\n\n"
            f"Code after insertion point:\n```\n{context_after}\n```\n\n"
            f"Write ONLY the code to insert. "
            f"No explanation, no markdown fences, no preamble. "
            f"Match the indentation style of the surrounding code. "
            f"End with a single blank line."
        )

        try:
            if self.backend == "claude":
                payload = {
                    "model":      self.model,
                    "max_tokens": 2048,
                    "system":     "Output only raw code. No markdown. No explanation.",
                    "messages":   [{"role": "user", "content": stream_prompt}],
                    "stream":     True,
                }
                resp = requests.post(
                    self.api_url, json=payload,
                    headers=self._headers(), stream=True, timeout=60
                )
                self._parse_claude_stream(resp)

            elif self.backend == "gemini":
                url = (
                    f"https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{self.model}:streamGenerateContent?key={self.api_key.strip()}"
                )
                payload = {
                    "contents": [{"role": "user", "parts": [{"text": stream_prompt}]}],
                    "system_instruction": {
                        "parts": [{"text": "Output only raw code. No markdown. No explanation."}]
                    },
                    "generationConfig": {"maxOutputTokens": 2048},
                }
                resp = requests.post(url, json=payload, stream=True, timeout=60)
                self._parse_gemini_stream(resp)

            else:
                full_messages = [
                    {"role": "system",
                     "content": "Output only raw code. No markdown. No explanation."},
                    {"role": "user", "content": stream_prompt},
                ]
                payload = {
                    "model":    self.model,
                    "messages": full_messages,
                    "stream":   True,
                }
                resp = requests.post(
                    self.api_url, json=payload,
                    headers=self._headers(), stream=True, timeout=60
                )
                self._parse_openai_stream(resp)

        except Exception as e:
            self.error.emit(str(e))

    def _parse_openai_stream(self, response):
        for line in response.iter_lines():
            if self._cancelled:
                return
            if not line:
                continue
            try:
                decoded = line.decode("utf-8")
            except Exception:
                continue
            if not decoded.startswith("data: "):
                continue
            data = decoded[6:]
            if data.strip() == "[DONE]":
                return
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            choices = chunk.get("choices", [])
            content = choices[0].get("delta", {}).get("content") if choices else None
            if content:
                self.chunk_ready.emit(content)

    def _parse_claude_stream(self, response):
        for line in response.iter_lines():
            if self._cancelled:
                return
            if not line:
                continue
            try:
                decoded = line.decode("utf-8")
            except Exception:
                continue
            if decoded.startswith("event:"):
                if "message_stop" in decoded:
                    return
                continue
            if not decoded.startswith("data: "):
                continue
            data = decoded[6:]
            if data.strip() == "[DONE]":
                return
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            if chunk.get("type") != "content_block_delta":
                continue
            content = chunk.get("delta", {}).get("text")
            if content:
                self.chunk_ready.emit(content)

    def _parse_gemini_stream(self, response):
        for line in response.iter_lines():
            if self._cancelled:
                return
            if not line:
                continue
            try:
                decoded = line.decode("utf-8")
            except Exception:
                continue
            if not decoded.startswith("data: "):
                continue
            data = decoded[6:]
            if data.strip() == "[DONE]":
                return
            try:
                chunk = json.loads(data)
                content = chunk["candidates"][0]["content"]["parts"][0]["text"]
                if content:
                    self.chunk_ready.emit(content)
            except (KeyError, IndexError, json.JSONDecodeError):
                continue

    @pyqtSlot()
    def run(self):
        print(f"[AIEditor] run() called on thread {__import__("threading").current_thread().name}")
        try:
            self._run_impl()
        except Exception as e:
            import traceback
            print(f"[AIEditor] EXCEPTION in run(): {e}")
            traceback.print_exc()
            self.error.emit(str(e))
            self.finished.emit()

    def _run_impl(self):
        # Phase 1: plan
        insert_line = self._plan_call()
        if self._cancelled:
            self.finished.emit()
            return

        insert_pos = self._line_to_char_pos(insert_line)
        self.insertion_ready.emit(insert_pos)

        # Phase 2: stream
        self._stream_code(insert_pos)
        self.finished.emit()