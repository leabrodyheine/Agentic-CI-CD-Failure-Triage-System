from triage_agent.report import render_report, write_report


def test_render_report_handles_empty_records():
    html = render_report([])

    assert "<html" in html
    assert "No triage records yet." in html
    assert "Total triaged</div>" in html or "Total triaged" in html


def test_render_report_includes_summary_stats(triage_record):
    html = render_report([triage_record])

    assert "Total triaged" in html
    assert "1" in html
    assert "Avg. confidence" in html
    assert "60%" in html  # triage_record fixture has confidence=0.6


def test_render_report_includes_category_breakdown(triage_record):
    html = render_report([triage_record])

    assert "flake" in html


def test_render_report_includes_issue_link_when_present(triage_record):
    record = triage_record.model_copy(
        update={"issue_url": "https://github.com/octo-org/octo-repo/issues/9"}
    )

    html = render_report([record])

    assert 'href="https://github.com/octo-org/octo-repo/issues/9"' in html


def test_render_report_shows_dash_when_no_issue_filed(triage_record):
    record = triage_record.model_copy(update={"issue_url": None})

    html = render_report([record])

    assert "—" in html


def test_render_report_escapes_untrusted_text(triage_record):
    malicious_run = triage_record.run.model_copy(
        update={"workflow_name": '<script>alert("x")</script>'}
    )
    record = triage_record.model_copy(update={"run": malicious_run})

    html = render_report([record])

    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html


def test_render_report_truncates_table_to_50_most_recent(triage_record):
    records = [
        triage_record.model_copy(update={"run": triage_record.run.model_copy(update={"job_id": i})})
        for i in range(60)
    ]

    html = render_report(records)

    assert "Showing the 50 most recent of 60 records." in html


def test_write_report_writes_file(tmp_path, triage_record):
    output_path = tmp_path / "report.html"

    write_report([triage_record], output_path)

    content = output_path.read_text()
    assert "<html" in content
