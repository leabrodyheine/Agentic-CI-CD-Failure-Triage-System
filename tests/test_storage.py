from triage_agent.storage import TriageStorage


def test_is_run_processed_false_before_save(tmp_path, triage_record):
    with TriageStorage(tmp_path / "triage.db") as storage:
        assert not storage.is_run_processed(
            triage_record.run.repo, triage_record.run.run_id, triage_record.run.job_id
        )


def test_save_and_lookup_round_trip(tmp_path, triage_record):
    with TriageStorage(tmp_path / "triage.db") as storage:
        storage.save_record(triage_record)

        assert storage.is_run_processed(
            triage_record.run.repo, triage_record.run.run_id, triage_record.run.job_id
        )
        fetched = storage.get_record(
            triage_record.run.repo, triage_record.run.run_id, triage_record.run.job_id
        )
        assert fetched == triage_record


def test_get_record_returns_none_when_missing(tmp_path):
    with TriageStorage(tmp_path / "triage.db") as storage:
        assert storage.get_record("octo-org/octo-repo", 1, 2) is None


def test_list_records_orders_most_recent_first(tmp_path, triage_record):
    with TriageStorage(tmp_path / "triage.db") as storage:
        second = triage_record.model_copy(
            update={"run": triage_record.run.model_copy(update={"job_id": 3})}
        )
        storage.save_record(triage_record)
        storage.save_record(second)

        records = storage.list_records()
        assert [r.run.job_id for r in records] == [3, 2]


def test_save_record_is_idempotent_per_run_job(tmp_path, triage_record):
    with TriageStorage(tmp_path / "triage.db") as storage:
        storage.save_record(triage_record)
        try:
            storage.save_record(triage_record)
        except Exception:
            pass
        else:
            raise AssertionError("expected duplicate save to raise")

        assert len(storage.list_records()) == 1


def test_persists_across_reopen(tmp_path, triage_record):
    db_path = tmp_path / "triage.db"
    with TriageStorage(db_path) as storage:
        storage.save_record(triage_record)

    with TriageStorage(db_path) as storage:
        assert len(storage.list_records()) == 1
