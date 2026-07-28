"""Shared helper for retrying Anthropic API calls on transient failures."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import anthropic

from triage_agent.retry import call_with_retries

_RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (
    anthropic.APIConnectionError,
    anthropic.APITimeoutError,
    anthropic.RateLimitError,
    anthropic.InternalServerError,
    anthropic.OverloadedError,
)


def create_with_retries(
    client: Any,
    *,
    max_attempts: int = 3,
    base_delay: float = 0.5,
    sleep: Callable[[float], None] = time.sleep,
    **kwargs: Any,
) -> Any:
    """Calls client.messages.create(**kwargs), retrying on transient Anthropic API errors
    (connection errors, timeouts, rate limits, 5xx/overloaded) with exponential backoff.
    """
    return call_with_retries(
        lambda: client.messages.create(**kwargs),
        max_attempts=max_attempts,
        base_delay=base_delay,
        retryable_exceptions=_RETRYABLE_EXCEPTIONS,
        sleep=sleep,
    )
