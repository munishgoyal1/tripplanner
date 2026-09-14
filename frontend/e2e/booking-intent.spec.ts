import { expect, test } from "@playwright/test";

test("booking intent preview, keyboard confirmation and small-screen layout", async ({ page }, testInfo) => {
  const row = { id: "stay-1", category: "hotels", name: "Seaside Double · breakfast included",
    amount: 70000, currency: "INR", start_date: "2026-12-01", end_date: "2026-12-03", time: "",
    provider: "liteapi", checked_at: "2026-09-14T08:00:00Z", expires_at: "2026-09-14T08:15:00Z",
    complete_cost: true, url: "https://example.com/hotel", handoff: "product_page",
    details: { room_name: "Double", board_name: "Breakfast", search_context: { adults_per_room: 2, rooms: 1 } },
    decision_id: "stay-1", option_id: "rate-1", alternatives: [], booked: false, actual: null,
    intended: null, intent_state: "draft", evidence: "stale", disposition: "needs_booking", selected: true };
  const view = { trip_id: "trip-1", updated_at: "v1", destination: "Goa", travelers: "2 adults",
    rows: [row], coverage: "LiteAPI flight/hotel research. Other items use your research.",
    locked_count: 0, booked_count: 0, category_caps: { hotels: { amount: 80000, currency: "INR" } },
    budgets: { hotels: { amount: 80000, currency: "INR", known_total: 70000, unknown_items: 0, incomplete_items: 0, status: "unverified" } } };
  let writes = 0;
  await page.route("**/trip/bookings?*", (route) => route.fulfill({ json: view }));
  await page.route("**/trip/bookings", async (route) => {
    const command = route.request().postDataJSON();
    expect(command.trip_id).toBe("trip-1");
    expect(command.updated_at).toBe("v1");
    if (!command.preview) { expect(command.preview_token).toBe("bound-preview"); writes++; }
    await route.fulfill({ json: { ok: true, message: "Intention saved", preview_token: "bound-preview",
      bookings: { ...view, updated_at: command.preview ? "v1" : "v2", locked_count: 1,
        rows: [{ ...row, intent_state: "locked" }] }, warnings: ["This does not reserve inventory."] } });
  });
  if (testInfo.project.name === "mobile") await page.setViewportSize({ width: 320, height: 740 });
  await page.goto("/bookings");
  await expect(page.getByRole("heading", { name: "Bookings · Goa" })).toBeVisible();
  expect(writes).toBe(0);
  await page.screenshot({ path: testInfo.outputPath("booking-page.png"), fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole("button", { name: "Lock intention", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Review before saving" })).toBeFocused();
  expect(writes).toBe(0);
  await page.getByRole("button", { name: "Confirm adjustment" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "Unlock intention" })).toBeVisible();
  expect(writes).toBe(1);
  await expect(page.getByRole("link", { name: /Open provider/ })).toHaveAttribute("rel", "noopener noreferrer");
  await page.getByRole("button", { name: "Export booking intent list" }).click();
  await expect(page.getByRole("heading", { name: "Export booking intent list" })).toBeVisible();
});
