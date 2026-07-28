"""Thin wrapper around the GitHub REST API for the subset of endpoints the agent needs."""

from __future__ import annotations

from typing import Any

import requests

_API_BASE = "https://api.github.com"


class GitHubClient:
    def __init__(self, token: str, repo: str, session: requests.Session | None = None):
        self.repo = repo
        self._session = session or requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )

    def list_failed_workflow_runs(self, per_page: int = 50) -> list[dict[str, Any]]:
        resp = self._session.get(
            f"{_API_BASE}/repos/{self.repo}/actions/runs",
            params={"status": "failure", "per_page": per_page},
        )
        resp.raise_for_status()
        return resp.json()["workflow_runs"]

    def list_jobs_for_run(self, run_id: int) -> list[dict[str, Any]]:
        resp = self._session.get(f"{_API_BASE}/repos/{self.repo}/actions/runs/{run_id}/jobs")
        resp.raise_for_status()
        return resp.json()["jobs"]

    def fetch_job_log(self, job_id: int) -> str:
        resp = self._session.get(f"{_API_BASE}/repos/{self.repo}/actions/jobs/{job_id}/logs")
        resp.raise_for_status()
        return resp.text

    def create_issue(
        self, title: str, body: str, labels: list[str] | None = None
    ) -> dict[str, Any]:
        resp = self._session.post(
            f"{_API_BASE}/repos/{self.repo}/issues",
            json={"title": title, "body": body, "labels": labels or []},
        )
        resp.raise_for_status()
        return resp.json()


def extract_failed_step_name(job: dict[str, Any]) -> str | None:
    """Return the name of the first step in a job that failed, if any."""
    for step in job.get("steps", []):
        if step.get("conclusion") == "failure":
            return step.get("name")
    return None


def extract_pr_number(run: dict[str, Any]) -> int | None:
    """Return the PR number associated with a workflow run, if GitHub linked one."""
    pull_requests = run.get("pull_requests") or []
    if not pull_requests:
        return None
    return pull_requests[0]["number"]
