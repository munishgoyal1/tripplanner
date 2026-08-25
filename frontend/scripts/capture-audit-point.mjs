import { chromium } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { dirname } from "node:path";

function arg(name, fallback = "") {
  const hit = process.argv.find((entry) => entry.startsWith(`--${name}=`));
  return hit ? hit.slice(name.length + 3) : fallback;
}

const url = arg("url");
const output = arg("output");
const day = arg("day");
if (!url || !output) {
  console.error("ERROR: --url and --output are required");
  process.exit(2);
}

async function launchBrowser() {
  try {
    return await chromium.launch({ channel: "chrome" });
  } catch (error) {
    try {
      return await chromium.launch();
    } catch {
      console.error("ERROR: Google Chrome or Playwright Chromium is required");
      throw error;
    }
  }
}

const browser = await launchBrowser();
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  await context.addInitScript(() => {
    localStorage.setItem("tripplanner_public_entry_skipped", "1");
  });
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 45000 });
  await page.waitForURL(
    (current) => current.pathname === "/planner" && current.search === "",
    { timeout: 20000 },
  );

  const hideChat = page.getByRole("button", { name: "Hide Chat" });
  if (await hideChat.count()) await hideChat.first().click();
  const maximizeItinerary = page.getByRole("button", { name: "Maximize Itinerary" });
  if (await maximizeItinerary.count()) await maximizeItinerary.first().click();

  const selector = day ? `[data-audit-day="${day}"]` : '[data-testid="audit-itinerary"]';
  const target = page.locator(selector).first();
  await target.waitFor({ state: "visible", timeout: 30000 });
  await target.scrollIntoViewIfNeeded();
  await page.waitForTimeout(500);
  await mkdir(dirname(output), { recursive: true });
  await target.screenshot({ path: output });
  console.log(`Captured ${day ? `day ${day}` : "itinerary"} to ${output}`);
} finally {
  await browser.close();
}