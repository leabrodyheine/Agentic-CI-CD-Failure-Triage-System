"""Claude-based root-cause hypothesis generation for a classified CI failure."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from triage_agent.anthropic_utils import create_with_retries
from triage_agent.models import FailedRun, FailureClassification, RootCauseHypothesis

DEFAULT_MODEL = "claude-sonnet-5"

_TOOL_NAME = "submit_root_cause"
_PROMPT_PATH = Path(__file__).parent / "prompts" / "root_cause.md"

_ROOT_CAUSE_TOOL = {
    "name": _TOOL_NAME,
    "description": "Submit a root-cause hypothesis for a CI failure.",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "Concrete 1-3 sentence description of the likely root cause.",
            },
            "evidence": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Log lines that support the hypothesis.",
            },
            "suspected_commit_sha": {
                "type": ["string", "null"],
                "description": "Commit SHA believed to have introduced the issue, or null.",
            },
            "confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "description": "Confidence in this hypothesis, from 0 to 1.",
            },
        },
        "required": ["summary", "evidence", "confidence"],
    },
}


def _system_prompt() -> str:
    return _PROMPT_PATH.read_text()


def _build_user_prompt(run: FailedRun, classification: FailureClassification) -> str:
    return (
        f"Workflow: {run.workflow_name}\n"
        f"Job: {run.job_name}\n"
        f"Failed step: {run.failed_step_name or 'unknown'}\n"
        f"Branch: {run.head_branch}\n"
        f"Commit: {run.head_sha}\n"
        f"Classification: {classification.category.value} "
        f"(confidence {classification.confidence:.2f}) - {classification.reasoning}\n\n"
        f"Log excerpt:\n{run.log_excerpt}"
    )


def _extract_tool_input(response: Any, tool_name: str) -> dict[str, Any]:
    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
            return block.input
    raise ValueError(f"Expected a '{tool_name}' tool_use block in the response")


def generate_root_cause(
    run: FailedRun,
    classification: FailureClassification,
    client: Any,
    model: str = DEFAULT_MODEL,
    max_retry_attempts: int = 3,
    retry_base_delay: float = 0.5,
    sleep: Callable[[float], None] = time.sleep,
) -> RootCauseHypothesis:
    """Generate a root-cause hypothesis using Claude.

    `client` is an anthropic.Anthropic instance. Transient API errors (connection issues,
    timeouts, rate limits, 5xx) are retried with exponential backoff; see
    triage_agent.anthropic_utils.create_with_retries.
    """
    response = create_with_retries(
        client,
        max_attempts=max_retry_attempts,
        base_delay=retry_base_delay,
        sleep=sleep,
        model=model,
        max_tokens=1024,
        system=_system_prompt(),
        tools=[_ROOT_CAUSE_TOOL],
        tool_choice={"type": "tool", "name": _TOOL_NAME},
        messages=[{"role": "user", "content": _build_user_prompt(run, classification)}],
    )
    tool_input = _extract_tool_input(response, _TOOL_NAME)
    return RootCauseHypothesis(**tool_input)
