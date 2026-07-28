"""Configures structured logging for the triage agent.

DESIGN.md's observability goal is that every agent decision - a classification, a root-cause
hypothesis, filing vs. skipping an issue, retrying a flaky API call - is logged and auditable.
This module just sets the format/level; the actual decision logging lives in the modules that
make those decisions (poller.py, issue_filer.py, classifier.py, root_cause.py, retry.py).
"""

from __future__ import annotations

import logging

_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
_VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def configure_logging(level: str = "INFO") -> None:
    """Configures the root logger. Safe to call more than once (e.g. once per CLI command)."""
    normalized = level.upper()
    if normalized not in _VALID_LEVELS:
        normalized = "INFO"

    root = logging.getLogger()
    root.setLevel(normalized)
    if not root.handlers:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(logging.Formatter(_FORMAT))
        root.addHandler(stream_handler)
    else:
        for existing_handler in root.handlers:
            existing_handler.setFormatter(logging.Formatter(_FORMAT))
