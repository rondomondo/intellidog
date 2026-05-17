"""Inject a single out-of-band anomaly event to test LLM and threshold detection."""

import argparse
import json
import sys
from datetime import UTC, datetime

import httpx

ANOMALY_TEMPLATES = {
    "latency_spike": {
        "source": "api-gateway",
        "event_type": "metric",
        "severity": "critical",
        "message": "P99 latency spike detected: 45000ms",
        "payload": {"duration_ms": 45000, "endpoint": "/checkout", "region": "eu-west-1"},
        "tags": ["latency", "spike", "anomaly"],
    },
    "error_burst": {
        "source": "payment-service",
        "event_type": "error",
        "severity": "critical",
        "message": "Burst of payment failures: 47 in 10 seconds",
        "payload": {"failure_count": 47, "gateway": "stripe", "error_code": "rate_limit"},
        "tags": ["payment", "error_burst", "anomaly"],
    },
    "memory_oom": {
        "source": "worker",
        "event_type": "error",
        "severity": "critical",
        "message": "OOM kill: worker process exceeded memory limit",
        "payload": {"pid": 9999, "memory_mb": 8192, "limit_mb": 4096},
        "tags": ["oom", "memory", "anomaly"],
    },
    "cascade_failure": {
        "source": "db-proxy",
        "event_type": "error",
        "severity": "critical",
        "message": "Database connection pool exhausted -- all downstream services affected",
        "payload": {"pool_size": 50, "waiting_connections": 312, "timeout_ms": 30000},
        "tags": ["cascade", "database", "anomaly"],
    },
}


def main() -> None:
    """Inject a synthetic anomaly event to test Intellidog detection."""
    parser = argparse.ArgumentParser(description="Inject an anomaly event into Intellidog")
    parser.add_argument("--host", default="http://localhost:8000", help="API base URL")
    parser.add_argument(
        "--type",
        default="latency_spike",
        choices=list(ANOMALY_TEMPLATES.keys()),
        help="Anomaly type to inject",
    )
    parser.add_argument("--source", default=None, help="Override the event source")
    parser.add_argument("--message", default=None, help="Override the event message")
    parser.add_argument("--dry-run", action="store_true", help="Print payload without POSTing")
    args = parser.parse_args()

    payload = dict(ANOMALY_TEMPLATES[args.type])
    payload["timestamp"] = datetime.now(UTC).isoformat()
    if args.source:
        payload["source"] = args.source
    if args.message:
        payload["message"] = args.message

    if args.dry_run:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    base = args.host.rstrip("/")
    with httpx.Client(timeout=10.0) as client:
        try:
            r = client.post(f"{base}/events", json=payload)
            r.raise_for_status()
            print(json.dumps(r.json(), indent=2, ensure_ascii=False))
        except httpx.HTTPError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
