import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import TripSnapshot from "./TripSnapshot";

const { recheckPricesMock } = vi.hoisted(() => ({ recheckPricesMock: vi.fn() }));

vi.mock("../api", () => ({ recheckPrices: recheckPricesMock }));

vi.mock("../lib/displayPreferences", () => ({
  formatDate: (value: string) => value,
  formatSourceAmount: (value: number) => String(value),
  useDisplayPreferences: () => ({ currency: "EUR" }),
}));

const overview = {
  destination: "Lisbon",
  origin: "London",
  departure_date: "2026-09-10",
  return_date: "2026-09-13",
  travelers: "2",
  status: "finalized",
  notes: "",
  counts: { flights: 1, hotels: 1, activities: 2, days: 3 },
  total_cost: 900,
  total_cost_display: "EUR 900",
  price_rechecks: [
    { kind: "flights", provider: "liteapi", reason: "finalized but unbooked quote expired" },
  ],
};

describe("TripSnapshot price recheck", () => {
  beforeEach(() => recheckPricesMock.mockReset());

  it("runs only after the explicit action and does not trigger map focus", async () => {
    const onTripChanged = vi.fn();
    const onAllDaysMap = vi.fn();
    recheckPricesMock.mockResolvedValue({
      ok: true,
      stale: false,
      message: "Rechecked the trip's stale provider prices.",
      rechecked: 1,
      results: [
        {
          kind: "flights",
          provider: "liteapi",
          status: "live",
          previous_total: 400,
          current_total: 430,
          delta: 30,
          currency: "EUR",
          observed_at: "2026-08-25T10:00:00Z",
        },
      ],
    });

    render(
      <TripSnapshot
        overview={overview}
        onTripChanged={onTripChanged}
        onAllDaysMap={onAllDaysMap}
      />,
    );

    expect(recheckPricesMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Recheck prices" }));

    await waitFor(() => expect(recheckPricesMock).toHaveBeenCalledOnce());
    expect(onTripChanged).toHaveBeenCalledOnce();
    expect(onAllDaysMap).not.toHaveBeenCalled();
    expect(screen.getByText("Rechecked 1; 1 price changed.")).toBeInTheDocument();
  });
});
