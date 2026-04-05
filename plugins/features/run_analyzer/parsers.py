"""
parsers.py

Pattern matchers for Ansible and Terraform/OpenTofu output streams.
Each parser maintains state across chunks and emits structured results.
"""

import re
from dataclasses import dataclass, field
from enum import Enum


class Severity(Enum):
    INFO    = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR   = "error"


@dataclass
class RunEvent:
    """A single detected event from a run."""
    tool:       str           # "ansible" | "terraform" | "tofu"
    severity:   Severity
    title:      str
    detail:     str  = ""
    file_hint:  str  = ""     # filename to search for
    task_name:  str  = ""     # ansible task name
    resource:   str  = ""     # terraform resource


# ── Ansible parser ────────────────────────────────────────────────────────────

class AnsibleParser:
    """
    Parses ansible-playbook output line by line.

    Recognizes:
      PLAY [name]
      TASK [name]
      ok: [host]
      changed: [host]
      failed: [host]
      fatal: [host]: MSG
      PLAY RECAP
      ERROR! message
    """

    _RE_PLAY      = re.compile(r'^PLAY \[(.+?)\]')
    _RE_TASK      = re.compile(r'^TASK \[(.+?)\]')
    _RE_OK        = re.compile(r'^ok: \[(.+?)\]')
    _RE_CHANGED   = re.compile(r'^changed: \[(.+?)\]')
    _RE_FAILED    = re.compile(r'^(failed|fatal): \[(.+?)\](.*)$')
    _RE_SKIPPING  = re.compile(r'^skipping: \[(.+?)\]')
    _RE_RECAP     = re.compile(r'^PLAY RECAP')
    _RE_RECAP_LINE= re.compile(
        r'^(\S+)\s+: ok=(\d+)\s+changed=(\d+)\s+unreachable=(\d+)\s+failed=(\d+)'
    )
    _RE_ERROR     = re.compile(r'^ERROR! (.+)')
    _RE_WARNING   = re.compile(r'^(\[WARNING\]|WARNING:?) (.+)')

    def __init__(self):
        self._current_play = ""
        self._current_task = ""
        self._in_recap     = False

    def feed_line(self, line: str) -> list[RunEvent]:
        events = []
        line = line.rstrip()

        m = self._RE_PLAY.match(line)
        if m:
            self._current_play = m.group(1)
            self._in_recap     = False
            events.append(RunEvent(
                tool="ansible", severity=Severity.INFO,
                title=f"Play: {self._current_play}",
            ))
            return events

        m = self._RE_TASK.match(line)
        if m:
            self._current_task = m.group(1)
            return events

        m = self._RE_FAILED.match(line)
        if m:
            host   = m.group(2)
            detail = m.group(3).strip()
            # Extract msg from detail if present
            msg_match = re.search(r'"msg":\s*"([^"]+)"', detail)
            msg = msg_match.group(1) if msg_match else detail[:120]
            events.append(RunEvent(
                tool      = "ansible",
                severity  = Severity.ERROR,
                title     = f"Failed: {self._current_task}",
                detail    = f"Host: {host}\n{msg}",
                task_name = self._current_task,
                file_hint = self._task_to_file_hint(self._current_task),
            ))
            return events

        m = self._RE_ERROR.match(line)
        if m:
            events.append(RunEvent(
                tool     = "ansible",
                severity = Severity.ERROR,
                title    = "Ansible error",
                detail   = m.group(1),
            ))
            return events

        m = self._RE_WARNING.match(line)
        if m:
            events.append(RunEvent(
                tool     = "ansible",
                severity = Severity.WARNING,
                title    = "Warning",
                detail   = m.group(2),
            ))
            return events

        if self._RE_RECAP.match(line):
            self._in_recap = True
            return events

        if self._in_recap:
            m = self._RE_RECAP_LINE.match(line)
            if m:
                host        = m.group(1)
                ok          = int(m.group(2))
                changed     = int(m.group(3))
                unreachable = int(m.group(4))
                failed      = int(m.group(5))
                if failed > 0 or unreachable > 0:
                    sev = Severity.ERROR
                elif changed > 0:
                    sev = Severity.WARNING
                else:
                    sev = Severity.SUCCESS
                events.append(RunEvent(
                    tool     = "ansible",
                    severity = sev,
                    title    = f"Recap: {host}",
                    detail   = (
                        f"ok={ok} changed={changed} "
                        f"unreachable={unreachable} failed={failed}"
                    ),
                ))

        return events

    def _task_to_file_hint(self, task_name: str) -> str:
        """
        Try to infer which file a task lives in from its name.
        e.g. 'db | Configure MySQL' → look for files with 'db' or 'mysql'
        """
        if '|' in task_name:
            role = task_name.split('|')[0].strip().lower()
            return role
        words = task_name.lower().split()
        if words:
            return words[0]
        return ""


# ── Terraform / OpenTofu parser ───────────────────────────────────────────────

class TerraformParser:
    """
    Parses terraform/tofu plan and apply output.

    Recognizes:
      Error: message
      Warning: message
      Plan: N to add, N to change, N to destroy
      Apply complete! Resources: N added, N changed, N destroyed
      resource_type.name (create/update/destroy)
    """

    _RE_ERROR    = re.compile(r'^(?:╷\s*)?│?\s*Error: (.+)')
    _RE_ERROR_ON = re.compile(r'on (.+?) line (\d+)')
    _RE_WARNING  = re.compile(r'^(?:│\s*)?Warning: (.+)')
    _RE_PLAN     = re.compile(
        r'Plan: (\d+) to add, (\d+) to change, (\d+) to destroy'
    )
    _RE_APPLY    = re.compile(
        r'Apply complete! Resources: (\d+) added, (\d+) changed, (\d+) destroyed'
    )
    _RE_DESTROY  = re.compile(r'^  # (\S+) will be destroyed')
    _RE_CREATE   = re.compile(r'^  # (\S+) will be created')
    _RE_UPDATE   = re.compile(r'^  # (\S+) will be updated in-place')
    _RE_RESOURCE_ERR = re.compile(r'with (\S+),')

    def __init__(self):
        self._pending_error = None

    def feed_line(self, line: str) -> list[RunEvent]:
        events = []
        line_s = line.rstrip()

        m = self._RE_ERROR.match(line_s)
        if m:
            self._pending_error = RunEvent(
                tool     = "terraform",
                severity = Severity.ERROR,
                title    = f"Error: {m.group(1)[:80]}",
                detail   = m.group(1),
            )
            events.append(self._pending_error)
            return events

        # "on file.tf line N, in resource..." — annotate pending error
        if self._pending_error:
            m = self._RE_ERROR_ON.search(line_s)
            if m:
                self._pending_error.file_hint = m.group(1)
                self._pending_error.detail   += f"\n{m.group(1)} line {m.group(2)}"
            m = self._RE_RESOURCE_ERR.search(line_s)
            if m:
                self._pending_error.resource = m.group(1)
            if line_s.strip() == '':
                self._pending_error = None

        m = self._RE_WARNING.match(line_s)
        if m:
            events.append(RunEvent(
                tool     = "terraform",
                severity = Severity.WARNING,
                title    = f"Warning: {m.group(1)[:80]}",
                detail   = m.group(1),
            ))
            return events

        m = self._RE_PLAN.search(line_s)
        if m:
            add, change, destroy = int(m.group(1)), int(m.group(2)), int(m.group(3))
            sev = Severity.ERROR if destroy > 0 else (
                  Severity.WARNING if change > 0 else Severity.SUCCESS)
            events.append(RunEvent(
                tool     = "terraform",
                severity = sev,
                title    = "Plan summary",
                detail   = (
                    f"{add} to add  {change} to change  {destroy} to destroy"
                ),
            ))
            return events

        m = self._RE_APPLY.search(line_s)
        if m:
            events.append(RunEvent(
                tool     = "terraform",
                severity = Severity.SUCCESS,
                title    = "Apply complete",
                detail   = (
                    f"{m.group(1)} added  {m.group(2)} changed  "
                    f"{m.group(3)} destroyed"
                ),
            ))
            return events

        m = self._RE_DESTROY.match(line_s)
        if m:
            events.append(RunEvent(
                tool     = "terraform",
                severity = Severity.WARNING,
                title    = f"Will destroy: {m.group(1)}",
                resource = m.group(1),
                file_hint= m.group(1).split('.')[0] if '.' in m.group(1) else "",
            ))
            return events

        return events