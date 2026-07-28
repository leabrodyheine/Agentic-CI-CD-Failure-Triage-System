"""Builds a structured issue body from a triage result and files it via GitHubClient."""

from __future__ import annotations

from triage_agent.github_client import GitHubClient
from triage_agent.models import FailedRun, FailureClassification, RootCauseHypothesis

_DEFAULT_LABEL = "triage-agent"


def build_issue_title(run: FailedRun, classification: FailureClassification) -> str:
    return f"[{classification.category.value}] {run.workflow_name} / {run.job_name} failing on {run.head_branch}"


def build_issue_body(
    run: FailedRun, classification: FailureClassification, hypothesis: RootCauseHypothesis
) -> str:
    evidence_section = (
        "\n".join(f"- `{line}`" for line in hypothesis.evidence)
        if hypothesis.evidence
        else "_No specific log evidence cited._"
    )
    suspected_commit = hypothesis.suspected_commit_sha or "_not identified_"

    return f"""## Summary
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


def file_issue(
    run: FailedRun,
    classification: FailureClassification,
    hypothesis: RootCauseHypothesis,
    client: GitHubClient,
) -> str:
    """Files a structured issue for this triage result and returns the issue URL."""
    title = build_issue_title(run, classification)
    body = build_issue_body(run, classification, hypothesis)
    labels = [_DEFAULT_LABEL, classification.category.value]

    result = client.create_issue(title, body, labels=labels)
    return result["html_url"]
