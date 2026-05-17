"""Capture screenshots of the Intellidog API docs and Grafana dashboard using Playwright.

Designed to run inside the official Playwright Docker image:
    docker run -it --rm \\
        --network host \\
        -v $(pwd)/assets/screenshots:/screenshots \\
        mcr.microsoft.com/playwright:v1.59.1-jammy \\
        bash -c "pip install playwright && python /scripts/take_screenshots.py"

Or run locally if playwright is installed:
    pip install playwright
    playwright install chromium
    python scripts/take_screenshots.py
"""

import argparse
import sys
import time
from pathlib import Path


TARGETS = [
    {
        "name": "api_health",
        "url": "http://host-gateway:8000/health",
        "wait_for": "text=ok",
        "title": "API Health Endpoint",
        "full_page": False,
        "viewport": {"width": 1280, "height": 720},
    },
    {
        "name": "api_docs",
        "url": "http://host-gateway:8000/docs",
        "wait_for": "text=Intellidog",
        "title": "API OpenAPI Docs",
        "full_page": True,
        "viewport": {"width": 1440, "height": 900},
    },
    {
        "name": "api_metrics",
        "url": "http://host-gateway:8000/metrics/summary",
        "wait_for": "text=rate",
        "title": "Metrics Summary",
        "full_page": False,
        "viewport": {"width": 1280, "height": 720},
    },
    {
        "name": "api_alerts",
        "url": "http://host-gateway:8000/alerts",
        "wait_for": "text=alerts",
        "title": "Alerts List",
        "full_page": False,
        "viewport": {"width": 1280, "height": 720},
    },
    {
        "name": "api_rules",
        "url": "http://host-gateway:8000/rules",
        "wait_for": "text=rules",
        "title": "Rules List",
        "full_page": False,
        "viewport": {"width": 1280, "height": 720},
    },
    {
        "name": "grafana_login",
        "url": "http://host-gateway:3000/login",
        "wait_for": "text=Sign in",
        "title": "Grafana Login",
        "full_page": False,
        "viewport": {"width": 1440, "height": 900},
        "grafana_login": True,
    },
    {
        "name": "grafana_dashboard",
        "url": "http://host-gateway:3000/d/intellidog-main/intellidog-event-watchdog?orgId=1&refresh=10s&from=now-1h&to=now",
        "wait_for": "text=Intellidog",
        "title": "Grafana Main Dashboard",
        "full_page": True,
        "viewport": {"width": 1920, "height": 1080},
        "grafana_pre_login": True,
        "wait_ms": 5000,
    },
]

GRAFANA_USER = "admin"
GRAFANA_PASS = "intellidog"


def _host_url(url: str, api_host: str, grafana_host: str) -> str:
    return url.replace("host-gateway:8000", api_host).replace("host-gateway:3000", grafana_host)


def take_screenshots(output_dir: Path, api_host: str, grafana_host: str) -> None:
    """Capture all target screenshots and save to output_dir.

    Args:
        output_dir: Directory to write PNG files into.
        api_host: host:port for the Intellidog API.
        grafana_host: host:port for Grafana.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: playwright not installed. Run: pip install playwright && playwright install chromium", file=sys.stderr)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)
    grafana_logged_in = False

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context()
        page = context.new_page()

        for target in TARGETS:
            url = _host_url(target["url"], api_host, grafana_host)
            name = target["name"]
            print(f"  Capturing: {name} -- {url}")

            page.set_viewport_size(target["viewport"])

            # Grafana login flow -- do once before any grafana page
            if target.get("grafana_pre_login") and not grafana_logged_in:
                login_url = _host_url("http://host-gateway:3000/login", api_host, grafana_host)
                page.goto(login_url, timeout=15000)
                page.wait_for_timeout(2000)
                try:
                    page.fill('input[name="user"]', GRAFANA_USER)
                    page.fill('input[name="password"]', GRAFANA_PASS)
                    page.click('button[type="submit"]')
                    page.wait_for_timeout(3000)
                    grafana_logged_in = True
                    print("    Grafana login successful")
                except Exception as exc:
                    print(f"    WARNING: Grafana login failed: {exc}", file=sys.stderr)

            try:
                page.goto(url, timeout=20000, wait_until="networkidle")
            except Exception as exc:
                print(f"    WARNING: navigation error for {name}: {exc}", file=sys.stderr)

            wait_ms = target.get("wait_ms", 2000)
            page.wait_for_timeout(wait_ms)

            # Try selector wait but don't fail hard if missing
            try:
                selector = target.get("wait_for")
                if selector:
                    page.wait_for_selector(f"text={selector.replace('text=', '')}", timeout=8000)
            except Exception:
                pass

            out_path = output_dir / f"{name}.png"
            page.screenshot(path=str(out_path), full_page=target.get("full_page", False))
            size_kb = out_path.stat().st_size // 1024
            print(f"    Saved: {out_path.name} ({size_kb}KB)")

        browser.close()

    print(f"\nAll screenshots saved to: {output_dir}")


def main() -> None:
    """Entry point for screenshot capture."""
    parser = argparse.ArgumentParser(description="Capture Intellidog screenshots with Playwright")
    parser.add_argument("--output", default="assets/screenshots", help="Output directory for PNG files")
    parser.add_argument("--api-host", default="localhost:8000", help="Intellidog API host:port")
    parser.add_argument("--grafana-host", default="localhost:3000", help="Grafana host:port")
    args = parser.parse_args()

    output_dir = Path(args.output)
    print(f"Intellidog Screenshot Capture")
    print(f"  API:     http://{args.api_host}")
    print(f"  Grafana: http://{args.grafana_host}")
    print(f"  Output:  {output_dir}\n")

    take_screenshots(output_dir, args.api_host, args.grafana_host)


if __name__ == "__main__":
    main()
