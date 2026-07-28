from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from triage_agent.models import (
    FailedRun,
    FailureCategory,
    FailureClassification,
    RootCauseHypothesis,
    TriageRecord,
)


def _failed_run(**overrides) -> FailedRun:
    base = dict(
        repo="octo-org/octo-repo",
        run_id=1,
        job_id=2,
        workflow_name="CI",
        job_name="test",
        failed_step_name="Run pytest",
        head_sha="a" * 40,
        head_branch="main",
        pr_number=42,
        html_url="https://github.com/octo-org/octo-repo/actions/runs/1",
        created_at=datetime.now(timezone.utc),
        log_excerpt="AssertionError: expected 1 got 2",
    )
    base.update(overrides)
    return FailedRun(**base)


def test_failure_classification_rejects_out_of_range_confidence():
    with pytest.raises(ValidationError):
        FailureClassification(category=FailureCategory.FLAKE, confidence=1.5, reasoning="x")


def test_failure_classification_accepts_valid_confidence():
    classification = FailureClassification(
        category=FailureCategory.REGRESSION, confidence=0.9, reasoning="matches known pattern"
    )
    assert classification.category == FailureCategory.REGRESSION


def test_root_cause_hypothesis_defaults_evidence_to_empty_list():
    hypothesis = RootCauseHypothesis(summary="likely a timeout", confidence=0.4)
    assert hypothesis.evidence == []
    assert hypothesis.suspected_commit_sha is None


def test_triage_record_round_trips_through_json():
    record = TriageRecord(
        run=_failed_run(),
        classification=FailureClassification(
            category=FailureCategory.FLAKE, confidence=0.6, reasoning="intermittent network error"
        ),
        hypothesis=RootCauseHypothesis(summary="DNS flake", confidence=0.5),
        issue_url=None,
        triaged_at=datetime.now(timezone.utc),
    )

    restored = TriageRecord.model_validate_json(record.model_dump_json())
    assert restored == record
