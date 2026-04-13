"""
ai/agent_worker.py

AgentWorker — agentic loop for QuillAI.

Wraps the LLM in a tool-use loop:
  1. Send user message + tool definitions to model
  2. Parse tool_call tags from response
  3. Execute read tools immediately, queue write tools
  4. Feed results back, repeat up to MAX_ITERATIONS
  5. When model emits <agent_done/> or no more tool calls:
     - Stream final answer via chat_update
     - Return queued write ops for user confirmation

Signals (same interface as AIWorker for drop-in compatibility):
  chat_update(str)   — streaming text chunks for chat display
  tool_status(str)   — HTML snippet for the collapsible status panel
  write_ops(list)    — list of pending write operations for confirmation
  finished()
"""

from __future__ import annotations

import json
import re
import requests
from PyQt6.QtCore import QObject, pyqtSignal

from ai.tools import (
    TOOL_DEFINITIONS, run_tool, is_write_tool,
    describe_tool_call, parse_tool_calls,
    has_agent_done, strip_tool_calls,
)

MAX_ITERATIONS = 10


class AgentWorker(QObject):
    chat_update  = pyqtSignal(str)
    tool_status  = pyqtSignal(str)   # emits HTML for status panel
    write_ops    = pyqtSignal(list)  # emits pending write ops
    finished     = pyqtSignal()

    def __init__(
        self,
        user_text: str,
        context: str,          # pre-built context string from ContextEngine
        project_root: str,
        model: str,
        api_url: str,
        api_key: str,
        backend: str,
        repo_map=None,
        settings_manager=None,
        plugin_manager=None,
    ):
        super().__init__()
        self.user_text    = user_text
        self.context      = context
        self.project_root = project_root
        self.model        = model
        self.api_url      = api_url.rstrip("/")
        self.api_key      = api_key
        self.backend      = backend.lower()
        self.repo_map         = repo_map
        self._settings_manager = settings_manager
        self.plugin_manager = plugin_manager
        self._cancelled        = False
        self._tool_log    = []   # [(name, description, result_summary), ...]
        self._write_queue = []   # [{name, attrs, description}, ...]

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            self._agent_loop()
        except Exception as e:
            self.chat_update.emit(f"\n\n⚠ Agent error: {e}")
        finally:
            self.finished.emit()

    # ── Agent loop ────────────────────────────────────────────────────────

    def _agent_loop(self):
        system = self._build_system_prompt()
        messages = [
            {"role": "user", "content": self._build_user_message()}
        ]

        seen_calls: dict = {}  # call_key -> attempt count
        no_tool_streak: int = 0  # consecutive iterations with no new tool calls

        for iteration in range(MAX_ITERATIONS):
            if self._cancelled:
                return

            # Call the model
            response_text = self._call_model(system, messages)
            if not response_text:
                break

            # Parse tool calls
            tool_calls = parse_tool_calls(response_text)
            done       = has_agent_done(response_text)

            # Separate read vs write
            read_calls  = [t for t in tool_calls if not is_write_tool(t["name"])]
            write_calls = [t for t in tool_calls if is_write_tool(t["name"])]

            # Dedup: skip tool calls seen 3+ times
            deduped = []
            for tc in read_calls:
                key = f"{tc['name']}:{tuple(sorted(tc['attrs'].items()))}"
                if seen_calls.get(key, 0) < 3:
                    deduped.append((tc, key))
            read_calls_keyed = deduped
            read_calls = [tc for tc, _ in deduped]

            # Queue write ops (don't execute yet)
            for tc in write_calls:
                desc = describe_tool_call(tc["name"], tc["attrs"])
                self._write_queue.append({
                    "name":        tc["name"],
                    "attrs":       tc["attrs"],
                    "description": desc,
                })

            # Execute read tools and collect results
            tool_results = []
            for tc, call_key in read_calls_keyed:
                if self._cancelled:
                    return
                name = tc["name"]
                desc = describe_tool_call(name, tc["attrs"])

                # Emit status update
                self._tool_log.append((name, desc, None))
                self._emit_status_panel()

                success, output = run_tool(name, tc["attrs"], self.project_root, self.plugin_manager)
                summary = output[:100] + "..." if len(output) > 100 else output
                # Track for dedup
                seen_calls[call_key] = seen_calls.get(call_key, 0) + 1

                # Update log with result
                self._tool_log[-1] = (name, desc, summary)
                self._emit_status_panel()

                tool_results.append(
                    f'<tool_result name="{name}" success="{str(success).lower()}">'
                    f'\n{output}\n</tool_result>'
                )

            # If no tool calls, the response IS the answer — show it
            if not tool_calls:
                clean = strip_tool_calls(response_text)
                if clean:
                    self.chat_update.emit(clean)
                self._emit_status_panel(done=True)
                return

            # Track iterations where all tool calls were deduped away
            if not read_calls and not write_calls:
                no_tool_streak += 1
                if no_tool_streak >= 2:
                    clean = strip_tool_calls(response_text)
                    if clean:
                        self.chat_update.emit(clean)
                    if self._write_queue:
                        self.write_ops.emit(self._write_queue)
                    self._emit_status_panel(done=True)
                    return
            else:
                no_tool_streak = 0


            # Add assistant turn to history
            messages.append({
                "role":    "assistant",
                "content": response_text,
            })

            # If there were tool results, feed them back
            if tool_results:
                messages.append({
                    "role":    "user",
                    "content": "\n\n".join(tool_results),
                })

            # If done or no more tool calls, stream the clean final answer
            if done or not read_calls:
                clean = strip_tool_calls(response_text)
                if clean:
                    self.chat_update.emit(clean)

                # Emit write ops for confirmation if any
                if self._write_queue:
                    self.write_ops.emit(self._write_queue)

                # Finalize status panel
                self._emit_status_panel(done=True)
                return

        # Hit iteration limit
        self.chat_update.emit(
            "\n\n⚠ Reached maximum tool call limit. "
            "Here's what I found so far."
        )
        self._emit_status_panel(done=True)

    # ── Model call ────────────────────────────────────────────────────────

    def _call_model(self, system: str, messages: list) -> str:
        headers = {
            "Content-Type": "application/json",
            "User-Agent":   "QuillAI-IDE/1.0",
        }

        if self.backend == "claude":
            url = "https://api.anthropic.com/v1/messages"
            headers["x-api-key"]         = self.api_key.strip()
            headers["anthropic-version"] = "2023-06-01"
            payload = {
                "model":      self.model,
                "max_tokens": self._get_max_tokens(),
                "system":     system,
                "messages":   messages,
            }
        else:
            if self.backend == "openai":
                url = self.api_url or "https://api.openai.com/v1/chat/completions"
                if self.api_key:
                    headers["Authorization"] = f"Bearer {self.api_key.strip()}"
            else:
                url = self.api_url
            all_messages = [{"role": "system", "content": system}] + messages
            payload = {
                "model":       self.model,
                "messages":    all_messages,
                "max_tokens":  self._get_max_tokens(),
                "temperature": 0.2,
                "stream":      False,
            }

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=120)
            if resp.status_code != 200:
                return ""
            data = resp.json()
            if self.backend == "claude":
                blocks = data.get("content", [])
                return " ".join(b.get("text", "") for b in blocks if b.get("type") == "text")
            else:
                choices = data.get("choices", [])
                if not choices:
                    return ""
                return choices[0].get("message", {}).get("content", "")
        except requests.exceptions.Timeout:
            print("[AgentWorker] request timed out")
            return ""
        except Exception as e:
            return ""

    # ── Prompt builders ───────────────────────────────────────────────────

    def _get_max_tokens(self) -> int:
        """Get max tokens from settings, capped sensibly for agent use."""
        if self._settings_manager:
            budget = self._settings_manager.get_token_budget()
            # Use at most half the budget for response, leave room for prompt
            return min(2048, budget // 2)
        return 1024

    def _build_system_prompt(self) -> str:
        return (
            "You are QuillAI, an AI coding assistant with tool access. "
            "You can investigate the codebase using tools before answering. "
            "Use tools to look up symbols, read files, and search for patterns. "
            "\n\n"
            "patch_file RULE: The 'old' attribute MUST be copied verbatim "
            "from a read_file result — exact whitespace, exact indentation. "
            "Never guess or reconstruct the old text from memory. "
            "If you haven't read the file yet, read it first. "
            "\n\n"
            "STOP RULES — follow these strictly:\n"
            "1. As soon as you have enough information to answer, STOP calling tools "
            "and emit <agent_done/> followed by your answer. "
            "2. If a tool returns the same or equivalent output as a previous call, "
            "you already have that information — do NOT call it again. "
            "3. Do NOT try variations of a command that already succeeded. "
            "If ls showed you the files, do not call ls again with different flags. "
            "4. Use find_files to list files — it is more reliable than ls. "
            "5. After 3 read tool calls, ask yourself: do I have enough to answer? "
            "If yes, stop and answer. "
            "\n\n"
            "WRITE RULES:\n"
            "- Emit write tool calls only after investigation is complete. "
            "- When user confirms with 'yes', 'ok', 'proceed' — immediately emit "
            "write tool calls without re-investigating. "
            "\n\n"
            + TOOL_DEFINITIONS
        )

    def _build_user_message(self) -> str:
        parts = []
        if self.context:
            parts.append(self.context)
        parts.append(self.user_text)
        return "\n\n".join(parts)

    # ── Status panel ──────────────────────────────────────────────────────

    def _emit_status_panel(self, done: bool = False):
        """Emit HTML for the collapsible agent status panel."""
        rows = []
        for name, desc, result in self._tool_log:
            if result:
                first_line = result.splitlines()[0][:60] if result.strip() else ''
                suffix = '...' if len(result.splitlines()) > 1 or len(result) > 60 else ''
                rows.append(f"{desc} → {first_line}{suffix}")
            else:
                rows.append(f"{desc} ...")

        if self._write_queue:
            rows.append("")
            rows.append(f"✏️ {len(self._write_queue)} write operation(s) pending confirmation")

        count   = len(self._tool_log)
        summary = f"✓ {count} tool call{'s' if count != 1 else ''}" if done else f"⟳ {count} tool call{'s' if count != 1 else ''}..."
        content = "\n".join(rows)

        html = json.dumps({
            "type":    "agent_status",
            "summary": summary,
            "content": content,
            "done":    done,
        })
        self.tool_status.emit(html)