"""Scores the classifier against a labeled eval set of historical failures.

See eval/eval_set.json for the example format and eval/run_eval.py for the CLI entry point.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from triage_agent.classifier import classify_failure
from triage_agent.models import FailedRun, FailureCategory

DEFAULT_EVAL_SET_PATH = Path(__file__).resolve().parents[2] / "eval" / "eval_set.json"


def _load_examples(path: Path) -> list[dict[str, Any]]:
    return json.loads(Path(path).read_text())


def _to_failed_run(example: dict[str, Any], index: int) -> FailedRun:
    return FailedRun(
        repo="eval",
        run_id=index,
        job_id=index,
        workflow_name=example["workflow_name"],
        job_name=example["job_name"],
        failed_step_name=example.get("failed_step_name"),
        head_sha="0" * 40,
        head_branch=example.get("head_branch", "main"),
        pr_number=None,
        html_url="https://example.invalid/eval",
        created_at=datetime.now(UTC),
        log_excerpt=example["log_excerpt"],
    )


def run_eval(eval_set_path: Path, client: Any) -> dict[str, Any]:
    """Classifies every example in the eval set and scores the predictions.

    `client` is an anthropic.Anthropic instance (or a test double with the same interface).
    """
    examples = _load_examples(eval_set_path)

    results = []
    for i, example in enumerate(examples):
        failed_run = _to_failed_run(example, i)
        expected = FailureCategory(example["expected_category"])
        predicted = classify_failure(failed_run, client).category
        results.append((example["id"], expected, predicted))

    total = len(results)
    correct = sum(1 for _, expected, predicted in results if expected == predicted)
    accuracy = correct / total if total else 0.0

    flake_binary_correct = sum(
        1
        for _, expected, predicted in results
        if (expected == FailureCategory.FLAKE) == (predicted == FailureCategory.FLAKE)
    )
    flake_vs_real_accuracy = flake_binary_correct / total if total else 0.0

    confusion = Counter((expected.value, predicted.value) for _, expected, predicted in results)

    return {
        "total": total,
        "accuracy": accuracy,
        "flake_vs_real_accuracy": flake_vs_real_accuracy,
        "confusion": dict(confusion),
        "misclassified": [
            {"id": id_, "expected": expected.value, "predicted": predicted.value}
            for id_, expected, predicted in results
            if expected != predicted
        ],
    }


def main() -> None:
    import anthropic

    eval_set_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_EVAL_SET_PATH
    report = run_eval(eval_set_path, anthropic.Anthropic())

    print(f"Examples:               {report['total']}")
    print(f"Accuracy (exact):       {report['accuracy']:.1%}")
    print(f"Accuracy (flake/real):  {report['flake_vs_real_accuracy']:.1%}")
    if report["misclassified"]:
        print("\nMisclassified:")
        for m in report["misclassified"]:
            print(f"  {m['id']}: expected={m['expected']} predicted={m['predicted']}")


if __name__ == "__main__":
    main()
