import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@tripplanner/client";
import { clearNotices } from "../lib/notices";
import type { SavedTrip } from "../types";
import StatusBar from "./StatusBar";
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
describe("TripSwitcher notifications", () => {
  beforeEach(() => {
    fetchSavedTripsMock.mockResolvedValue([GOA_TRIP, ROME_TRIP]);
    deleteTripMock.mockReset();
    switchTripMock.mockReset();
    clearNotices();
  });

  const openAndPickRome = async () => {
    fireEvent.click(await screen.findByTitle("Switch between your saved trips"));
    fireEvent.click(screen.getByRole("button", { name: /Rome/ }));
  };

  it("announces the switch on the status bar and confirms when it lands", async () => {
    let resolveSwitch: (value: null) => void = () => {};
    switchTripMock.mockReturnValue(new Promise<null>((resolve) => { resolveSwitch = resolve; }));
    render(<><StatusBar /><TripSwitcher version={1} onSwitched={vi.fn()} /></>);

    await openAndPickRome();
    expect(await screen.findByText("Switching to Rome…")).toBeInTheDocument();

    resolveSwitch({ view: {}, map: null, itinerary: null } as never);
    expect(await screen.findByText("Switched to Rome.")).toBeInTheDocument();
  });

  it("retries once when the workspace is briefly locked", async () => {
    const onSwitched = vi.fn();
    switchTripMock
      .mockRejectedValueOnce(new ApiError("Could not switch trips (409).", 409, 0))
      .mockResolvedValueOnce({ view: {}, map: null, itinerary: null });
    render(<><StatusBar /><TripSwitcher version={1} onSwitched={onSwitched} /></>);

    await openAndPickRome();

    await waitFor(() => expect(switchTripMock).toHaveBeenCalledTimes(2));
    expect(onSwitched).toHaveBeenCalledWith("rome-trip", { view: {}, map: null, itinerary: null });
    expect(await screen.findByText("Switched to Rome.")).toBeInTheDocument();
  });

  it("explains a busy workspace instead of a generic failure", async () => {
    switchTripMock.mockRejectedValue(new ApiError("Could not switch trips (409).", 409, 0));
    render(<><StatusBar /><TripSwitcher version={1} onSwitched={vi.fn()} /></>);

    await openAndPickRome();

    expect(
      await screen.findByText("Rome is busy finishing another update. Try again in a moment."),
    ).toBeInTheDocument();
  });
});
