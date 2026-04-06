"""
analyzer.py

Stream buffer that feeds terminal output to parsers and
emits structured RunEvents.
"""

import re
from plugins.features.run_analyzer.parsers import (
    AnsibleParser, TerraformParser, RunEvent, Severity
)


# Tool detection patterns
_RE_ANSIBLE   = re.compile(r'ansible-playbook|ansible ')
_RE_TERRAFORM = re.compile(r'\bterraform\b|\btofu\b')

# Strip ANSI escape sequences before parsing
_RE_ANSI = re.compile(r'\x1b\[[0-9;]*[mABCDEFGHJKSTfsu]')

class RunAnalyzer:
    """
    Buffers terminal output, detects which tool is running,
    and routes lines to the appropriate parser.
    """

    def __init__(self, on_event, on_failure=None, on_complete=None):
        """
        on_event: callable(RunEvent) — called for each detected event
        """
        self._on_event    = on_event
        self._on_failure  = on_failure   
        self._on_complete = on_complete 
        self._buf         = ""
        self._tool        = None
        self._ansible     = AnsibleParser()
        self._terraform   = TerraformParser()
        self._had_failure = False

    def feed(self, text: str):
        clean = _RE_ANSI.sub('', text)
        self._buf += clean
        while '\n' in self._buf:
            line, self._buf = self._buf.split('\n', 1)
            self._process_line(line)

    def reset(self):
        self._buf         = ""
        self._tool        = None
        self._ansible     = AnsibleParser()
        self._terraform   = TerraformParser()
        self._had_failure = False

    def _process_line(self, line: str):
        if self._tool is None:
            if re.search(r'ansible-playbook|ansible ', line):
                self._tool = "ansible"
            elif re.search(r'\bterraform\b|\btofu\b', line):
                self._tool = "terraform"

        events = []
        if self._tool == "ansible":
            events = self._ansible.feed_line(line)
        elif self._tool == "terraform":
            events = self._terraform.feed_line(line)
        else:
            events = (
                self._ansible.feed_line(line) or
                self._terraform.feed_line(line)
            )

        for event in events:
            self._on_event(event)

            if event.severity == Severity.ERROR:
                self._had_failure = True
                if self._on_failure:
                    self._on_failure(event)

            # Recap = run complete
            if event.title.startswith("Recap:") and self._on_complete:
                self._on_complete(
                    self._tool or "ansible",
                    not self._had_failure,
                    event.detail,
                )