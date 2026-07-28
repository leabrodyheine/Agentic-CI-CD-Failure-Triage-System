import pytest

from triage_agent.issue_filer import (
    build_failure_signature,
    build_issue_body,
    build_issue_title,
    build_pr_comment_body,
    file_issue,
    find_duplicate_issue,
    post_pr_comment,
)
from triage_agent.models import FailureCategory, FailureClassification, RootCauseHypothesis


@pytest.fixture
def classification():
    return FailureClassification(
        category=FailureCategory.REGRESSION, confidence=0.85, reasoning="matches recent diff"
    )


@pytest.fixture
def hypothesis(failed_run):
    return RootCauseHypothesis(
        summary="The new retry decorator swallows the underlying exception.",
        evidence=["AssertionError: expected 1 got 2"],
        suspected_commit_sha=failed_run.head_sha,
        confidence=0.7,
    )


def test_build_issue_title_includes_category_and_context(failed_run, classification):
    title = build_issue_title(failed_run, classification)

    assert "regression" in title
    assert failed_run.workflow_name in title
    assert failed_run.job_name in title
    assert failed_run.head_branch in title


def test_build_issue_body_includes_all_key_fields(failed_run, classification, hypothesis):
    body = build_issue_body(failed_run, classification, hypothesis)

    assert hypothesis.summary in body
    assert "85%" in body
    assert "70%" in body
    assert hypothesis.evidence[0] in body
    assert failed_run.head_sha in body
    assert f"#{failed_run.pr_number}" in body
    assert failed_run.log_excerpt in body


def test_build_issue_body_handles_missing_evidence_and_pr(failed_run, classification):
    hypothesis = RootCauseHypothesis(summary="unclear", evidence=[], confidence=0.2)
    run = failed_run.model_copy(update={"pr_number": None})

    body = build_issue_body(run, classification, hypothesis)

    assert "_No specific log evidence cited._" in body
    assert "_none_" in body
    assert "_not identified_" in body


class FakeGitHubClient:
    def __init__(self, existing_issues=None):
        self.calls = []
        self.pr_comments = []
        self._existing_issues = existing_issues or []
        self.list_issues_calls = []

    def create_issue(self, title, body, labels=None):
        self.calls.append({"title": title, "body": body, "labels": labels})
        return {"html_url": "https://github.com/octo-org/octo-repo/issues/7"}

    def create_pr_comment(self, pr_number, body):
        self.pr_comments.append({"pr_number": pr_number, "body": body})
        return {"html_url": f"https://github.com/octo-org/octo-repo/pull/{pr_number}#comment-1"}

    def list_issues(self, labels=None, state="open"):
        self.list_issues_calls.append({"labels": labels, "state": state})
        return self._existing_issues


def test_file_issue_creates_issue_with_expected_labels(failed_run, classification, hypothesis):
    client = FakeGitHubClient()

    url = file_issue(failed_run, classification, hypothesis, client)

    assert url == "https://github.com/octo-org/octo-repo/issues/7"
    call = client.calls[0]
    assert call["labels"] == ["triage-agent", "regression"]
    assert call["title"] == build_issue_title(failed_run, classification)


def test_build_pr_comment_body_includes_key_fields(failed_run, classification, hypothesis):
    body = build_pr_comment_body(failed_run, classification, hypothesis)

    assert failed_run.job_name in body
    assert failed_run.failed_step_name in body
    assert "regression" in body
    assert "85%" in body
    assert hypothesis.summary in body
    assert "Filed as" not in body


def test_build_pr_comment_body_includes_issue_link_when_provided(
    failed_run, classification, hypothesis
):
    body = build_pr_comment_body(
        failed_run, classification, hypothesis, issue_url="https://github.com/o/r/issues/7"
    )

    assert "https://github.com/o/r/issues/7" in body


def test_post_pr_comment_posts_when_pr_number_present(failed_run, classification, hypothesis):
    client = FakeGitHubClient()

    url = post_pr_comment(failed_run, classification, hypothesis, client)

    assert url == f"https://github.com/octo-org/octo-repo/pull/{failed_run.pr_number}#comment-1"
    assert client.pr_comments[0]["pr_number"] == failed_run.pr_number


def test_post_pr_comment_returns_none_when_no_pr(failed_run, classification, hypothesis):
    client = FakeGitHubClient()
    run = failed_run.model_copy(update={"pr_number": None})

    url = post_pr_comment(run, classification, hypothesis, client)

    assert url is None
    assert client.pr_comments == []


def test_build_failure_signature_is_stable_for_same_inputs(failed_run, classification):
    assert build_failure_signature(failed_run, classification) == build_failure_signature(
        failed_run, classification
    )


def test_build_failure_signature_differs_by_category(failed_run, classification):
    other = classification.model_copy(update={"category": FailureCategory.FLAKE})

    assert build_failure_signature(failed_run, classification) != build_failure_signature(
        failed_run, other
    )


def test_build_failure_signature_differs_by_job(failed_run, classification):
    other_run = failed_run.model_copy(update={"job_name": "other-job"})

    assert build_failure_signature(failed_run, classification) != build_failure_signature(
        other_run, classification
    )


def test_build_issue_body_embeds_signature_marker(failed_run, classification, hypothesis):
    body = build_issue_body(failed_run, classification, hypothesis)
    signature = build_failure_signature(failed_run, classification)

    assert f"<!-- triage-agent-signature: {signature} -->" in body


def test_find_duplicate_issue_returns_none_when_no_match(failed_run, classification):
    client = FakeGitHubClient(existing_issues=[{"html_url": "x", "body": "unrelated"}])

    assert find_duplicate_issue(failed_run, classification, client) is None
    assert client.list_issues_calls[0]["labels"] == ["triage-agent"]


def test_find_duplicate_issue_finds_matching_signature(failed_run, classification):
    signature = build_failure_signature(failed_run, classification)
    existing = {
        "html_url": "https://github.com/octo-org/octo-repo/issues/3",
        "body": f"...\n<!-- triage-agent-signature: {signature} -->\n...",
    }
    client = FakeGitHubClient(existing_issues=[existing])

    result = find_duplicate_issue(failed_run, classification, client)

    assert result == "https://github.com/octo-org/octo-repo/issues/3"


def test_file_issue_returns_existing_url_instead_of_filing_when_duplicate(
    failed_run, classification, hypothesis
):
    signature = build_failure_signature(failed_run, classification)
    existing = {
        "html_url": "https://github.com/octo-org/octo-repo/issues/3",
        "body": f"<!-- triage-agent-signature: {signature} -->",
    }
    client = FakeGitHubClient(existing_issues=[existing])

    url = file_issue(failed_run, classification, hypothesis, client)

    assert url == "https://github.com/octo-org/octo-repo/issues/3"
    assert client.calls == []


def test_file_issue_logs_reuse_of_duplicate(failed_run, classification, hypothesis, caplog):
    signature = build_failure_signature(failed_run, classification)
    existing = {
        "html_url": "https://github.com/octo-org/octo-repo/issues/3",
        "body": f"<!-- triage-agent-signature: {signature} -->",
    }
    client = FakeGitHubClient(existing_issues=[existing])

    with caplog.at_level("INFO", logger="triage_agent.issue_filer"):
        file_issue(failed_run, classification, hypothesis, client)

    assert any("reusing existing issue" in r.message for r in caplog.records)


def test_file_issue_logs_new_filing(failed_run, classification, hypothesis, caplog):
    client = FakeGitHubClient()

    with caplog.at_level("INFO", logger="triage_agent.issue_filer"):
        file_issue(failed_run, classification, hypothesis, client)

    assert any("filed issue" in r.message for r in caplog.records)


def test_file_issue_files_new_issue_when_skip_if_duplicate_is_false(
    failed_run, classification, hypothesis
):
    signature = build_failure_signature(failed_run, classification)
    existing = {
        "html_url": "https://github.com/octo-org/octo-repo/issues/3",
        "body": f"<!-- triage-agent-signature: {signature} -->",
    }
    client = FakeGitHubClient(existing_issues=[existing])

    url = file_issue(failed_run, classification, hypothesis, client, skip_if_duplicate=False)

    assert url == "https://github.com/octo-org/octo-repo/issues/7"
    assert len(client.calls) == 1
