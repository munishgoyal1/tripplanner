// Capture UI evidence for a local debugging session: screenshots, the API
// view-models behind them, console output, and the rendered DOM. Pairing the
// pixels with /trip/view is what separates "backend sent wrong data" from
// "UI rendered good data wrong".
import { chromium } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";

function arg(name, fallback = "") {
  const hit = process.argv.find((entry) => entry.startsWith(`--${name}=`));
  return hit ? hit.slice(name.length + 3) : fallback;
}

const url = arg("url", "http://127.0.0.1:5173");
const outDir = arg("out");
const label = arg("label", "capture");
const pinnedUser = arg("user");

if (!outDir) {
  console.error("ERROR: --out=<directory> is required");
  process.exit(2);
}

const ENDPOINTS = ["trip/view", "trip/map", "trip/itinerary", "trips"];
const ELEMENTS = [
  ["chat-transcript", '[data-testid="chat-transcript"]'],
  ["details-inspector", '[data-testid="context-inspector"]'],
  ["saved-trips-menu", '[data-testid="saved-trips-menu"]'],
];

const console_lines = [];
const page_errors = [];

// The repo's Playwright config drives system Chrome, so bundled browsers are
// usually absent; fall back only if a managed chromium happens to be present.
async function launchBrowser() {
  try {
    return await chromium.launch({ channel: "chrome" });
  } catch (error) {
    try {
      return await chromium.launch();
    } catch {
      console.error(
        "ERROR: no browser available. Install Google Chrome, or run 'npx playwright install chromium' in frontend/.",
      );
      throw error;
    }
  }
}

const browser = await launchBrowser();
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();
// Land in the workspace, not the public entry, and optionally as the identity
// whose trips were just restored.
await context.addInitScript((user) => {
  localStorage.setItem("tripplanner_public_entry_skipped", "1");
  if (user) localStorage.setItem("tripplanner_user_id", user);
}, pinnedUser);
page.on("console", (message) => {
  console_lines.push(`[${message.type()}] ${message.text()}`);
});
page.on("pageerror", (error) => page_errors.push(String(error)));

await mkdir(outDir, { recursive: true });

let identity = "";
let apiPayloads = {};
try {
  await page.goto(url, { waitUntil: "networkidle", timeout: 45000 });
  await page.waitForTimeout(1200);

  identity = await page.evaluate(() => localStorage.getItem("tripplanner_user_id") || "");

  apiPayloads = await page.evaluate(async (endpoints) => {
    const userId = localStorage.getItem("tripplanner_user_id") || "";
    const out = {};
    for (const endpoint of endpoints) {
      try {
        const response = await fetch(`/api/${endpoint}?user_id=${encodeURIComponent(userId)}`, {
          credentials: "same-origin",
        });
        out[endpoint] = { status: response.status, body: await response.json() };
      } catch (error) {
        out[endpoint] = { status: 0, error: String(error) };
      }
    }
    return out;
  }, ENDPOINTS);

  await page.screenshot({ path: join(outDir, "desktop-full.png"), fullPage: true });
  await page.screenshot({ path: join(outDir, "desktop-viewport.png") });

  for (const [name, selector] of ELEMENTS) {
    const element = page.locator(selector).first();
    if (await element.count()) {
      try {
        await element.screenshot({ path: join(outDir, `${name}.png`) });
      } catch {
        // An element can be present but not visible; the full-page shot still has it.
      }
    }
  }

  await writeFile(join(outDir, "page.html"), await page.content(), "utf-8");

  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(600);
  await page.screenshot({ path: join(outDir, "mobile-full.png"), fullPage: true });
} finally {
  await writeFile(
    join(outDir, "capture.json"),
    JSON.stringify(
      {
        label,
        url,
        captured_at: new Date().toISOString(),
        user_id: identity,
        api: apiPayloads,
        console: console_lines,
        page_errors,
      },
      null,
      2,
    ),
    "utf-8",
  );
  await browser.close();
}

console.log(`Captured UI evidence for '${label}' into ${outDir}`);
if (page_errors.length) {
  console.log(`  ${page_errors.length} page error(s) recorded`);
}
