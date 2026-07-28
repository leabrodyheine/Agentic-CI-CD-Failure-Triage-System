# Design Doc: Agentic CI/CD Failure Triage System

## 1. Overview

**Problem:** When CI/CD pipelines fail, engineers spend significant time manually reading logs, determining whether a failure is a flake or a real regression, identifying the likely root cause, and filing/tagging a bug report. This is slow, repetitive, and delays fix time.

**Solution:** An autonomous agent that watches CI pipeline runs, ingests failure logs, classifies the failure type, hypothesizes a root cause, and automatically files a structured bug report (or comments on the relevant PR) with its findings — with a confidence score and supporting evidence.

**Target roles this demonstrates:** EngProd, Developer Productivity, Platform/Infra Engineering, Agentic AI Systems.

---

## 2. Goals & Non-Goals

### Goals
- Automatically detect and classify CI failures (flake vs. regression vs. infra issue vs. new bug)
- Generate a root-cause hypothesis with supporting log evidence
- Auto-file a structured issue (GitHub Issues API) with reproducible steps, stack trace excerpt, and suspected commit/PR
- Reduce manual triage time measurably (this is your resume metric — e.g., "reduced average triage time from X min to Y min")
- Be observable: every agent decision should be logged and auditable

### Non-Goals (v1)
- Auto-fixing code (out of scope — too risky for a portfolio project, and not needed to prove the concept)
- Supporting every CI provider (start with GitHub Actions only)
- Perfect root-cause accuracy (target "helpful hypothesis," not "always correct")

---

## 3. Success Metrics

| Metric | Target |
|---|---|
| % of failures correctly classified (flake vs. real) | >80% on eval set |
| Time from failure to filed report | <2 min |
| Root-cause hypothesis judged "useful" by human review | >70% |
| False positive rate (flagging passing tests as failures) | <5% |

Build a small labeled eval set (50–100 historical failures, manually labeled) to measure against — this is what separates a "wrapper" from a real system, and it's the artifact that proves rigor in interviews.

---

## 4. System Architecture
