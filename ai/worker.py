import requests
import json
from PyQt6.QtCore import QObject, pyqtSignal


def clean_code(text: str) -> str:
    text = text.strip()

    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        text = "\n".join(lines)

    if text.endswith("```"):
        text = text.rsplit("\n", 1)[0]

    return text.strip()


def _wiki_block(wiki_context: str) -> str:
    """Wrap wiki context in a labeled XML block for the model."""
    if not wiki_context:
        return ""
    return f"\n\n<wiki_context>\n{wiki_context.strip()}\n</wiki_context>"


def _build_headers(backend: str, api_key: str) -> dict:
    """Return the correct auth headers for each backend."""
    base = {
        "Content-Type": "application/json",
        "User-Agent": "QuillAI-IDE/1.0",
    }
    if not api_key:
        return base

    if backend == "claude":
        base["x-api-key"] = api_key.strip()
        base["anthropic-version"] = "2023-06-01"
    elif backend == "gemini":
        pass  # Gemini key goes as ?key= query param, not a header
    else:
        base["Authorization"] = f"Bearer {api_key.strip()}"

    return base


class AIWorker(QObject):
    update_ghost = pyqtSignal(str)
    function_ready = pyqtSignal(str)
    chat_update = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(
        self,
        prompt: str,
        editor_text: str,
        cursor_pos: int,
        generate_function: bool = False,
        is_edit: bool = False,
        is_chat: bool = False,
        model: str = "",
        api_url: str = "",
        api_key: str = "",
        backend: str = "openai",
        wiki_context: str = "",
    ):
        super().__init__()

        self.prompt = prompt
        self.editor_text = editor_text
        self.cursor_pos = int(cursor_pos)
        self.generate_function = generate_function
        self.is_edit = is_edit
        self.is_chat = is_chat
        self.model = model
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.backend = backend.lower()
        self.wiki_context = wiki_context

        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def build_messages(self) -> tuple:
        """Return (system_prompt: str, messages: list).
        Keeping system separate lets each backend place it correctly:
        Anthropic → top-level `system` param; OpenAI → role=system message.
        """
        lang = self._detect_language()
        wiki = _wiki_block(self.wiki_context)

        if self.is_chat:
            system = (
                f"You are QuillAI, an AI coding agent built directly into the user's IDE. "
                f"For questions about the codebase — finding usages, locating files, "
                f"understanding structure, or making changes — you MUST emit "
                f"<needs_tools/> as your entire response so QuillAI can give you "
                f"tool access to investigate accurately. "
                f"Do NOT answer codebase investigation questions from memory or guess. "
                f"For general programming questions not specific to this codebase, "
                f"answer normally without <needs_tools/>. "
            )
            if lang:
                system += f"The user is currently working in {lang}. "
            system += (
                "IMPORTANT: If you need to search files, read code, or investigate "
                "the project to answer accurately — and the source code provided is "
                "insufficient — emit <needs_tools/> as the FIRST thing in your response "
                "instead of guessing. QuillAI will then give you full tool access. "
                "Only emit <needs_tools/> when you genuinely cannot answer from the "
                "provided context. Do NOT emit it for general questions. "
                "\n"
                "Be concise and use markdown for code blocks. "
                "When suggesting code, match the style and conventions visible "
                "in the provided context. "
                "If memory or past conversations are provided, use them to give "
                "more personalised and relevant responses. "
                "IMPORTANT: Source code is injected at the top of the user message. "
                "When answering questions about how something works or what a function does, "
                "you MUST use ONLY the source code provided — do not invent, guess, or "
                "paraphrase from memory. Quote the actual implementation. "
                "If no source code is provided for a symbol, say so explicitly rather "
                "than generating a plausible-looking implementation. "
                "When you suggest a code change to a specific file, wrap it in a "
                "file_change tag so the user can apply it directly: "
                "<file_change path=\"relative/path/to/file.py\" mode=\"function\"> "
                "def my_function(...): ... </file_change> "
                "Use mode=\"function\" to replace a single function or class (preferred). "
                "Use mode=\"full\" only when rewriting the entire file. "
"When using mode=full, you MUST include the COMPLETE file content — "
"every single line. Never output just a snippet or just the changed part. "
                "Always use paths relative to the project root. "
"NEVER use absolute paths like /home/user/... or /dev/... in file_change tags. "
"Use only the filename or relative path like editor/ghost_editor.py. "
                "IMPORTANT: When a refactor, rename, or change affects multiple files, "
                "you MUST emit a separate file_change tag for EACH affected file. "
                "Do not ask the user to make changes manually if you can emit file_change tags. "
                "Multiple file_change tags in one response are fully supported and preferred "
                "over partial changes."
                "When renaming a symbol or refactoring, you MUST write the complete, "
                "full implementation of every function — never use pass, ..., or stubs. "
                "The output must be production-ready code, not a skeleton. "
                "Use file_change when suggesting code changes to specific files. "
                "Always write the complete full implementation, never stubs."
            )
            user_content = self.prompt + wiki
            return system, [{"role": "user", "content": user_content}]

        before = self.editor_text[max(0, self.cursor_pos - 1000):self.cursor_pos]
        after = self.editor_text[self.cursor_pos:self.cursor_pos + 300]

        if self.is_edit:
            return (
                "Return ONLY clean Python code. No markdown. No explanation.",
                [{"role": "user", "content": self.prompt + wiki}],
            )

        elif self.generate_function:
            return (
                "Return ONLY valid Python code.",
                [{"role": "user", "content": f"""
Generate a complete Python function.

Context BEFORE:
{before}

Context AFTER:
{after}

Request:
{self.prompt}
{wiki}
Rules:
- Only Python code
- No markdown
- No explanation
"""}],
            )

        else:
            wiki_prefix = wiki + "\n\n" if wiki else ""
            return [
                {
                    "role": "system",
                    "content": "Return ONLY the missing code at the cursor. No markdown.",
                },
                {
                    "role": "user",
                    "content": f"""
<context_before>
{wiki_prefix}{before}
</context_before>
<context_after>
{after}
</context_after>

Only output the exact missing code between contexts.
Do NOT repeat any code from context_after.
""",
                },
            ]

    def _detect_language(self) -> str:
        context = (self.prompt + self.editor_text).lower()
        patterns = [
            ("Python",     ["def ", "import ", "class ", "elif ", "print("]),
            ("Nix",        ["nixpkgs", "mkshell", "buildInputs", "environment.systemPackages"]),
            ("Ansible",    ["ansible.builtin", "- name:", "hosts:", "tasks:"]),
            ("Bash",       ["#!/bin/bash", "#!/usr/bin/env bash", "echo ", "fi\n", "done\n"]),
            ("HTML",       ["<!doctype", "<html", "<div", "<body"]),
            ("JavaScript", ["const ", "let ", "function ", "=>"]),
            ("TypeScript", ["interface ", ": string", ": number", "tsx"]),
            ("YAML",       ["---\n", "  - ", ": \n"]),
        ]
        for lang, signals in patterns:
            if any(s in context for s in signals):
                return lang
        return ""

    def _parse_claude_stream(self, response) -> None:
        """
        Parse Anthropic's native SSE stream format.
        Events: message_start, content_block_start, content_block_delta, message_stop
        The actual text lives in delta.text inside content_block_delta events.
        """
        raw_output = ""
        last_emitted = ""

        for line in response.iter_lines():
            if self._cancelled:
                break
            if not line:
                continue

            try:
                decoded = line.decode("utf-8")
            except Exception:
                continue

            # SSE lines are either "event: <type>" or "data: <json>"
            if decoded.startswith("event:"):
                event_type = decoded[6:].strip()
                if event_type == "message_stop":
                    break
                continue

            if not decoded.startswith("data: "):
                continue

            data = decoded[6:]
            if data.strip() == "[DONE]":
                break

            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue

            # Only content_block_delta carries text
            if chunk.get("type") != "content_block_delta":
                continue

            content = chunk.get("delta", {}).get("text")
            if not content:
                continue

            self._emit_content(content, raw_output, last_emitted)
            raw_output += content
            if self.generate_function or self.is_edit:
                last_emitted = clean_code(raw_output)

    def _parse_gemini_stream(self, response) -> None:
        """
        Parse Gemini SSE stream.
        Each data chunk is a JSON object with candidates[0].content.parts[0].text
        """
        raw_output = ""
        last_emitted = ""

        for line in response.iter_lines():
            if self._cancelled:
                break
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
                break
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            try:
                content = (
                    chunk["candidates"][0]["content"]["parts"][0]["text"]
                )
            except (KeyError, IndexError):
                continue
            if not content:
                continue
            self._emit_content(content, raw_output, last_emitted)
            raw_output += content
            if self.generate_function or self.is_edit:
                last_emitted = clean_code(raw_output)

    def _parse_openai_stream(self, response) -> None:
        """Parse OpenAI-compatible SSE stream (llama.cpp, OpenAI, inline FIM)."""
        raw_output = ""
        last_emitted = ""
        is_local_fim = self.backend == "llama" and not self.generate_function \
                       and not self.is_edit and not self.is_chat

        for line in response.iter_lines():
            if self._cancelled:
                break
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
                break

            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue

            if is_local_fim:
                content = chunk.get("content")
            else:
                choices = chunk.get("choices", [])
                content = choices[0].get("delta", {}).get("content") if choices else None

            if not content:
                continue

            self._emit_content(content, raw_output, last_emitted)
            raw_output += content
            if self.generate_function or self.is_edit:
                last_emitted = clean_code(raw_output)

    def _emit_content(self, content: str, raw_output: str, last_emitted: str) -> None:
        """Route a content chunk to the correct signal."""
        current_raw = raw_output + content

        if self.is_chat:
            self.chat_update.emit(content)
            return

        cleaned = clean_code(current_raw)

        if self.generate_function or self.is_edit:
            delta = cleaned[len(last_emitted):] if cleaned.startswith(last_emitted) else cleaned
            self.function_ready.emit(delta)
        else:
            # Inline ghost — strip overlap with existing text
            recent = self.editor_text[max(0, self.cursor_pos - 100):self.cursor_pos]
            overlap = 0
            for i in range(min(len(recent), len(cleaned)), 0, -1):
                if recent.endswith(cleaned[:i]):
                    overlap = i
                    break
            self.update_ghost.emit(cleaned[overlap:])

    def run(self):
        print(f"🚀 Worker created with api_url='{self.api_url}' backend='{self.backend}'")

        try:
            is_inline = not self.generate_function and not self.is_edit and not self.is_chat
            is_local  = self.backend == "llama"

            headers = _build_headers(self.backend, self.api_key)

            # ── Routing ───────────────────────────────────────────
            if is_inline and is_local:
                target_url = self.api_url.replace("/v1/chat/completions", "/infill")
                before = self.editor_text[max(0, self.cursor_pos - 1000):self.cursor_pos]
                after  = self.editor_text[self.cursor_pos:self.cursor_pos + 300]
                wiki   = _wiki_block(self.wiki_context)
                payload = {
                    "input_prefix": (wiki + "\n\n" + before) if wiki else before,
                    "input_suffix": after,
                    "temperature":  0.1,
                    "stream":       True,
                    "n_predict":    60,
                    "stop":         ["\n\n", "```"],
                }
                print(f"👻 Using llama.cpp FIM → {target_url}")
            else:
                target_url = self.api_url
                # Gemini requires API key as query param
                if self.backend == "gemini" and self.api_key:
                    target_url = f"{target_url}?key={self.api_key.strip()}"
                system_prompt, messages = self.build_messages()

                if self.backend == "claude":
                    # Anthropic: system is a top-level param, NOT a message role.
                    # max_tokens is required (Anthropic rejects requests without it).
                    payload = {
                        "model":      self.model,
                        "max_tokens": 8192,
                        "messages":   messages,
                        "stream":     True,
                    }
                    if system_prompt:
                        payload["system"] = system_prompt
                elif self.backend == "gemini":
                    # Gemini uses contents[] with parts[], system_instruction separate
                    contents = []
                    for m in messages:
                        role = "user" if m["role"] == "user" else "model"
                        contents.append({"role": role, "parts": [{"text": m["content"]}]})
                    payload = {
                        "contents": contents,
                        "generationConfig": {
                            "temperature": 0.1 if is_inline else 0.7,
                        },
                    }
                    if system_prompt:
                        payload["system_instruction"] = {"parts": [{"text": system_prompt}]}
                    # Gemini streaming uses :streamGenerateContent endpoint
                    target_url = target_url.replace(":generateContent", ":streamGenerateContent")
                else:
                    # OpenAI-compatible: system goes as first message with role="system"
                    full_messages = (
                        [{"role": "system", "content": system_prompt}] + messages
                        if system_prompt else messages
                    )
                    payload = {
                        "model":       self.model,
                        "messages":    full_messages,
                        "temperature": 0.1 if is_inline else 0.7,
                        "stream":      True,
                    }
                if is_inline:
                    print("⚠️ OpenAI inline fallback (no FIM support)")

            print(f"🌐 Backend: {self.backend} | URL: {target_url} | Wiki: {len(self.wiki_context)} chars")

            timeout = 5 if is_inline else 120
            response = requests.post(
                target_url,
                json=payload,
                headers=headers,
                stream=True,
                timeout=timeout,
            )

            if response.status_code != 200:
                print(f"❌ API Error {response.status_code}: {response.text}")
                return

            # ── Stream parsing ────────────────────────────────────
            if self.backend == "claude":
                self._parse_claude_stream(response)
            elif self.backend == "gemini":
                self._parse_gemini_stream(response)
            else:
                self._parse_openai_stream(response)

        except requests.exceptions.Timeout:
            print("⏳ Request timed out.")
        except Exception as e:
            print("🚨 Worker error:", e)
        finally:
            self.finished.emit()