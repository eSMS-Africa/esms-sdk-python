"""The eSMS Africa SMS client."""

from __future__ import annotations

import hashlib
import hmac
import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from .errors import EsmsConnectionError, EsmsError, error_from_response
from .models import (
    Balance,
    BulkSendResult,
    Message,
    MessageList,
    MessageSummary,
    RetryResult,
    Route,
    SendResult,
)

__version__ = "1.1.0"

DEFAULT_BASE_URL = "https://sms.esmsafrica.io/api"

# Methods that are safe to repeat after a 5xx or network error. A POST is only
# retried then when it carries an Idempotency-Key.
_IDEMPOTENT_METHODS = {"GET", "HEAD", "PUT", "DELETE", "OPTIONS"}


class Esms:
    """Client for the eSMS Africa SMS API.

    Example::

        from esms import Esms

        esms = Esms(api_key="esms_live_...")
        res = esms.messages.send(to="+256700000000", text="Hello!")
        print(res.id, res.status)
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        if not api_key:
            raise ValueError(
                "An API key is required. Create one in the eSMS dashboard "
                "under Developers -> API Keys."
            )
        self._api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries

        self.messages = MessagesResource(self)
        self.balance = BalanceResource(self)
        self.routes = RoutesResource(self)
        self.verify = VerifyResource(self)
        self.opt_outs = OptOutsResource(self)

    @staticmethod
    def verify_webhook(raw_body: Union[str, bytes], signature: Optional[str], secret: str) -> bool:
        """Verify an incoming webhook's HMAC-SHA256 signature (constant-time).

        raw_body   the exact raw request body (str or bytes), not re-serialized.
        signature  the ``X-Webhook-Signature`` header value (e.g. ``sha256=...``).
        secret     your webhook signing secret.
        """
        if not signature or not secret:
            return False
        body = raw_body.encode() if isinstance(raw_body, str) else raw_body
        expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)

    # ── transport ────────────────────────────────────────────────────
    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        url = self.base_url + path
        if params:
            clean = {k: v for k, v in params.items() if v is not None}
            if clean:
                url += "?" + urllib.parse.urlencode(clean)

        data = None
        req_headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
            "User-Agent": f"esms-python/{__version__}",
        }
        if headers:
            req_headers.update({k: v for k, v in headers.items() if v is not None})
        headers = req_headers
        if body is not None:
            clean_body = {k: v for k, v in body.items() if v is not None}
            data = json.dumps(clean_body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        retry_safe = method.upper() in _IDEMPOTENT_METHODS or any(
            k.lower() == "idempotency-key" for k in headers
        )
        last_exc: Optional[BaseException] = None
        for attempt in range(self._max_retries + 1):
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                    raw = resp.read().decode("utf-8", "replace")
                    status = resp.status
                    rid = resp.headers.get("X-Request-Id") if resp.headers else None
                if not raw:
                    return None
                try:
                    return json.loads(raw)
                except ValueError:
                    # A 2xx that is not JSON (e.g. an HTML page from a proxy).
                    raise EsmsError(
                        f"Unexpected non-JSON response (HTTP {status})",
                        status=status, detail=raw[:500], request_id=rid,
                    ) from None
            except urllib.error.HTTPError as e:
                raw = e.read().decode("utf-8", "replace")
                parsed = _safe_json(raw)
                request_id = e.headers.get("X-Request-Id") if e.headers else None
                if (e.code == 429 or (e.code >= 500 and retry_safe)) and attempt < self._max_retries:
                    last_exc = error_from_response(e.code, parsed, request_id)
                    time.sleep(_backoff(attempt, e.headers.get("Retry-After") if e.headers else None))
                    continue
                raise error_from_response(e.code, parsed, request_id) from None
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                # The request may already have been processed; only retry when safe.
                last_exc = e
                if retry_safe and attempt < self._max_retries:
                    time.sleep(_backoff(attempt, None))
                    continue
                raise EsmsConnectionError(
                    f"Could not reach the eSMS API: {e}"
                ) from e
        if isinstance(last_exc, EsmsError):
            raise last_exc
        raise EsmsConnectionError("Request failed")


class MessagesResource:
    def __init__(self, client: Esms) -> None:
        self._c = client

    def send(
        self,
        *,
        to: str,
        text: str,
        sender_id: Optional[str] = None,
        route: Optional[str] = None,
        schedule_mode: Optional[str] = None,
        scheduled_at: Optional[Union[str, datetime]] = None,
        international: Optional[bool] = None,
        idempotency_key: Optional[str] = None,
        flash: Optional[bool] = None,
        validity_period: Optional[int] = None,
        priority: Optional[int] = None,
        binary: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Send a single SMS.

        ``idempotency_key`` makes the send safe to retry (a repeat returns the
        original result). A random key is generated per call when omitted.

        Advanced options: ``flash`` (class-0 SMS), ``validity_period`` (minutes,
        1-4320), ``priority`` (0-3) and ``binary`` (``{"data": hex, "udh": hex,
        "data_coding": 4}``, pass ``text=""``).
        """
        body = {
            "to": to,
            "text": text,
            "sender_id": sender_id,
            "route": route,
            "schedule_mode": schedule_mode,
            "scheduled_at": _iso(scheduled_at),
            "international": international,
            "flash": flash,
            "validity_period": validity_period,
            "priority": priority,
            "binary": {k: v for k, v in binary.items() if v is not None} if binary else None,
        }
        headers = {"Idempotency-Key": idempotency_key or str(uuid.uuid4())}
        return SendResult.from_dict(
            self._c._request("POST", "/messages/send", body=body, headers=headers)
        )

    def schedule(
        self,
        *,
        to: str,
        text: str,
        scheduled_at: Union[str, datetime],
        sender_id: Optional[str] = None,
        route: Optional[str] = None,
        international: Optional[bool] = None,
        idempotency_key: Optional[str] = None,
    ) -> SendResult:
        """Schedule an SMS for later delivery (5 minutes to 7 days out).

        A naive ``datetime`` is treated as UTC."""
        return self.send(
            to=to,
            text=text,
            sender_id=sender_id,
            route=route,
            schedule_mode="scheduled",
            scheduled_at=scheduled_at,
            international=international,
            idempotency_key=idempotency_key,
        )

    def list(
        self,
        *,
        page: int = 0,
        limit: int = 20,
        status: Optional[str] = None,
        to: Optional[str] = None,
        batch_id: Optional[str] = None,
        date_from: Optional[Union[str, datetime]] = None,
        date_to: Optional[Union[str, datetime]] = None,
        environment: Optional[str] = None,
    ) -> MessageList:
        """List messages, most recent first.

        ``environment`` is ``live`` (default), ``test`` or ``all``. Listed
        ``text`` is truncated to 100 characters; use :meth:`get` for the full body.
        """
        data = self._c._request(
            "GET",
            "/messages",
            params={
                "page": page,
                "limit": limit,
                "status": status,
                "to": to,
                "batch_id": batch_id,
                "date_from": _iso(date_from),
                "date_to": _iso(date_to),
                "environment": environment,
            },
        )
        return MessageList(
            messages=[MessageSummary.from_dict(m) for m in data.get("messages", [])],
            total=int(data.get("total", 0)),
            page=int(data.get("page", 0)),
            limit=int(data.get("limit", 0)),
        )

    def get(self, message_id: str) -> Message:
        """Fetch a single message with its full delivery timeline."""
        data = self._c._request(
            "GET", f"/messages/{_q(message_id)}"
        )
        return Message.from_dict(data)

    def retry(self, message_id: str) -> RetryResult:
        """Retry a failed, undelivered, rejected, expired or unknown message."""
        data = self._c._request(
            "POST", f"/messages/{_q(message_id)}/retry"
        )
        return RetryResult.from_dict(data)

    def send_bulk(
        self,
        *,
        text: str,
        contact_list_ids: Optional[List[int]] = None,
        recipients: Optional[List[Dict[str, Any]]] = None,
        sender_id: Optional[str] = None,
        route: Optional[str] = None,
        schedule_mode: Optional[str] = None,
        scheduled_at: Optional[Union[str, datetime]] = None,
        drip_rate: Optional[int] = None,
        international: Optional[bool] = None,
        flash: Optional[bool] = None,
        validity_period: Optional[int] = None,
        priority: Optional[int] = None,
        skip_unavailable: Optional[bool] = None,
        idempotency_key: Optional[str] = None,
    ) -> BulkSendResult:
        """Send one message to many recipients.

        Pass ``contact_list_ids`` and/or inline ``recipients``
        (``[{"to": "+2567...", "name": ..., "vars": {...}}]``). ``schedule_mode``
        is ``now`` (default), ``scheduled`` (contact lists only) or ``drip``
        (with ``drip_rate`` messages per minute). ``skip_unavailable`` drops
        (uncharged) recipients that cannot be reached instead of rejecting the
        request. Track it with :meth:`get_batch`. ``idempotency_key`` (one is
        generated when omitted) makes retries safe: a repeat returns the
        original batch instead of sending and charging it again.
        """
        data = self._c._request(
            "POST",
            "/messages/send-bulk",
            headers={"Idempotency-Key": idempotency_key or str(uuid.uuid4())},
            body={
                "contact_list_ids": contact_list_ids,
                "recipients": recipients,
                "text": text,
                "sender_id": sender_id,
                "route": route,
                "schedule_mode": schedule_mode,
                "scheduled_at": _iso(scheduled_at),
                "drip_rate": drip_rate,
                "international": international,
                "flash": flash,
                "validity_period": validity_period,
                "priority": priority,
                "skip_unavailable": skip_unavailable,
            },
        )
        return BulkSendResult.from_dict(data)

    def cancel(self, message_id: str) -> Dict[str, Any]:
        """Cancel a scheduled message before it is sent; the charge is refunded."""
        return self._c._request("POST", f"/messages/{_q(message_id)}/cancel")

    def cancel_batch(self, batch_id: str) -> Dict[str, Any]:
        """Cancel a scheduled bulk batch before its send time; the charge is refunded."""
        return self._c._request("POST", f"/messages/batch/{_q(batch_id)}/cancel")

    def get_batch(self, batch_id: str, *, page: int = 0, limit: int = 50) -> Dict[str, Any]:
        """Aggregate status of a bulk batch plus a page of its messages."""
        return self._c._request(
            "GET",
            f"/messages/batch/{_q(batch_id)}",
            params={"page": page, "limit": limit},
        )

    def statuses(self, message_ids: List[str]) -> Dict[str, Any]:
        """Delivery status for up to 100 messages in one call (``{"messages": [...]}``)."""
        return self._c._request(
            "GET", "/messages/status", params={"ids": ",".join(message_ids)}
        )

    def rate(
        self,
        *,
        to: Union[str, List[str]],
        text: str,
        route: Optional[str] = None,
        international: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Price a message before sending - no charge, no delivery."""
        return self._c._request(
            "POST",
            "/messages/rate",
            body={"to": to, "text": text, "route": route, "international": international},
        )

    def validate(self, phone: Union[str, List[str]]) -> Dict[str, Any]:
        """Validate numbers offline (format, line type, carrier) - no charge.

        A single number returns one result; a list returns
        ``{"count", "valid", "invalid", "mobile", "results"}``."""
        return self._c._request("POST", "/messages/validate", body={"phone": phone})


class BalanceResource:
    def __init__(self, client: Esms) -> None:
        self._c = client

    def get(self) -> Balance:
        """Get the current account balance and an SMS estimate."""
        d = self._c._request("GET", "/balance")
        return Balance(
            balance=float(d.get("balance", 0) or 0),
            currency=str(d.get("currency", "")),
            sms_estimate=d.get("sms_estimate"),
        )


class RoutesResource:
    def __init__(self, client: Esms) -> None:
        self._c = client

    def list(self) -> List[Route]:
        """List all active routes (one per country you can reach)."""
        data = self._c._request("GET", "/routes")
        return [Route.from_dict(r) for r in (data or [])]


class VerifyResource:
    """Managed OTP verification - we generate, send, and check the code."""

    def __init__(self, client: Esms) -> None:
        self._c = client

    def start(self, to: str, *, app_id: Optional[str] = None, sender_id: Optional[str] = None,
              code_length: Optional[int] = None, expiry_seconds: Optional[int] = None,
              template: Optional[str] = None, idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        """Send a verification code to a phone number.

        Pass ``app_id`` to use a Verify App's brand/template/policy.
        ``idempotency_key`` makes retries safe (a repeat returns the original);
        a random key is generated per call when omitted."""
        body = {"to": to, "app_id": app_id, "sender_id": sender_id, "code_length": code_length,
                "expiry_seconds": expiry_seconds, "template": template}
        headers = {"Idempotency-Key": idempotency_key or str(uuid.uuid4())}
        return self._c._request("POST", "/verify/start",
                                body={k: v for k, v in body.items() if v is not None}, headers=headers)

    def check(self, code: str, *, verification_id: Optional[str] = None, to: Optional[str] = None) -> Dict[str, Any]:
        """Check a code the user entered. Returns ``{"status": "approved" | "pending" | ...}``."""
        body = {"code": code, "verification_id": verification_id, "to": to}
        return self._c._request("POST", "/verify/check", body={k: v for k, v in body.items() if v is not None})

    def get(self, verification_id: str) -> Dict[str, Any]:
        """Fetch a verification's status without consuming an attempt."""
        return self._c._request("GET", f"/verify/{_q(verification_id)}")

    def resend(self, verification_id: str) -> Dict[str, Any]:
        """Send a fresh code for the same verification."""
        return self._c._request("POST", f"/verify/{_q(verification_id)}/resend")

    def cancel(self, verification_id: str) -> Dict[str, Any]:
        """Void an in-flight verification."""
        return self._c._request("POST", f"/verify/{_q(verification_id)}/cancel")

    def list(self, *, status: Optional[str] = None, app_id: Optional[str] = None,
             to: Optional[str] = None, page: int = 0, limit: int = 20) -> Dict[str, Any]:
        """List your verifications (most recent first)."""
        params = {"status": status, "app_id": app_id, "to": to, "page": page, "limit": limit}
        return self._c._request("GET", "/verify", params={k: v for k, v in params.items() if v is not None})

    # ---- Verify Apps ----
    def list_apps(self) -> Dict[str, Any]:
        """List your Verify Apps."""
        return self._c._request("GET", "/verify/apps")

    def create_app(self, **fields: Any) -> Dict[str, Any]:
        """Create a Verify App (name, sender_id, template, code_length, expiry_seconds,
        max_attempts, allowed_countries, locale, enabled)."""
        return self._c._request("POST", "/verify/apps", body={k: v for k, v in fields.items() if v is not None})

    def get_app(self, app_id: str) -> Dict[str, Any]:
        return self._c._request("GET", f"/verify/apps/{_q(app_id)}")

    def update_app(self, app_id: str, **fields: Any) -> Dict[str, Any]:
        """Update a Verify App (full replace - send all fields; name is required)."""
        return self._c._request("PATCH", f"/verify/apps/{_q(app_id)}", body={k: v for k, v in fields.items() if v is not None})

    def delete_app(self, app_id: str) -> None:
        self._c._request("DELETE", f"/verify/apps/{_q(app_id)}")

    def app_stats(self, app_id: str, *, days: int = 30) -> Dict[str, Any]:
        """Per-app verification stats (starts / success rate)."""
        return self._c._request("GET", f"/verify/apps/{_q(app_id)}/stats", params={"days": days})


class OptOutsResource:
    """Manage the opt-out (STOP / DND) list."""

    def __init__(self, client: Esms) -> None:
        self._c = client

    def list(self, *, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """List numbers that have opted out of your messages (default 200, max 1000)."""
        return (self._c._request("GET", "/opt-outs", params={"limit": limit}) or {}).get("opt_outs", [])

    def add(self, phone: str) -> Dict[str, Any]:
        """Manually add a number to your opt-out list."""
        return self._c._request("POST", "/opt-outs", body={"phone": phone})

    def remove(self, phone: str) -> Dict[str, Any]:
        """Remove a number from your opt-out list."""
        return self._c._request("DELETE", "/opt-outs/" + _q(phone))


def _q(segment: str) -> str:
    return urllib.parse.quote(segment, safe="")


def _iso(value: Optional[Union[str, datetime]]) -> Optional[str]:
    """ISO-8601 with timezone (the API rejects naive times); naive = UTC."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return value


def _safe_json(raw: str) -> Any:
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return raw


def _backoff(attempt: int, retry_after: Optional[str]) -> float:
    if retry_after:
        try:
            return min(float(retry_after), 20.0)
        except ValueError:
            pass
    base = min(0.5 * (2 ** attempt), 10.0)
    return base + base * 0.2 * random.random()
