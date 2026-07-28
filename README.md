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
```

Relevant env vars beyond the required three (see `.env.example` for the full list):

- `TRIAGE_DRY_RUN=true` — run the full pipeline and log the decision without filing an issue.
- `TRIAGE_MIN_CONFIDENCE_TO_FILE=0.7` — only file an issue when classification confidence meets
  this threshold; below it, the decision is still logged, just not filed.
- `TRIAGE_COMMENT_ON_PR=true` — also post a condensed triage summary as a PR comment when the run
  is linked to one.

A recurring failure (same repo/workflow/job/step/category) won't get a fresh issue filed every
time it happens again — `triage` detects the existing open issue via a hidden signature marker
and reuses its URL instead. Transient GitHub/Anthropic API errors (rate limits, 5xx) are retried
automatically with backoff.

## Running it on a schedule

[.github/workflows/triage.yml](.github/workflows/triage.yml) runs `triage poll --once` every 15
minutes via `workflow_dispatch`/`schedule`, using the default `GITHUB_TOKEN` and
`github.repository`. To enable it on a repo: add an `ANTHROPIC_API_KEY` repository secret, then
push the workflow file. The audit log (`triage.db`) is cached between runs via `actions/cache` so
polling stays idempotent across the workflow's fresh checkouts.

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
