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
        self.wiki_context = wiki_context  # ← NEW

        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def build_messages(self):
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
                "Always use paths relative to the project root. "
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
            # Wiki injected into user message so the model attends to it
            # alongside the actual question, not buried in system.
            user_content = self.prompt + wiki
            return [
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ]

        before = self.editor_text[max(0, self.cursor_pos - 1000):self.cursor_pos]
        after = self.editor_text[self.cursor_pos:self.cursor_pos + 300]

        if self.is_edit:
            return [
                {
                    "role": "system",
                    "content": "Return ONLY clean Python code. No markdown. No explanation.",
                },
                {
                    "role": "user",
                    "content": self.prompt + wiki,
                },
            ]

        elif self.generate_function:
            return [
                {
                    "role": "system",
                    "content": "Return ONLY valid Python code.",
                },
                {
                    "role": "user",
                    "content": f"""
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
""",
                },
            ]

        else:
            # Inline ghost — wiki prepended to context_before so FIM and
            # chat-fallback paths both receive it naturally.
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
        """Infer the language from the editor context."""
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

    def run(self):
        print(f"🚀 Worker created with api_url='{self.api_url}' backend='{self.backend}'")
        raw_output = ""
        last_emitted = ""

        try:
            is_inline = not self.generate_function and not self.is_edit and not self.is_chat
            is_local = self.backend == "llama"
            is_openai = self.backend == "openai"

            headers = {
                "Content-Type": "application/json",
                "User-Agent": "QuillAI-IDE/1.0",
            }

            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key.strip()}"

            # -------------------------------
            # 🚀 ROUTING LOGIC
            # -------------------------------
            if is_inline:
                if is_local:
                    # ✅ llama.cpp FIM
                    target_url = self.api_url.replace("/v1/chat/completions", "/infill")

                    before = self.editor_text[max(0, self.cursor_pos - 1000):self.cursor_pos]
                    after = self.editor_text[self.cursor_pos:self.cursor_pos + 300]

                    # Prepend wiki context to FIM prefix when available
                    wiki = _wiki_block(self.wiki_context)
                    fim_prefix = (wiki + "\n\n" + before) if wiki else before

                    print(f"👻 Using llama.cpp FIM → {target_url}")

                    payload = {
                        "input_prefix": fim_prefix,
                        "input_suffix": after,
                        "temperature": 0.1,
                        "stream": True,
                        "n_predict": 60,
                        "stop": ["\n\n", "```"],
                    }

                else:
                    # ⚠️ OpenAI fallback (no FIM support)
                    print("⚠️ OpenAI inline fallback (no FIM support)")

                    target_url = self.api_url
                    payload = {
                        "model": self.model,
                        "messages": self.build_messages(),
                        "temperature": 0.1,
                        "stream": True,
                    }

            else:
                # ✅ Chat / Function / Edit
                target_url = self.api_url

                payload = {
                    "model": self.model,
                    "messages": self.build_messages(),
                    "temperature": 0.7 if not is_inline else 0.1,
                    "stream": True,
                }

            print(f"🌐 Backend: {self.backend} | URL: {target_url} | Wiki context: {len(self.wiki_context)} chars")

            timeout = 5 if is_inline else 60

            response = requests.post(
                target_url,
                json=payload,
                headers=headers,
                stream=True,
                timeout=timeout,
            )

            if response.status_code != 200:
                print(f"❌ API Error {response.status_code}: {response.text}")
                self.finished.emit()
                return

            # -------------------------------
            # 📡 STREAM PARSING
            # -------------------------------
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

                if is_inline and is_local:
                    content = chunk.get("content")
                else:
                    choices = chunk.get("choices", [])
                    if choices:
                        content = choices[0].get("delta", {}).get("content")
                    else:
                        content = None

                if not content:
                    continue

                raw_output += content

                # -------------------------------
                # 💬 CHAT MODE
                # -------------------------------
                if self.is_chat:
                    self.chat_update.emit(content)
                    continue

                cleaned = clean_code(raw_output)

                # -------------------------------
                # 🧠 FUNCTION / EDIT MODE
                # -------------------------------
                if self.generate_function or self.is_edit:
                    if cleaned.startswith(last_emitted):
                        delta = cleaned[len(last_emitted):]
                    else:
                        delta = cleaned

                    last_emitted = cleaned
                    self.function_ready.emit(delta)

                # -------------------------------
                # 👻 INLINE GHOST MODE
                # -------------------------------
                else:
                    recent = self.editor_text[max(0, self.cursor_pos - 100):self.cursor_pos]

                    overlap = 0
                    max_overlap = min(len(recent), len(cleaned))

                    for i in range(max_overlap, 0, -1):
                        if recent.endswith(cleaned[:i]):
                            overlap = i
                            break

                    ghost = cleaned[overlap:]
                    self.update_ghost.emit(ghost)

        except requests.exceptions.Timeout:
            print("⏳ Request timed out.")
        except Exception as e:
            print("🚨 Worker error:", e)
        finally:
            self.finished.emit()
