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
  config.py          # env-var driven settings (tokens, repo, poll interval, dry-run)
  models.py           # pydantic models: FailureClassification, RootCauseHypothesis, TriageRecord
  storage.py           # SQLite audit log (processed runs, decisions, filed issue links)
  github_client.py     # list failed runs, fetch/extract logs, create issues
  log_parser.py         # extract the failing step's relevant excerpt from raw logs
  classifier.py          # Claude call: classify failure type + confidence
  root_cause.py           # Claude call: root-cause hypothesis + evidence
  issue_filer.py           # builds issue body from records, files via github_client
  poller.py                 # orchestrates the pipeline per new failed run
  cli.py                     # `triage poll|run|eval` entrypoints
  prompts/
    classify.md
    root_cause.md
eval/
  eval_set.json        # labeled historical failures (schema + seed examples)
  run_eval.py            # computes classification accuracy / false-positive rate
tests/
  test_log_parser.py
  test_storage.py
  test_classifier.py
  test_root_cause.py
  test_issue_filer.py
  test_poller.py
.github/workflows/ci.yml   # lint + pytest on push
```

## Commit plan

Small, buildable increments, roughly in dependency order:

1. Add this implementation plan doc.
2. Scaffold Python package (`pyproject.toml`, `src/triage_agent/__init__.py`, `.gitignore`).
3. Add `config.py` — env-var settings (GitHub token, repo, Anthropic key, poll interval, dry-run).
4. Add `models.py` — pydantic models for classification, hypothesis, and triage records.
5. Add `storage.py` — SQLite audit log (schema + read/write) with tests.
6. Add `github_client.py` — list failed workflow runs, fetch/extract job logs, create issues (unit-tested against a mocked API).
7. Add `log_parser.py` — extract the failing step's relevant excerpt from raw logs, with tests.
8. Add classification prompt + `classifier.py` (Claude call, structured output), with tests against a mocked client.
9. Add root-cause prompt + `root_cause.py` (Claude call, structured output), with tests.
10. Add `issue_filer.py` — builds the structured issue Markdown and files it, with tests.
11. Add `poller.py` — orchestrates ingestion → classify → root-cause → file → audit-log per run, with tests.
12. Add `cli.py` — `triage poll` / `triage run` / `triage eval` commands.
13. Add `eval/eval_set.json` schema + seed examples and `eval/run_eval.py` metrics script.
14. Add `.env.example` and expand `README.md` with setup/usage instructions.
15. Add `.github/workflows/ci.yml` to lint and test the project itself on push.

Each commit leaves the repo in a working state (imports resolve, tests pass for what exists so
far). LLM- and GitHub-API-touching code is unit-tested against mocks/fakes — no network calls in
the test suite.
