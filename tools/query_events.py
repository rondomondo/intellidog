"""Query and pretty-print events, logs, alerts and metrics from the Intellidog API."""

import argparse
import json
import sys

import httpx


def _print_json(data: object) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def main() -> None:
    """Query Intellidog API endpoints and pretty-print results."""
    parser = argparse.ArgumentParser(description="Query Intellidog API")
    parser.add_argument("--host", default="http://localhost:8000", help="API base URL")
    sub = parser.add_subparsers(dest="cmd", required=True)

    ev = sub.add_parser("events", help="Query events")
    ev.add_argument("--source", default=None)
    ev.add_argument("--severity", default=None)
    ev.add_argument("--event-type", default=None)
    ev.add_argument("--since", default=None, help="ISO-8601 UTC datetime")
    ev.add_argument("--limit", type=int, default=20)

    lg = sub.add_parser("logs", help="Query logs")
    lg.add_argument("--host-filter", default=None)
    lg.add_argument("--service", default=None)
    lg.add_argument("--level", default=None)
    lg.add_argument("--since", default=None)
    lg.add_argument("--limit", type=int, default=20)

    al = sub.add_parser("alerts", help="Query alerts")
    al.add_argument("--status", default=None, choices=["active", "resolved", "suppressed"])
    al.add_argument("--limit", type=int, default=20)

    sub.add_parser("metrics", help="Show metrics summary")
    sub.add_parser("health", help="Show health status")

    args = parser.parse_args()
    base = args.host.rstrip("/")

    with httpx.Client(timeout=10.0) as client:
        try:
            if args.cmd == "events":
                params = {k: v for k, v in {
                    "source": args.source,
                    "severity": args.severity,
                    "event_type": args.event_type,
                    "since": args.since,
                    "limit": args.limit,
                }.items() if v is not None}
                r = client.get(f"{base}/events", params=params)
            elif args.cmd == "logs":
                params = {k: v for k, v in {
                    "host": args.host_filter,
                    "service": args.service,
                    "level": args.level,
                    "since": args.since,
                    "limit": args.limit,
                }.items() if v is not None}
                r = client.get(f"{base}/logs", params=params)
            elif args.cmd == "alerts":
                params = {k: v for k, v in {
                    "alert_status": args.status,
                    "limit": args.limit,
                }.items() if v is not None}
                r = client.get(f"{base}/alerts", params=params)
            elif args.cmd == "metrics":
                r = client.get(f"{base}/metrics/summary")
            elif args.cmd == "health":
                r = client.get(f"{base}/health")
            else:
                parser.print_help()
                sys.exit(1)

            r.raise_for_status()
            _print_json(r.json())
        except httpx.HTTPError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
