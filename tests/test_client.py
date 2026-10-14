"""Tests for the eSMS Python SDK, using a stubbed transport."""

import json

import pytest

from esms import (
    AuthenticationError,
    Esms,
    EsmsConnectionError,
    InsufficientBalanceError,
    NotFoundError,
)


class FakeResp:
    def __init__(self, status, body, headers=None):
        self.status = status
        self._body = json.dumps(body).encode()
        self.headers = headers or {}

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def make_client(monkeypatch, handler):
    """Patch urlopen so no real network is used. `handler(url, data, method)`
    returns (status, body); non-2xx raises HTTPError like urllib does."""
    import urllib.error
    import urllib.request

    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["headers"] = {k.lower(): v for k, v in req.header_items()}
        captured["data"] = json.loads(req.data.decode()) if req.data else None
        status, body = handler(req.full_url, captured["data"], req.get_method())
        if status >= 400:
            raise urllib.error.HTTPError(
                req.full_url, status, "err", {"X-Request-Id": "req_1"},
                _BytesFile(json.dumps(body).encode()),
            )
        return FakeResp(status, body)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    client = Esms(api_key="esms_test_abc", max_retries=0)
    return client, captured


class _BytesFile:
    def __init__(self, data):
        self._data = data

    def read(self):
        return self._data

    def close(self):
        pass


def test_requires_api_key():
    with pytest.raises(ValueError):
        Esms(api_key="")


def test_default_base_url():
    assert Esms(api_key="k").base_url == "https://sms.esmsafrica.io/api"


def test_send_message(monkeypatch):
    def handler(url, data, method):
        assert url == "https://sms.esmsafrica.io/api/messages/send"
        assert method == "POST"
        assert data == {"to": "+256700000000", "text": "Hi"}
        return 200, {
            "id": "msg_1",
            "status": "submitted",
            "segments": 1,
            "cost": 0.4,
            "cost_currency": "KES",
            "route_cost": 35,
            "route_currency": "UGX",
            "route": "ESMS_UG",
            "balance_after": 9.6,
            "scheduled_at": None,
        }

    client, cap = make_client(monkeypatch, handler)
    res = client.messages.send(to="+256700000000", text="Hi")
    assert res.id == "msg_1"
    assert res.status == "submitted"
    assert res.cost_currency == "KES"
    assert res.balance_after == 9.6
    assert cap["headers"]["authorization"] == "Bearer esms_test_abc"


def test_schedule_sets_mode(monkeypatch):
    def handler(url, data, method):
        assert data["schedule_mode"] == "scheduled"
        # A naive datetime is sent as UTC (the API rejects times without a zone).
        assert data["scheduled_at"] == "2026-08-01T09:00:00+00:00"
        return 200, {"id": "m", "status": "scheduled", "scheduled_at": data["scheduled_at"]}

    client, _ = make_client(monkeypatch, handler)
    from datetime import datetime

    res = client.messages.schedule(
        to="+256700000000", text="x", scheduled_at=datetime(2026, 8, 1, 9, 0, 0)
    )
    assert res.status == "scheduled"


def test_auth_error(monkeypatch):
    client, _ = make_client(monkeypatch, lambda *a: (401, {"detail": "Not authenticated"}))
    with pytest.raises(AuthenticationError):
        client.messages.list()


def test_insufficient_balance(monkeypatch):
    body = {
        "detail": {
            "code": "insufficient_balance",
            "message": "Balance KES 1 < cost KES 5",
            "balance": 1,
            "cost": 5,
            "currency": "KES",
        }
    }
    client, _ = make_client(monkeypatch, lambda *a: (402, body))
    with pytest.raises(InsufficientBalanceError) as exc:
        client.messages.send(to="+256700000000", text="x")
    assert exc.value.balance == 1
    assert exc.value.cost == 5
    assert exc.value.currency == "KES"


def test_not_found(monkeypatch):
    client, _ = make_client(monkeypatch, lambda *a: (404, {"detail": "Message not found"}))
    with pytest.raises(NotFoundError):
        client.messages.get("nope")


def test_connection_error(monkeypatch):
    import urllib.request

    def boom(req, timeout=None):
        raise OSError("network down")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    client = Esms(api_key="k", max_retries=0)
    with pytest.raises(EsmsConnectionError):
        client.balance.get()


def test_routes(monkeypatch):
    body = [
        {
            "code": "ESMS_UG",
            "name": "Uganda",
            "country_code": "UG",
            "country_name": "Uganda",
            "currency": "UGX",
            "price_per_segment": 35,
            "sender_id_default": "eSMSAfrica",
            "is_active": True,
        }
    ]
    client, _ = make_client(monkeypatch, lambda *a: (200, body))
    routes = client.routes.list()
    assert routes[0].code == "ESMS_UG"
    assert routes[0].price_per_segment == 35
    assert routes[0].is_active is True


def test_send_has_idempotency_key(monkeypatch):
    client, cap = make_client(monkeypatch, lambda u, d, m: (200, {"id": "m", "status": "submitted"}))
    client.messages.send(to="+256700000000", text="Hi")
    assert len(cap["headers"]["idempotency-key"]) == 36


def test_naive_datetime_is_utc(monkeypatch):
    from datetime import datetime

    client, cap = make_client(monkeypatch, lambda u, d, m: (200, {"id": "m", "status": "scheduled"}))
    client.messages.schedule(to="+256700000000", text="x", scheduled_at=datetime(2026, 8, 1, 9, 0))
    assert cap["data"]["scheduled_at"] == "2026-08-01T09:00:00+00:00"


def test_error_envelope_and_validation_list(monkeypatch):
    from esms import InvalidRequestError, RateLimitError

    body = {
        "error": {"code": "validation_error", "message": "Request validation failed", "request_id": "r1"},
        "detail": [{"loc": ["body", "to"], "msg": "Field required", "type": "missing"}],
    }
    client, _ = make_client(monkeypatch, lambda u, d, m: (422, body))
    with pytest.raises(InvalidRequestError) as ei:
        client.messages.send(to="", text="x")
    assert ei.value.code == "validation_error"
    assert ei.value.message == "Request validation failed: body.to: Field required"

    client, _ = make_client(monkeypatch, lambda u, d, m: (429, {"error": "Rate limit exceeded: 30 per 1 minute"}))
    with pytest.raises(RateLimitError) as ei:
        client.balance.get()
    assert ei.value.message == "Rate limit exceeded: 30 per 1 minute"


def test_insufficient_balance_402_required_available(monkeypatch):
    body = {"detail": {"code": "insufficient_balance", "message": "no", "required": 5, "available": 1}}
    client, _ = make_client(monkeypatch, lambda u, d, m: (402, body))
    with pytest.raises(InsufficientBalanceError) as ei:
        client.messages.retry("m1")
    assert ei.value.balance == 1 and ei.value.cost == 5


def test_post_without_key_not_retried_on_5xx(monkeypatch):
    import esms.client as ec
    from esms import ApiError

    monkeypatch.setattr(ec.time, "sleep", lambda s: None)
    calls = []

    def handler(u, d, m):
        calls.append(u)
        return 500, {"detail": "Internal server error"}

    client, _ = make_client(monkeypatch, handler)
    client._max_retries = 2
    with pytest.raises(ApiError):
        client.messages.retry("m1")
    assert len(calls) == 1
    calls.clear()
    with pytest.raises(ApiError):
        client.messages.send(to="+256700000000", text="x")
    assert len(calls) == 3


def test_retry_and_bulk_results(monkeypatch):
    def handler(u, d, m):
        if u.endswith("/retry"):
            return 200, {"id": "m2", "status": "submitted", "retry_count": 1}
        return 200, {"batch_id": "b1", "total_recipients": 2, "estimated_cost": 1.5, "status": "processing"}

    client, cap = make_client(monkeypatch, handler)
    r = client.messages.retry("m1")
    assert (r.id, r.status, r.retry_count) == ("m2", "submitted", 1)
    b = client.messages.send_bulk(text="hi", recipients=[{"to": "+256700000000"}])
    assert b.batch_id == "b1" and b["batch_id"] == "b1" and b.total_recipients == 2
    assert cap["data"] == {"text": "hi", "recipients": [{"to": "+256700000000"}]}


def test_insufficient_balance_currency_from_live_message(monkeypatch):
    # The live API states the currency only inside the message text.
    client, _ = make_client(monkeypatch, lambda u, d, m: (402, {
        "error": {"code": "insufficient_balance", "message": "x", "request_id": "r"},
        "detail": {"code": "insufficient_balance",
                   "message": "Insufficient balance. Required KES 5.0, available KES 1.0",
                   "required": 5.0, "available": 1.0},
    }))
    with pytest.raises(InsufficientBalanceError) as ei:
        client.messages.send(to="+254711000000", text="x")
    assert ei.value.currency == "KES"
    assert ei.value.balance == 1.0 and ei.value.cost == 5.0


def test_route_null_sender_stays_none(monkeypatch):
    client, _ = make_client(monkeypatch, lambda u, d, m: (200, [{
        "code": "ESMS_UG", "name": "Uganda", "country_code": "UG", "country_name": "Uganda",
        "currency": "UGX", "price_per_segment": 30, "sender_id_default": None, "is_active": True,
        "dial_code": "+256", "region": "East Africa"}]))
    (r,) = client.routes.list()
    assert r.sender_id_default is None
    assert r.dial_code == "+256" and r.region == "East Africa"


def test_send_and_bulk_advanced_options(monkeypatch):
    client, cap = make_client(monkeypatch, lambda u, d, m: (200, {"id": "m", "status": "submitted"}))
    client.messages.send(to="+256700000000", text="x", flash=True, validity_period=60, priority=1)
    assert cap["data"]["flash"] is True and cap["data"]["validity_period"] == 60 and cap["data"]["priority"] == 1
    client.messages.send_bulk(text="x", recipients=[{"to": "+256700000000"}], skip_unavailable=True)
    assert cap["data"]["skip_unavailable"] is True
    assert "flash" not in cap["data"]


def test_non_json_2xx_raises_esms_error(monkeypatch):
    import urllib.request
    from esms import EsmsError

    class HtmlResp(FakeResp):
        def read(self):
            return b"<html>gateway</html>"

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: HtmlResp(200, None))
    client = Esms(api_key="esms_test_abc", max_retries=0)
    with pytest.raises(EsmsError, match="non-JSON"):
        client.balance.get()
