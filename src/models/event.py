import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class EventType(str, Enum):
    error = "error"
    warning = "warning"
    info = "info"
    metric = "metric"
    custom = "custom"


class EventSeverity(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"
    info = "info"


class LogLevel(str, Enum):
    ERROR = "ERROR"
    WARN = "WARN"
    INFO = "INFO"
    DEBUG = "DEBUG"


class NotificationChannel(str, Enum):
    slack = "slack"
    webhook = "webhook"
    email = "email"
    pagerduty = "pagerduty"


class EventEntry(BaseModel):
    """Structured application event."""

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source: str
    event_type: EventType = EventType.info
    severity: EventSeverity = EventSeverity.info
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("timestamp", mode="before")
    @classmethod
    def ensure_utc(cls, v: object) -> datetime:
        """Reject naive datetimes; attach UTC if offset is missing on a datetime object."""
        if isinstance(v, str):
            dt = datetime.fromisoformat(v)
            return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
        if isinstance(v, datetime):
            return v if v.tzinfo is not None else v.replace(tzinfo=UTC)
        return v  # type: ignore[return-value]


class LogEntry(BaseModel):
    """Structured system log entry."""

    log_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    host: str
    service: str
    level: LogLevel = LogLevel.INFO
    message: str
    process: str = ""
    pid: int | None = None
    tags: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("timestamp", mode="before")
    @classmethod
    def ensure_utc(cls, v: object) -> datetime:
        """Reject naive datetimes; attach UTC if offset is missing on a datetime object."""
        if isinstance(v, str):
            dt = datetime.fromisoformat(v)
            return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
        if isinstance(v, datetime):
            return v if v.tzinfo is not None else v.replace(tzinfo=UTC)
        return v  # type: ignore[return-value]


class NotificationEntry(BaseModel):
    """Async notification event from an external system."""

    notification_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    channel: NotificationChannel = NotificationChannel.webhook
    source_system: str
    title: str
    body: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("timestamp", mode="before")
    @classmethod
    def ensure_utc(cls, v: object) -> datetime:
        """Reject naive datetimes; attach UTC if offset is missing on a datetime object."""
        if isinstance(v, str):
            dt = datetime.fromisoformat(v)
            return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
        if isinstance(v, datetime):
            return v if v.tzinfo is not None else v.replace(tzinfo=UTC)
        return v  # type: ignore[return-value]
