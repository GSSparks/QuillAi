"""
plugins/features/gitlab_ci/client.py

GitLab API client for QuillAI.
Fetches pipelines, jobs, logs, and merge requests.
"""
from __future__ import annotations

import re
import threading
from typing import Optional
from urllib.parse import urljoin

import requests


class GitLabClient:
    """
    Thin GitLab REST API v4 client.
    All methods return plain dicts/lists or raise on error.
    """

    def __init__(self, url: str, token: str, project_id: str):
        self.base    = url.rstrip("/") + "/api/v4"
        self.token   = token
        self.project = requests.utils.quote(project_id, safe="")
        self._session = requests.Session()
        self._session.headers.update({
            "PRIVATE-TOKEN": token,
            "User-Agent": "QuillAI/1.0",
        })

    def _get(self, path: str, params: dict = None) -> any:
        url = f"{self.base}{path}"
        r   = self._session.get(url, params=params, timeout=15)
        r.raise_for_status()
        return r.json()

    # ── Pipelines ─────────────────────────────────────────────────────────

    def list_pipelines(self, ref: str = None, status: str = None,
                       per_page: int = 10) -> list:
        params = {"per_page": per_page, "order_by": "id", "sort": "desc"}
        if ref:    params["ref"]    = ref
        if status: params["status"] = status
        return self._get(f"/projects/{self.project}/pipelines", params)

    def get_pipeline(self, pipeline_id: int) -> dict:
        return self._get(f"/projects/{self.project}/pipelines/{pipeline_id}")

    def get_pipeline_jobs(self, pipeline_id: int) -> list:
        return self._get(
            f"/projects/{self.project}/pipelines/{pipeline_id}/jobs",
            {"per_page": 100}
        )

    # ── Jobs ──────────────────────────────────────────────────────────────

    def get_job(self, job_id: int) -> dict:
        return self._get(f"/projects/{self.project}/jobs/{job_id}")

    def get_job_trace(self, job_id: int, max_bytes: int = 50000) -> str:
        """Return the last max_bytes of a job's log output."""
        url = f"{self.base}/projects/{self.project}/jobs/{job_id}/trace"
        r   = self._session.get(url, timeout=30)
        r.raise_for_status()
        text = r.text
        if len(text) > max_bytes:
            # Keep last max_bytes — errors are usually at the end
            text = "…(truncated)\n" + text[-max_bytes:]
        return text

    # ── Project ───────────────────────────────────────────────────────────

    def get_project_info(self) -> dict:
        return self._get(f"/projects/{self.project}")

    def list_branches(self, search: str = None) -> list:
        params = {"per_page": 20}
        if search: params["search"] = search
        return self._get(f"/projects/{self.project}/repository/branches", params)

    def get_branch(self, branch: str) -> dict:
        branch_enc = requests.utils.quote(branch, safe="")
        return self._get(
            f"/projects/{self.project}/repository/branches/{branch_enc}"
        )

    # ── Test connection ───────────────────────────────────────────────────

    def ping(self) -> tuple[bool, str]:
        try:
            info = self.get_project_info()
            return True, info.get("name_with_namespace", "connected")
        except Exception as e:
            return False, str(e)


def format_pipeline_summary(pipeline: dict, jobs: list = None) -> str:
    """Format a pipeline into a short context string for AI injection."""
    status_icon = {
        "success":  "✓",
        "failed":   "✗",
        "running":  "⟳",
        "pending":  "…",
        "canceled": "⊘",
        "skipped":  "–",
    }.get(pipeline.get("status", ""), "?")

    lines = [
        f"Pipeline #{pipeline['id']} {status_icon} {pipeline.get('status','').upper()}",
        f"  Ref:      {pipeline.get('ref', '?')}",
        f"  Created:  {pipeline.get('created_at', '?')[:19]}",
        f"  Duration: {pipeline.get('duration', '?')}s",
    ]

    if jobs:
        failed  = [j for j in jobs if j.get("status") == "failed"]
        running = [j for j in jobs if j.get("status") == "running"]
        if failed:
            lines.append(f"  Failed jobs: {', '.join(j['name'] for j in failed)}")
        if running:
            lines.append(f"  Running:     {', '.join(j['name'] for j in running)}")
        lines.append(f"  Total jobs:  {len(jobs)}")

    return "\n".join(lines)


def format_job_trace_for_context(job: dict, trace: str,
                                  max_chars: int = 3000) -> str:
    """Format a job trace for injection into AI context."""
    header = (
        f"Job: {job.get('name', '?')} "
        f"[{job.get('status', '?').upper()}] "
        f"(#{job.get('id', '?')})\n"
        f"Stage: {job.get('stage', '?')}\n"
        f"---\n"
    )
    # Strip ANSI escape codes
    clean = re.sub(r'\x1b\[[0-9;]*[mGKHF]', '', trace)
    # Keep last max_chars of the clean log
    if len(clean) > max_chars:
        clean = "…(truncated)\n" + clean[-max_chars:]
    return header + clean