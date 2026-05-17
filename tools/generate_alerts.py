"""Trigger alert scenarios by injecting batches of events designed to breach rules."""

import argparse
import json
import sys
import time
from datetime import UTC, datetime

import httpx

SCENARIOS = {
    "spike": "Inject 50 error events rapidly to trigger error rate rules",
    "sustained": "Inject error events every 2 seconds for a sustained period",
    "recovery": "Inject info events to simulate service recovery after an incident",
    "latency": "Inject high-latency metric events to trigger p99/p95 rules",
    "webhook": "POST a simulated Grafana alert webhook payload to /webhook/grafana",
    "webhook-resolve": "POST a simulated Grafana resolved webhook payload to /webhook/grafana",
    "error-rate-80": "Inject enough critical events to breach the 80% error rate threshold",
}


def _error_event(source: str = "payment-service") -> dict:
    return {
        "source": source,
        "event_type": "error",
        "severity": "critical",
        "message": "Simulated alert scenario: critical error",
        "payload": {"duration_ms": 12000, "scenario": "alert_test"},
        "tags": ["scenario", "alert_test"],
        "timestamp": datetime.now(UTC).isoformat(),
    }


def _info_event(source: str = "payment-service") -> dict:
    return {
        "source": source,
        "event_type": "info",
        "severity": "info",
        "message": "Service recovered: all checks passing",
        "payload": {"duration_ms": 45, "scenario": "recovery"},
        "tags": ["scenario", "recovery"],
        "timestamp": datetime.now(UTC).isoformat(),
    }


def _latency_event(duration_ms: int = 8000, source: str = "api-gateway") -> dict:
    return {
        "source": source,
        "event_type": "metric",
        "severity": "high",
        "message": f"High latency recorded: {duration_ms}ms",
        "payload": {"duration_ms": duration_ms, "endpoint": "/api/v1/checkout"},
        "tags": ["latency", "scenario"],
        "timestamp": datetime.now(UTC).isoformat(),
    }


def main() -> None:
    """Run an alert scenario against the Intellidog API."""
    parser = argparse.ArgumentParser(description="Trigger alert scenarios in Intellidog")
    parser.add_argument("--host", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--scenario", default="spike", choices=list(SCENARIOS.keys()), help="Scenario to run")
    parser.add_argument("--source", default="payment-service", help="Event source name")
    parser.add_argument("--count", type=int, default=50, help="Number of events (spike/latency scenarios)")
    parser.add_argument("--duration", type=int, default=30, help="Duration in seconds (sustained scenario)")
    parser.add_argument("--dry-run", action="store_true", help="Print events without POSTing")
    args = parser.parse_args()

    print(f"Scenario: {args.scenario} -- {SCENARIOS[args.scenario]}", file=sys.stderr)
    base = args.host.rstrip("/")

    def post_batch(events: list) -> None:
        if args.dry_run:
            print(json.dumps(events, indent=2, ensure_ascii=False))
            return
        with httpx.Client(timeout=10.0) as client:
            try:
                r = client.post(f"{base}/events", json=events)
                r.raise_for_status()
                print(f"Posted {len(events)} events: {r.json()}")
            except httpx.HTTPError as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                sys.exit(1)

    if args.scenario == "spike":
        events = [_error_event(args.source) for _ in range(args.count)]
        post_batch(events)

    elif args.scenario == "sustained":
        end = time.time() + args.duration
        total = 0
        while time.time() < end:
            post_batch([_error_event(args.source)])
            total += 1
            time.sleep(2)
        print(f"Sustained scenario complete: {total} batches sent")

    elif args.scenario == "recovery":
        events = [_info_event(args.source) for _ in range(args.count)]
        post_batch(events)

    elif args.scenario == "latency":
        import random

        events = [_latency_event(random.randint(5000, 20000), args.source) for _ in range(args.count)]
        post_batch(events)

    elif args.scenario == "error-rate-80":
        # 80 critical + 20 info = 80% error rate, breaches the critical threshold rule
        critical_events = [_error_event(args.source) for _ in range(80)]
        info_events = [
            {
                "source": args.source,
                "event_type": "info",
                "severity": "info",
                "message": "Baseline healthy request",
                "payload": {"duration_ms": 20},
                "tags": ["scenario", "error_rate_80"],
                "timestamp": datetime.now(UTC).isoformat(),
            }
            for _ in range(20)
        ]
        post_batch(critical_events + info_events)

    elif args.scenario in ("webhook", "webhook-resolve"):
        state = "alerting" if args.scenario == "webhook" else "ok"
        status_label = "firing" if state == "alerting" else "resolved"
        payload = {
            "receiver": "intellidog-webhook",
            "status": state,
            "alerts": [
                {
                    "status": status_label,
                    "labels": {
                        "alertname": "Critical Error Rate Threshold",
                        "severity": "critical",
                        "source": args.source,
                        "rule_id": "critical_error_rate_threshold",
                    },
                    "annotations": {
                        "summary": f"Error rate exceeded 80% on {args.source}",
                        "description": (
                            "The proportion of critical/high severity events has breached the 80% threshold. "
                            "Immediate investigation required."
                        ),
                    },
                    "startsAt": datetime.now(UTC).isoformat(),
                    "endsAt": "0001-01-01T00:00:00Z" if state == "alerting" else datetime.now(UTC).isoformat(),
                    "generatorURL": f"http://localhost:3000/alerting/list",
                    "fingerprint": "abc123def456",
                }
            ],
            "groupLabels": {"alertname": "Critical Error Rate Threshold"},
            "commonLabels": {"severity": "critical"},
            "commonAnnotations": {"summary": f"Error rate exceeded 80% on {args.source}"},
            "externalURL": "http://localhost:3000",
            "version": "1",
            "groupKey": f"{{}}:{{alertname='Critical Error Rate Threshold'}}",
            "truncatedAlerts": 0,
            "orgId": 1,
            "title": f"[{status_label.upper()}] Critical Error Rate Threshold",
            "state": state,
            "message": f"Error rate on {args.source} is above 80%",
        }
        if args.dry_run:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return
        with httpx.Client(timeout=10.0) as client:
            try:
                r = client.post(f"{base}/webhook/grafana", json=payload)
                r.raise_for_status()
                print(f"Webhook POSTed ({state}): HTTP {r.status_code}")
                # Immediately show what the endpoint recorded
                r2 = client.get(f"{base}/webhook/grafana")
                data = r2.json()
                print(f"Stored entries: {data['count']}/{data['max']}")
                if data["entries"]:
                    latest = data["entries"][0]
                    print(f"  Latest: received_at={latest['received_at']} state={latest['payload'].get('status')}")
            except httpx.HTTPError as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                sys.exit(1)


if __name__ == "__main__":
    main()
