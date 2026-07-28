from datetime import datetime, timezone

import pytest

from triage_agent.config import Settings
from triage_agent.poller import ingest_failed_job, poll_once, triage_failed_job
from triage_agent.storage import TriageStorage


def _run(run_id=1, **overrides):
    base = dict(
        id=run_id,
        name="CI",
        head_sha="a" * 40,
        head_branch="main",
        html_url=f"https://github.com/octo-org/octo-repo/actions/runs/{run_id}",
        created_at=datetime.now(timezone.utc).isoformat(),
        pull_requests=[{"number": 42}],
    )
    base.update(overrides)
    return base


def _job(job_id=2, conclusion="failure", **overrides):
    base = dict(
        id=job_id,
        name="test",
        conclusion=conclusion,
        steps=[
            {"name": "Checkout", "conclusion": "success"},
            {"name": "Run pytest", "conclusion": conclusion},
        ],
    )
    base.update(overrides)
    return base


class FakeGitHubClient:
    def __init__(self, runs, jobs_by_run, logs_by_job):
        self._runs = runs
        self._jobs_by_run = jobs_by_run
        self._logs_by_job = logs_by_job
        self.filed_issues = []

    def list_failed_workflow_runs(self):
        return self._runs

    def list_jobs_for_run(self, run_id):
        return self._jobs_by_run.get(run_id, [])

    def fetch_job_log(self, job_id):
        return self._logs_by_job[job_id]

    def create_issue(self, title, body, labels=None):
        self.filed_issues.append({"title": title, "body": body, "labels": labels})
        return {"html_url": f"https://github.com/octo-org/octo-repo/issues/{len(self.filed_issues)}"}


class FakeAnthropicClientMulti:
    """Routes each call to a canned tool response based on the forced tool_choice name."""

    def __init__(self, responses_by_tool: dict[str, dict]):
        self._responses_by_tool = responses_by_tool
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        tool_name = kwargs["tool_choice"]["name"]
        tool_input = self._responses_by_tool[tool_name]

        class Block:
            type = "tool_use"

        block = Block()
        block.name = tool_name
        block.input = tool_input

        class Response:
            content = [block]

        return Response()


@pytest.fixture
def anthropic_client():
    return FakeAnthropicClientMulti(
        {
            "submit_classification": {
                "category": "flake",
                "confidence": 0.6,
                "reasoning": "network blip",
            },
            "submit_root_cause": {
                "summary": "transient DNS failure",
                "evidence": [],
                "suspected_commit_sha": None,
                "confidence": 0.4,
            },
        }
    )


@pytest.fixture
def settings():
    return Settings(
        github_token="tok",
        github_repo="octo-org/octo-repo",
        anthropic_api_key="key",
        dry_run=False,
    )


def test_ingest_failed_job_builds_failed_run():
    github_client = FakeGitHubClient(
        runs=[], jobs_by_run={}, logs_by_job={2: "##[error]boom"}
    )

    result = ingest_failed_job(github_client, "octo-org/octo-repo", _run(), _job())

    assert result.repo == "octo-org/octo-repo"
    assert result.run_id == 1
    assert result.job_id == 2
    assert result.failed_step_name == "Run pytest"
    assert result.pr_number == 42
    assert "boom" in result.log_excerpt


def test_triage_failed_job_files_issue_and_saves_record(tmp_path, anthropic_client):
    github_client = FakeGitHubClient(
        runs=[], jobs_by_run={}, logs_by_job={2: "##[error]boom"}
    )
    with TriageStorage(tmp_path / "triage.db") as storage:
        record = triage_failed_job(
            github_client, anthropic_client, storage, "octo-org/octo-repo", _run(), _job()
        )

        assert record.issue_url is not None
        assert len(github_client.filed_issues) == 1
        assert storage.is_run_processed("octo-org/octo-repo", 1, 2)


def test_triage_failed_job_dry_run_skips_filing(tmp_path, anthropic_client):
    github_client = FakeGitHubClient(
        runs=[], jobs_by_run={}, logs_by_job={2: "##[error]boom"}
    )
    with TriageStorage(tmp_path / "triage.db") as storage:
        record = triage_failed_job(
            github_client,
            anthropic_client,
            storage,
            "octo-org/octo-repo",
            _run(),
            _job(),
            dry_run=True,
        )

        assert record.issue_url is None
        assert github_client.filed_issues == []
        assert storage.is_run_processed("octo-org/octo-repo", 1, 2)


def test_poll_once_skips_already_processed_and_non_failed_jobs(
    tmp_path, anthropic_client, settings
):
    runs = [_run(run_id=1)]
    jobs_by_run = {1: [_job(job_id=2, conclusion="failure"), _job(job_id=3, conclusion="success")]}
    logs_by_job = {2: "##[error]boom"}
    github_client = FakeGitHubClient(runs, jobs_by_run, logs_by_job)

    with TriageStorage(tmp_path / "triage.db") as storage:
        first_pass = poll_once(settings, github_client, anthropic_client, storage)
        assert len(first_pass) == 1
        assert first_pass[0].run.job_id == 2

        second_pass = poll_once(settings, github_client, anthropic_client, storage)
        assert second_pass == []
