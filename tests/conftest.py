from datetime import datetime, timezone

import pytest

from triage_agent.models import (
    FailedRun,
    FailureCategory,
    FailureClassification,
    RootCauseHypothesis,
    TriageRecord,
)


def make_failed_run(**overrides) -> FailedRun:
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


def make_triage_record(**overrides) -> TriageRecord:
    base = dict(
        run=make_failed_run(),
        classification=FailureClassification(
            category=FailureCategory.FLAKE, confidence=0.6, reasoning="intermittent network error"
        ),
        hypothesis=RootCauseHypothesis(summary="DNS flake", confidence=0.5),
        issue_url=None,
        triaged_at=datetime.now(timezone.utc),
    )
    base.update(overrides)
    return TriageRecord(**base)


@pytest.fixture
def failed_run():
    return make_failed_run()


@pytest.fixture
def triage_record():
    return make_triage_record()


class FakeToolUseBlock:
    def __init__(self, name: str, input: dict):
        self.type = "tool_use"
        self.name = name
        self.input = input


class FakeAnthropicResponse:
    def __init__(self, content: list):
        self.content = content


class FakeAnthropicClient:
    """Stands in for anthropic.Anthropic; records calls and returns a canned tool_use response."""

    def __init__(self, tool_name: str, tool_input: dict):
        self._tool_name = tool_name
        self._tool_input = tool_input
        self.calls: list[dict] = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeAnthropicResponse(
            content=[FakeToolUseBlock(self._tool_name, self._tool_input)]
        )


@pytest.fixture
def fake_anthropic_client():
    def _make(tool_name: str, tool_input: dict) -> FakeAnthropicClient:
        return FakeAnthropicClient(tool_name, tool_input)

    return _make
