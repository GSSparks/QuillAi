"""
parsers.py

Pattern matchers for Ansible and Terraform/OpenTofu output streams.
Each parser maintains state across chunks and emits structured results.

Supports both normal and verbose (-v/-vv) ansible-playbook output.
In verbose mode captures full JSON detail blocks including msg, stdout,
stderr, rc, and per-host results.
"""

import json
import re
from dataclasses import dataclass, field
from enum import Enum


class Severity(Enum):
    INFO    = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR   = "error"


@dataclass
class HostResult:
    """Result for a single host on a single task."""
    host:    str
    status:  str        # "ok" | "changed" | "failed" | "skipped" | "unreachable"
    msg:     str = ""
    stdout:  str = ""
    stderr:  str = ""
    rc:      int = 0
    detail:  dict = field(default_factory=dict)  # full parsed JSON


@dataclass
class RunEvent:
    """A single detected event from a run."""
    tool:         str           # "ansible" | "terraform" | "tofu"
    severity:     Severity
    title:        str
    detail:       str  = ""
    file_hint:    str  = ""     # filename to search for
    task_name:    str  = ""     # ansible task name
    play_name:    str  = ""     # ansible play name
    resource:     str  = ""     # terraform resource
    # Per-host results (populated from verbose output)
    host_results: dict = field(default_factory=dict)  # host -> HostResult
    # Raw verbose JSON if captured
    raw_json:     str  = ""


# ── Ansible parser ────────────────────────────────────────────────────────────

class AnsibleParser:
    """
    Parses ansible-playbook output line by line.

    Normal mode recognizes:
      PLAY [name], TASK [name], ok/changed/failed/fatal/skipping: [host]
      PLAY RECAP, ERROR!, WARNING

    Verbose mode (-v) additionally captures:
      JSON detail blocks after result lines
      stdout, stderr, rc, msg from task results
    """

    _RE_PLAY       = re.compile(r'^PLAY \[(.+?)\] \*+')
    _RE_TASK       = re.compile(r'^TASK \[(.+?)\] \*+')
    _RE_OK         = re.compile(r'^ok: \[(.+?)\]')
    _RE_CHANGED    = re.compile(r'^changed: \[(.+?)\]')
    _RE_FAILED     = re.compile(r'^(failed|fatal): \[(.+?)\](.*)')
    _RE_SKIPPING   = re.compile(r'^skipping: \[(.+?)\]')
    _RE_UNREACHABLE= re.compile(r'^fatal: \[(.+?)\]: UNREACHABLE!')
    _RE_RECAP      = re.compile(r'^PLAY RECAP')
    _RE_RECAP_LINE = re.compile(
        r'^(\S+)\s+: ok=(\d+)\s+changed=(\d+)\s+unreachable=(\d+)\s+failed=(\d+)'
    )
    _RE_ERROR      = re.compile(r'^ERROR! (.+)')
    _RE_WARNING    = re.compile(r'^(\[WARNING\]|WARNING:?) (.+)')
    # Verbose JSON result lines: "ok: [host] => {" or "failed: [host] => {"
    _RE_VERBOSE    = re.compile(
        r'^(ok|changed|failed|fatal|skipping): \[(.+?)\] => (\{.*)'
    )
    # Handler notifications
    _RE_NOTIFIED   = re.compile(r'^\s+\S+ : (.+) +NOTIFIED')
    # Include/role markers
    _RE_INCLUDE    = re.compile(r'^RUNNING HANDLER \[(.+?)\]')

    def __init__(self):
        self._current_play  = ""
        self._current_task  = ""
        self._in_recap      = False
        # Verbose JSON capture state
        self._json_buf      = ""
        self._json_host     = ""
        self._json_status   = ""
        self._json_depth    = 0
        self._capturing_json= False
        # Task event accumulator — collects all host results for current task
        self._task_event: RunEvent | None = None
        self._task_hosts: dict = {}   # host -> HostResult

    def feed_line(self, line: str) -> list[RunEvent]:
        events = []
        raw = line.rstrip()

        # ── JSON capture mode ─────────────────────────────────────────────
        if self._capturing_json:
            self._json_buf += "\n" + raw
            self._json_depth += raw.count('{') - raw.count('}')
            if self._json_depth <= 0:
                self._capturing_json = False
                self._flush_json(events)
            return events

        # ── Verbose result line (status: [host] => {json...}) ────────────
        m = self._RE_VERBOSE.match(raw)
        if m:
            status    = m.group(1)
            host      = m.group(2)
            json_part = m.group(3)
            self._json_host   = host
            self._json_status = status
            self._json_buf    = json_part
            self._json_depth  = json_part.count('{') - json_part.count('}')
            if self._json_depth > 0:
                self._capturing_json = True
            else:
                self._flush_json(events)
            return events

        # ── PLAY ──────────────────────────────────────────────────────────
        m = self._RE_PLAY.match(raw)
        if m:
            self._flush_task_event(events)
            self._current_play = m.group(1)
            self._in_recap     = False
            events.append(RunEvent(
                tool      = "ansible",
                severity  = Severity.INFO,
                title     = f"Play: {self._current_play}",
                play_name = self._current_play,
            ))
            return events

        # ── TASK ──────────────────────────────────────────────────────────
        m = self._RE_TASK.match(raw)
        if m:
            self._flush_task_event(events)
            self._current_task = m.group(1)
            self._task_hosts   = {}
            return events

        # ── Non-verbose result lines ──────────────────────────────────────
        m = self._RE_UNREACHABLE.match(raw)
        if m:
            host = m.group(1)
            hr = HostResult(host=host, status="unreachable",
                            msg="Host unreachable")
            self._task_hosts[host] = hr
            events.append(RunEvent(
                tool      = "ansible",
                severity  = Severity.ERROR,
                title     = f"Unreachable: {self._current_task}",
                detail    = f"Host: {host}\nHost unreachable",
                task_name = self._current_task,
                play_name = self._current_play,
                file_hint = self._task_to_file_hint(self._current_task),
                host_results = {host: hr},
            ))
            return events

        m = self._RE_FAILED.match(raw)
        if m:
            host      = m.group(2)
            remainder = m.group(3).strip()
            msg_match = re.search(r'"msg":\s*"([^"]+)"', remainder)
            msg = msg_match.group(1) if msg_match else remainder[:120]
            hr = HostResult(host=host, status="failed", msg=msg)
            self._task_hosts[host] = hr
            # Build/update task event
            if self._task_event is None:
                self._task_event = RunEvent(
                    tool      = "ansible",
                    severity  = Severity.ERROR,
                    title     = f"Failed: {self._current_task}",
                    detail    = f"Host: {host}\n{msg}",
                    task_name = self._current_task,
                    play_name = self._current_play,
                    file_hint = self._task_to_file_hint(self._current_task),
                )
            self._task_event.host_results[host] = hr
            return events

        m = self._RE_OK.match(raw)
        if m:
            host = m.group(1)
            hr = HostResult(host=host, status="ok")
            self._task_hosts[host] = hr
            if self._task_event:
                self._task_event.host_results[host] = hr
            return events

        m = self._RE_CHANGED.match(raw)
        if m:
            host = m.group(1)
            hr = HostResult(host=host, status="changed")
            self._task_hosts[host] = hr
            if self._task_event:
                self._task_event.host_results[host] = hr
            return events

        m = self._RE_SKIPPING.match(raw)
        if m:
            host = m.group(1)
            self._task_hosts[host] = HostResult(host=host, status="skipped")
            return events

        m = self._RE_ERROR.match(raw)
        if m:
            self._flush_task_event(events)
            events.append(RunEvent(
                tool      = "ansible",
                severity  = Severity.ERROR,
                title     = "Ansible error",
                detail    = m.group(1),
                play_name = self._current_play,
            ))
            return events

        m = self._RE_WARNING.match(raw)
        if m:
            events.append(RunEvent(
                tool     = "ansible",
                severity = Severity.WARNING,
                title    = "Warning",
                detail   = m.group(2),
            ))
            return events

        if self._RE_RECAP.match(raw):
            self._flush_task_event(events)
            self._in_recap = True
            return events

        if self._in_recap:
            m = self._RE_RECAP_LINE.match(raw)
            if m:
                host        = m.group(1)
                ok          = int(m.group(2))
                changed     = int(m.group(3))
                unreachable = int(m.group(4))
                failed      = int(m.group(5))
                sev = (Severity.ERROR   if failed > 0 or unreachable > 0 else
                       Severity.WARNING if changed > 0 else
                       Severity.SUCCESS)
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

    def _flush_json(self, events: list):
        """Parse accumulated JSON blob and update host result."""
        try:
            data = json.loads(self._json_buf)
        except json.JSONDecodeError:
            return

        host   = self._json_host
        status = self._json_status

        hr = HostResult(
            host   = host,
            status = status,
            msg    = str(data.get("msg", "")),
            stdout = str(data.get("stdout", "")),
            stderr = str(data.get("stderr", "")),
            rc     = int(data.get("rc", 0)),
            detail = data,
        )

        self._task_hosts[host] = hr

        # Update or create task event
        if status in ("failed", "fatal"):
            msg_short = hr.msg[:120] if hr.msg else ""
            if self._task_event is None:
                self._task_event = RunEvent(
                    tool      = "ansible",
                    severity  = Severity.ERROR,
                    title     = f"Failed: {self._current_task}",
                    detail    = f"Host: {host}\n{msg_short}",
                    task_name = self._current_task,
                    play_name = self._current_play,
                    file_hint = self._task_to_file_hint(self._current_task),
                    raw_json  = self._json_buf,
                )
            self._task_event.host_results[host] = hr
            self._task_event.detail = f"Host: {host}\n{msg_short}"

        elif self._task_event:
            self._task_event.host_results[host] = hr

    def _flush_task_event(self, events: list):
        """Emit accumulated task event if any."""
        if self._task_event is not None:
            events.append(self._task_event)
            self._task_event = None
        self._task_hosts = {}

    def _task_to_file_hint(self, task_name: str) -> str:
        if '|' in task_name:
            return task_name.split('|')[0].strip().lower()
        words = task_name.lower().split()
        return words[0] if words else ""


# ── Terraform / OpenTofu parser ───────────────────────────────────────────────

class TerraformParser:
    """
    Parses terraform/tofu plan and apply output.
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
            sev = (Severity.ERROR   if destroy > 0 else
                   Severity.WARNING if change  > 0 else
                   Severity.SUCCESS)
            events.append(RunEvent(
                tool     = "terraform",
                severity = sev,
                title    = "Plan summary",
                detail   = f"{add} to add  {change} to change  {destroy} to destroy",
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