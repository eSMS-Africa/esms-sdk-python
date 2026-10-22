# esms-sms

Official Python SDK for the [eSMS Africa](https://esmsafrica.io) SMS API.

Send SMS across Africa, track delivery, schedule messages, run managed OTP verification, and check your balance. Fully typed, zero required dependencies (uses the standard library).

## Install

```bash
pip install esms-sms
```

Requires Python 3.8+.

## Quick start

```python
from esms import Esms

esms = Esms(api_key="esms_live_...")

res = esms.messages.send(
    to="+256700000000",
    text="Your verification code is 123456",
    sender_id="eSMSAfrica",  # optional - falls back to the route default
)

print(res.id, res.status)  # "...", "submitted"
```

Get an API key from the eSMS dashboard under **Developers → API Keys**. Live keys look like `esms_live_…`; test keys look like `esms_test_…`.

## Sending

```python
# Auto-detects the route (country) from the number.
esms.messages.send(to="+254711000000", text="Hi from Kenya")

# Or pin a route explicitly.
esms.messages.send(to="+256700000000", text="Hi", route="ESMS_UG")

# Schedule for later (5 minutes to 7 days out).
from datetime import datetime, timedelta, timezone
esms.messages.schedule(
    to="+256700000000",
    text="Reminder",
    scheduled_at=datetime.now(timezone.utc) + timedelta(hours=1),  # naive datetimes are treated as UTC
)

# Price a message before sending (no charge, no delivery).
quote = esms.messages.rate(to="+256700000000", text="Hi")

# Send to many numbers at once (inline recipients and/or contact lists).
batch = esms.messages.send_bulk(
    recipients=[{"to": "+256700000000"}, {"to": "+254711000000"}],
    text="Hello from eSMS",
)
summary = esms.messages.get_batch(batch.batch_id)
```

`messages.send` attaches a random `Idempotency-Key` to every call so a retried request can never send or charge twice. Pass your own `idempotency_key=` to make retries safe across process restarts too.

Advanced options: `flash=True` (class-0 SMS shown on screen), `validity_period` (minutes, 1-4320), `priority` (0-3) and `binary={"data": hex, "udh": hex}` (pass `text=""`). `send_bulk` also takes `flash`, `validity_period`, `priority` and `skip_unavailable=True` (drop unreachable recipients, uncharged, instead of rejecting the whole batch).

## Personalised bulk + campaigns

Requires SDK 1.2.0 or later.

```python
# One call: a template with per-recipient merge fields. Invalid, duplicate and
# opted-out numbers come back in "rejected" and are never charged.
batch = esms.messages.send_batch(
    template="Hi {first_name|there}, your balance is UGX {balance}. Pay by {due_date}.",
    recipients=[
        {"to": "+256772123456", "name": "Ada Obi", "vars": {"balance": "1,500", "due_date": "1 Nov"}},
        {"to": "0701234567", "vars": {"balance": "200", "due_date": "1 Nov"}},
    ],
    default_country="UG",
    sender_id="ACMEBANK",
    schedule={"mode": "scheduled", "at": "2026-11-01T09:00", "timezone": "Africa/Kampala"},
)
status = esms.messages.get_batch(batch["batch_id"])

# Big lists: upload a CSV / Excel file, map columns, then run a campaign.
imp = esms.imports.upload("debtors.xlsx", default_country="UG")
job = esms.imports.process(imp["id"], mapping={"phone": "Mobile", "name": "Name", "fields": {"Amount Due": "amount"}})
# poll esms.jobs.get(job["job_id"]) until status is "done"
c = esms.campaigns.create(name="October dues", text="Hi {first_name}, you owe {amount|0}.",
                          audience=[{"type": "import", "id": imp["id"]}], idempotency_key="october-dues")
esms.campaigns.prepare(c["id"])            # exact cost per country + checks
if esms.campaigns.review(c["id"])["review"]["can_launch"]:
    esms.campaigns.launch(c["id"])
report = esms.campaigns.report(c["id"])
```

Also: `campaigns.pause/resume/cancel/retry_failed/duplicate/recipients/runs`, `contacts`, `groups`, `templates` (with `starter_pack()` and `use_starter(key)`).
The signed `campaign.completed` webhook uses the same `Esms.verify_webhook` check.

## Delivery status

```python
msg = esms.messages.get(res.id)
print(msg.status)    # queued | submitted | delivered | failed | ...
for event in msg.timeline:
    print(event.at, event.event, event.detail)

# List recent messages (filters: status, to, batch_id, date_from, date_to, environment)
page = esms.messages.list(limit=20, status="delivered")
print(page.total, len(page.messages))

# Status of up to 100 messages in one call
statuses = esms.messages.statuses([res.id])["messages"]

# Retry a failed one -> RetryResult(id, status, retry_count)
esms.messages.retry(res.id)
```

## Balance & routes

```python
bal = esms.balance.get()
print(f"{bal.currency} {bal.balance} (~{bal.sms_estimate} SMS left)")

for r in esms.routes.list():
    print(r.code, r.country_name, f"{r.currency} {r.price_per_segment}/segment")
```

## Verify (managed OTP)

```python
v = esms.verify.start("+256700000000")  # or start(to, app_id="...")
# ...user types the code...
check = esms.verify.check("123456", verification_id=v["verification_id"])
if check["status"] == "approved":
    pass  # verified
```

Also available: `verify.get`, `verify.resend`, `verify.cancel`, `verify.list`, and Verify Apps (`list_apps`, `create_app`, `get_app`, `update_app`, `delete_app`, `app_stats`).

## Opt-outs

```python
esms.opt_outs.add("+256700000000")
opted_out = esms.opt_outs.list()
esms.opt_outs.remove("+256700000000")
```

## Webhooks

Delivery-report webhooks are signed with HMAC-SHA256 in the `X-Webhook-Signature` header (`sha256=<hex>`). Verify against the exact raw body:

```python
ok = Esms.verify_webhook(request.body, request.headers.get("X-Webhook-Signature"), webhook_secret)
```

## Errors

Every failure is an `EsmsError`. Catch specific subclasses to branch:

```python
from esms import (
    Esms,
    InsufficientBalanceError,
    AuthenticationError,
    EsmsError,
)

try:
    esms.messages.send(to="+256700000000", text="Hi")
except InsufficientBalanceError as e:
    print(f"Top up needed: have {e.balance}, need {e.cost} {e.currency}")
except AuthenticationError:
    print("Check your API key.")
except EsmsError as e:
    print(f"{e.status} {e.code}: {e.message}")
```

| Class | When |
|-------|------|
| `AuthenticationError` | 401 - key missing or invalid |
| `PermissionDenied` | 403 - not allowed |
| `NotFoundError` | 404 - no such message |
| `InvalidRequestError` | 400 / 409 / 413 / 422 - bad request |
| `InsufficientBalanceError` | 402 - not enough credit (`.balance`, `.cost`, `.currency`) |
| `RateLimitError` | 429 - slow down |
| `ApiError` | 5xx - server error |
| `EsmsConnectionError` | network failure or timeout |

## Configuration

```python
Esms(
    api_key="esms_live_...",
    base_url="https://sms.esmsafrica.io/api",  # default
    timeout=30.0,     # seconds, default 30
    max_retries=2,    # transient failures (network, 429, 5xx) with backoff
)
```

Requests authenticate with `Authorization: Bearer <key>`. Non-idempotent POSTs (bulk sends, retries, OTP resends) are only retried on 429, never after a 5xx or network error, so they cannot run twice.

## License

MIT © eSMS Africa
