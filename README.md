# Agentic CI/CD Failure Triage System

An autonomous agent that watches a GitHub Actions repo for failed runs, classifies each failure
(flake / regression / infra issue / new bug) with Claude, generates a root-cause hypothesis with
cited log evidence, and files a structured GitHub issue with a confidence score — with every
decision recorded in an auditable SQLite log.

See [DESIGN.md](DESIGN.md) for the problem statement and goals, and
[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for the architecture and build plan.

## Setup

Requires Python 3.11+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # then fill in GITHUB_TOKEN, GITHUB_REPO, ANTHROPIC_API_KEY
```

`GITHUB_TOKEN` needs `repo` scope (to read Actions runs/logs and file issues) on the target repo.

## Usage

Load your `.env` (e.g. `set -a && source .env && set +a`), then:

```bash
# Poll continuously, triaging any newly-failed run/job not already in the audit log.
triage poll

# Poll a single time and exit (useful for cron / a scheduled GitHub Actions workflow).
triage poll --once

# Triage one specific currently-failing run/job (debugging or a live demo).
triage run <run_id> <job_id>

# Score the classifier against a labeled eval set (defaults to eval/eval_set.json).
triage eval [--eval-set path/to/eval_set.json]

# Generate a static HTML report from the audit log (default: ./triage-report.html).
triage report [--output path.html] [--limit 500]
```

Relevant env vars beyond the required three (see `.env.example` for the full list):

- `TRIAGE_DRY_RUN=true` — run the full pipeline and log the decision without filing an issue.
- `TRIAGE_MIN_CONFIDENCE_TO_FILE=0.7` — only file an issue when classification confidence meets
  this threshold; below it, the decision is still logged, just not filed.
- `TRIAGE_COMMENT_ON_PR=true` — also post a condensed triage summary as a PR comment when the run
  is linked to one.
- `TRIAGE_LOG_LEVEL=DEBUG` — controls the verbosity of the agent's decision log (see below).

A recurring failure (same repo/workflow/job/step/category) won't get a fresh issue filed every
time it happens again — `triage` detects the existing open issue via a hidden signature marker
and reuses its URL instead. Transient GitHub/Anthropic API errors (rate limits, 5xx) are retried
automatically with backoff.

## Observability

Every agent decision is logged (`triage_agent.{classifier,root_cause,issue_filer,poller,retry}`
loggers, INFO by default): each classification and its confidence, each root-cause hypothesis,
whether an issue was filed or an existing one reused, why an issue was skipped, and every retried
API call. `TRIAGE_LOG_LEVEL=DEBUG` adds per-job skip decisions during polling.

`triage report` turns the SQLite audit log into a self-contained HTML page (summary stats, a
category breakdown chart, and a table of recent records with issue links) — no server, just a
file to open in a browser.

## Running it in GitHub Actions

[.github/workflows/triage.yml](.github/workflows/triage.yml) runs `triage poll --once` using the
default `GITHUB_TOKEN` and `github.repository`. It's manual-only (`workflow_dispatch`) by
default — nothing runs automatically just from pushing this file. To trigger it, go to the
Actions tab and click "Run workflow"; it needs an `ANTHROPIC_API_KEY` repository secret to
succeed. The audit log (`triage.db`) is cached between runs via `actions/cache` so repeated runs
stay idempotent across the workflow's fresh checkouts.

A commented-out `schedule:` trigger in the workflow file would make it run automatically (every
15 minutes, by default) — deliberately left off. Enabling it means: it runs unattended even with
no failures to look at, and if a run fails (e.g. a missing/expired secret), GitHub's default
behavior is to email the repo owner/watchers about the failure.

## Testing

```bash
pytest
```

All tests run against fakes/mocks for the GitHub and Anthropic APIs — no network calls, no
credentials required.

## Evaluating the classifier

```bash
python eval/run_eval.py
# or, equivalently:
triage eval
```

Scores the classifier against the labeled examples in `eval/eval_set.json` and reports accuracy,
flake-vs-real accuracy, and any misclassifications. The seed set has 6 examples as a schema
reference; grow it to 50-100 real labeled failures from your own CI history for the accuracy
numbers to be meaningful (see DESIGN.md's success metrics).
