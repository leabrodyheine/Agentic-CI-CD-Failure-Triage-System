import pytest

from triage_agent.classifier import classify_failure
from triage_agent.models import FailureCategory


def test_classify_failure_returns_parsed_classification(failed_run, fake_anthropic_client):
    client = fake_anthropic_client(
        "submit_classification",
        {"category": "flake", "confidence": 0.75, "reasoning": "looks like a network timeout"},
    )

    result = classify_failure(failed_run, client)

    assert result.category == FailureCategory.FLAKE
    assert result.confidence == 0.75
    assert "timeout" in result.reasoning


def test_classify_failure_sends_log_excerpt_and_metadata(failed_run, fake_anthropic_client):
    client = fake_anthropic_client(
        "submit_classification",
        {"category": "regression", "confidence": 0.9, "reasoning": "x"},
    )

    classify_failure(failed_run, client)

    call = client.calls[0]
    user_content = call["messages"][0]["content"]
    assert failed_run.log_excerpt in user_content
    assert failed_run.workflow_name in user_content
    assert failed_run.head_sha in user_content
    assert call["tool_choice"] == {"type": "tool", "name": "submit_classification"}


def test_classify_failure_raises_when_tool_not_used(failed_run):
    class EmptyResponse:
        content: list = []

    class NoToolClient:
        class messages:
            @staticmethod
            def create(**kwargs):
                return EmptyResponse()

    with pytest.raises(ValueError, match="submit_classification"):
        classify_failure(failed_run, NoToolClient())


def test_classify_failure_propagates_invalid_category(failed_run, fake_anthropic_client):
    client = fake_anthropic_client(
        "submit_classification",
        {"category": "not_a_real_category", "confidence": 0.5, "reasoning": "x"},
    )

    with pytest.raises(Exception):
        classify_failure(failed_run, client)
