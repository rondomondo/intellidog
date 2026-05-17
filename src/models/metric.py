from datetime import datetime

from pydantic import BaseModel


class PercentileStats(BaseModel):
    """Latency percentile breakdown for a numeric payload field."""

    p50: float | None = None
    p95: float | None = None
    p99: float | None = None
    min: float | None = None
    max: float | None = None
    count: int = 0


class RateStats(BaseModel):
    """Event rate statistics over a time window."""

    total: int = 0
    per_minute: float = 0.0
    error_count: int = 0
    error_rate_pct: float = 0.0
    window_seconds: int = 60


class SourceStat(BaseModel):
    """Per-source event count."""

    source: str
    count: int


class MetricSummary(BaseModel):
    """Aggregated metrics snapshot returned by GET /metrics/summary."""

    window_seconds: int
    computed_at: datetime
    rate: RateStats
    severity_breakdown: dict[str, int]
    top_sources: list[SourceStat]
    latency: PercentileStats
    active_alerts: int
    llm_anomalies_last_hour: int
