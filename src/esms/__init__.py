"""Official Python SDK for the eSMS Africa SMS API.

    from esms import Esms

    esms = Esms(api_key="esms_live_...")
    res = esms.messages.send(to="+256700000000", text="Hello!")
"""

from .client import DEFAULT_BASE_URL, Esms, __version__
from .errors import (
    ApiError,
    AuthenticationError,
    EsmsConnectionError,
    EsmsError,
    InsufficientBalanceError,
    InvalidRequestError,
    NotFoundError,
    PermissionDenied,
    RateLimitError,
)
from .models import (
    Balance,
    Message,
    MessageList,
    MessageSummary,
    Route,
    SendResult,
    TimelineEvent,
)

# Alias to mirror the other eSMS SDKs.
EsmsClient = Esms

__all__ = [
    "Esms",
    "EsmsClient",
    "DEFAULT_BASE_URL",
    "__version__",
    # errors
    "EsmsError",
    "EsmsConnectionError",
    "AuthenticationError",
    "PermissionDenied",
    "NotFoundError",
    "InvalidRequestError",
    "InsufficientBalanceError",
    "RateLimitError",
    "ApiError",
    # models
    "SendResult",
    "Message",
    "MessageSummary",
    "MessageList",
    "TimelineEvent",
    "Balance",
    "Route",
]
