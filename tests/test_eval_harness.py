import json

import pytest

from triage_agent.eval_harness import format_report, run_eval


class FakeSequentialAnthropicClient:
    """Returns one canned classification per call, in the order given."""

    def __init__(self, categories: list[str]):
        self._categories = iter(categories)
        self.messages = self

    def create(self, **kwargs):
        category = next(self._categories)

        class Block:
            type = "tool_use"
            name = "submit_classification"
            input = {"category": category, "confidence": 0.8, "reasoning": "test"}

        class Response:
            content = [Block()]

        return Response()


@pytest.fixture
def eval_set_path(tmp_path):
    examples = [
        {
            "id": "a",
            "workflow_name": "CI",
            "job_name": "test",
            "failed_step_name": "Run pytest",
            "log_excerpt": "boom",
            "expected_category": "flake",
        },
        {
            "id": "b",
            "workflow_name": "CI",
            "job_name": "test",
            "failed_step_name": "Run pytest",
            "log_excerpt": "boom",
            "expected_category": "regression",
        },
        {
            "id": "c",
            "workflow_name": "CI",
            "job_name": "test",
            "failed_step_name": "Run pytest",
            "log_excerpt": "boom",
            "expected_category": "infra_issue",
        },
    ]
    path = tmp_path / "eval_set.json"
    path.write_text(json.dumps(examples))
    return path


def test_run_eval_scores_all_correct(eval_set_path):
    client = FakeSequentialAnthropicClient(["flake", "regression", "infra_issue"])

    report = run_eval(eval_set_path, client)

    assert report["total"] == 3
    assert report["accuracy"] == 1.0
    assert report["flake_vs_real_accuracy"] == 1.0
    assert report["misclassified"] == []


def test_run_eval_reports_misclassifications(eval_set_path):
    client = FakeSequentialAnthropicClient(["regression", "regression", "infra_issue"])

    report = run_eval(eval_set_path, client)

    assert report["total"] == 3
    assert report["accuracy"] == pytest.approx(2 / 3)
    assert report["misclassified"] == [{"id": "a", "expected": "flake", "predicted": "regression"}]


def test_run_eval_flake_vs_real_accuracy_ignores_real_category_confusion(eval_set_path):
    client = FakeSequentialAnthropicClient(["flake", "infra_issue", "regression"])

    report = run_eval(eval_set_path, client)

    assert report["accuracy"] == pytest.approx(1 / 3)
    assert report["flake_vs_real_accuracy"] == 1.0


def test_format_report_includes_summary_lines():
    report = {
        "total": 3,
        "accuracy": 1.0,
        "flake_vs_real_accuracy": 1.0,
        "confusion": {},
        "misclassified": [],
    }

    text = format_report(report)

    assert "Examples:               3" in text
    assert "100.0%" in text
    assert "Misclassified" not in text


def test_format_report_lists_misclassifications():
    report = {
        "total": 2,
        "accuracy": 0.5,
        "flake_vs_real_accuracy": 0.5,
        "confusion": {},
        "misclassified": [{"id": "a", "expected": "flake", "predicted": "regression"}],
    }

    text = format_report(report)

    assert "Misclassified:" in text
    assert "a: expected=flake predicted=regression" in text
