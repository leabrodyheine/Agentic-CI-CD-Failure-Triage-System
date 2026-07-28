"""Core data models shared across the pipeline."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class FailureCategory(StrEnum):
    FLAKE = "flake"
    REGRESSION = "regression"
    INFRA_ISSUE = "infra_issue"
    NEW_BUG = "new_bug"


class FailedRun(BaseModel):
    """Metadata about a single failed GitHub Actions run/job, as ingested from the API."""

    repo: str
    run_id: int
    job_id: int
    workflow_name: str
    job_name: str
    failed_step_name: str | None
    head_sha: str
    head_branch: str
    pr_number: int | None
    html_url: str
    created_at: datetime
    log_excerpt: str


class FailureClassification(BaseModel):
    category: FailureCategory
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str


class RootCauseHypothesis(BaseModel):
    summary: str
    evidence: list[str] = Field(default_factory=list)
    suspected_commit_sha: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)


class TriageRecord(BaseModel):
    """A full audit record of one triage pass over a failed run."""

    run: FailedRun
    classification: FailureClassification
    hypothesis: RootCauseHypothesis
    issue_url: str | None = None
    pr_comment_url: str | None = None
    triaged_at: datetime
    stage_durations_seconds: dict[str, float] = Field(default_factory=dict)

    @property
    def total_duration_seconds(self) -> float:
        """Sum of all recorded stage durations - the total time.

        Time is measured from ingest through filing, i.e. how long this triage pass took to
        run once it started (DESIGN.md's "time from failure to filed report" metric, minus
        however long the run sat unprocessed before this poll picked it up).
        """
        return sum(self.stage_durations_seconds.values())
