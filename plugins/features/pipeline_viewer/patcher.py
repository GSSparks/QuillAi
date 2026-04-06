"""
patcher.py

Surgical YAML editor for GitLab CI files.
Makes targeted line-level changes without destroying comments,
anchors, or user formatting.
"""

import re
import os


class YAMLPatcher:
    """
    Reads a YAML file, makes surgical edits, writes it back.
    Never reformats — only touches the specific lines that changed.
    """

    def __init__(self, file_path: str):
        self.file_path = file_path
        self._lines    = []
        self._load()

    def _load(self):
        with open(self.file_path, 'r', encoding='utf-8') as f:
            self._lines = f.read().splitlines(keepends=True)

    def _save(self):
        with open(self.file_path, 'w', encoding='utf-8') as f:
            f.writelines(self._lines)

    # ── Job field edit ────────────────────────────────────────────────────

    def set_job_stage(self, job_name: str, new_stage: str) -> bool:
        """Change the stage: value of a job. Returns True on success."""
        job_start = self._find_job_line(job_name)
        if job_start < 0:
            return False

        job_end   = self._find_job_end(job_start)
        indent    = self._detect_indent(job_start)

        # Look for existing stage: line within the job block
        for i in range(job_start + 1, job_end + 1):
            line = self._lines[i] if i < len(self._lines) else ''
            m    = re.match(r'^(\s+stage\s*:\s*)(.+)(\s*)$', line)
            if m:
                self._lines[i] = f"{m.group(1)}{new_stage}\n"
                self._save()
                return True

        # No stage: line found — insert one after the job header
        new_line = f"{indent}  stage: {new_stage}\n"
        insert_at = job_start + 1
        # Skip any comment lines immediately after the job header
        while (insert_at < len(self._lines) and
               self._lines[insert_at].strip().startswith('#')):
            insert_at += 1
        self._lines.insert(insert_at, new_line)
        self._save()
        return True

    def set_job_field(self, job_name: str,
                      field: str, value: str) -> bool:
        """Set an arbitrary scalar field on a job."""
        job_start = self._find_job_line(job_name)
        if job_start < 0:
            return False

        job_end = self._find_job_end(job_start)
        indent  = self._detect_indent(job_start) + '  '

        # Find and replace existing field
        pattern = re.compile(
            r'^(\s+' + re.escape(field) + r'\s*:\s*)(.+)(\s*)$'
        )
        for i in range(job_start + 1, job_end + 1):
            if i >= len(self._lines):
                break
            m = pattern.match(self._lines[i])
            if m:
                # Preserve quoting style if value contains special chars
                val_str = _quote_if_needed(value)
                self._lines[i] = f"{m.group(1)}{val_str}\n"
                self._save()
                return True

        # Insert new field
        new_line  = f"{indent}{field}: {_quote_if_needed(value)}\n"
        insert_at = job_start + 1
        while (insert_at < len(self._lines) and
               self._lines[insert_at].strip().startswith('#')):
            insert_at += 1
        self._lines.insert(insert_at, new_line)
        self._save()
        return True

    def set_job_allow_failure(self, job_name: str,
                               value: bool) -> bool:
        return self.set_job_field(
            job_name, 'allow_failure', 'true' if value else 'false'
        )

    def rename_job(self, old_name: str, new_name: str) -> bool:
        """Rename a job — changes the top-level key."""
        job_start = self._find_job_line(old_name)
        if job_start < 0:
            return False
        line = self._lines[job_start]
        self._lines[job_start] = line.replace(
            f"{old_name}:", f"{new_name}:", 1
        )
        self._save()
        return True

    def add_need(self, job_name: str, need: str) -> bool:
        """Add a job to the needs: list of another job."""
        job_start = self._find_job_line(job_name)
        if job_start < 0:
            return False

        job_end = self._find_job_end(job_start)
        indent  = self._detect_indent(job_start) + '  '

        # Find existing needs: block
        for i in range(job_start + 1, job_end + 1):
            if i >= len(self._lines):
                break
            line = self._lines[i]
            m    = re.match(r'^(\s+needs\s*:\s*)(.*)', line)
            if m:
                # Inline list: needs: [job1, job2]
                rest = m.group(2).strip()
                if rest.startswith('['):
                    inner = rest[1:rest.rfind(']')]
                    items = [x.strip() for x in inner.split(',')
                             if x.strip()]
                    if need not in items:
                        items.append(need)
                        self._lines[i] = (
                            f"{m.group(1)}"
                            f"[{', '.join(items)}]\n"
                        )
                        self._save()
                    return True
                else:
                    # Block list — find end and append
                    j = i + 1
                    while (j < len(self._lines) and
                           re.match(r'^\s+-\s+', self._lines[j])):
                        existing = self._lines[j].strip().lstrip('- ')
                        if existing == need:
                            return True   # already there
                        j += 1
                    self._lines.insert(
                        j, f"{indent}  - {need}\n"
                    )
                    self._save()
                    return True

        # No needs: block — insert one
        new_lines = [
            f"{indent}needs:\n",
            f"{indent}  - {need}\n",
        ]
        insert_at = job_start + 1
        while (insert_at < len(self._lines) and
               self._lines[insert_at].strip().startswith('#')):
            insert_at += 1
        for offset, nl in enumerate(new_lines):
            self._lines.insert(insert_at + offset, nl)
        self._save()
        return True

    def insert_job(self, job_name: str, stage: str,
                   image: str = "", script: str = "") -> bool:
        """Append a new job block at the end of the file."""
        lines = [f"\n{job_name}:\n",
                 f"  stage: {stage}\n"]
        if image:
            lines.append(f"  image: {image}\n")
        if script:
            lines.append(f"  script:\n")
            lines.append(f"    - {script}\n")
        else:
            lines.append(f"  script:\n")
            lines.append(f"    - echo \"TODO\"\n")

        self._lines.extend(lines)
        self._save()
        return True

    def add_stage(self, stage_name: str) -> bool:
        """Add a new stage to the stages: list."""
        for i, line in enumerate(self._lines):
            if re.match(r'^stages\s*:', line):
                # Find end of stages block
                j = i + 1
                while (j < len(self._lines) and
                       re.match(r'^\s+-\s+', self._lines[j])):
                    existing = self._lines[j].strip().lstrip('- ')
                    if existing == stage_name:
                        return True  # already exists
                    j += 1
                self._lines.insert(j, f"  - {stage_name}\n")
                self._save()
                return True
        return False

    def set_job_script(self, job_name: str, script_text: str) -> bool:
        """Replace the script: block for a job with new content."""
        job_start = self._find_job_line(job_name)
        if job_start < 0:
            return False
    
        job_end = self._find_job_end(job_start)
        indent  = self._detect_indent(job_start) + '  '
    
        lines   = [l.strip() for l in script_text.splitlines() if l.strip()]
    
        # Find existing script: block start and end
        script_start = -1
        script_end   = -1
        for i in range(job_start + 1, job_end + 1):
            if i >= len(self._lines):
                break
            line = self._lines[i]
            if re.match(r'^\s+script\s*:', line):
                script_start = i
                # Find end of script block
                j = i + 1
                while (j < len(self._lines) and
                       j <= job_end and
                       re.match(r'^\s+-\s+', self._lines[j])):
                    j += 1
                script_end = j
                break
    
        new_lines = [f"{indent}script:\n"]
        for line in lines:
            # Preserve existing quoting — wrap in quotes if needed
            new_lines.append(f"{indent}  - {_quote_if_needed(line)}\n")
    
        if script_start >= 0:
            # Replace existing block
            self._lines[script_start:script_end] = new_lines
        else:
            # Insert after job header
            insert_at = job_start + 1
            while (insert_at < len(self._lines) and
                   self._lines[insert_at].strip().startswith('#')):
                insert_at += 1
            for offset, nl in enumerate(new_lines):
                self._lines.insert(insert_at + offset, nl)
    
        self._save()
        return True

    # ── Internals ─────────────────────────────────────────────────────────

    def _find_job_line(self, job_name: str) -> int:
        """Find the line index of 'job_name:' at column 0."""
        pattern = re.compile(r'^' + re.escape(job_name) + r'\s*:')
        for i, line in enumerate(self._lines):
            if pattern.match(line):
                return i
        return -1

    def _find_job_end(self, job_start: int) -> int:
        """Find the last line of a job block."""
        for i in range(job_start + 1, len(self._lines)):
            line = self._lines[i]
            if line and line[0] not in (' ', '\t', '#', '\n', '\r'):
                return i - 1
        return len(self._lines) - 1

    def _detect_indent(self, job_line: int) -> str:
        """Detect indentation of a top-level key (usually empty)."""
        line = self._lines[job_line]
        m    = re.match(r'^(\s*)', line)
        return m.group(1) if m else ''

    def reload(self):
        """Reload from disk after external changes."""
        self._load()


def _quote_if_needed(value: str) -> str:
    """Wrap in quotes if value contains YAML special characters."""
    specials = [':', '#', '{', '}', '[', ']', ',', '&', '*', '?',
                '|', '-', '<', '>', '=', '!', '%', '@', '`']
    if any(c in value for c in specials):
        return f'"{value}"'
    return value