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
    ):
        super().__init__()
        self.user_text    = user_text
        self.context      = context
        self.project_root = project_root
        self.model        = model
        self.api_url      = api_url.rstrip("/")
        self.api_key      = api_key
        self.backend      = backend.lower()
        self.repo_map     = repo_map
        self._cancelled   = False
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
            for tc in read_calls:
                if self._cancelled:
                    return
                name = tc["name"]
                desc = describe_tool_call(name, tc["attrs"])

                # Emit status update
                self._tool_log.append((name, desc, None))
                self._emit_status_panel()

                success, output = run_tool(name, tc["attrs"], self.project_root)
                summary = output[:100] + "..." if len(output) > 100 else output

                # Update log with result
                self._tool_log[-1] = (name, desc, summary)
                self._emit_status_panel()

                tool_results.append(
                    f'<tool_result name="{name}" success="{str(success).lower()}">'
                    f'\n{output}\n</tool_result>'
                )

            # If no tool calls and no done signal, we're implicitly done
            if not tool_calls:
                done = True

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
                "max_tokens": 4096,
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
                "max_tokens":  4096,
                "temperature": 0.2,
                "stream":      False,
            }

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=60)
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

    def _build_system_prompt(self) -> str:
        return (
            "You are QuillAI, an AI coding assistant with tool access. "
            "You can investigate the codebase using tools before answering. "
            "Use tools to look up symbols, read files, and search for patterns. "
            "Always investigate thoroughly before proposing changes. "
            "Emit write tool calls only after you have gathered all needed context. "
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
        icon_map = {
            "grep":        "🔍",
            "read_file":   "📄",
            "find_files":  "📁",
            "find_symbol": "🔎",
            "run_shell":   "⚙",
            "patch_file":  "✏️",
            "write_file":  "✏️",
            "shell_write": "⚙",
        }

        rows = []
        for name, desc, result in self._tool_log:
            icon   = icon_map.get(name, "🔧")
            status = f"→ {result}" if result else "..."
            rows.append(f"{icon} {desc}\n   {status}")

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