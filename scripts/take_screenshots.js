// Capture screenshots of Intellidog API and Grafana using Playwright (Node.js).
// Runs inside mcr.microsoft.com/playwright:v1.59.1-jammy via run_screenshots.sh
//
// Usage (direct):
//   npx playwright install chromium
//   node scripts/take_screenshots.js [--api-host localhost:8000] [--grafana-host localhost:3000] [--output assets/screenshots]

// Try playwright first (installed at runtime), fall back to playwright-core (pre-installed in image)
let chromium;
try {
  ({ chromium } = require('/tmp/node_modules/playwright'));
} catch (_) {
  ({ chromium } = require('playwright'));
}
const fs = require('fs');
const path = require('path');

const args = process.argv.slice(2);
const get = (flag, def) => { const i = args.indexOf(flag); return i !== -1 ? args[i + 1] : def; };

const API_HOST     = get('--api-host',     'host-gateway:8000');
const GRAFANA_HOST = get('--grafana-host', 'host-gateway:3000');
const OUTPUT_DIR   = get('--output',       '/screenshots');

const GRAFANA_USER = 'admin';
const GRAFANA_PASS = 'intellidog';

const TARGETS = [
  {
    name:      'api_health',
    url:       `http://${API_HOST}/health`,
    waitFor:   null,
    fullPage:  false,
    viewport:  { width: 1280, height: 720 },
    waitMs:    1500,
  },
  {
    name:      'api_docs',
    url:       `http://${API_HOST}/docs`,
    waitFor:   '.swagger-ui',
    fullPage:  true,
    viewport:  { width: 1440, height: 900 },
    waitMs:    3000,
  },
  {
    name:      'api_metrics',
    url:       `http://${API_HOST}/metrics/summary`,
    waitFor:   null,
    fullPage:  false,
    viewport:  { width: 1280, height: 720 },
    waitMs:    1500,
  },
  {
    name:      'api_alerts',
    url:       `http://${API_HOST}/alerts`,
    waitFor:   null,
    fullPage:  false,
    viewport:  { width: 1280, height: 720 },
    waitMs:    1500,
  },
  {
    name:      'api_rules',
    url:       `http://${API_HOST}/rules`,
    waitFor:   null,
    fullPage:  false,
    viewport:  { width: 1280, height: 720 },
    waitMs:    1500,
  },
  {
    name:          'grafana_dashboard',
    url:           `http://${GRAFANA_HOST}/d/intellidog-main/intellidog-event-watchdog?orgId=1&refresh=10s&from=now-1h&to=now`,
    waitFor:       '.dashboard-container',
    fullPage:      true,
    viewport:      { width: 1920, height: 1080 },
    waitMs:        8000,
    grafanaLogin:  true,
  },
  {
    name:         'grafana_alerts_panel',
    url:          `http://${GRAFANA_HOST}/d/intellidog-main/intellidog-event-watchdog?orgId=1&viewPanel=8`,
    waitFor:      '.panel-container',
    fullPage:     false,
    viewport:     { width: 1440, height: 900 },
    waitMs:       5000,
    grafanaLogin: false,
  },
];

async function grafanaLogin(page) {
  console.log('  Logging into Grafana...');
  await page.goto(`http://${GRAFANA_HOST}/login`, { timeout: 15000 });
  await page.waitForTimeout(2000);
  await page.fill('input[name="user"]', GRAFANA_USER);
  await page.fill('input[name="password"]', GRAFANA_PASS);
  await page.click('button[type="submit"]');
  await page.waitForTimeout(3000);
  console.log('  Grafana login done');
}

(async () => {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });

  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  });
  const context = await browser.newContext();
  const page    = await context.newPage();

  let grafanaReady = false;

  for (const target of TARGETS) {
    console.log(`  Capturing: ${target.name}`);
    await page.setViewportSize(target.viewport);

    if (target.grafanaLogin && !grafanaReady) {
      try {
        await grafanaLogin(page);
        grafanaReady = true;
      } catch (err) {
        console.warn(`  WARNING: Grafana login failed: ${err.message}`);
      }
    }

    try {
      await page.goto(target.url, { timeout: 20000, waitUntil: 'networkidle' });
    } catch (err) {
      console.warn(`  WARNING: navigation error (${target.name}): ${err.message}`);
    }

    await page.waitForTimeout(target.waitMs || 2000);

    if (target.waitFor) {
      try {
        await page.waitForSelector(target.waitFor, { timeout: 8000 });
      } catch (_) { /* best-effort */ }
    }

    const outPath = path.join(OUTPUT_DIR, `${target.name}.png`);
    await page.screenshot({ path: outPath, fullPage: target.fullPage });
    const sizeKb = Math.round(fs.statSync(outPath).size / 1024);
    console.log(`    Saved: ${target.name}.png (${sizeKb}KB)`);
  }

  await browser.close();
  console.log(`\nAll screenshots saved to: ${OUTPUT_DIR}`);
})();
