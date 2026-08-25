import { chromium } from "@playwright/test";

function argument(name) {
  const prefix = `--${name}=`;
  return process.argv.find((entry) => entry.startsWith(prefix))?.slice(prefix.length) || "";
}

const baseUrl = argument("url").replace(/\/$/, "");
if (!baseUrl) {
  console.error("ERROR: --url=<hosted app URL> is required");
  process.exit(2);
}

async function launchBrowser() {
  try {
    return await chromium.launch({ channel: "chrome" });
  } catch {
    return chromium.launch();
  }
}

const browser = await launchBrowser();
const context = await browser.newContext();
const page = await context.newPage();
const browserErrors = [];
page.on("console", (message) => {
  if (message.type() === "error") browserErrors.push(message.text());
});
page.on("pageerror", (error) => browserErrors.push(String(error)));

try {
  await page.goto(baseUrl, { waitUntil: "domcontentloaded", timeout: 45000 });
  const mapResult = await page.evaluate(async () => {
    const configResponse = await fetch("/api/maps/config");
    const config = await configResponse.json();
    if (!config.enabled || !config.key) return { loaded: false, reason: "Maps disabled" };

    return new Promise((resolve) => {
      const timeout = window.setTimeout(
        () => resolve({ loaded: false, reason: "Maps callback timed out" }),
        15000,
      );
      window.gm_authFailure = () => {
        window.__tripplannerMapsAuthFailed = true;
        window.clearTimeout(timeout);
        resolve({ loaded: false, reason: "Google rejected the browser key or referrer" });
      };
      window.__tripplannerSmoke = () => {
        window.clearTimeout(timeout);
        resolve({ loaded: Boolean(window.google?.maps), reason: "Maps callback completed" });
      };
      const script = document.createElement("script");
      script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(config.key)}&callback=__tripplannerSmoke`;
      script.onerror = () => {
        window.clearTimeout(timeout);
        resolve({ loaded: false, reason: "Maps script failed to load" });
      };
      document.head.appendChild(script);
    });
  });
  if (!mapResult.loaded) throw new Error(mapResult.reason);
  await page.evaluate(() => {
    const container = document.createElement("div");
    container.style.cssText = "width:320px;height:240px";
    document.body.appendChild(container);
    window.__tripplannerSmokeMap = new window.google.maps.Map(container, {
      center: { lat: 48.8566, lng: 2.3522 },
      zoom: 10,
    });
  });
  await page.waitForTimeout(2500);
  const authFailed = await page.evaluate(() => Boolean(window.__tripplannerMapsAuthFailed));
  if (authFailed) throw new Error("Google rejected the browser key or referrer");
  if (browserErrors.some((line) => /Google Maps JavaScript API error|UrlAuthenticationCommonError/.test(line))) {
    throw new Error(browserErrors.join(" | "));
  }
  console.log(`[PASS] Maps JavaScript authorized for ${baseUrl}`);

  const overviewResponse = await context.request.get(
    `${baseUrl}/api/destination/overview?destination=Paris&news=false`,
  );
  if (!overviewResponse.ok()) throw new Error(`destination overview HTTP ${overviewResponse.status()}`);
  const overview = await overviewResponse.json();
  const photoUrl = overview.photos?.[0] || overview.key_attractions?.find((item) => item.photo)?.photo;
  if (!photoUrl) throw new Error("destination overview returned no photo");
  const photoResponse = await context.request.get(photoUrl);
  if (!photoResponse.ok()) throw new Error(`destination photo HTTP ${photoResponse.status()}`);
  console.log(`[PASS] Destination photo loaded (${photoResponse.status()})`);
} finally {
  await browser.close();
}