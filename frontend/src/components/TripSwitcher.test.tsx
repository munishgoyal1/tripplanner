import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { SavedTrip } from "../types";
import TripSwitcher from "./TripSwitcher";

const { deleteTripMock, fetchSavedTripsMock, switchTripMock } = vi.hoisted(() => ({
  deleteTripMock: vi.fn(),
  fetchSavedTripsMock: vi.fn(),
  switchTripMock: vi.fn(),
}));

vi.mock("../api", () => ({
  deleteTrip: deleteTripMock,
  fetchSavedTrips: fetchSavedTripsMock,
  switchTrip: switchTripMock,
}));

const GOA_TRIP: SavedTrip = {
  trip_id: "goa-trip",
  destination: "Goa",
  departure_date: "2026-09-10",
  return_date: "2026-09-14",
  status: "draft",
  total_cost: 0,
  currency: "INR",
  counts: { flights: 1, hotels: 1, activities: 4 },
  updated_at: "2026-08-04T00:00:00Z",
  is_active: true,
};

const ROME_TRIP: SavedTrip = {
  ...GOA_TRIP,
  trip_id: "rome-trip",
  destination: "Rome",
  is_active: false,
};

describe("TripSwitcher deletion", () => {
  beforeEach(() => {
    fetchSavedTripsMock.mockResolvedValue([GOA_TRIP, ROME_TRIP]);
    deleteTripMock.mockReset();
    switchTripMock.mockReset();
    vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  it("deletes only the checked trip", async () => {
    deleteTripMock.mockResolvedValue([ROME_TRIP]);
    const onSwitched = vi.fn();
    render(<TripSwitcher version={1} onSwitched={onSwitched} />);

    fireEvent.click(await screen.findByTitle("Switch between your saved trips"));
    fireEvent.click(screen.getByRole("button", { name: "Delete trips" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Select Goa for deletion" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete 1 trip" }));

    await waitFor(() => expect(deleteTripMock).toHaveBeenCalledWith("goa-trip"));
    expect(deleteTripMock).toHaveBeenCalledTimes(1);
    expect(window.confirm).toHaveBeenCalledWith(
      "Delete Goa and its chat history? This cannot be undone.",
    );
    expect(onSwitched).toHaveBeenCalledOnce();
  });

  it("selects and deletes all saved trips", async () => {
    deleteTripMock
      .mockResolvedValueOnce([ROME_TRIP])
      .mockResolvedValueOnce([]);
    const onSwitched = vi.fn();
    render(<TripSwitcher version={1} onSwitched={onSwitched} />);

    fireEvent.click(await screen.findByTitle("Switch between your saved trips"));
    fireEvent.click(screen.getByRole("button", { name: "Delete trips" }));
    fireEvent.click(screen.getByRole("button", { name: "Select all" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete all 2 trips" }));

    await waitFor(() => expect(deleteTripMock).toHaveBeenCalledTimes(2));
    expect(deleteTripMock).toHaveBeenNthCalledWith(1, "goa-trip");
    expect(deleteTripMock).toHaveBeenNthCalledWith(2, "rome-trip");
    expect(window.confirm).toHaveBeenCalledWith(
      "Delete all 2 saved trips and their chat history? This cannot be undone.",
    );
    expect(onSwitched).toHaveBeenCalledOnce();
  });
});