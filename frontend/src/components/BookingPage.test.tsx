import { fireEvent, render, screen, waitFor, cleanup } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import BookingPage from "./BookingPage";
import type { BookingView } from "../bookingApi";

const fetchBookings = vi.fn();
const bookingCommand = vi.fn();
const shareBookings = vi.fn();
vi.mock("../bookingApi", () => ({
  fetchBookings: (...args: unknown[]) => fetchBookings(...args),
  bookingCommand: (...args: unknown[]) => bookingCommand(...args),
  shareBookings: (...args: unknown[]) => shareBookings(...args),
  bookingJsonUrl: () => "/api/trip/bookings/export.json",
}));
vi.mock("./ExportModal", () => ({
  default: ({ bookingTrip }: { bookingTrip: { trip_id: string; updated_at: string } }) =>
    <div role="dialog">Booking export {bookingTrip.trip_id} {bookingTrip.updated_at}</div>,
}));
const view: BookingView = {
  trip_id: "goa", updated_at: "v1", destination: "Goa", travelers: "2 adults",
  category_caps: {}, budgets: {}, locked_count: 0, booked_count: 0, coverage: "LiteAPI only",
  rows: [{
    id: "stay", category: "hotels", name: "Garden Hotel", selected: true,
    amount: 70000, currency: "INR", start_date: "2026-12-01", end_date: "2026-12-03", time: "",
    checked_at: "2026-11-01", expires_at: "", provider: "liteapi", complete_cost: false,
    url: "https://example.com/hotel", handoff: "product_page", details: { room_name: "Double" },
    decision_id: "stay", option_id: "room-1", alternatives: [], booked: false, actual: null,
    intended: null, intent_state: "draft", evidence: "stale", disposition: "needs_booking",
  }],
};
beforeEach(() => {
  vi.resetAllMocks();
  fetchBookings.mockResolvedValue(structuredClone(view));
});
afterEach(cleanup);

describe("Booking intent workflow", () => {
  it("opens saved evidence without research and exports the bound trip", async () => {
    render(<BookingPage />);
    await screen.findByRole("heading", { name: "Garden Hotel" });
    expect(bookingCommand).not.toHaveBeenCalled();
    expect(screen.getByText(/Mandatory fees/)).toBeTruthy();
    expect(screen.getByRole("link", { name: /Open provider/ }).getAttribute("rel")).toContain("noopener");
    fireEvent.click(screen.getByRole("button", { name: "Export booking intent list" }));
    expect(screen.getByRole("dialog").textContent).toContain("goa v1");
  });

  it("previews a lock without booking, then commits exactly that preview", async () => {
    const locked = structuredClone(view);
    locked.rows[0].intent_state = "locked";
    locked.locked_count = 1;
    bookingCommand.mockResolvedValueOnce({ ok: true, bookings: locked, preview_token: "token",
      warnings: ["No inventory is held."] });
    bookingCommand.mockResolvedValueOnce({ ok: true, bookings: locked, message: "Saved" });
    render(<BookingPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Lock intention" }));
    await screen.findByRole("heading", { name: "Review before saving" });
    expect(bookingCommand).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: "Unlock intention" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Confirm adjustment" }));
    await screen.findByRole("button", { name: "Unlock intention" });
    expect(bookingCommand.mock.calls[1][2]).toBe("token");
    expect(bookingCommand.mock.calls[1][0].updated_at).toBe("v1");
    expect(screen.queryByText(/Reported booked through/)).toBeNull();
  });

  it("keeps saved data on stale apply and offers reload", async () => {
    bookingCommand.mockResolvedValueOnce({ ok: true, bookings: view, preview_token: "token" })
      .mockRejectedValueOnce(new Error("The trip changed. Reload and preview again."));
    render(<BookingPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Lock intention" }));
    fireEvent.click(await screen.findByRole("button", { name: "Confirm adjustment" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Reload");
    expect(screen.getByRole("button", { name: "Lock intention" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Reload saved plan" }));
    await waitFor(() => expect(fetchBookings).toHaveBeenCalledTimes(2));
    expect(fetchBookings.mock.calls[1][0]).toBe("goa");
  });

  it("previews offline actuals with unknown amount instead of inventing zero", async () => {
    bookingCommand.mockResolvedValue({ ok: true, bookings: view, preview_token: "report" });
    render(<BookingPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Record booking made elsewhere" }));
    fireEvent.change(screen.getByLabelText("Booked through / offline"), { target: { value: "Offline agent" } });
    fireEvent.change(screen.getByLabelText("Confirmation reference (private)"), { target: { value: "PRIVATE" } });
    fireEvent.click(screen.getByRole("button", { name: "Preview booking update" }));
    await waitFor(() => expect(bookingCommand).toHaveBeenCalledTimes(1));
    expect(bookingCommand.mock.calls[0][1]).toMatchObject({
      action: "report", item_id: "stay", actual: { amount: null, provider: "Offline agent", reference: "PRIVATE" },
    });
  });
});
