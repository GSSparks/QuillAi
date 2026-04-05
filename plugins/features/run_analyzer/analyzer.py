"""
analyzer.py

Stream buffer that feeds terminal output to parsers and
emits structured RunEvents.
"""

import re
from plugins.features.run_analyzer.parsers import (
    AnsibleParser, TerraformParser, RunEvent
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

    def __init__(self, on_event):
        """
        on_event: callable(RunEvent) — called for each detected event
        """
        self._on_event  = on_event
        self._buf       = ""
        self._tool      = None   # "ansible" | "terraform" | None
        self._ansible   = AnsibleParser()
        self._terraform = TerraformParser()

    def feed(self, text: str):
        # Strip ANSI before buffering
        clean = _RE_ANSI.sub('', text)
        self._buf += clean
        while '\n' in self._buf:
            line, self._buf = self._buf.split('\n', 1)
            self._process_line(line)
            
    def reset(self):
        """Call when a new command starts."""
        self._buf       = ""
        self._tool      = None
        self._ansible   = AnsibleParser()
        self._terraform = TerraformParser()

    def _process_line(self, line: str):
        # Auto-detect tool from output
        if self._tool is None:
            if _RE_ANSIBLE.search(line):
                self._tool = "ansible"
            elif _RE_TERRAFORM.search(line):
                self._tool = "terraform"

        # Route to parser
        events = []
        if self._tool == "ansible":
            events = self._ansible.feed_line(line)
        elif self._tool == "terraform":
            events = self._terraform.feed_line(line)
        else:
            # Try both parsers speculatively
            events = (
                self._ansible.feed_line(line) or
                self._terraform.feed_line(line)
            )

        for event in events:
            self._on_event(event)