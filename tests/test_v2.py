"""v2 surface: personalised batch, campaigns, imports, contacts, groups, templates."""

import hashlib
import hmac
import json
import urllib.request

import pytest

import esms.client as esms_client

from esms import Esms


class Resp:
    def __init__(self, status, body):
        self.status = status
        self._b = b"" if body is None else json.dumps(body).encode()
        self.headers = {}

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def calls(monkeypatch):
    seen = []

    def fake(req, timeout=None):
        seen.append({"url": req.full_url, "method": req.get_method(), "data": req.data,
                     "headers": {k.lower(): v for k, v in req.header_items()}})
        return Resp(204 if req.get_method() == "DELETE" and "/contacts/" in req.full_url else 200,
                    None if req.get_method() == "DELETE" and "/contacts/" in req.full_url else {"id": 1, "ok": True})

    monkeypatch.setattr(esms_client, "_urlopen", fake)
    return seen


def client():
    return Esms(api_key="esms_test_abc", max_retries=0)


def test_send_batch_body_and_idempotency(calls):
    client().messages.send_batch(
        template="Hi {first_name}, owe {amount}",
        recipients=[{"to": "+256772123456", "name": "Ada", "vars": {"amount": "1,500"}}],
        sender_id="ACME", schedule={"mode": "scheduled", "at": "2026-11-01T09:00", "timezone": "Africa/Kampala"},
        throttle_per_minute=100)
    c = calls[0]
    assert c["url"].endswith("/api/messages/batch") and c["method"] == "POST"
    assert len(c["headers"]["idempotency-key"]) == 36
    body = json.loads(c["data"])
    assert body["recipients"][0]["vars"]["amount"] == "1,500" and body["throttle_per_minute"] == 100
    assert "idempotency_key" not in body


def test_send_batch_keeps_caller_key(calls):
    client().messages.send_batch(messages=[{"to": "+1", "text": "x"}], idempotency_key="k-1")
    assert calls[0]["headers"]["idempotency-key"] == "k-1"


def test_campaign_paths(calls):
    e = client()
    e.campaigns.create(name="Dues", text="Hi", audience=[{"type": "group", "id": 2}], idempotency_key="c-1")
    e.campaigns.prepare(3)
    e.campaigns.review(3)
    e.campaigns.launch(3)
    e.campaigns.approve(3, "ok")
    e.campaigns.retry_failed(3)
    e.campaigns.recipients(3, status="failed", page=1)
    got = [f'{c["method"]} {c["url"].split("/api", 1)[1]}' for c in calls]
    assert got == ["POST /campaigns", "POST /campaigns/3/prepare", "GET /campaigns/3/review", "POST /campaigns/3/launch",
                   "POST /campaigns/3/approve", "POST /campaigns/3/retry-failed",
                   "GET /campaigns/3/recipients?status=failed&page=1"]
    assert calls[0]["headers"]["idempotency-key"] == "c-1"
    assert json.loads(calls[4]["data"]) == {"note": "ok"}


def test_import_upload_multipart(calls, tmp_path):
    p = tmp_path / "debtors.csv"
    p.write_bytes(b"phone\n0772123456\n")
    client().imports.upload(str(p), default_country="UG")
    c = calls[0]
    assert c["headers"]["content-type"].startswith("multipart/form-data; boundary=")
    assert b'name="file"; filename="debtors.csv"' in c["data"] and b"0772123456" in c["data"]
    assert b'name="default_country"' in c["data"] and b"UG" in c["data"]


def test_import_process_and_save(calls):
    e = client()
    e.imports.process("imp_1", mapping={"phone": "Mobile", "fields": {"Amount Due": "amount"}}, default_country="UG")
    e.imports.save_to_group("imp_1", name="Debtors")
    assert json.loads(calls[0]["data"]) == {"mapping": {"phone": "Mobile", "fields": {"Amount Due": "amount"}},
                                            "default_country": "UG"}
    assert calls[1]["url"].endswith("/imports/imp_1/save-to-group")


def test_contacts_groups_templates(calls):
    e = client()
    e.contacts.get("+256772123456")
    e.contacts.upsert(phone="+256772123456", group_ids=[1])
    assert e.contacts.delete("+256772123456") is None
    e.groups.add_contacts(5, [{"phone": "0772123456"}], default_country="UG")
    e.templates.use_starter("payment-reminder")
    assert "/contacts/%2B256772123456" in calls[0]["url"]
    assert json.loads(calls[1]["data"]) == {"phone": "+256772123456", "group_ids": [1]}
    assert calls[2]["method"] == "DELETE"
    assert json.loads(calls[3]["data"])["default_country"] == "UG"
    assert calls[4]["url"].endswith("/templates/starter-pack/payment-reminder")


def test_campaign_completed_webhook_verifies():
    body = json.dumps({"event": "campaign.completed", "campaign_id": 1})
    sig = "sha256=" + hmac.new(b"whsec_x", body.encode(), hashlib.sha256).hexdigest()
    assert Esms.verify_webhook(body, sig, "whsec_x")
