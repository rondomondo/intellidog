"""Simulate and POST application events and system log entries to the Intellidog API."""

import argparse
import json
import random
import sys
import time
from datetime import UTC, datetime

import httpx

SOURCES = ["payment-service", "auth-service", "api-gateway", "worker", "scheduler", "db-proxy"]
EVENT_TYPES = ["error", "warning", "info", "metric", "custom"]
SEVERITIES = ["critical", "high", "medium", "low", "info"]
LOG_LEVELS = ["ERROR", "WARN", "INFO", "DEBUG"]
HOSTS = ["web-01", "web-02", "worker-01", "worker-02", "db-01"]
SERVICES = ["nginx", "gunicorn", "celery", "postgres", "redis"]

MESSAGES = {
    "error": [
        "Payment gateway timeout after 30s",
        "Database connection pool exhausted",
        "Upstream service returned 503",
        "JWT validation failed: token expired",
        "Unhandled exception in request handler",
    ],
    "warning": [
        "Response time approaching SLO threshold",
        "Cache miss rate elevated: 45%",
        "Retry attempt 2 of 3 for downstream call",
        "Memory usage at 85% of limit",
    ],
    "info": [
        "Request processed successfully",
        "Cache warmed for region eu-west-1",
        "Deployment completed: v2.3.1",
        "Health check passed",
    ],
    "metric": ["duration_ms recorded", "request_count incremented", "queue_depth sampled"],
    "custom": ["Custom event fired", "Audit log entry created", "Feature flag evaluated"],
}


def _make_event(event_type: str, severity: str, source: str) -> dict:
    base_duration = random.randint(10, 200)
    if severity in ("critical", "high"):
        base_duration = random.randint(2000, 15000)
    message = random.choice(MESSAGES.get(event_type, ["Event occurred"]))
    return {
        "source": source,
        "event_type": event_type,
        "severity": severity,
        "message": message,
        "payload": {
            "duration_ms": base_duration,
            "request_id": f"req-{random.randint(100000, 999999)}",
            "region": random.choice(["eu-west-1", "us-east-1", "ap-southeast-1"]),
        },
        "tags": [source, event_type, severity],
        "timestamp": datetime.now(UTC).isoformat(),
    }


def _make_log(level: str, host: str, service: str) -> dict:
    log_messages = {
        "ERROR": ["upstream timed out", "disk write failed", "OOM killer activated", "segfault in worker"],
        "WARN": ["slow query detected (>500ms)", "connection retry attempt", "high memory usage"],
        "INFO": ["request handled", "worker started", "config reloaded"],
        "DEBUG": ["cache key computed", "handler resolved", "middleware chain complete"],
    }
    return {
        "host": host,
        "service": service,
        "level": level,
        "message": random.choice(log_messages.get(level, ["log entry"])),
        "process": service,
        "pid": random.randint(1000, 9999),
        "tags": [host, service, level.lower()],
        "timestamp": datetime.now(UTC).isoformat(),
    }


def main() -> None:
    """Generate and POST synthetic events and logs to the Intellidog API."""
    parser = argparse.ArgumentParser(description="Generate synthetic events for Intellidog")
    parser.add_argument("--host", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--count", type=int, default=20, help="Number of events to generate")
    parser.add_argument("--logs", type=int, default=10, help="Number of log entries to generate")
    parser.add_argument("--source", default=None, help="Force a specific source name")
    parser.add_argument("--severity", default=None, choices=SEVERITIES, help="Force a specific severity")
    parser.add_argument("--event-type", default=None, choices=EVENT_TYPES, help="Force a specific event type")
    parser.add_argument("--spike", action="store_true", help="Generate a spike: all events are error/critical")
    parser.add_argument("--delay", type=float, default=0.0, help="Delay in seconds between batches")
    parser.add_argument("--dry-run", action="store_true", help="Print events without POSTing")
    args = parser.parse_args()

    events = []
    for _ in range(args.count):
        et = args.event_type or ("error" if args.spike else random.choice(EVENT_TYPES))
        sev = args.severity or ("critical" if args.spike else random.choice(SEVERITIES))
        src = args.source or random.choice(SOURCES)
        events.append(_make_event(et, sev, src))

    logs = []
    for _ in range(args.logs):
        lvl = "ERROR" if args.spike else random.choice(LOG_LEVELS)
        logs.append(_make_log(lvl, random.choice(HOSTS), random.choice(SERVICES)))

    if args.dry_run:
        print(json.dumps({"events": events, "logs": logs}, indent=2, ensure_ascii=False))
        return

    base = args.host.rstrip("/")
    with httpx.Client(timeout=10.0) as client:
        try:
            r = client.post(f"{base}/events", json=events)
            r.raise_for_status()
            print(f"Events: {r.json()}", file=sys.stdout)
            if args.delay:
                time.sleep(args.delay)
            r = client.post(f"{base}/logs", json=logs)
            r.raise_for_status()
            print(f"Logs: {r.json()}", file=sys.stdout)
        except httpx.HTTPError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
