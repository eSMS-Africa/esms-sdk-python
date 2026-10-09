"""Error hierarchy for the eSMS Africa SDK.

Every failure raised by the client is an :class:`EsmsError`. Inspect
``err.status`` and ``err.code`` to branch, or catch a specific subclass.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class EsmsError(Exception):
    """Base class for every error raised by the SDK."""

    def __init__(
        self,
        message: str,
        *,
        status: Optional[int] = None,
        code: Optional[str] = None,
        detail: Any = None,
        request_id: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.detail = detail
        self.request_id = request_id

    def __str__(self) -> str:  # pragma: no cover - trivial
        parts = []
        if self.status is not None:
            parts.append(f"HTTP {self.status}")
        if self.code:
            parts.append(self.code)
        prefix = " ".join(parts)
        return f"{prefix}: {self.message}" if prefix else self.message


class EsmsConnectionError(EsmsError):
    """The request never reached the API (DNS, TLS, timeout, offline)."""


class AuthenticationError(EsmsError):
    """401 - the API key or token is missing or invalid."""


class PermissionError_(EsmsError):
    """403 - authenticated, but not allowed to perform this action."""


# Public alias that does not shadow the builtin ``PermissionError``.
PermissionDenied = PermissionError_


class NotFoundError(EsmsError):
    """404 - the requested resource does not exist."""


class InvalidRequestError(EsmsError):
    """400 / 409 / 413 / 422 - the request was rejected as invalid."""


class InsufficientBalanceError(InvalidRequestError):
    """402 ``insufficient_balance`` - not enough credit to send.

    Exposes ``balance``, ``cost`` and ``currency`` so callers can prompt a
    top-up.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        d = self.detail if isinstance(self.detail, dict) else {}
        # Some paths report available/required instead of balance/cost.
        self.balance = d.get("balance", d.get("available"))
        self.cost = d.get("cost", d.get("required"))
        self.currency = d.get("currency")


class RateLimitError(EsmsError):
    """429 - too many requests; back off and retry later."""


class ApiError(EsmsError):
    """5xx - the API had an internal error."""


def parse_error_body(status: int, body: Any) -> Dict[str, Any]:
    """Pull code / message / detail / request_id out of an error body.

    The API returns ``{"detail": <str | dict | list>, "error": {code, message,
    request_id}}``; the rate limiter returns ``{"error": "<text>"}``.
    """
    obj = body if isinstance(body, dict) else None
    detail: Any = obj["detail"] if obj is not None and "detail" in obj else body
    envelope = obj.get("error") if obj is not None and isinstance(obj.get("error"), dict) else None

    code = None
    message = None
    if isinstance(detail, dict):
        code = detail.get("code") if isinstance(detail.get("code"), str) else None
        message = detail.get("message") if isinstance(detail.get("message"), str) else None
    elif isinstance(detail, str) and detail:
        message = detail
    elif isinstance(detail, list) and detail and isinstance(detail[0], dict) and detail[0].get("msg"):
        # 422 validation errors: [{"loc": [...], "msg": "..."}]
        loc = ".".join(str(x) for x in detail[0].get("loc") or [])
        message = f"Request validation failed: {loc + ': ' if loc else ''}{detail[0]['msg']}"
    if envelope is not None:
        code = code or (envelope.get("code") if isinstance(envelope.get("code"), str) else None)
        message = message or (envelope.get("message") if isinstance(envelope.get("message"), str) else None)
    elif obj is not None and isinstance(obj.get("error"), str) and not message:
        message = obj["error"]
    request_id = envelope.get("request_id") if envelope is not None else None
    return {
        "code": code,
        "message": message or f"HTTP {status}",
        "detail": detail,
        "request_id": request_id or None,
    }


def error_from_response(
    status: int, body: Any, request_id: Optional[str] = None
) -> EsmsError:
    """Build the right error subclass from an HTTP status and parsed body."""
    p = parse_error_body(status, body)
    code = p["code"]
    message = p["message"]
    kwargs = dict(
        status=status, code=code, detail=p["detail"], request_id=request_id or p["request_id"]
    )

    if code == "insufficient_balance" or status == 402:
        return InsufficientBalanceError(message, **kwargs)
    if status == 401:
        return AuthenticationError(message, **kwargs)
    if status == 403:
        return PermissionDenied(message, **kwargs)
    if status == 404:
        return NotFoundError(message, **kwargs)
    if status in (400, 409, 413, 422):
        return InvalidRequestError(message, **kwargs)
    if status == 429:
        return RateLimitError(message, **kwargs)
    if status >= 500:
        return ApiError(message, **kwargs)
    return EsmsError(message, **kwargs)
