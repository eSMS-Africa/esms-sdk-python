"""Typed response models (lightweight dataclasses)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def _f(d: Dict[str, Any], key: str, default: Any = None) -> Any:
    return d.get(key, default)


@dataclass
class SendResult:
    id: str
    status: str
    segments: int
    cost: float
    cost_currency: str
    route_cost: float
    route_currency: str
    route: str
    balance_after: float
    scheduled_at: Optional[str]
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SendResult":
        return cls(
            id=str(_f(d, "id", "")),
            status=str(_f(d, "status", "")),
            segments=int(_f(d, "segments", 0) or 0),
            cost=float(_f(d, "cost", 0) or 0),
            cost_currency=str(_f(d, "cost_currency", "")),
            route_cost=float(_f(d, "route_cost", 0) or 0),
            route_currency=str(_f(d, "route_currency", "")),
            route=str(_f(d, "route", "")),
            balance_after=float(_f(d, "balance_after", 0) or 0),
            scheduled_at=_f(d, "scheduled_at"),
            raw=d,
        )


@dataclass
class MessageSummary:
    id: str
    phone: str
    text: str
    sender_id: Optional[str]
    route: Optional[str]
    country: Optional[str]
    segments: int
    cost: float
    currency: Optional[str]
    status: str
    error_code: Optional[str]
    retry_count: int
    created_at: str
    delivered_at: Optional[str]
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MessageSummary":
        return cls(
            id=str(_f(d, "id", "")),
            phone=str(_f(d, "phone", "")),
            text=str(_f(d, "text", "")),
            sender_id=_f(d, "sender_id"),
            route=_f(d, "route"),
            country=_f(d, "country"),
            segments=int(_f(d, "segments", 0) or 0),
            cost=float(_f(d, "cost", 0) or 0),
            currency=_f(d, "currency"),
            status=str(_f(d, "status", "")),
            error_code=_f(d, "error_code"),
            retry_count=int(_f(d, "retry_count", 0) or 0),
            created_at=str(_f(d, "created_at", "")),
            delivered_at=_f(d, "delivered_at"),
            raw=d,
        )


@dataclass
class TimelineEvent:
    event: str
    status: str
    detail: Optional[str]
    at: str
    metadata: Optional[Dict[str, Any]]


@dataclass
class Message(MessageSummary):
    error_message: Optional[str] = None
    submitted_at: Optional[str] = None
    failed_at: Optional[str] = None
    timeline: List[TimelineEvent] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Message":
        base = MessageSummary.from_dict(d)
        timeline = [
            TimelineEvent(
                event=str(e.get("event", "")),
                status=str(e.get("status", "")),
                detail=e.get("detail"),
                at=str(e.get("at", "")),
                metadata=e.get("metadata"),
            )
            for e in (d.get("timeline") or [])
        ]
        return cls(
            **{k: getattr(base, k) for k in base.__dataclass_fields__ if k != "raw"},
            raw=d,
            error_message=d.get("error_message"),
            submitted_at=d.get("submitted_at"),
            failed_at=d.get("failed_at"),
            timeline=timeline,
        )


@dataclass
class MessageList:
    messages: List[MessageSummary]
    total: int
    page: int
    limit: int

    def __iter__(self):
        return iter(self.messages)

    def __len__(self) -> int:
        return len(self.messages)


@dataclass
class Balance:
    balance: float
    currency: str
    sms_estimate: Optional[int] = None


@dataclass
class Route:
    code: str
    name: str
    country_code: str
    country_name: str
    currency: str
    price_per_segment: float
    sender_id_default: str
    is_active: bool

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Route":
        return cls(
            code=str(d.get("code", "")),
            name=str(d.get("name", "")),
            country_code=str(d.get("country_code", "")),
            country_name=str(d.get("country_name", "")),
            currency=str(d.get("currency", "")),
            price_per_segment=float(d.get("price_per_segment", 0) or 0),
            sender_id_default=str(d.get("sender_id_default", "")),
            is_active=bool(d.get("is_active", False)),
        )
