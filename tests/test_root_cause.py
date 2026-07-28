import pytest

from triage_agent.models import FailureCategory, FailureClassification
from triage_agent.root_cause import generate_root_cause


@pytest.fixture
def classification():
    return FailureClassification(
        category=FailureCategory.REGRESSION, confidence=0.85, reasoning="matches recent diff"
    )


def test_generate_root_cause_returns_parsed_hypothesis(
    failed_run, classification, fake_anthropic_client
):
    client = fake_anthropic_client(
        "submit_root_cause",
        {
            "summary": "The new retry decorator swallows the underlying exception.",
            "evidence": ["AssertionError: expected 1 got 2"],
            "suspected_commit_sha": failed_run.head_sha,
            "confidence": 0.7,
        },
    )

    result = generate_root_cause(failed_run, classification, client)

    assert "retry decorator" in result.summary
    assert result.suspected_commit_sha == failed_run.head_sha
    assert result.confidence == 0.7
    assert result.evidence == ["AssertionError: expected 1 got 2"]


def test_generate_root_cause_allows_null_commit_sha(
    failed_run, classification, fake_anthropic_client
):
    client = fake_anthropic_client(
        "submit_root_cause",
        {
            "summary": "Inconclusive - looks like a transient network blip.",
            "evidence": [],
            "suspected_commit_sha": None,
            "confidence": 0.3,
        },
    )

    result = generate_root_cause(failed_run, classification, client)

    assert result.suspected_commit_sha is None
    assert result.evidence == []


def test_generate_root_cause_sends_classification_context(
    failed_run, classification, fake_anthropic_client
):
    client = fake_anthropic_client(
        "submit_root_cause",
        {"summary": "x", "evidence": [], "suspected_commit_sha": None, "confidence": 0.5},
    )

    generate_root_cause(failed_run, classification, client)

    call = client.calls[0]
    user_content = call["messages"][0]["content"]
    assert classification.category.value in user_content
    assert classification.reasoning in user_content
    assert call["tool_choice"] == {"type": "tool", "name": "submit_root_cause"}


def test_generate_root_cause_raises_when_tool_not_used(failed_run, classification):
    class EmptyResponse:
        content: list = []

    class NoToolClient:
        class messages:
            @staticmethod
            def create(**kwargs):
                return EmptyResponse()

    with pytest.raises(ValueError, match="submit_root_cause"):
        generate_root_cause(failed_run, classification, NoToolClient())
