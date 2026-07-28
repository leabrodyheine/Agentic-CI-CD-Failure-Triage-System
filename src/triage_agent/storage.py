"""SQLite-backed audit log of every triage decision the agent has made."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from triage_agent.models import TriageRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS triage_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo TEXT NOT NULL,
    run_id INTEGER NOT NULL,
    job_id INTEGER NOT NULL,
    category TEXT NOT NULL,
    classification_confidence REAL NOT NULL,
    issue_url TEXT,
    triaged_at TEXT NOT NULL,
    record_json TEXT NOT NULL,
    UNIQUE (repo, run_id, job_id)
);

CREATE TABLE IF NOT EXISTS agent_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_LAST_POLL_TIME_KEY_PREFIX = "last_poll_time:"


class TriageStorage:
    """Thin wrapper around a SQLite audit log of processed runs and their triage records."""

    def __init__(self, db_path: str | Path):
        self._conn = sqlite3.connect(db_path)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> TriageStorage:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def is_run_processed(self, repo: str, run_id: int, job_id: int) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM triage_records WHERE repo = ? AND run_id = ? AND job_id = ?",
            (repo, run_id, job_id),
        ).fetchone()
        return row is not None

    def save_record(self, record: TriageRecord) -> None:
        self._conn.execute(
            """
            INSERT INTO triage_records
                (repo, run_id, job_id, category, classification_confidence, issue_url,
                 triaged_at, record_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.run.repo,
                record.run.run_id,
                record.run.job_id,
                record.classification.category.value,
                record.classification.confidence,
                record.issue_url,
                record.triaged_at.isoformat(),
                record.model_dump_json(),
            ),
        )
        self._conn.commit()

    def list_records(self, limit: int = 100) -> list[TriageRecord]:
        rows = self._conn.execute(
            "SELECT record_json FROM triage_records ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [TriageRecord.model_validate_json(row[0]) for row in rows]

    def get_record(self, repo: str, run_id: int, job_id: int) -> TriageRecord | None:
        row = self._conn.execute(
            "SELECT record_json FROM triage_records WHERE repo = ? AND run_id = ? AND job_id = ?",
            (repo, run_id, job_id),
        ).fetchone()
        return TriageRecord.model_validate_json(row[0]) if row else None

    def get_last_poll_time(self, repo: str) -> datetime | None:
        row = self._conn.execute(
            "SELECT value FROM agent_state WHERE key = ?",
            (_LAST_POLL_TIME_KEY_PREFIX + repo,),
        ).fetchone()
        return datetime.fromisoformat(row[0]) if row else None

    def set_last_poll_time(self, repo: str, when: datetime) -> None:
        self._conn.execute(
            "INSERT INTO agent_state (key, value) VALUES (?, ?) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            (_LAST_POLL_TIME_KEY_PREFIX + repo, when.isoformat()),
        )
        self._conn.commit()
