from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from triage_agent.models import (
    FailureCategory,
    FailureClassification,
    RootCauseHypothesis,
    TriageRecord,
)


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


def test_triage_record_round_trips_through_json(failed_run):
    record = TriageRecord(
        run=failed_run,
        classification=FailureClassification(
            category=FailureCategory.FLAKE, confidence=0.6, reasoning="intermittent network error"
        ),
        hypothesis=RootCauseHypothesis(summary="DNS flake", confidence=0.5),
        issue_url=None,
        triaged_at=datetime.now(UTC),
    )

    restored = TriageRecord.model_validate_json(record.model_dump_json())
    assert restored == record


def test_total_duration_seconds_sums_stage_durations(failed_run):
    record = TriageRecord(
        run=failed_run,
        classification=FailureClassification(
            category=FailureCategory.FLAKE, confidence=0.6, reasoning="x"
        ),
        hypothesis=RootCauseHypothesis(summary="x", confidence=0.5),
        triaged_at=datetime.now(UTC),
        stage_durations_seconds={"ingest": 0.1, "classify": 0.2, "root_cause": 0.3},
    )

    assert record.total_duration_seconds == pytest.approx(0.6)


def test_total_duration_seconds_defaults_to_zero(failed_run):
    record = TriageRecord(
        run=failed_run,
        classification=FailureClassification(
            category=FailureCategory.FLAKE, confidence=0.6, reasoning="x"
        ),
        hypothesis=RootCauseHypothesis(summary="x", confidence=0.5),
        triaged_at=datetime.now(UTC),
    )

    assert record.total_duration_seconds == 0.0
    assert record.stage_durations_seconds == {}
