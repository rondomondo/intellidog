#!/usr/bin/env bash
# Run the Playwright screenshot capture inside the official Playwright Docker image.
# Usage: ./scripts/run_screenshots.sh [--api-host HOST:PORT] [--grafana-host HOST:PORT]
#
# Requires: Docker, Intellidog API running on :8000, Grafana on :3000

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUTPUT_DIR="$PROJECT_ROOT/assets/screenshots"
PLAYWRIGHT_IMAGE="mcr.microsoft.com/playwright:v1.59.1-jammy"

API_HOST="${INTELLIDOG_API_HOST:-host-gateway:8000}"
GRAFANA_HOST="${INTELLIDOG_GRAFANA_HOST:-host-gateway:3000}"

mkdir -p "$OUTPUT_DIR"

echo "==> Pulling Playwright image: $PLAYWRIGHT_IMAGE"
docker pull "$PLAYWRIGHT_IMAGE" --quiet

echo "==> Running screenshot capture..."
docker run --rm \
    --add-host=host-gateway:host-gateway \
    --network host \
    -v "$PROJECT_ROOT/scripts:/scripts:ro" \
    -v "$OUTPUT_DIR:/screenshots" \
    "$PLAYWRIGHT_IMAGE" \
    bash -c "
        cd /tmp &&
        npm install playwright@1.59.1 --save --quiet 2>&1 | tail -2 &&
        node /scripts/take_screenshots.js \
            --output /screenshots \
            --api-host $API_HOST \
            --grafana-host $GRAFANA_HOST
    "

echo ""
echo "==> Screenshots written to: $OUTPUT_DIR"
ls -lh "$OUTPUT_DIR"/*.png 2>/dev/null || echo "  (no PNG files found)"
