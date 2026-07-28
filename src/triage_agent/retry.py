"""Generic retry-with-backoff helper for transient failures against external APIs."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


class RetryError(RuntimeError):
    """Raised when all retry attempts are exhausted. The original error is chained as __cause__."""


def call_with_retries(
    fn: Callable[[], T],
    *,
    max_attempts: int = 3,
    base_delay: float = 0.5,
    retryable_exceptions: tuple[type[BaseException], ...] = (Exception,),
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Calls `fn`, retrying with exponential backoff if it raises a retryable exception.

    Only exceptions matching `retryable_exceptions` are retried; anything else propagates
    immediately. After `max_attempts` failed attempts, raises RetryError chained to the last
    underlying exception.
    """
    last_exc: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except retryable_exceptions as exc:
            last_exc = exc
            if attempt == max_attempts:
                break
            sleep(base_delay * (2 ** (attempt - 1)))
    raise RetryError(f"failed after {max_attempts} attempts") from last_exc
