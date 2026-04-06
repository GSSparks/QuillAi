"""
parsers.py

Parses CI/CD pipeline definitions into a unified graph structure.
Supports GitLab CI (.gitlab-ci.yml) and GitHub Actions (.github/workflows/*.yml).
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
class PipelineJob:
    name:       str
    stage:      str        = "default"
    needs:      list       = field(default_factory=list)
    depends_on: list       = field(default_factory=list)
    image:      str        = ""
    script:     list       = field(default_factory=list)
    rules:      list       = field(default_factory=list)
    when:       str        = "on_success"
    allow_failure: bool    = False
    tags:       list       = field(default_factory=list)
    environment: str       = ""
    parallel:   int        = 0
    # GitHub specific
    runs_on:    str        = ""
    uses:       str        = ""   # reusable workflow
    # Display
    is_manual:  bool       = False
    is_deploy:  bool       = False


@dataclass
class Pipeline:
    type:    PipelineType
    stages:  list[str]
    jobs:    dict[str, PipelineJob]   # name → job
    file_path: str = ""
    errors:  list[str] = field(default_factory=list)


# ── GitLab CI parser ──────────────────────────────────────────────────────────

_GITLAB_RESERVED = {
    'stages', 'workflow', 'include', 'variables', 'default',
    'image', 'services', 'before_script', 'after_script',
    'cache', 'artifacts',
}


def parse_gitlab(content: str, file_path: str = "") -> Pipeline:
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

    for key, val in data.items():
        if key in _GITLAB_RESERVED or key.startswith('.'):
            continue
        if not isinstance(val, dict):
            continue

        job = PipelineJob(name=key)
        job.stage        = val.get('stage', stages[0] if stages else 'default')
        job.image        = _str(val.get('image', ''))
        job.tags         = _list(val.get('tags', []))
        job.allow_failure = bool(val.get('allow_failure', False))
        job.environment  = _str(val.get('environment', {}) if isinstance(
            val.get('environment'), str) else
            val.get('environment', {}).get('name', '') if isinstance(
            val.get('environment'), dict) else '')

        # Script
        script = val.get('script', [])
        job.script = _list(script)

        # Needs (DAG)
        needs = val.get('needs', [])
        if isinstance(needs, list):
            for n in needs:
                if isinstance(n, str):
                    job.needs.append(n)
                elif isinstance(n, dict):
                    job.needs.append(n.get('job', ''))

        # When
        job.when      = val.get('when', 'on_success')
        job.is_manual = job.when == 'manual'

        # Detect deploy jobs
        job.is_deploy = (
            'deploy' in key.lower() or
            bool(job.environment) or
            job.stage in ('deploy', 'release', 'production', 'staging')
        )

        # Rules
        rules = val.get('rules', [])
        if isinstance(rules, list):
            job.rules = rules

        jobs[key] = job

    return Pipeline(PipelineType.GITLAB, stages, jobs, file_path=file_path)


# ── GitHub Actions parser ─────────────────────────────────────────────────────

def parse_github(content: str, file_path: str = "") -> Pipeline:
    if not HAS_YAML:
        return Pipeline(PipelineType.GITHUB, [], {},
                        errors=["pyyaml not installed"])
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        return Pipeline(PipelineType.GITHUB, [], {},
                        errors=[str(e)])

    if not isinstance(data, dict):
        return Pipeline(PipelineType.GITHUB, [], {})

    gha_jobs = data.get('jobs', {})
    if not isinstance(gha_jobs, dict):
        return Pipeline(PipelineType.GITHUB, [], {})

    # GitHub Actions doesn't have explicit stages — infer from needs graph
    # Build topological order as "stages"
    all_jobs  = set(gha_jobs.keys())
    no_needs  = [j for j, v in gha_jobs.items()
                 if not v.get('needs')]
    has_needs = [j for j, v in gha_jobs.items()
                 if v.get('needs')]

    stages = ['run']  # default single stage
    jobs   = {}

    for key, val in gha_jobs.items():
        if not isinstance(val, dict):
            continue

        job          = PipelineJob(name=key)
        job.runs_on  = _str(val.get('runs-on', ''))
        job.uses     = _str(val.get('uses', ''))
        job.environment = _str(val.get('environment', ''))

        # needs
        needs = val.get('needs', [])
        if isinstance(needs, str):
            job.needs = [needs]
        elif isinstance(needs, list):
            job.needs = [n for n in needs if isinstance(n, str)]

        # steps → script summary
        steps = val.get('steps', [])
        if isinstance(steps, list):
            for step in steps:
                if isinstance(step, dict):
                    name = step.get('name', step.get('uses', step.get('run', '')))
                    if name:
                        job.script.append(str(name)[:60])

        job.is_manual = isinstance(val.get('environment'), dict) and \
                        'review' in str(val.get('environment', '')).lower()
        job.is_deploy = (
            'deploy' in key.lower() or
            bool(job.environment) or
            job.uses != ''
        )

        # Infer stage from position in needs graph
        if not job.needs:
            job.stage = 'build'
        elif all(gha_jobs.get(n, {}).get('needs') is None
                 for n in job.needs):
            job.stage = 'test'
        else:
            job.stage = 'deploy'

        jobs[key] = job

    # Collect unique stages in order
    seen   = []
    stages = []
    for job in jobs.values():
        if job.stage not in seen:
            seen.append(job.stage)
            stages.append(job.stage)

    return Pipeline(PipelineType.GITHUB, stages, jobs, file_path=file_path)


# ── Auto-detect ───────────────────────────────────────────────────────────────

def detect_and_parse(file_path: str) -> Pipeline | None:
    """Detect pipeline type from file path and parse it."""
    if not os.path.exists(file_path):
        return None
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return None

    name = os.path.basename(file_path)

    if name == '.gitlab-ci.yml' or name == '.gitlab-ci.yaml':
        return parse_gitlab(content, file_path)

    # GitHub Actions workflow
    if '.github' in file_path and name.endswith(('.yml', '.yaml')):
        return parse_github(content, file_path)

    # Try to auto-detect from content
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