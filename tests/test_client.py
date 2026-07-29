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
        assert data["scheduled_at"] == "2026-08-01T09:00:00"
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
    client, _ = make_client(monkeypatch, lambda *a: (422, body))
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
