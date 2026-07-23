import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Itinerary } from "../types";
import ItineraryPanel from "./ItineraryPanel";

const { fetchItineraryMock, setStopBookedMock } = vi.hoisted(() => ({
  fetchItineraryMock: vi.fn(),
  setStopBookedMock: vi.fn(),
}));

vi.mock("../api", () => ({
  fetchItinerary: fetchItineraryMock,
  setStopBooked: setStopBookedMock,
}));

const itinerary: Itinerary = {
  has_itinerary: true,
  destination: "Paris",
  currency: "EUR",
  stats: { days: 1, stops: 2, booked: 0 },
  days: [
    {
      day: 1,
      date: "2026-09-12",
      title: "Museums and river",
      summary: "A compact first day in central Paris.",
      color: "#e11d48",
      reachability: "All stops are within central Paris.",
      google_maps_url: "https://maps.google.com/example",
      route: {
        distance_km: 4.2,
        duration_min: 35,
        mode: "walk",
        distance_display: "4.2 km",
        duration_display: "35 min",
      },
      stops: [
        {
          name: "Louvre Museum",
          kind: "attraction",
          time: "10:00",
          duration_min: 120,
          note: "",
          booked: false,
          selected: true,
          color: "#e11d48",
        },
        {
          name: "Seine cruise",
          kind: "attraction",
          time: "15:00",
          duration_min: 60,
          note: "",
          booked: false,
          selected: true,
          color: "#e11d48",
        },
      ],
    },
  ],
};

describe("ItineraryPanel", () => {
  beforeEach(() => {
    fetchItineraryMock.mockReset().mockResolvedValue(itinerary);
    setStopBookedMock.mockReset();
  });

  it("shows compact stop, duration, and route metadata", async () => {
    render(<ItineraryPanel />);

    expect(await screen.findByText("Museums and river")).toBeInTheDocument();
    expect(screen.getByText("2 stops")).toBeInTheDocument();
    expect(screen.getByText("3h planned")).toBeInTheDocument();
    expect(screen.getByText(/4\.2 km/)).toHaveTextContent("35 min");
    expect(screen.getByRole("link", { name: "Open route" })).toHaveAttribute(
      "href",
      "https://maps.google.com/example",
    );
  });

  it("rolls back an optimistic booking update when persistence fails", async () => {
    setStopBookedMock.mockRejectedValue(new Error("offline"));
    render(<ItineraryPanel />);

    const checkbox = await screen.findByRole("checkbox", { name: "Louvre Museum: Mark booked" });
    fireEvent.click(checkbox);
    expect(checkbox).toHaveAttribute("aria-checked", "true");

    await waitFor(() => expect(checkbox).toHaveAttribute("aria-checked", "false"));
    expect(screen.getByRole("status")).toHaveTextContent("Could not update the booking status.");
  });
});
