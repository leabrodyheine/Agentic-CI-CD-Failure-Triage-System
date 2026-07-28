from datetime import UTC, datetime

import pytest
import requests

from triage_agent.github_client import (
    GitHubClient,
    extract_failed_step_name,
    extract_pr_number,
)


class FakeResponse:
    def __init__(self, json_data, status_code=200, text=""):
        self._json_data = json_data
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    """Stubs GET/POST by URL suffix. A list of responses is consumed in order (useful for
    simulating a transient failure followed by success); the last response repeats once
    exhausted. A `raises` queue can be stubbed instead to simulate connection errors."""

    def __init__(self):
        self.headers = {}
        self.requests: list[tuple[str, str, dict]] = []
        self.get_kwargs: list[dict] = []
        self._get_responses: dict[str, list] = {}
        self._post_response: FakeResponse | None = None

    def stub_get(self, url_suffix: str, response_or_responses):
        responses = (
            list(response_or_responses)
            if isinstance(response_or_responses, list)
            else [response_or_responses]
        )
        self._get_responses[url_suffix] = responses

    def stub_post(self, response: FakeResponse):
        self._post_response = response

    def get(self, url, params=None, **kwargs):
        self.requests.append(("GET", url, params or {}))
        self.get_kwargs.append(kwargs)
        for suffix, responses in self._get_responses.items():
            if url.endswith(suffix):
                item = responses.pop(0) if len(responses) > 1 else responses[0]
                if isinstance(item, Exception):
                    raise item
                return item
        raise AssertionError(f"unstubbed GET {url}")

    def post(self, url, json=None, **kwargs):
        self.requests.append(("POST", url, json or {}))
        return self._post_response


@pytest.fixture
def session():
    return FakeSession()


@pytest.fixture
def client(session):
    return GitHubClient(
        token="tok", repo="octo-org/octo-repo", session=session, sleep=lambda s: None
    )


def test_sets_auth_headers(session):
    GitHubClient(token="tok", repo="octo-org/octo-repo", session=session)
    assert session.headers["Authorization"] == "Bearer tok"


def test_list_failed_workflow_runs(client, session):
    session.stub_get("/actions/runs", FakeResponse({"workflow_runs": [{"id": 1}, {"id": 2}]}))

    runs = client.list_failed_workflow_runs()

    assert [r["id"] for r in runs] == [1, 2]
    method, url, params = session.requests[0]
    assert method == "GET"
    assert params["status"] == "failure"
    assert "created" not in params


def test_list_failed_workflow_runs_with_created_after_filter(client, session):
    session.stub_get("/actions/runs", FakeResponse({"workflow_runs": []}))
    cutoff = datetime(2026, 1, 1, tzinfo=UTC)

    client.list_failed_workflow_runs(created_after=cutoff)

    _, _, params = session.requests[0]
    assert params["created"] == ">=2026-01-01T00:00:00+00:00"


def test_list_jobs_for_run(client, session):
    session.stub_get("/runs/123/jobs", FakeResponse({"jobs": [{"id": 9, "conclusion": "failure"}]}))

    jobs = client.list_jobs_for_run(123)

    assert jobs[0]["id"] == 9


def test_fetch_job_log_returns_raw_text(client, session):
    session.stub_get("/jobs/9/logs", FakeResponse({}, text="##[error] boom"))

    log = client.fetch_job_log(9)

    assert log == "##[error] boom"


def test_fetch_job_log_sends_range_header_for_tail_bytes(client, session):
    session.stub_get("/jobs/9/logs", FakeResponse({}, text="short log"))

    client.fetch_job_log(9, max_bytes=1000)

    assert session.get_kwargs[0]["headers"] == {"Range": "bytes=-1000"}


def test_fetch_job_log_truncates_client_side_if_server_ignores_range(client, session):
    full_log = "x" * 100
    session.stub_get("/jobs/9/logs", FakeResponse({}, text=full_log))

    log = client.fetch_job_log(9, max_bytes=10)

    assert log == full_log[-10:]
    assert len(log) == 10


def test_fetch_job_log_no_cap_when_max_bytes_none(client, session):
    session.stub_get("/jobs/9/logs", FakeResponse({}, text="x" * 100))

    log = client.fetch_job_log(9, max_bytes=None)

    assert len(log) == 100
    assert session.get_kwargs[0]["headers"] is None


def test_create_issue_posts_expected_payload(client, session):
    session.stub_post(FakeResponse({"html_url": "https://github.com/o/r/issues/1"}))

    result = client.create_issue("Title", "Body", labels=["triage-agent"])

    assert result["html_url"].endswith("/issues/1")
    method, url, payload = session.requests[0]
    assert method == "POST"
    assert payload == {"title": "Title", "body": "Body", "labels": ["triage-agent"]}


def test_create_pr_comment_posts_to_issue_comments_endpoint(client, session):
    session.stub_post(FakeResponse({"html_url": "https://github.com/o/r/pull/5#comment-1"}))

    result = client.create_pr_comment(5, "Looks like a flake.")

    assert result["html_url"].endswith("#comment-1")
    method, url, payload = session.requests[0]
    assert method == "POST"
    assert url.endswith("/issues/5/comments")
    assert payload == {"body": "Looks like a flake."}


def test_list_issues_defaults_to_open_state(client, session):
    session.stub_get("/issues", FakeResponse([{"id": 1}, {"id": 2}]))

    issues = client.list_issues()

    assert [i["id"] for i in issues] == [1, 2]
    _, _, params = session.requests[0]
    assert params["state"] == "open"
    assert "labels" not in params


def test_list_issues_joins_labels(client, session):
    session.stub_get("/issues", FakeResponse([]))

    client.list_issues(labels=["triage-agent", "flake"])

    _, _, params = session.requests[0]
    assert params["labels"] == "triage-agent,flake"


def test_extract_failed_step_name_finds_failing_step():
    job = {
        "steps": [
            {"name": "Checkout", "conclusion": "success"},
            {"name": "Run tests", "conclusion": "failure"},
            {"name": "Upload artifact", "conclusion": "skipped"},
        ]
    }
    assert extract_failed_step_name(job) == "Run tests"


def test_extract_failed_step_name_returns_none_when_no_failure():
    job = {"steps": [{"name": "Checkout", "conclusion": "success"}]}
    assert extract_failed_step_name(job) is None


def test_extract_pr_number_present():
    run = {"pull_requests": [{"number": 42}]}
    assert extract_pr_number(run) == 42


def test_extract_pr_number_absent():
    assert extract_pr_number({"pull_requests": []}) is None
    assert extract_pr_number({}) is None


def test_retries_on_503_then_succeeds(client, session):
    session.stub_get(
        "/actions/runs",
        [
            FakeResponse({}, status_code=503),
            FakeResponse({}, status_code=503),
            FakeResponse({"workflow_runs": [{"id": 1}]}),
        ],
    )

    runs = client.list_failed_workflow_runs()

    assert [r["id"] for r in runs] == [1]
    assert len(session.requests) == 3


def test_retries_on_connection_error_then_succeeds(client, session):
    session.stub_get(
        "/actions/runs",
        [
            requests.ConnectionError("boom"),
            FakeResponse({"workflow_runs": [{"id": 1}]}),
        ],
    )

    runs = client.list_failed_workflow_runs()

    assert [r["id"] for r in runs] == [1]


def test_does_not_retry_on_404(client, session):
    session.stub_get("/actions/runs", FakeResponse({}, status_code=404))

    with pytest.raises(RuntimeError, match="404"):
        client.list_failed_workflow_runs()

    assert len(session.requests) == 1


def test_gives_up_after_max_retry_attempts(session):
    client = GitHubClient(
        token="tok",
        repo="octo-org/octo-repo",
        session=session,
        max_retry_attempts=2,
        sleep=lambda s: None,
    )
    session.stub_get("/actions/runs", [FakeResponse({}, status_code=503)] * 5)

    with pytest.raises(Exception, match="failed after 2 attempts"):
        client.list_failed_workflow_runs()

    assert len(session.requests) == 2
