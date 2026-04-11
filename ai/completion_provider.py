"""
ai/completion_provider.py

AI-powered completion provider for QuillAI.

Makes a direct (non-streaming) request to the active backend and returns
a list of LSP-shaped completion items with source="ai" for display in the
CompletionPopup alongside (or instead of) LSP results.

Used in two modes:
  - Supplement: fires in parallel with LSP, AI items appended after LSP items
  - Standalone:  fires alone when no LSP server supports the current file
"""

import json
import threading
import requests
from typing import Callable


# AI completion item kind — displayed as ✦ in the popup
AI_KIND = 99


def _build_prompt(
    file_path: str,
    prefix: str,        # text before cursor (up to ~60 lines)
    suffix: str,        # text after cursor (~10 lines)
    word: str,          # current incomplete word / trigger
    lsp_labels: list,   # labels already provided by LSP (to avoid dupes)
    repo_map: str = "",
) -> list:
    """Build the messages list for the completion request."""

    lang = _detect_language(file_path)
    lang_hint = f"Language: {lang}\n" if lang else ""
    file_hint = f"File: {file_path}\n" if file_path else ""

    lsp_hint = ""
    if lsp_labels:
        sample = ", ".join(lsp_labels[:12])
        lsp_hint = (
            f"\nThe LSP server already provided these completions (do NOT repeat them): "
            f"{sample}\n"
        )

    repo_hint = ""
    if repo_map:
        repo_hint = f"\n<repo_map>\n{repo_map[:1200]}\n</repo_map>\n"

    system = (
        "You are an expert code completion engine embedded in an IDE. "
        "Your ONLY job is to suggest what should come next at the cursor. "
        "Respond with a JSON array of completion objects and NOTHING else — "
        "no prose, no markdown fences, no explanation. "
        "Each object must have these fields:\n"
        '  "label":  the completion text to insert (the full symbol/expression)\n'
        '  "detail": a very short type or signature hint (e.g. "(x, y) -> bool")\n'
        '  "documentation": one sentence explaining what it does\n'
        '  "kind":   one of: function, method, class, variable, keyword, '
        'snippet, value\n'
        "Rules:\n"
        "- Return 4–8 items, most relevant first\n"
        "- Prefer multi-token, semantic completions over single-word ones\n"
        "- For comment lines, suggest the full implementation as a snippet\n"
        "- Match the coding style visible in the context\n"
        "- Never return the same text as the prefix already contains\n"
    )

    user = (
        f"{lang_hint}{file_hint}{lsp_hint}{repo_hint}"
        f"\n<context_before>\n{prefix}\n</context_before>"
        f"\n<context_after>\n{suffix}\n</context_after>"
        f"\n\nCursor is after: {json.dumps(word)}"
        f"\n\nReturn the JSON array now."
    )

    return [
        {"role": "system", "content": system},
        {"role": "user",   "content": user},
    ]


def _detect_language(file_path: str) -> str:
    if not file_path:
        return ""
    ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
    return {
        "py":   "Python",
        "js":   "JavaScript",
        "ts":   "TypeScript",
        "tsx":  "TypeScript/React",
        "jsx":  "JavaScript/React",
        "sh":   "Bash",
        "bash": "Bash",
        "nix":  "Nix",
        "lua":  "Lua",
        "pl":   "Perl",
        "pm":   "Perl",
        "yaml": "YAML",
        "yml":  "YAML",
        "md":   "Markdown",
        "html": "HTML",
        "css":  "CSS",
        "json": "JSON",
        "rs":   "Rust",
        "go":   "Go",
        "cpp":  "C++",
        "c":    "C",
        "rb":   "Ruby",
    }.get(ext, "")


def _kind_to_lsp_int(kind_str: str) -> int:
    """Map AI kind string to LSP CompletionItemKind int for icon lookup."""
    return {
        "function":  3,
        "method":    2,
        "class":     7,
        "variable":  6,
        "keyword":   14,
        "snippet":   15,
        "value":     12,
        "module":    9,
    }.get(kind_str.lower(), AI_KIND)


def _parse_response(text: str) -> list:
    """
    Extract the JSON array from the model response.
    Handles models that wrap output in markdown fences.
    """
    text = text.strip()

    # Strip markdown fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(
            l for l in lines
            if not l.strip().startswith("```")
        ).strip()

    # Find the outermost JSON array
    start = text.find("[")
    end   = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []

    try:
        raw_items = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return []

    items = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        label = str(raw.get("label", "")).strip()
        if not label:
            continue

        kind_str = str(raw.get("kind", "value"))
        items.append({
            "label":         label,
            "detail":        str(raw.get("detail", "")),
            "documentation": str(raw.get("documentation", "")),
            "kind":          _kind_to_lsp_int(kind_str),
            "source":        "ai",          # consumed by CompletionPopup
            "sortText":      "zz_" + label, # sorts AI items after LSP items
        })

    return items


def _make_request(
    messages: list,
    settings,
) -> list:
    """
    Synchronous API call — run in a background thread.
    Returns a list of LSP-shaped completion items.
    """
    backend = settings.get_backend()
    model   = settings.get_inline_model()
    api_key = settings.get_api_key()

    headers = {
        "Content-Type": "application/json",
        "User-Agent":   "QuillAI-IDE/1.0",
    }

    # ── Anthropic ────────────────────────────────────────────────────────
    if backend == "claude":
        url = "https://api.anthropic.com/v1/messages"
        headers["x-api-key"]         = api_key.strip()
        headers["anthropic-version"] = "2023-06-01"

        # Anthropic uses system as a top-level field
        system_content = ""
        user_messages  = []
        for msg in messages:
            if msg["role"] == "system":
                system_content = msg["content"]
            else:
                user_messages.append(msg)

        payload = {
            "model":      model,
            "max_tokens": 512,
            "system":     system_content,
            "messages":   user_messages,
        }

    # ── OpenAI / local ───────────────────────────────────────────────────
    else:
        if backend == "openai":
            url = settings.get("cloud_llm_url") or "https://api.openai.com/v1/chat/completions"
            if api_key:
                headers["Authorization"] = f"Bearer {api_key.strip()}"
        else:
            # llama — use chat/completions endpoint (not FIM) for structured JSON
            url = settings.get("local_llm_url") or "http://localhost:11434/v1/chat/completions"

        payload = {
            "model":       model,
            "messages":    messages,
            "max_tokens":  512,
            "temperature": 0.2,
            "stream":      False,
        }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=8)
        if resp.status_code != 200:
            print(f"[ai_completion] API error {resp.status_code}: {resp.text[:200]}")
            return []

        data = resp.json()

        # Extract text content from response
        if backend == "claude":
            content_blocks = data.get("content", [])
            text = " ".join(
                b.get("text", "") for b in content_blocks
                if b.get("type") == "text"
            )
        else:
            choices = data.get("choices", [])
            if not choices:
                return []
            text = choices[0].get("message", {}).get("content", "")

        return _parse_response(text)

    except requests.exceptions.Timeout:
        print("[ai_completion] request timed out")
        return []
    except Exception as e:
        print(f"[ai_completion] error: {e}")
        return []


class AICompletionProvider:
    """
    Async AI completion requests.

    Usage:
        provider = AICompletionProvider(settings_manager)
        provider.request(
            file_path, prefix, suffix, word,
            lsp_labels=[...],
            repo_map="...",
            callback=fn,   # called on main thread via Qt signal
        )
    """

    def __init__(self, settings):
        self._settings = settings
        self._current_thread: threading.Thread | None = None
        self._cancelled = False

    def cancel(self):
        """Cancel any in-flight request."""
        self._cancelled = True

    def request(
        self,
        file_path: str,
        prefix: str,
        suffix: str,
        word: str,
        callback: Callable[[list], None],
        lsp_labels: list | None = None,
        repo_map: str = "",
    ):
        """
        Fire an async completion request.
        `callback` is called with the item list from a background thread —
        callers must marshal to the main thread (use QMetaObject.invokeMethod
        or a Qt signal).
        """
        self._cancelled = False
        messages = _build_prompt(
            file_path, prefix, suffix, word,
            lsp_labels or [],
            repo_map,
        )
        settings = self._settings

        cancelled_ref = [False]

        def run():
            if cancelled_ref[0]:
                return
            items = _make_request(messages, settings)
            if not cancelled_ref[0]:
                callback(items)

        self._cancelled_ref = cancelled_ref
        t = threading.Thread(target=run, daemon=True)
        self._current_thread = t
        t.start()

    def cancel(self):
        if hasattr(self, "_cancelled_ref"):
            self._cancelled_ref[0] = True