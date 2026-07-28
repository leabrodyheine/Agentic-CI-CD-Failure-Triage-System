#!/usr/bin/env python
"""CLI entry point: scores the classifier against eval/eval_set.json.

Usage:
    ANTHROPIC_API_KEY=... python eval/run_eval.py [path/to/eval_set.json]
"""

from triage_agent.eval_harness import main

if __name__ == "__main__":
    main()
