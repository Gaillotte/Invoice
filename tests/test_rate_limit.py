import json

import httplib2
import pytest
from googleapiclient.errors import HttpError

from invoice_manager.config import Config
from invoice_manager.fetcher import fetch
from invoice_manager.gmail import GmailClient, RateLimitError, RETRY_WAITS
from invoice_manager.store import Store


def http_error(status, reason="rateLimitExceeded", message="Quota exceeded for quota metric"):
    body = {"error": {"code": status, "message": message, "errors": [{"reason": reason}]}}
    return HttpError(httplib2.Response({"status": status}), json.dumps(body).encode())


class Request:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def execute(self):
        self.calls += 1
        out = self.outcomes.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


@pytest.fixture
def client():
    sleeps = []
    c = GmailClient(service=object(), sleep=sleeps.append, clock=lambda: 0.0, log=lambda *_: None)
    c.sleeps = sleeps
    return c


def test_retries_then_succeeds(client):
    req = Request([http_error(429), http_error(403), {"ok": True}])
    assert client._execute(req) == {"ok": True}
    assert req.calls == 3
    assert [s for s in client.sleeps if s >= 1] == [RETRY_WAITS[0], RETRY_WAITS[1]]


def test_gives_up_after_retries(client):
    req = Request([http_error(429)] * (len(RETRY_WAITS) + 1))
    with pytest.raises(RateLimitError, match="run 'invoices fetch' again"):
        client._execute(req)


def test_other_errors_are_not_retried(client):
    req = Request([http_error(404, reason="notFound", message="Not Found")])
    with pytest.raises(HttpError):
        client._execute(req)
    assert req.calls == 1
    req = Request([http_error(403, reason="forbidden", message="Forbidden")])
    with pytest.raises(HttpError):
        client._execute(req)


def test_calls_are_paced():
    sleeps, now = [], [0.0]
    c = GmailClient(service=object(), sleep=lambda s: (sleeps.append(s), now.__setitem__(0, now[0] + s)),
                    clock=lambda: now[0], log=lambda *_: None)
    for _ in range(3):
        c._execute(Request([{}]))
    assert len(sleeps) == 2 and all(s > 0 for s in sleeps)


def test_fetch_stops_on_rate_limit(tmp_path):
    from test_fetch import FakeSource, _msg

    class Limited(FakeSource):
        def get_message(self, message_id):
            if message_id == "m2":
                raise RateLimitError("quota")
            return super().get_message(message_id)

    cfg = Config(data_dir=tmp_path)
    store = Store(cfg.db_path)
    src = Limited({"m1": _msg("m1", {"a.xml": b"1"}), "m2": _msg("m2", {"b.xml": b"2"}),
                   "m3": _msg("m3", {"c.xml": b"3"})})
    report = fetch(src, store, cfg, log=lambda *_: None)
    assert report.stopped and len(report.invoices_added) == 1
    assert store.is_processed("m1") and not store.is_processed("m2") and not store.is_processed("m3")
