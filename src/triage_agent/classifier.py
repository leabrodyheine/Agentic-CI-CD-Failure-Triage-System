"""Claude-based classification of a CI failure into a FailureCategory."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from triage_agent.anthropic_utils import create_with_retries
from triage_agent.models import FailedRun, FailureCategory, FailureClassification

DEFAULT_MODEL = "claude-sonnet-5"

_TOOL_NAME = "submit_classification"
_PROMPT_PATH = Path(__file__).parent / "prompts" / "classify.md"

_CLASSIFY_TOOL = {
    "name": _TOOL_NAME,
    "description": "Submit the classification of a CI failure.",
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "enum": [c.value for c in FailureCategory],
                "description": "The failure category.",
            },
            "confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "description": "Confidence in this classification, from 0 to 1.",
            },
            "reasoning": {
                "type": "string",
                "description": "Brief explanation citing evidence from the log excerpt.",
            },
        },
        "required": ["category", "confidence", "reasoning"],
    },
}


def _system_prompt() -> str:
    return _PROMPT_PATH.read_text()


def _build_user_prompt(run: FailedRun) -> str:
    return (
        f"Workflow: {run.workflow_name}\n"
        f"Job: {run.job_name}\n"
        f"Failed step: {run.failed_step_name or 'unknown'}\n"
        f"Branch: {run.head_branch}\n"
        f"Commit: {run.head_sha}\n\n"
        f"Log excerpt:\n{run.log_excerpt}"
    )


def _extract_tool_input(response: Any, tool_name: str) -> dict[str, Any]:
    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
            return block.input
    raise ValueError(f"Expected a '{tool_name}' tool_use block in the response")


def classify_failure(
    run: FailedRun,
    client: Any,
    model: str = DEFAULT_MODEL,
    max_retry_attempts: int = 3,
    retry_base_delay: float = 0.5,
    sleep: Callable[[float], None] = time.sleep,
) -> FailureClassification:
    """Classify a failed run using Claude. `client` is an anthropic.Anthropic instance.

    Transient API errors (connection issues, timeouts, rate limits, 5xx) are retried with
    exponential backoff; see triage_agent.anthropic_utils.create_with_retries.
    """
    response = create_with_retries(
        client,
        max_attempts=max_retry_attempts,
        base_delay=retry_base_delay,
        sleep=sleep,
        model=model,
        max_tokens=1024,
        system=_system_prompt(),
        tools=[_CLASSIFY_TOOL],
        tool_choice={"type": "tool", "name": _TOOL_NAME},
        messages=[{"role": "user", "content": _build_user_prompt(run)}],
    )
    tool_input = _extract_tool_input(response, _TOOL_NAME)
    return FailureClassification(**tool_input)
