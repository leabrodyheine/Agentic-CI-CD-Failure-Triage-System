"""Environment-driven settings for the triage agent."""

from __future__ import annotations

import os
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

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Settings:
        env = env if env is not None else os.environ

        def require(key: str) -> str:
            value = env.get(key)
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
            poll_interval_seconds=int(env.get("POLL_INTERVAL_SECONDS", "60")),
            db_path=env.get("TRIAGE_DB_PATH", "triage.db"),
            dry_run=env.get("TRIAGE_DRY_RUN", "").lower() in {"1", "true", "yes"},
        )
