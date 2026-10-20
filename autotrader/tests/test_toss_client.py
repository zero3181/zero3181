import pytest

from autotrader.broker.toss import TossApiError, TossClient, TossCredentials


class FakeResp:
    def __init__(self, status, body=None):
        self.status_code = status
        self._body = body or {}
        self.text = str(self._body)

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0
        self.token_calls = 0

    def post(self, url, **kw):
        self.token_calls += 1
        return FakeResp(200, {"access_token": "tok", "expires_in": 3600})

    def request(self, method, url, **kw):
        self.calls += 1
        return self.responses.pop(0)


def client(session):
    return TossClient(TossCredentials("id", "secret"), "acc", session=session, min_interval_sec=0)


def test_retries_on_429(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    s = FakeSession([FakeResp(429), FakeResp(200, {"x": 1})])
    assert client(s)._request("GET", "/p") == {"x": 1}
    assert s.calls == 2


def test_no_retry_when_disabled(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    s = FakeSession([FakeResp(503), FakeResp(200)])
    with pytest.raises(TossApiError):
        client(s)._request("POST", "/order", retry=False)
    assert s.calls == 1


def test_no_retry_on_400():
    s = FakeSession([FakeResp(400), FakeResp(200)])
    with pytest.raises(TossApiError):
        client(s)._request("GET", "/p")
    assert s.calls == 1


def test_token_cached():
    s = FakeSession([FakeResp(200), FakeResp(200)])
    c = client(s)
    c._request("GET", "/a")
    c._request("GET", "/b")
    assert s.token_calls == 1


def test_unimplemented_endpoints_fail_loudly():
    c = client(FakeSession([]))
    with pytest.raises(NotImplementedError):
        c.get_price("005930")
