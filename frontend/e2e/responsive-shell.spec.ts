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
  await page.addInitScript(() => {
    window.localStorage.setItem("tripplanner_assistant_open", "true");
  });
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let body: unknown = {};
    if (path.endsWith("/auth/config")) body = { google: false };
    else if (path.endsWith("/auth/me")) body = { authenticated: false };
    else if (path.endsWith("/auth/guest/session")) body = { token: "e2e-guest-token" };
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
  await page.goto("/planner");

  const composer = page.getByPlaceholder("e.g. Plan a 5-day trip to Goa in December for 2 people");
  await expect(composer).toHaveCount(1);
  await expect(composer).toBeEnabled();

  const desktop = await page.evaluate(() => window.matchMedia("(min-width: 768px)").matches);
  if (desktop) {
    await expect(page.locator("main")).toHaveCount(1);
    await expect(page.getByRole("heading", { name: "Itinerary" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Map" })).toBeVisible();
    await expect(page.getByTestId("context-inspector")).toBeVisible();
    await expect(page.getByRole("separator", { name: "Resize itinerary and map" })).toBeVisible();
    await expect(page.getByRole("separator", { name: "Resize map and details" })).toBeVisible();
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

test("refreshes the persisted itinerary after a completed planning turn", async ({ page }) => {
  let planned = false;
  let streamDelivered = false;
  let refreshedTripView = false;
  let itineraryRequests = 0;
  let postCompletionItineraryRequests = 0;
  await page.unroute("**/api/**");
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.endsWith("/chat/stream") && request.method() === "POST") {
      planned = true;
      await route.fulfill({
        status: 200,
        headers: {
          "cache-control": "no-cache",
          "content-type": "text/event-stream; charset=utf-8",
        },
        body: [
          'event: token\ndata: {"text":"Your Goa plan is ready."}\n\n',
          'event: done\ndata: {"reply":"Your Goa plan is ready."}\n\n',
        ].join(""),
      });
      streamDelivered = true;
      return;
    }

    let body: unknown = {};
    if (path.endsWith("/auth/config")) body = { google: false };
    else if (path.endsWith("/auth/me")) body = { authenticated: false };
    else if (path.endsWith("/auth/guest/session")) body = { token: "e2e-guest-token" };
    else if (path.endsWith("/chat/history")) {
      body = {
        messages: planned ? [
          { role: "user", text: "Plan a five-day Goa trip from Delhi in December." },
          { role: "assistant", text: "Your Goa plan is ready." },
        ] : [],
      };
    }
    else if (path.endsWith("/trip/view")) {
      if (planned) refreshedTripView = true;
      body = planned ? {
        ...emptyTrip,
        has_trip: true,
        title: "Goa escape",
        destination: "Goa",
        overview: {
          ...emptyTrip.overview,
          destination: "Goa",
          origin: "Delhi",
          departure_date: "2026-12-01",
          return_date: "2026-12-05",
          counts: { flights: 0, hotels: 1, activities: 1, days: 1 },
        },
      } : emptyTrip;
    } else if (path.endsWith("/trip/itinerary")) {
      itineraryRequests += 1;
      if (streamDelivered) postCompletionItineraryRequests += 1;
      body = planned ? {
        has_itinerary: true,
        destination: "Goa",
        currency: "INR",
        days: [{
          day: 1,
          date: "2026-12-01",
          title: "North Goa",
          summary: "Settle in, then explore the fort.",
          color: "#e11d48",
          stops: [{
            name: "Fort Aguada",
            kind: "attraction",
            time: "10:00",
            duration_min: 90,
            note: "Sea views",
            booked: false,
            selected: true,
            color: "#e11d48",
          }],
        }],
        stats: { days: 1, stops: 1, booked: 0 },
      } : {
        has_itinerary: false,
        destination: "",
        days: [],
        stats: { days: 0, stops: 0, booked: 0 },
      };
    } else if (path.endsWith("/maps/config")) body = { enabled: false, key: "" };
    else if (path.endsWith("/trip/map")) {
      body = {
        enabled: false,
        destination: planned ? "Goa" : "",
        center: null,
        pins: [],
        days: [],
        unscheduled_pin_ids: [],
        airport: null,
        empty_message: "",
      };
    } else if (path.endsWith("/trips")) {
      body = { trips: [] };
    }
    await route.fulfill({ json: body });
  });

  await page.goto("/planner");
  const initialItineraryRequests = itineraryRequests;
  const composer = page.getByPlaceholder("e.g. Plan a 5-day trip to Goa in December for 2 people");
  await expect(composer).toBeEnabled();
  await composer.fill("Plan a five-day Goa trip from Delhi in December.");
  await page.getByRole("button", { name: "Send" }).click();

  await expect.poll(() => planned).toBe(true);
  await expect.poll(() => refreshedTripView).toBe(true);
  await expect.poll(() => itineraryRequests).toBeGreaterThan(initialItineraryRequests);
  await expect.poll(() => postCompletionItineraryRequests).toBeGreaterThan(0);
});
