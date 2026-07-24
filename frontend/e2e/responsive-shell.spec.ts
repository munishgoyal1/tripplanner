import { expect, test } from "@playwright/test";

const emptyTrip = {
  has_trip: false,
  title: "",
  destination: "",
  focus: null,
  is_fallback: false,
  empty_message: "",
  overview: {
    destination: "",
    origin: "",
    departure_date: "",
    return_date: "",
    travelers: 1,
    status: "draft",
    notes: "",
    counts: { flights: 0, hotels: 0, activities: 0, days: 0 },
    total_cost: null,
    total_cost_display: "",
  },
  items: [],
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let body: unknown = {};
    if (path.endsWith("/auth/config")) body = { google: false };
    else if (path.endsWith("/auth/me")) body = { authenticated: false };
    else if (path.endsWith("/chat/history")) body = { messages: [] };
    else if (path.endsWith("/trip/view")) body = emptyTrip;
    else if (path.endsWith("/maps/config")) body = { enabled: false, key: "" };
    else if (path.endsWith("/trip/map")) {
      body = {
        enabled: false,
        destination: "",
        center: null,
        pins: [],
        days: [],
        unscheduled_pin_ids: [],
        airport: null,
        empty_message: "",
      };
    } else if (path.endsWith("/trip/itinerary")) {
      body = {
        has_itinerary: false,
        destination: "",
        days: [],
        stats: { days: 0, stops: 0, booked: 0 },
      };
    } else if (path.endsWith("/trips")) {
      body = {
        trips: [{
          trip_id: "goa_2026-07-01_2026-07-05",
          destination: "Goa",
          departure_date: "2026-07-01",
          return_date: "2026-07-05",
          status: "draft",
          total_cost: 0,
          currency: "INR",
          counts: { flights: 1, hotels: 1, activities: 3 },
          updated_at: "2026-07-24T00:00:00",
          is_active: true,
        }],
      };
    }
    await route.fulfill({ json: body });
  });
});

test("mounts exactly one chat workspace", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Trip Planner" })).toHaveCount(1);

  const desktop = await page.evaluate(() => window.matchMedia("(min-width: 768px)").matches);
  if (desktop) {
    await expect(page.getByRole("heading", { name: "Itinerary" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Map" })).toBeVisible();
    await expect(page.getByTestId("context-inspector")).toBeVisible();
    await expect(page.getByRole("separator", { name: "Resize itinerary and map" })).toBeVisible();
    await expect(page.getByRole("separator", { name: "Resize map and details" })).toBeVisible();
    await expect(page.getByRole("separator", { name: "Resize details and chat" })).toBeVisible();
    await page.getByRole("button", { name: /Goa.*1/ }).click();
    const menu = page.getByTestId("saved-trips-menu");
    await expect(menu).toBeVisible();
    expect(await menu.evaluate((element) => {
      const rect = element.getBoundingClientRect();
      const topmost = document.elementFromPoint(rect.left + rect.width / 2, rect.top + 12);
      return topmost === element || element.contains(topmost);
    })).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollHeight <= window.innerHeight)).toBe(true);
  } else {
    await expect(page.getByTestId("context-inspector")).toHaveCount(0);
  }
});
