import pytest

from triage_agent.config import ConfigError, Settings


def _env(**overrides):
    base = {
        "GITHUB_TOKEN": "gh-token",
        "GITHUB_REPO": "octo-org/octo-repo",
        "ANTHROPIC_API_KEY": "anthropic-key",
    }
    base.update(overrides)
    return base


def test_from_env_reads_required_fields():
    settings = Settings.from_env(_env())

    assert settings.github_token == "gh-token"
    assert settings.github_repo == "octo-org/octo-repo"
    assert settings.anthropic_api_key == "anthropic-key"


def test_from_env_applies_defaults():
    settings = Settings.from_env(_env())

    assert settings.poll_interval_seconds == 60
    assert settings.db_path == "triage.db"
    assert settings.dry_run is False
    assert settings.min_confidence_to_file == 0.0
    assert settings.comment_on_pr is False


def test_from_env_parses_overrides():
    settings = Settings.from_env(
        _env(
            POLL_INTERVAL_SECONDS="30",
            TRIAGE_DB_PATH="/tmp/x.db",
            TRIAGE_DRY_RUN="true",
            TRIAGE_MIN_CONFIDENCE_TO_FILE="0.5",
            TRIAGE_COMMENT_ON_PR="true",
        )
    )

    assert settings.poll_interval_seconds == 30
    assert settings.db_path == "/tmp/x.db"
    assert settings.dry_run is True
    assert settings.min_confidence_to_file == 0.5
    assert settings.comment_on_pr is True


def test_from_env_missing_required_raises():
    env = _env()
    del env["GITHUB_TOKEN"]

    with pytest.raises(ConfigError, match="GITHUB_TOKEN"):
        Settings.from_env(env)


def test_from_env_rejects_malformed_repo():
    with pytest.raises(ConfigError, match="GITHUB_REPO"):
        Settings.from_env(_env(GITHUB_REPO="not-a-repo"))
