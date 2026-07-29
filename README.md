# esms-sms

Official Python SDK for the [eSMS Africa](https://esmsafrica.io) SMS API.

Send SMS across 14+ African countries, track delivery, schedule messages, and check your balance. Fully typed, zero required dependencies (uses the standard library).

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
    sender_id="eSMSAfrica",  # optional — falls back to the route default
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
    scheduled_at=datetime.now(timezone.utc) + timedelta(hours=1),
)
```

## Delivery status

```python
msg = esms.messages.get(res.id)
print(msg.status)    # queued | submitted | delivered | failed | ...
for event in msg.timeline:
    print(event.at, event.event, event.detail)

# List recent messages
page = esms.messages.list(limit=20, status="delivered")
print(page.total, len(page.messages))

# Retry a failed one
esms.messages.retry(res.id)
```

## Balance & routes

```python
bal = esms.balance.get()
print(f"{bal.currency} {bal.balance} (~{bal.sms_estimate} SMS left)")

for r in esms.routes.list():
    print(r.code, r.country_name, f"{r.currency} {r.price_per_segment}/segment")
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
| `AuthenticationError` | 401 — key missing or invalid |
| `PermissionDenied` | 403 — not allowed |
| `NotFoundError` | 404 — no such message |
| `InvalidRequestError` | 400 / 422 — bad request |
| `InsufficientBalanceError` | 422 — not enough credit (`.balance`, `.cost`, `.currency`) |
| `RateLimitError` | 429 — slow down |
| `ApiError` | 5xx — server error |
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

## License

MIT © eSMS Africa
