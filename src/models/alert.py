import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class AlertSeverity(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class AlertStatus(str, Enum):
    active = "active"
    resolved = "resolved"
    suppressed = "suppressed"


class RuleCondition(BaseModel):
    """Condition clause for an alert rule."""

    metric: str
    operator: str
    threshold: float
    window_seconds: int = 60
    field: str | None = None
    event_type: str | None = None
    source: str | None = None


class AlertRule(BaseModel):
    """Alert rule definition -- loaded from YAML/JSON or created via API."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""
    condition: RuleCondition
    severity: AlertSeverity = AlertSeverity.medium
    enabled: bool = True
    source: str = "config"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("created_at", mode="before")
    @classmethod
    def ensure_utc(cls, v: object) -> datetime:
        """Reject naive datetimes."""
        if isinstance(v, str):
            dt = datetime.fromisoformat(v)
            return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
        if isinstance(v, datetime):
            return v if v.tzinfo is not None else v.replace(tzinfo=UTC)
        return v  # type: ignore[return-value]


class Alert(BaseModel):
    """A fired alert instance."""

    alert_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    rule_id: str | None = None
    rule_name: str
    severity: AlertSeverity
    status: AlertStatus = AlertStatus.active
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    source: str = "engine"
    fired_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = None

    @field_validator("fired_at", mode="before")
    @classmethod
    def ensure_utc(cls, v: object) -> datetime:
        """Reject naive datetimes."""
        if isinstance(v, str):
            dt = datetime.fromisoformat(v)
            return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
        if isinstance(v, datetime):
            return v if v.tzinfo is not None else v.replace(tzinfo=UTC)
        return v  # type: ignore[return-value]
