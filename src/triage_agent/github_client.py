"""Thin wrapper around the GitHub REST API for the subset of endpoints the agent needs."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import requests

from triage_agent.retry import call_with_retries

_API_BASE = "https://api.github.com"
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class TransientGitHubError(RuntimeError):
    """Raised for GitHub API responses considered safe to retry (429s and 5xxs)."""


def _check_status(resp: Any) -> None:
    if resp.status_code in _RETRYABLE_STATUS_CODES:
        raise TransientGitHubError(f"transient GitHub API error: HTTP {resp.status_code}")
    resp.raise_for_status()


class GitHubClient:
    def __init__(
        self,
        token: str,
        repo: str,
        session: requests.Session | None = None,
        max_retry_attempts: int = 3,
        retry_base_delay: float = 0.5,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.repo = repo
        self._session = session or requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )
        self._max_retry_attempts = max_retry_attempts
        self._retry_base_delay = retry_base_delay
        self._sleep = sleep

    def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        def attempt() -> Any:
            resp = getattr(self._session, method)(url, **kwargs)
            _check_status(resp)
            return resp

        return call_with_retries(
            attempt,
            max_attempts=self._max_retry_attempts,
            base_delay=self._retry_base_delay,
            retryable_exceptions=(
                TransientGitHubError,
                requests.ConnectionError,
                requests.Timeout,
            ),
            sleep=self._sleep,
        )

    def list_failed_workflow_runs(self, per_page: int = 50) -> list[dict[str, Any]]:
        resp = self._request(
            "get",
            f"{_API_BASE}/repos/{self.repo}/actions/runs",
            params={"status": "failure", "per_page": per_page},
        )
        return resp.json()["workflow_runs"]

    def list_jobs_for_run(self, run_id: int) -> list[dict[str, Any]]:
        resp = self._request("get", f"{_API_BASE}/repos/{self.repo}/actions/runs/{run_id}/jobs")
        return resp.json()["jobs"]

    def fetch_job_log(self, job_id: int) -> str:
        resp = self._request("get", f"{_API_BASE}/repos/{self.repo}/actions/jobs/{job_id}/logs")
        return resp.text

    def create_issue(
        self, title: str, body: str, labels: list[str] | None = None
    ) -> dict[str, Any]:
        resp = self._request(
            "post",
            f"{_API_BASE}/repos/{self.repo}/issues",
            json={"title": title, "body": body, "labels": labels or []},
        )
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
