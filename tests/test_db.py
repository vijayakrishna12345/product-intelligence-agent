import pytest
from httpx import RemoteProtocolError

from pia.db import is_transient, retry_call


def test_is_transient_walks_cause():
    inner = RemoteProtocolError("Server disconnected")
    outer = RuntimeError("wrapped")
    outer.__cause__ = inner
    assert is_transient(outer)
    assert not is_transient(ValueError("nope"))


def test_retry_call_succeeds_after_disconnect(monkeypatch):
    monkeypatch.setattr("pia.db.time.sleep", lambda _delay: None)
    calls = {"n": 0}

    def boom():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RemoteProtocolError("Server disconnected")
        return "ok"

    assert retry_call(boom) == "ok"
    assert calls["n"] == 3


def test_retry_call_gives_up(monkeypatch):
    monkeypatch.setattr("pia.db.time.sleep", lambda _delay: None)

    def boom():
        raise RemoteProtocolError("Server disconnected")

    with pytest.raises(RemoteProtocolError):
        retry_call(boom)
