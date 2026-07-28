import pytest

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
    def __init__(self):
        self.headers = {}
        self.requests: list[tuple[str, str, dict]] = []
        self._get_responses: dict[str, FakeResponse] = {}
        self._post_response: FakeResponse | None = None

    def stub_get(self, url_suffix: str, response: FakeResponse):
        self._get_responses[url_suffix] = response

    def stub_post(self, response: FakeResponse):
        self._post_response = response

    def get(self, url, params=None, **kwargs):
        self.requests.append(("GET", url, params or {}))
        for suffix, response in self._get_responses.items():
            if url.endswith(suffix):
                return response
        raise AssertionError(f"unstubbed GET {url}")

    def post(self, url, json=None, **kwargs):
        self.requests.append(("POST", url, json or {}))
        return self._post_response


@pytest.fixture
def session():
    return FakeSession()


@pytest.fixture
def client(session):
    return GitHubClient(token="tok", repo="octo-org/octo-repo", session=session)


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


def test_list_jobs_for_run(client, session):
    session.stub_get("/runs/123/jobs", FakeResponse({"jobs": [{"id": 9, "conclusion": "failure"}]}))

    jobs = client.list_jobs_for_run(123)

    assert jobs[0]["id"] == 9


def test_fetch_job_log_returns_raw_text(client, session):
    session.stub_get("/jobs/9/logs", FakeResponse({}, text="##[error] boom"))

    log = client.fetch_job_log(9)

    assert log == "##[error] boom"


def test_create_issue_posts_expected_payload(client, session):
    session.stub_post(FakeResponse({"html_url": "https://github.com/o/r/issues/1"}))

    result = client.create_issue("Title", "Body", labels=["triage-agent"])

    assert result["html_url"].endswith("/issues/1")
    method, url, payload = session.requests[0]
    assert method == "POST"
    assert payload == {"title": "Title", "body": "Body", "labels": ["triage-agent"]}


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
