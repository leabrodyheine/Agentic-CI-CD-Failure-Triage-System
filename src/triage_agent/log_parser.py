"""Extracts the relevant excerpt from a raw GitHub Actions job log.

Raw logs are long (often thousands of lines) and timestamp-prefixed. We strip the
timestamps and pull a bounded window of lines around the clearest error signal, so the
LLM prompt stays small and focused instead of being handed the entire log.
"""

from __future__ import annotations

import re

_TIMESTAMP_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z\s?")

_ERROR_MARKERS = (
    re.compile(r"##\[error\]"),
    re.compile(r"\bTraceback \(most recent call last\)"),
    re.compile(r"\bFAILED\b"),
    re.compile(r"\bError\b"),
    re.compile(r"\bException\b"),
    re.compile(r"\bpanic:"),
    re.compile(r"\bfatal:"),
)

_DEFAULT_CONTEXT_BEFORE = 15
_DEFAULT_CONTEXT_AFTER = 10
_DEFAULT_MAX_LINES = 50


def strip_timestamps(log: str) -> str:
    lines = log.splitlines()
    return "\n".join(_TIMESTAMP_PREFIX.sub("", line) for line in lines)


def _find_error_anchor(lines: list[str]) -> int | None:
    """Return the index of the last line matching an error marker, if any."""
    for marker in _ERROR_MARKERS:
        for i in range(len(lines) - 1, -1, -1):
            if marker.search(lines[i]):
                return i
    return None


def extract_error_excerpt(
    log: str,
    context_before: int = _DEFAULT_CONTEXT_BEFORE,
    context_after: int = _DEFAULT_CONTEXT_AFTER,
    max_lines: int = _DEFAULT_MAX_LINES,
) -> str:
    """Return a bounded excerpt of the log centered on the clearest error signal.

    Falls back to the tail of the log when no recognizable error marker is found,
    since failures usually surface in the last lines regardless.
    """
    cleaned = strip_timestamps(log)
    lines = cleaned.splitlines()
    if not lines:
        return ""

    anchor = _find_error_anchor(lines)
    if anchor is None:
        excerpt_lines = lines[-max_lines:]
    else:
        start = max(0, anchor - context_before)
        end = min(len(lines), anchor + context_after + 1)
        excerpt_lines = lines[start:end][:max_lines]

    return "\n".join(excerpt_lines)
