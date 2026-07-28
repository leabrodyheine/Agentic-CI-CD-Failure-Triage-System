from triage_agent.log_parser import extract_error_excerpt, strip_timestamps


def test_strip_timestamps_removes_iso_prefix():
    log = "2024-01-01T12:00:00.1234567Z Run pytest\n2024-01-01T12:00:01.0000000Z All good"

    stripped = strip_timestamps(log)

    assert stripped == "Run pytest\nAll good"


def test_strip_timestamps_leaves_lines_without_prefix_unchanged():
    log = "no timestamp here"
    assert strip_timestamps(log) == log


def test_extract_error_excerpt_centers_on_error_marker():
    lines = [f"2024-01-01T00:00:00.0000000Z setup line {i}" for i in range(30)]
    lines.append("2024-01-01T00:00:00.0000000Z ##[error]Process completed with exit code 1.")
    lines += [f"2024-01-01T00:00:00.0000000Z trailer {i}" for i in range(5)]
    log = "\n".join(lines)

    excerpt = extract_error_excerpt(log, context_before=3, context_after=2)

    assert "##[error]Process completed with exit code 1." in excerpt
    assert "setup line 29" in excerpt
    assert "trailer 1" in excerpt
    assert "setup line 26" not in excerpt
    assert "trailer 2" not in excerpt


def test_extract_error_excerpt_prefers_explicit_error_marker_over_generic_word():
    log = "\n".join(
        [
            "Error: this is a red herring near the top",
            *[f"noise {i}" for i in range(20)],
            "##[error]Real failure signal",
        ]
    )

    excerpt = extract_error_excerpt(log, context_before=2, context_after=2)

    assert "Real failure signal" in excerpt
    assert "red herring" not in excerpt


def test_extract_error_excerpt_falls_back_to_tail_when_no_marker():
    lines = [f"line {i}" for i in range(100)]
    log = "\n".join(lines)

    excerpt = extract_error_excerpt(log, max_lines=10)

    assert excerpt.splitlines() == lines[-10:]


def test_extract_error_excerpt_respects_max_lines():
    lines = [f"line {i}" for i in range(30)]
    lines.append("##[error]boom")
    log = "\n".join(lines)

    excerpt = extract_error_excerpt(log, context_before=20, context_after=20, max_lines=5)

    assert len(excerpt.splitlines()) <= 5


def test_extract_error_excerpt_empty_log_returns_empty_string():
    assert extract_error_excerpt("") == ""
