"""Error hierarchy for the eSMS Africa SDK.

Every failure raised by the client is an :class:`EsmsError`. Inspect
``err.status`` and ``err.code`` to branch, or catch a specific subclass.
"""

from __future__ import annotations

from typing import Any, Optional


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
    """400 / 422 - the request was rejected as invalid."""


class InsufficientBalanceError(InvalidRequestError):
    """422 ``insufficient_balance`` - not enough credit to send.

    Exposes ``balance``, ``cost`` and ``currency`` so callers can prompt a
    top-up.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        d = self.detail if isinstance(self.detail, dict) else {}
        self.balance = d.get("balance")
        self.cost = d.get("cost")
        self.currency = d.get("currency")


class RateLimitError(EsmsError):
    """429 - too many requests; back off and retry later."""


class ApiError(EsmsError):
    """5xx - the API had an internal error."""


def error_from_response(
    status: int, body: Any, request_id: Optional[str] = None
) -> EsmsError:
    """Build the right error subclass from an HTTP status and parsed body."""
    detail: Any = body
    if isinstance(body, dict) and "detail" in body:
        detail = body["detail"]

    code = None
    message = None
    if isinstance(detail, dict):
        code = detail.get("code")
        message = detail.get("message")
    elif isinstance(detail, str):
        message = detail
    if not message:
        message = f"HTTP {status}"

    kwargs = dict(status=status, code=code, detail=detail, request_id=request_id)

    if code == "insufficient_balance":
        return InsufficientBalanceError(message, **kwargs)
    if status == 401:
        return AuthenticationError(message, **kwargs)
    if status == 403:
        return PermissionDenied(message, **kwargs)
    if status == 404:
        return NotFoundError(message, **kwargs)
    if status in (400, 422):
        return InvalidRequestError(message, **kwargs)
    if status == 429:
        return RateLimitError(message, **kwargs)
    if status >= 500:
        return ApiError(message, **kwargs)
    return EsmsError(message, **kwargs)
