import json

import pytest

from triage_agent.eval_harness import run_eval


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
