import anthropic
import httpx
import pytest

from triage_agent.anthropic_utils import create_with_retries
from triage_agent.retry import RetryError

_REQUEST = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def _internal_server_error() -> anthropic.InternalServerError:
    response = httpx.Response(500, request=_REQUEST)
    return anthropic.InternalServerError("server error", response=response, body=None)


def _rate_limit_error() -> anthropic.RateLimitError:
    response = httpx.Response(429, request=_REQUEST)
    return anthropic.RateLimitError("rate limited", response=response, body=None)


def _connection_error() -> anthropic.APIConnectionError:
    return anthropic.APIConnectionError(request=_REQUEST)


class FakeMessages:
    def __init__(self, side_effects):
        self._side_effects = list(side_effects)
        self.calls = 0
        self.received_kwargs = []

    def create(self, **kwargs):
        self.calls += 1
        self.received_kwargs.append(kwargs)
        effect = self._side_effects.pop(0)
        if isinstance(effect, Exception):
            raise effect
        return effect


class FakeClient:
    def __init__(self, side_effects):
        self.messages = FakeMessages(side_effects)


def test_returns_response_on_first_success():
    client = FakeClient(["ok"])

    result = create_with_retries(client, sleep=lambda s: None, model="x")

    assert result == "ok"
    assert client.messages.calls == 1


def test_retries_on_internal_server_error_then_succeeds():
    client = FakeClient([_internal_server_error(), "ok"])

    result = create_with_retries(client, sleep=lambda s: None, model="x")

    assert result == "ok"
    assert client.messages.calls == 2


def test_retries_on_rate_limit_error():
    client = FakeClient([_rate_limit_error(), "ok"])

    result = create_with_retries(client, sleep=lambda s: None, model="x")

    assert result == "ok"


def test_retries_on_connection_error():
    client = FakeClient([_connection_error(), "ok"])

    result = create_with_retries(client, sleep=lambda s: None, model="x")

    assert result == "ok"


def test_does_not_retry_on_non_retryable_error():
    response = httpx.Response(400, request=_REQUEST)
    client = FakeClient([anthropic.BadRequestError("bad request", response=response, body=None)])

    with pytest.raises(anthropic.BadRequestError):
        create_with_retries(client, sleep=lambda s: None, model="x")

    assert client.messages.calls == 1


def test_gives_up_after_max_attempts():
    client = FakeClient([_internal_server_error()] * 5)

    with pytest.raises(RetryError):
        create_with_retries(client, max_attempts=2, sleep=lambda s: None, model="x")

    assert client.messages.calls == 2


def test_forwards_kwargs_to_create():
    client = FakeClient(["ok"])

    create_with_retries(client, sleep=lambda s: None, model="claude-sonnet-5", max_tokens=99)

    assert client.messages.received_kwargs == [{"model": "claude-sonnet-5", "max_tokens": 99}]
