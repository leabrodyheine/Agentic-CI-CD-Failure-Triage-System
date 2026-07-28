"""Orchestrates the ingest -> classify -> root-cause -> file -> audit pipeline."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, TypeVar

from triage_agent.classifier import classify_failure
from triage_agent.config import Settings
from triage_agent.github_client import GitHubClient, extract_failed_step_name, extract_pr_number
from triage_agent.issue_filer import file_issue
from triage_agent.log_parser import extract_error_excerpt
from triage_agent.models import FailedRun, TriageRecord
from triage_agent.root_cause import generate_root_cause
from triage_agent.storage import TriageStorage

T = TypeVar("T")


def _timed(fn: Callable[[], T]) -> tuple[T, float]:
    start = time.perf_counter()
    result = fn()
    return result, time.perf_counter() - start


def ingest_failed_job(
    github_client: GitHubClient, repo: str, run: dict[str, Any], job: dict[str, Any]
) -> FailedRun:
    """Fetches the job's log and assembles a FailedRun from the raw API payloads."""
    raw_log = github_client.fetch_job_log(job["id"])
    excerpt = extract_error_excerpt(raw_log)

    return FailedRun(
        repo=repo,
        run_id=run["id"],
        job_id=job["id"],
        workflow_name=run.get("name") or "unknown",
        job_name=job["name"],
        failed_step_name=extract_failed_step_name(job),
        head_sha=run["head_sha"],
        head_branch=run["head_branch"],
        pr_number=extract_pr_number(run),
        html_url=run["html_url"],
        created_at=run["created_at"],
        log_excerpt=excerpt,
    )


def triage_failed_job(
    github_client: GitHubClient,
    anthropic_client: Any,
    storage: TriageStorage,
    repo: str,
    run: dict[str, Any],
    job: dict[str, Any],
    dry_run: bool = False,
    min_confidence_to_file: float = 0.0,
) -> TriageRecord:
    """Runs the full pipeline for one failed job and persists the resulting record.

    The issue is only filed if classification confidence meets min_confidence_to_file;
    below that, the pipeline still runs and the decision is still logged, just not filed,
    to avoid spamming issues for low-confidence guesses.
    """
    failed_run, ingest_seconds = _timed(lambda: ingest_failed_job(github_client, repo, run, job))

    classification, classify_seconds = _timed(
        lambda: classify_failure(failed_run, anthropic_client)
    )
    hypothesis, root_cause_seconds = _timed(
        lambda: generate_root_cause(failed_run, classification, anthropic_client)
    )

    issue_url = None
    file_issue_seconds = 0.0
    if not dry_run and classification.confidence >= min_confidence_to_file:
        issue_url, file_issue_seconds = _timed(
            lambda: file_issue(failed_run, classification, hypothesis, github_client)
        )

    record = TriageRecord(
        run=failed_run,
        classification=classification,
        hypothesis=hypothesis,
        issue_url=issue_url,
        triaged_at=datetime.now(UTC),
        stage_durations_seconds={
            "ingest": ingest_seconds,
            "classify": classify_seconds,
            "root_cause": root_cause_seconds,
            "file_issue": file_issue_seconds,
        },
    )
    storage.save_record(record)
    return record


def poll_once(
    settings: Settings,
    github_client: GitHubClient,
    anthropic_client: Any,
    storage: TriageStorage,
) -> list[TriageRecord]:
    """Finds newly-failed runs/jobs not yet in the audit log and triages each of them.

    Bounds the scan to runs created since the last successful poll (tracked per-repo in
    storage), so repeated polling doesn't keep re-scanning a repo's entire failure history.
    The cutoff is captured before fetching runs, so anything created mid-poll is simply
    picked up again next time; is_run_processed() makes that safe to repeat.
    """
    new_records: list[TriageRecord] = []
    poll_started_at = datetime.now(UTC)
    since = storage.get_last_poll_time(settings.github_repo)

    for run in github_client.list_failed_workflow_runs(created_after=since):
        for job in github_client.list_jobs_for_run(run["id"]):
            if job.get("conclusion") != "failure":
                continue
            if storage.is_run_processed(settings.github_repo, run["id"], job["id"]):
                continue

            record = triage_failed_job(
                github_client,
                anthropic_client,
                storage,
                settings.github_repo,
                run,
                job,
                dry_run=settings.dry_run,
                min_confidence_to_file=settings.min_confidence_to_file,
            )
            new_records.append(record)

    storage.set_last_poll_time(settings.github_repo, poll_started_at)
    return new_records
