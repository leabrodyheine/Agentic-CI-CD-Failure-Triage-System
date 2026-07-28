"""Environment-driven settings for the triage agent."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    github_token: str
    github_repo: str  # "owner/name"
    anthropic_api_key: str
    poll_interval_seconds: int = 60
    db_path: str = "triage.db"
    dry_run: bool = False
    min_confidence_to_file: float = 0.0
    comment_on_pr: bool = False
    log_level: str = "INFO"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        resolved_env: Mapping[str, str] = env if env is not None else os.environ

        def require(key: str) -> str:
            value = resolved_env.get(key)
            if not value:
                raise ConfigError(f"Missing required environment variable: {key}")
            return value

        repo = require("GITHUB_REPO")
        if "/" not in repo:
            raise ConfigError(f"GITHUB_REPO must be in 'owner/name' form, got: {repo!r}")

        return cls(
            github_token=require("GITHUB_TOKEN"),
            github_repo=repo,
            anthropic_api_key=require("ANTHROPIC_API_KEY"),
            poll_interval_seconds=int(resolved_env.get("POLL_INTERVAL_SECONDS", "60")),
            db_path=resolved_env.get("TRIAGE_DB_PATH", "triage.db"),
            dry_run=resolved_env.get("TRIAGE_DRY_RUN", "").lower() in {"1", "true", "yes"},
            min_confidence_to_file=float(
                resolved_env.get("TRIAGE_MIN_CONFIDENCE_TO_FILE", "0.0")
            ),
            comment_on_pr=resolved_env.get("TRIAGE_COMMENT_ON_PR", "").lower()
            in {"1", "true", "yes"},
            log_level=resolved_env.get("TRIAGE_LOG_LEVEL", "INFO"),
        )
