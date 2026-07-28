import pytest
from click.testing import CliRunner

from triage_agent import cli


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    monkeypatch.setenv("GITHUB_REPO", "octo-org/octo-repo")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")
    monkeypatch.setenv("TRIAGE_DB_PATH", str(tmp_path / "triage.db"))


@pytest.fixture
def runner():
    return CliRunner()


def test_poll_once_reports_triaged_records(monkeypatch, runner, triage_record):
    monkeypatch.setattr(cli, "_build_clients", lambda settings: (object(), object()))
    monkeypatch.setattr(cli, "poll_once", lambda *a, **k: [triage_record])

    result = runner.invoke(cli.main, ["poll", "--once"])

    assert result.exit_code == 0
    assert "flake" in result.output
    assert str(triage_record.run.job_id) in result.output


def test_poll_missing_config_raises_clean_error(monkeypatch, runner):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    result = runner.invoke(cli.main, ["poll", "--once"])

    assert result.exit_code != 0
    assert "GITHUB_TOKEN" in result.output


class FakeGitHubClient:
    def __init__(self, runs, jobs):
        self._runs = runs
        self._jobs = jobs

    def list_failed_workflow_runs(self):
        return self._runs

    def list_jobs_for_run(self, run_id):
        return self._jobs.get(run_id, [])


def test_run_one_triages_matching_run_and_job(monkeypatch, runner, triage_record):
    fake_client = FakeGitHubClient(runs=[{"id": 1}], jobs={1: [{"id": 2}]})
    monkeypatch.setattr(cli, "_build_clients", lambda settings: (fake_client, object()))
    monkeypatch.setattr(cli, "triage_failed_job", lambda *a, **k: triage_record)

    result = runner.invoke(cli.main, ["run", "1", "2"])

    assert result.exit_code == 0
    assert '"category"' in result.output


def test_run_one_unknown_run_id_errors(monkeypatch, runner):
    fake_client = FakeGitHubClient(runs=[{"id": 1}], jobs={1: [{"id": 2}]})
    monkeypatch.setattr(cli, "_build_clients", lambda settings: (fake_client, object()))

    result = runner.invoke(cli.main, ["run", "999", "2"])

    assert result.exit_code != 0
    assert "999" in result.output


def test_run_one_unknown_job_id_errors(monkeypatch, runner):
    fake_client = FakeGitHubClient(runs=[{"id": 1}], jobs={1: [{"id": 2}]})
    monkeypatch.setattr(cli, "_build_clients", lambda settings: (fake_client, object()))

    result = runner.invoke(cli.main, ["run", "1", "404"])

    assert result.exit_code != 0
    assert "404" in result.output
