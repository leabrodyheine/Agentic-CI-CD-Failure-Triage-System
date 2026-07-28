"""Builds a structured issue body from a triage result and files it via GitHubClient."""

from __future__ import annotations

import hashlib
import logging

from triage_agent.github_client import GitHubClient
from triage_agent.models import FailedRun, FailureClassification, RootCauseHypothesis

logger = logging.getLogger(__name__)

_DEFAULT_LABEL = "triage-agent"
_SIGNATURE_COMMENT_TEMPLATE = "<!-- triage-agent-signature: {signature} -->"


def build_failure_signature(run: FailedRun, classification: FailureClassification) -> str:
    """A stable identifier for "this same failure recurring", independent of run/job id.

    Based on the repo, workflow, job, failed step, and category - deliberately not the log
    excerpt or commit, so the same recurring failure across multiple runs maps to one
    signature and doesn't get a fresh issue filed every time it happens again.
    """
    raw = "|".join(
        [
            run.repo,
            run.workflow_name,
            run.job_name,
            run.failed_step_name or "",
            classification.category.value,
        ]
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def build_issue_title(run: FailedRun, classification: FailureClassification) -> str:
    return (
        f"[{classification.category.value}] {run.workflow_name} / "
        f"{run.job_name} failing on {run.head_branch}"
    )


def build_issue_body(
    run: FailedRun, classification: FailureClassification, hypothesis: RootCauseHypothesis
) -> str:
    evidence_section = (
        "\n".join(f"- `{line}`" for line in hypothesis.evidence)
        if hypothesis.evidence
        else "_No specific log evidence cited._"
    )
    suspected_commit = hypothesis.suspected_commit_sha or "_not identified_"
    signature_comment = _SIGNATURE_COMMENT_TEMPLATE.format(
        signature=build_failure_signature(run, classification)
    )

    return f"""{signature_comment}
## Summary
{hypothesis.summary}

## Classification
- **Category:** `{classification.category.value}`
- **Confidence:** {classification.confidence:.0%}
- **Reasoning:** {classification.reasoning}

## Root-cause hypothesis
- **Confidence:** {hypothesis.confidence:.0%}
- **Suspected commit:** {suspected_commit}

### Evidence
{evidence_section}

## Run details
- **Workflow:** {run.workflow_name}
- **Job:** {run.job_name}
- **Failed step:** {run.failed_step_name or "unknown"}
- **Branch:** {run.head_branch}
- **Commit:** `{run.head_sha}`
- **PR:** {f"#{run.pr_number}" if run.pr_number else "_none_"}
- **Run URL:** {run.html_url}

## Log excerpt
```
{run.log_excerpt}
```

---
_Filed automatically by the CI/CD failure triage agent._
"""


def find_duplicate_issue(
    run: FailedRun, classification: FailureClassification, client: GitHubClient
) -> str | None:
    """Returns the URL of an already-open issue for this exact failure signature, if any."""
    marker = _SIGNATURE_COMMENT_TEMPLATE.format(
        signature=build_failure_signature(run, classification)
    )
    for issue in client.list_issues(labels=[_DEFAULT_LABEL]):
        if marker in (issue.get("body") or ""):
            return issue["html_url"]
    return None


def file_issue(
    run: FailedRun,
    classification: FailureClassification,
    hypothesis: RootCauseHypothesis,
    client: GitHubClient,
    skip_if_duplicate: bool = True,
) -> str:
    """Files a structured issue for this triage result and returns the issue URL.

    If skip_if_duplicate (default), and an open issue already exists for this exact failure
    signature (repo + workflow + job + failed step + category), returns that issue's URL
    instead of filing a new one - keeps a recurring failure from spawning a fresh issue
    every time it happens again.
    """
    if skip_if_duplicate:
        existing_url = find_duplicate_issue(run, classification, client)
        if existing_url is not None:
            logger.info(
                "reusing existing issue for run=%d job=%d: %s",
                run.run_id,
                run.job_id,
                existing_url,
            )
            return existing_url

    title = build_issue_title(run, classification)
    body = build_issue_body(run, classification, hypothesis)
    labels = [_DEFAULT_LABEL, classification.category.value]

    result = client.create_issue(title, body, labels=labels)
    logger.info(
        "filed issue for run=%d job=%d: %s", run.run_id, run.job_id, result["html_url"]
    )
    return result["html_url"]


def build_pr_comment_body(
    run: FailedRun,
    classification: FailureClassification,
    hypothesis: RootCauseHypothesis,
    issue_url: str | None = None,
) -> str:
    """A condensed version of the issue body, sized for a PR comment rather than an issue."""
    issue_line = f"\nFiled as {issue_url}." if issue_url else ""

    return (
        f"**CI failure triage: `{run.job_name}` / {run.failed_step_name or 'unknown step'}**\n\n"
        f"- **Category:** `{classification.category.value}` "
        f"({classification.confidence:.0%} confidence)\n"
        f"- **Likely cause:** {hypothesis.summary}\n"
        f"{issue_line}\n"
        f"\n_Filed automatically by the CI/CD failure triage agent._"
    )


def post_pr_comment(
    run: FailedRun,
    classification: FailureClassification,
    hypothesis: RootCauseHypothesis,
    client: GitHubClient,
    issue_url: str | None = None,
) -> str | None:
    """Posts a triage summary comment on the run's PR, if it has one. Returns the comment URL."""
    if run.pr_number is None:
        return None
    body = build_pr_comment_body(run, classification, hypothesis, issue_url)
    result = client.create_pr_comment(run.pr_number, body)
    return result["html_url"]
