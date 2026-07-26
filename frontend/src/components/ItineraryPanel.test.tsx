import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Itinerary, TripOverview } from "../types";
import ItineraryPanel from "./ItineraryPanel";

const { fetchItineraryMock, setStopBookedMock } = vi.hoisted(() => ({
  fetchItineraryMock: vi.fn(),
  setStopBookedMock: vi.fn(),
}));
const scrollIntoViewMock = vi.fn();

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
          travel_from_previous: {
            distance_km: 2.1,
            duration_min: 28,
            mode: "walk",
            distance_display: "2.1 km",
            duration_display: "28 min",
          },
        },
      ],
    },
  ],
};

const overview: TripOverview = {
  destination: "Paris",
  origin: "Delhi",
  departure_date: "2026-09-12",
  return_date: "2026-09-16",
  travelers: 2,
  status: "finalized",
  notes: "",
  counts: { flights: 1, hotels: 1, activities: 4, days: 5 },
  total_cost: 45000,
  total_cost_display: "₹45,000",
  constraints: ["Vegetarian meals"],
};

describe("ItineraryPanel", () => {
  beforeEach(() => {
    fetchItineraryMock.mockReset().mockResolvedValue(itinerary);
    setStopBookedMock.mockReset();
    scrollIntoViewMock.mockReset();
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: scrollIntoViewMock,
    });
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
    expect(screen.getByLabelText("Map stop 1")).toHaveTextContent("1");
    expect(screen.getByLabelText("Map stop 2")).toHaveTextContent("2");
    expect(screen.getByLabelText("Travel from previous stop: 2.1 km, 28 min")).toBeInTheDocument();
  });

  it("uses the itinerary entry point for the authoritative trip snapshot", async () => {
    render(<ItineraryPanel overview={overview} />);

    const snapshot = await screen.findByRole("region", { name: "Trip snapshot" });
    expect(snapshot).toHaveTextContent("Paris");
    expect(screen.getByLabelText("5 days")).toBeInTheDocument();
    expect(screen.getByLabelText("4 places")).toBeInTheDocument();
    expect(snapshot).toHaveTextContent("₹45,000");
    expect(snapshot).toHaveTextContent("0/2 stops booked");
    expect(snapshot).toHaveTextContent("Vegetarian meals");
  });

  it("matches map ordering for hotel endpoints and place stops", async () => {
    fetchItineraryMock.mockResolvedValue({
      ...itinerary,
      stats: { days: 1, stops: 5, booked: 0 },
      days: [{
        ...itinerary.days[0],
        stops: [
          { ...itinerary.days[0].stops[0], name: "Hotel Lutetia", kind: "hotel" },
          itinerary.days[0].stops[0],
          { ...itinerary.days[0].stops[0], name: "Cafe de Flore", kind: "meal" },
          itinerary.days[0].stops[1],
          { ...itinerary.days[0].stops[0], name: "Hotel Lutetia", kind: "hotel" },
        ],
      }],
    });

    render(<ItineraryPanel />);

    expect(await screen.findAllByLabelText("Hotel map marker")).toHaveLength(2);
    expect(screen.getByLabelText("Map stop 1")).toHaveTextContent("1");
    expect(screen.getByLabelText("Map stop 2")).toHaveTextContent("2");
    expect(screen.getByLabelText("Map stop 3")).toHaveTextContent("3");
  });

  it("requests the complete circuit when the day header is clicked", async () => {
    const onDayMap = vi.fn();
    fetchItineraryMock.mockResolvedValue({
      ...itinerary,
      stats: { days: 1, stops: 3, booked: 0 },
      days: [{
        ...itinerary.days[0],
        stops: [
          { ...itinerary.days[0].stops[0], name: "Hotel Lutetia", kind: "hotel" },
          itinerary.days[0].stops[0],
          { ...itinerary.days[0].stops[0], name: "Hotel Lutetia", kind: "hotel" },
        ],
      }],
    });

    render(<ItineraryPanel onDayMap={onDayMap} />);

    fireEvent.click(await screen.findByTitle("Show complete Day 1 circuit on map"));
    expect(onDayMap).toHaveBeenCalledTimes(1);
    expect(onDayMap).toHaveBeenCalledWith(1);
  });

  it("highlights only the exact focused occurrence of a repeated hotel", async () => {
    const hotel = { ...itinerary.days[0].stops[0], name: "Hotel Lutetia", kind: "hotel" };
    fetchItineraryMock.mockResolvedValue({
      ...itinerary,
      stats: { days: 2, stops: 2, booked: 0 },
      days: [
        { ...itinerary.days[0], day: 1, title: "Day 1", stops: [hotel] },
        { ...itinerary.days[0], day: 2, title: "Day 2", stops: [hotel] },
      ],
    });

    render(
      <ItineraryPanel
        focusName="Hotel Lutetia"
        focusDay={2}
        focusStop={1}
      />,
    );

    const markers = await screen.findAllByLabelText("Hotel map marker");
    expect(markers[0]).not.toHaveAttribute("aria-current");
    expect(markers[1]).toHaveAttribute("aria-current", "location");
    expect(markers[1]).toHaveClass("scale-110", "text-white");
    const dayTwoRow = document.querySelector('[data-stop-day="2"][data-stop-index="1"]');
    expect(scrollIntoViewMock.mock.instances[0]).toBe(dayTwoRow);
  });

  it("scrolls a map day jump to the start of the itinerary day summary", async () => {
    fetchItineraryMock.mockResolvedValue({
      ...itinerary,
      stats: { days: 2, stops: 4, booked: 0 },
      days: [
        { ...itinerary.days[0], day: 1, title: "Day 1" },
        { ...itinerary.days[0], day: 2, title: "Day 2" },
      ],
    });

    render(<ItineraryPanel jumpTo={{ day: 2, token: 17 }} />);

    await screen.findByText("Day 2");
    await waitFor(() => expect(scrollIntoViewMock).toHaveBeenCalled());
    expect(scrollIntoViewMock.mock.instances[0]).toBe(document.getElementById("it-day-2"));
    expect(scrollIntoViewMock).toHaveBeenCalledWith({ behavior: "smooth", block: "start" });
  });

  it("does not style concern rows as selected cards", async () => {
    fetchItineraryMock.mockResolvedValue({
      ...itinerary,
      days: [{
        ...itinerary.days[0],
        stops: itinerary.days[0].stops.map((stop) => ({
          ...stop,
          concern: "Check opening hours before visiting.",
        })),
      }],
    });

    render(<ItineraryPanel focusName="Louvre Museum" focusDay={1} focusStop={1} />);

    await screen.findByText("Museums and river");
    const louvre = document.querySelector('[data-stop-name="louvre museum"]');
    const cruise = document.querySelector('[data-stop-name="seine cruise"]');
    expect(louvre).toHaveClass("bg-brand/5");
    expect(cruise).not.toHaveClass("bg-brand/5");
    expect(cruise).not.toHaveClass("bg-rose-50/60");
    expect(cruise).not.toHaveClass("ring-rose-200");
    expect(screen.getAllByText("Check opening hours before visiting.")).toHaveLength(2);
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

  it("removes the exact itinerary occurrence", async () => {
    const onStopRemove = vi.fn().mockResolvedValue(undefined);
    render(<ItineraryPanel onStopRemove={onStopRemove} />);

    fireEvent.click(await screen.findByRole("button", { name: "Remove Seine cruise from itinerary" }));

    await waitFor(() => expect(onStopRemove).toHaveBeenCalledWith(
      "attraction",
      "Seine cruise",
      1,
      2,
    ));
  });
});
