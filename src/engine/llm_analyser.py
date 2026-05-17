import logging
import random
import sqlite3
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from src.db.repository import insert_alert, query_events
from src.models.alert import Alert, AlertSeverity

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert SRE anomaly detection engine. You analyse structured application
events and identify anomalies, out-of-band patterns, and reliability concerns that static threshold
rules would miss.

Given a JSON array of recent events, respond with a JSON object:
{
  "anomalies": [
    {
      "title": "<short descriptive title>",
      "severity": "critical|high|medium|low",
      "explanation": "<2-3 sentences explaining why this is anomalous>",
      "affected_sources": ["<source1>"],
      "event_ids": ["<event_id1>"]
    }
  ],
  "summary": "<one sentence overall assessment>"
}

If no anomalies are found, return {"anomalies": [], "summary": "No anomalies detected in this window."}.
Always respond with valid JSON only. No markdown, no preamble."""

MAX_EVENTS_PER_ANALYSIS = 50
ANALYSIS_WINDOW_SECONDS = 300


class LLMAnalyser:
    """Uses the Anthropic Claude API to detect anomalies in recent events.

    Args:
        api_key: Anthropic API key.
        model: Claude model ID to use.
        enabled: When False, analysis calls are skipped (useful when no key is configured).
    """

    def __init__(self, api_key: str, model: str, enabled: bool = True) -> None:
        self._api_key = api_key
        self._model = model
        self._enabled = enabled and bool(api_key)
        self._client: Any = None
        self._system_prompt_cache: list[dict[str, Any]] = []

    def connect(self) -> None:
        """Initialise the Anthropic client with prompt caching enabled."""
        if not self._enabled:
            logger.info("LLM analyser disabled (no API key or explicitly disabled)")
            return
        try:
            import anthropic

            self._client = anthropic.Anthropic(api_key=self._api_key)
            self._system_prompt_cache = [
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
            logger.info("LLM analyser connected: model=%s", self._model)
        except ImportError:
            logger.error("anthropic package not installed -- LLM analysis disabled")
            self._enabled = False

    def is_enabled(self) -> bool:
        """Return True if the analyser is active and has a client."""
        return self._enabled and self._client is not None

    def analyse(self, conn: sqlite3.Connection) -> list[Alert]:
        """Fetch recent events, call the LLM, and persist any detected anomalies.

        Args:
            conn: Open SQLite connection used for event fetching and alert persistence.

        Returns:
            List of Alert objects created from LLM-detected anomalies.
        """
        if not self.is_enabled():
            return []

        since = datetime.now(UTC) - timedelta(seconds=ANALYSIS_WINDOW_SECONDS)
        events = query_events(conn, since=since, limit=MAX_EVENTS_PER_ANALYSIS)
        if not events:
            logger.debug("LLM analyser: no events in window -- skipping")
            return []

        import json

        events_json = json.dumps(events, default=str, ensure_ascii=False)
        try:
            import anthropic

            response = self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                system=self._system_prompt_cache,
                messages=[
                    {
                        "role": "user",
                        "content": f"Analyse these {len(events)} recent events:\n\n{events_json}",
                    }
                ],
            )
            raw = response.content[0].text.strip()
            result: dict[str, Any] = json.loads(raw)
        except anthropic.APIError as exc:
            logger.error("LLM API error during analysis: %s", exc)
            return []
        except (json.JSONDecodeError, IndexError, KeyError) as exc:
            logger.error("LLM response parse error: %s", exc)
            return []

        fired: list[Alert] = []
        for anomaly in result.get("anomalies", []):
            try:
                alert = Alert(
                    rule_name=anomaly.get("title", "LLM Anomaly"),
                    severity=AlertSeverity(anomaly.get("severity", "medium")),
                    message=anomaly.get("explanation", ""),
                    details={
                        "affected_sources": anomaly.get("affected_sources", []),
                        "event_ids": anomaly.get("event_ids", []),
                        "llm_summary": result.get("summary", ""),
                    },
                    source="llm",
                    fired_at=datetime.now(UTC),
                )
                insert_alert(conn, alert)
                fired.append(alert)
                logger.info("LLM anomaly detected: %s [%s]", alert.rule_name, alert.severity.value)
            except Exception as exc:
                logger.error("Failed to persist LLM anomaly: %s", exc)

        return fired


# Heuristic thresholds used by the simulation mock
_MOCK_ERROR_RATE_THRESHOLD = 0.4
_MOCK_LATENCY_THRESHOLD_MS = 3000
_MOCK_SOURCE_BURST_THRESHOLD = 5
_MOCK_ANOMALY_FIRE_CHANCE = 0.15


class MockLLMAnalyser(LLMAnalyser):
    """Simulation mock that replaces the real Claude API call with deterministic heuristics.

    Useful for local development, demos, and CI environments where no API key is
    available. The heuristics inspect real event data and produce plausible anomaly
    alerts that exercise the full alert pipeline.

    Args:
        model: Model name label (used in log messages only -- no API call is made).
    """

    def __init__(self, model: str = "mock-heuristic") -> None:
        super().__init__(api_key="mock", model=model, enabled=True)
        self._client = object()

    def connect(self) -> None:
        """No-op -- mock needs no external connection."""
        logger.info("MockLLMAnalyser active -- simulation mode (no real API calls)")

    def is_enabled(self) -> bool:
        return True

    def analyse(self, conn: sqlite3.Connection) -> list[Alert]:
        """Run heuristic anomaly detection over recent events and persist results.

        Checks performed:
        - High error rate (>40% of events are critical/high severity)
        - Latency spike (any event with duration_ms above threshold)
        - Source burst (single source emitting more than threshold events in window)
        - Random low-probability ambient anomaly (simulates unexpected LLM finds)

        Args:
            conn: Open SQLite connection.

        Returns:
            List of Alert objects persisted to the DB.
        """
        since = datetime.now(UTC) - timedelta(seconds=ANALYSIS_WINDOW_SECONDS)
        events = query_events(conn, since=since, limit=MAX_EVENTS_PER_ANALYSIS)
        if not events:
            logger.debug("MockLLMAnalyser: no events in window -- skipping")
            return []

        fired: list[Alert] = []
        n = len(events)

        # Check 1: error rate
        error_count = sum(1 for e in events if e.get("severity") in ("critical", "high"))
        if n > 0 and (error_count / n) > _MOCK_ERROR_RATE_THRESHOLD:
            fired.append(
                self._make_alert(
                    title="Elevated Error Rate Detected",
                    severity="high",
                    explanation=(
                        f"Mock analysis found {error_count} of {n} events ({int(error_count/n*100)}%) "
                        f"are critical or high severity in the last {ANALYSIS_WINDOW_SECONDS}s window. "
                        "This pattern often precedes a cascade failure -- investigate the top sources."
                    ),
                    affected_sources=list({e["source"] for e in events if e.get("severity") in ("critical", "high")}),
                    event_ids=[e["event_id"] for e in events if e.get("severity") in ("critical", "high")][:5],
                )
            )

        # Check 2: latency spike
        high_latency = [
            e
            for e in events
            if isinstance(e.get("payload"), dict) and e["payload"].get("duration_ms", 0) > _MOCK_LATENCY_THRESHOLD_MS
        ]
        if high_latency:
            worst = max(high_latency, key=lambda e: e["payload"]["duration_ms"])
            fired.append(
                self._make_alert(
                    title="Latency Spike Identified",
                    severity="high" if worst["payload"]["duration_ms"] < 10000 else "critical",
                    explanation=(
                        f"Mock analysis detected {len(high_latency)} events with duration_ms "
                        f"exceeding {_MOCK_LATENCY_THRESHOLD_MS}ms. Worst observed: "
                        f"{worst['payload']['duration_ms']}ms from '{worst['source']}'. "
                        "SLO breach is likely if this persists beyond the current window."
                    ),
                    affected_sources=list({e["source"] for e in high_latency}),
                    event_ids=[e["event_id"] for e in high_latency[:5]],
                )
            )

        # Check 3: source burst
        source_counts: Counter[str] = Counter(e["source"] for e in events)
        bursting = [(src, cnt) for src, cnt in source_counts.most_common(3) if cnt >= _MOCK_SOURCE_BURST_THRESHOLD]
        for src, cnt in bursting:
            fired.append(
                self._make_alert(
                    title=f"Event Burst from '{src}'",
                    severity="medium",
                    explanation=(
                        f"Mock analysis observed {cnt} events from '{src}' in a "
                        f"{ANALYSIS_WINDOW_SECONDS}s window -- significantly above baseline. "
                        "This may indicate a retry storm, misconfigured emitter, or runaway process."
                    ),
                    affected_sources=[src],
                    event_ids=[e["event_id"] for e in events if e["source"] == src][:5],
                )
            )

        # Check 4: low-probability ambient anomaly (keeps the dashboard interesting on steady traffic)
        if not fired and random.random() < _MOCK_ANOMALY_FIRE_CHANCE:
            sample = random.choice(events)
            fired.append(
                self._make_alert(
                    title="Subtle Pattern Anomaly (Simulated)",
                    severity="low",
                    explanation=(
                        f"Mock analysis flagged a subtle deviation in event distribution from '{sample['source']}'. "
                        "Frequency and severity mix diverged from the rolling 24h baseline by more than 1.5 sigma. "
                        "No immediate action needed -- mark resolved once verified."
                    ),
                    affected_sources=[sample["source"]],
                    event_ids=[sample["event_id"]],
                )
            )

        for alert in fired:
            try:
                insert_alert(conn, alert)
                logger.info("MockLLMAnalyser anomaly: %s [%s]", alert.rule_name, alert.severity.value)
            except Exception as exc:
                logger.error("MockLLMAnalyser: failed to persist alert: %s", exc)

        return fired

    def _make_alert(
        self,
        title: str,
        severity: str,
        explanation: str,
        affected_sources: list[str],
        event_ids: list[str],
    ) -> Alert:
        return Alert(
            rule_name=title,
            severity=AlertSeverity(severity),
            message=explanation,
            details={
                "affected_sources": affected_sources,
                "event_ids": event_ids,
                "llm_summary": f"[MOCK] {title}",
                "mock": True,
            },
            source="llm",
            fired_at=datetime.now(UTC),
        )
