# Implementation Plan: Agentic CI/CD Failure Triage System

This plan fills in Section 4 (System Architecture) of [DESIGN.md](DESIGN.md), which was left
without content, and breaks the build into small, independently-committable increments.

Decisions made to unblock implementation (confirmed with the project owner):

- **Trigger:** polling script against the GitHub Actions REST API (no hosted webhook endpoint).
- **Language:** Python 3.11+.
- **LLM:** Anthropic Claude (Messages API), used directly (no provider abstraction for v1).
- **Storage:** SQLite for the audit trail / run history, JSON files for the labeled eval set.

## 4. System Architecture (proposed)

```
                    ┌─────────────────────┐
   GitHub Actions   │       Poller         │   polls REST API on an interval,
   REST API  ───────▶  (poller.py)         │   tracks last-seen run IDs in SQLite
                    └─────────┬────────────┘
                              │ new failed run
                              ▼
                    ┌─────────────────────┐
                    │   Log Ingestion      │  downloads job logs (zip), extracts
                    │  (github_client.py,  │  the failing step's raw text
                    │   log_parser.py)     │
                    └─────────┬────────────┘
                              │ log excerpt + run/PR metadata
                              ▼
                    ┌─────────────────────┐
                    │    Classifier        │  Claude call → flake / regression /
                    │  (classifier.py)     │  infra-issue / new-bug + confidence
                    └─────────┬────────────┘
                              ▼
                    ┌─────────────────────┐
                    │  Root-Cause Engine   │  Claude call → hypothesis + cited
                    │  (root_cause.py)     │  log evidence + suspected commit
                    └─────────┬────────────┘
                              ▼
                    ┌─────────────────────┐
                    │   Issue Filer        │  builds structured Markdown body,
                    │  (issue_filer.py)    │  files via GitHub Issues API
                    └─────────┬────────────┘
                              ▼
                    ┌─────────────────────┐
                    │   Audit Log (SQLite) │  every decision + evidence + links,
                    │  (storage.py)        │  for auditability & the eval harness
                    └─────────────────────┘
```

**Orchestration:** `poller.py` ties the pipeline together per run; `cli.py` exposes it as
`triage poll` (loop), `triage run <run-id>` (single run, for debugging/demo), and `triage eval`
(scores the classifier against the labeled eval set).

**Why polling over webhooks:** avoids needing a publicly reachable, hosted endpoint for a
portfolio project; the poll loop can run locally, via cron, or as a scheduled GitHub Actions
workflow. Trade-off is called out in DESIGN.md's non-goals as acceptable for v1.

### Project layout

```
pyproject.toml
.env.example
src/triage_agent/
  __init__.py
  config.py            # env-var driven settings (tokens, repo, poll interval, dry-run, ...)
  models.py             # pydantic models: FailureClassification, RootCauseHypothesis, TriageRecord
  storage.py             # SQLite audit log (processed runs, decisions, filed issue links, last-poll-time)
  retry.py                # generic retry-with-backoff helper
  github_client.py         # list failed runs, fetch/extract logs, create issues/PR comments, list issues
  anthropic_utils.py        # retries transient Anthropic API errors around messages.create()
  log_parser.py               # extract the failing step's relevant excerpt from raw logs
  classifier.py                 # Claude call: classify failure type + confidence
  root_cause.py                  # Claude call: root-cause hypothesis + evidence
  issue_filer.py                   # issue/PR-comment bodies, duplicate detection, filing
  poller.py                         # orchestrates the pipeline per new failed run
  eval_harness.py                    # scores the classifier against a labeled eval set
  cli.py                               # `triage poll|run|eval` entrypoints
  prompts/
    classify.md
    root_cause.md
eval/
  eval_set.json        # labeled historical failures (schema + seed examples)
  run_eval.py            # thin script wrapping eval_harness.main()
tests/                   # one test module per src module, all against fakes/mocks
.github/workflows/
  ci.yml                # lint (ruff) + type check (mypy) + pytest on push/PR
  triage.yml             # scheduled `triage poll --once` against the repo itself
```

## Beyond v1

Implemented after the initial build, per DESIGN.md's spirit of iterating past a bare wrapper:
retries with backoff on transient GitHub/Anthropic errors, log-fetch capping, a date-bounded
polling window, per-stage timing on every TriageRecord (the metric DESIGN.md's success criteria
actually need), a confidence threshold gating issue filing, PR-comment posting as an alternative
to issues, duplicate-issue detection via a hidden signature marker, an eval CLI subcommand, mypy,
and the scheduled workflow that actually invokes the CLI.

Still open, per the earlier gap analysis:

- `eval/eval_set.json` has 6 hand-written examples, not the 50-100 real labeled failures DESIGN.md
  calls for.
- No PR-comment de-duplication analogous to the issue-filing one.
