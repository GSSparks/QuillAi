"""
parsers.py

Parses CI/CD pipeline definitions into a unified graph structure.
Supports GitLab CI (.gitlab-ci.yml) with triggered child pipelines.
"""

import os
import re
from dataclasses import dataclass, field
from enum import Enum

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


class PipelineType(Enum):
    GITLAB  = "gitlab"
    GITHUB  = "github"
    UNKNOWN = "unknown"


@dataclass
class TriggerInfo:
    include:    str  = ""    # local file path
    project:    str  = ""    # remote project
    ref:        str  = ""    # remote ref
    strategy:   str  = ""    # depend / mirror
    is_remote:  bool = False


@dataclass
class PipelineJob:
    name:          str
    stage:         str   = "default"
    needs:         list  = field(default_factory=list)
    image:         str   = ""
    script:        list  = field(default_factory=list)
    rules:         list  = field(default_factory=list)
    when:          str   = "on_success"
    allow_failure: bool  = False
    tags:          list  = field(default_factory=list)
    environment:   str   = ""
    parallel:      int   = 0
    is_manual:     bool  = False
    is_deploy:     bool  = False
    trigger:       TriggerInfo | None = None
    is_template:   bool  = False   # dot-prefixed template job
    extends:       str   = ""    # name of template this extends
    parallel_count: int  = 0      # number of matrix instances
    # Source location for write-back
    file_path:     str   = ""
    line_start:    int   = 0
    line_end:      int   = 0


@dataclass
class Pipeline:
    type:      PipelineType
    stages:    list[str]
    jobs:      dict        # name → PipelineJob
    file_path: str         = ""
    errors:    list        = field(default_factory=list)
    # Child pipelines triggered by jobs in this pipeline
    children:  dict        = field(default_factory=dict)  # job_name → Pipeline
    templates:  dict       = field(default_factory=dict)  # name → PipelineJob
    includes:   list       = field(default_factory=list)   # raw include entries
    variables:  dict       = field(default_factory=dict)   # pipeline-level vars
    workflow:   list       = field(default_factory=list)   # workflow rule dicts


# ── GitLab CI parser ──────────────────────────────────────────────────────────

_GITLAB_RESERVED = {
    'stages', 'workflow', 'include', 'variables', 'default',
    'image', 'services', 'before_script', 'after_script',
    'cache', 'artifacts',
}


def _resolve_extends(jobs: dict, templates: dict) -> None:
    """
    Resolve extends: inheritance for all jobs in-place.
    Jobs inherit image, tags, script from their template
    if they don't define those fields themselves.
    Handles single string and list extends.
    """
    for job in jobs.values():
        if not job.extends:
            continue
        # extends can be a string or list — handle both
        names = ([job.extends] if isinstance(job.extends, str)
                 else job.extends)
        for tname in reversed(names):  # later entries win
            tmpl = templates.get(tname)
            if not tmpl:
                continue
            if not job.image and tmpl.image:
                job.image = tmpl.image
            if not job.script and tmpl.script:
                job.script = list(tmpl.script)
            if not job.tags and tmpl.tags:
                job.tags = list(tmpl.tags)
            if job.when == 'on_success' and tmpl.when != 'on_success':
                job.when = tmpl.when
                job.is_manual = tmpl.is_manual


def parse_gitlab(content: str, file_path: str = "",
                 _depth: int = 0) -> Pipeline:
    """Parse a GitLab CI YAML file. _depth prevents infinite recursion."""
    if not HAS_YAML:
        return Pipeline(PipelineType.GITLAB, [], {},
                        errors=["pyyaml not installed"])
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        return Pipeline(PipelineType.GITLAB, [], {},
                        errors=[str(e)])

    if not isinstance(data, dict):
        return Pipeline(PipelineType.GITLAB, [], {})

    stages = data.get('stages', ['build', 'test', 'deploy'])
    jobs   = {}

    # Build line index for write-back
    line_index = _build_line_index(content)

    templates: dict = {}  # dot-prefixed template jobs

    for key, val in data.items():
        if key in _GITLAB_RESERVED:
            continue
        if not isinstance(val, dict):
            continue

        is_tmpl = key.startswith('.')

        job           = PipelineJob(name=key)
        job.file_path = file_path
        job.is_template = is_tmpl
        job.stage     = val.get('stage', stages[0] if stages else 'default')
        job.image     = _str(val.get('image', ''))
        job.tags      = _list(val.get('tags', []))
        job.allow_failure = bool(val.get('allow_failure', False))
        job.when      = val.get('when', 'on_success')
        job.is_manual = job.when == 'manual'

        env = val.get('environment', '')
        if isinstance(env, dict):
            job.environment = env.get('name', '')
        else:
            job.environment = _str(env)

        # Script
        job.script = _list(val.get('script', []))

        # Extends
        ext = val.get('extends', '')
        if isinstance(ext, list):
            job.extends = ext  # keep as list
        else:
            job.extends = _str(ext)

        # Needs — handle string, plain dict, and parallel matrix dict
        needs = val.get('needs', [])
        if isinstance(needs, list):
            for n in needs:
                if isinstance(n, str):
                    job.needs.append(n)
                elif isinstance(n, dict):
                    jname = n.get('job', '')
                    if jname:
                        job.needs.append(jname)

        # Parallel matrix — count instances
        parallel = val.get('parallel')
        if isinstance(parallel, dict):
            matrix = parallel.get('matrix', [])
            count  = 1
            for entry in matrix:
                # Each matrix entry is a dict of variable lists
                entry_count = 1
                for v in entry.values():
                    if isinstance(v, list):
                        entry_count *= len(v)
                count += entry_count
            job.parallel_count = max(count - 1, len(matrix))
        elif isinstance(parallel, int) and parallel > 1:
            job.parallel_count = parallel

        # Trigger
        trigger_data = val.get('trigger')
        if trigger_data is not None:
            job.trigger = _parse_trigger(trigger_data)

        job.is_deploy = (
            'deploy' in key.lower() or
            bool(job.environment) or
            job.stage in ('deploy', 'release', 'production', 'staging')
        )

        # Line range for surgical edits
        job.line_start, job.line_end = line_index.get(key, (0, 0))

        if is_tmpl:
            templates[key] = job
        else:
            jobs[key] = job

    # Resolve extends inheritance
    _resolve_extends(jobs, templates)

    # Extract pipeline-level metadata
    raw_includes  = data.get('include', [])
    if isinstance(raw_includes, dict):
        raw_includes = [raw_includes]
    elif not isinstance(raw_includes, list):
        raw_includes = []

    raw_variables = {}
    for k, v in (data.get('variables') or {}).items():
        raw_variables[str(k)] = str(v) if v is not None else ''

    raw_workflow  = []
    wf = data.get('workflow', {})
    if isinstance(wf, dict):
        for rule in wf.get('rules', []):
            if isinstance(rule, dict):
                raw_workflow.append(rule)

    pipeline = Pipeline(
        PipelineType.GITLAB, stages, jobs,
        file_path=file_path,
        templates=templates,
        includes=raw_includes,
        variables=raw_variables,
        workflow=raw_workflow,
    )

    # Load triggered child pipelines
    if _depth < 3:
        base_dir = os.path.dirname(file_path) if file_path else ''
        for job in jobs.values():
            if job.trigger and not job.trigger.is_remote:
                child_path = os.path.join(base_dir, job.trigger.include)
                child_path = os.path.normpath(child_path)
                # Skip dynamic artifact includes and directories
                if (job.trigger.include.startswith('<artifact:')
                        or not job.trigger.include):
                    continue
                if os.path.exists(child_path) and os.path.isfile(child_path):
                    try:
                        with open(child_path, 'r', encoding='utf-8') as f:
                            child_content = f.read()
                        child = parse_gitlab(
                            child_content, child_path, _depth + 1
                        )
                        pipeline.children[job.name] = child
                    except Exception as e:
                        pipeline.errors.append(
                            f"Could not load child pipeline "
                            f"{job.trigger.include}: {e}"
                        )

    return pipeline


def _parse_trigger(trigger_data) -> TriggerInfo:
    info = TriggerInfo()
    if isinstance(trigger_data, str):
        # trigger: other/project
        info.project   = trigger_data
        info.is_remote = True
        return info

    if isinstance(trigger_data, dict):
        include = trigger_data.get('include', '')
        if isinstance(include, str):
            info.include = include
        elif isinstance(include, dict):
            # include: {project: ..., file: ...}
            info.project   = include.get('project', '')
            info.include   = include.get('file', '')
            info.ref       = include.get('ref', '')
            info.is_remote = bool(info.project)
        elif isinstance(include, list):
            # include: [{artifact: file.yml, job: jobname}]
            # Dynamic artifact-based include — mark as dynamic
            for item in include:
                if isinstance(item, dict):
                    if 'artifact' in item:
                        info.include  = f"<artifact:{item['artifact']}>"
                        info.is_remote = False  # same project
                    elif 'file' in item:
                        info.include = item['file']
                    break

        info.project  = _str(trigger_data.get('project', info.project))
        info.ref      = _str(trigger_data.get('ref',     info.ref))
        info.strategy = _str(trigger_data.get('strategy', ''))

        if info.project:
            info.is_remote = True

    return info


def _build_line_index(content: str) -> dict:
    """
    Build a map of job_name → (line_start, line_end) for surgical edits.
    A job block starts at 'name:' at column 0 and ends before
    the next top-level key or end of file.
    """
    lines   = content.splitlines()
    index   = {}
    current = None
    start   = 0

    for i, line in enumerate(lines):
        if not line or line[0] == ' ' or line[0] == '\t' or line[0] == '#':
            continue
        # Top-level key
        m = re.match(r'^([\w-]+)\s*:', line)
        if m:
            if current:
                index[current] = (start, i - 1)
            current = m.group(1)
            start   = i

    if current:
        index[current] = (start, len(lines) - 1)

    return index


# ── GitHub Actions parser ─────────────────────────────────────────────────────

def parse_github(content: str, file_path: str = "") -> Pipeline:
    if not HAS_YAML:
        return Pipeline(PipelineType.GITHUB, [], {},
                        errors=["pyyaml not installed"])
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        return Pipeline(PipelineType.GITHUB, [], {}, errors=[str(e)])

    if not isinstance(data, dict):
        return Pipeline(PipelineType.GITHUB, [], {})

    gha_jobs = data.get('jobs', {})
    if not isinstance(gha_jobs, dict):
        return Pipeline(PipelineType.GITHUB, [], {})

    jobs = {}
    for key, val in gha_jobs.items():
        if not isinstance(val, dict):
            continue
        job          = PipelineJob(name=key)
        job.file_path = file_path
        job.image    = _str(val.get('runs-on', ''))
        job.environment = _str(val.get('environment', ''))

        needs = val.get('needs', [])
        if isinstance(needs, str):
            job.needs = [needs]
        elif isinstance(needs, list):
            job.needs = [n for n in needs if isinstance(n, str)]

        steps = val.get('steps', [])
        if isinstance(steps, list):
            for step in steps:
                if isinstance(step, dict):
                    name = step.get('name', step.get('uses', ''))
                    if name:
                        job.script.append(str(name)[:60])

        job.is_deploy = 'deploy' in key.lower() or bool(job.environment)

        if not job.needs:
            job.stage = 'build'
        elif all(gha_jobs.get(n, {}).get('needs') is None
                 for n in job.needs):
            job.stage = 'test'
        else:
            job.stage = 'deploy'

        jobs[key] = job

    seen   = []
    stages = []
    for job in jobs.values():
        if job.stage not in seen:
            seen.append(job.stage)
            stages.append(job.stage)

    return Pipeline(PipelineType.GITHUB, stages, jobs, file_path=file_path)


# ── Auto-detect ───────────────────────────────────────────────────────────────

def detect_and_parse(file_path: str) -> Pipeline | None:
    if not os.path.exists(file_path):
        return None
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return None

    name = os.path.basename(file_path)

    if name in ('.gitlab-ci.yml', '.gitlab-ci.yaml'):
        return parse_gitlab(content, file_path)
    if '.github' in file_path and name.endswith(('.yml', '.yaml')):
        return parse_github(content, file_path)
    if 'stages:' in content and ('script:' in content or 'image:' in content):
        return parse_gitlab(content, file_path)
    if 'jobs:' in content and 'runs-on:' in content:
        return parse_github(content, file_path)

    return None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _str(val) -> str:
    return str(val) if val is not None else ''

def _list(val) -> list:
    if isinstance(val, list):
        return [str(v) for v in val]
    if isinstance(val, str):
        return [val]
    return []