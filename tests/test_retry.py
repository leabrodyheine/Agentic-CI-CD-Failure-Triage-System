import pytest

from triage_agent.retry import RetryError, call_with_retries


def test_returns_result_on_first_success():
    calls = []

    def fn():
        calls.append(1)
        return "ok"

    result = call_with_retries(fn, sleep=lambda s: None)

    assert result == "ok"
    assert len(calls) == 1


def test_retries_until_success():
    attempts = {"count": 0}

    def fn():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise ValueError("transient")
        return "ok"

    result = call_with_retries(fn, max_attempts=5, sleep=lambda s: None)

    assert result == "ok"
    assert attempts["count"] == 3


def test_raises_retry_error_after_exhausting_attempts():
    def fn():
        raise ValueError("always fails")

    with pytest.raises(RetryError):
        call_with_retries(fn, max_attempts=3, sleep=lambda s: None)


def test_chains_original_exception_as_cause():
    def fn():
        raise ValueError("root cause")

    with pytest.raises(RetryError) as exc_info:
        call_with_retries(fn, max_attempts=2, sleep=lambda s: None)

    assert isinstance(exc_info.value.__cause__, ValueError)
    assert str(exc_info.value.__cause__) == "root cause"


def test_only_retries_specified_exception_types():
    def fn():
        raise TypeError("not retryable")

    with pytest.raises(TypeError):
        call_with_retries(
            fn, max_attempts=3, retryable_exceptions=(ValueError,), sleep=lambda s: None
        )


def test_sleeps_with_exponential_backoff():
    delays = []

    def fn():
        raise ValueError("fail")

    with pytest.raises(RetryError):
        call_with_retries(
            fn, max_attempts=4, base_delay=1.0, sleep=lambda s: delays.append(s)
        )

    assert delays == [1.0, 2.0, 4.0]


def test_no_sleep_calls_when_first_attempt_succeeds():
    delays = []

    call_with_retries(lambda: "ok", sleep=lambda s: delays.append(s))

    assert delays == []


def test_logs_a_warning_on_each_retry(caplog):
    attempts = {"count": 0}

    def fn():
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise ValueError("transient")
        return "ok"

    with caplog.at_level("WARNING", logger="triage_agent.retry"):
        call_with_retries(fn, max_attempts=3, sleep=lambda s: None)

    assert len(caplog.records) == 1
    assert "attempt 1/3 failed" in caplog.records[0].message


def test_logs_a_warning_on_final_giveup(caplog):
    def fn():
        raise ValueError("always fails")

    with caplog.at_level("WARNING", logger="triage_agent.retry"), pytest.raises(RetryError):
        call_with_retries(fn, max_attempts=2, sleep=lambda s: None)

    assert len(caplog.records) == 2
    assert "giving up" in caplog.records[-1].message
