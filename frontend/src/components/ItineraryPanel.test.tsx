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
      schedule: {
        start: "10:00",
        end: "16:00",
        duration_min: 360,
        duration_display: "6 hr",
        travel_duration_min: 35,
        travel_duration_display: "35 min",
        estimated: false,
      },
      weather: {
        date: "2026-09-12",
        summary: "Light rain",
        condition: "rain",
        high_c: 18,
        low_c: 12,
        precip_mm: 3.2,
        precip_probability_pct: 65,
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
            mode: "Walk",
            distance_display: "2.1 km",
            duration_display: "28 min",
            detail: "Walk from Louvre Museum to Seine cruise.",
          },
          expected_arrival_time: "12:28",
          buffer_before_min: 152,
          buffer_before_display: "2 hr 32 min",
          rating: 4.7,
          review_count: 12500,
          popularity_score: 91,
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
  notes: "Five easy-paced days balancing museums, river views, and neighborhood meals.",
  counts: { flights: 1, hotels: 1, activities: 4, days: 5 },
  total_cost: 45000,
  total_cost_display: "₹45,000",
  weather: {
    source: "forecast",
    source_label: "Live forecast",
    note: "Real forecast from Open-Meteo.",
    days: [{
      date: "2026-09-12",
      summary: "Light rain",
      condition: "rain",
      high_c: 18,
      low_c: 12,
      precip_mm: 3.2,
      precip_probability_pct: 65,
    }],
    packing_advice: ["Compact umbrella and light rain jacket"],
  },
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

  it("shows the compact brief and agenda metadata", async () => {
    render(<ItineraryPanel />);

    expect(await screen.findByText("Museums and river")).toBeInTheDocument();
    expect(screen.getByText("Saturday · 12 September 2026")).toBeInTheDocument();
    expect(screen.getByText("2 planned stops")).toBeInTheDocument();
    expect(screen.getByText("Schedule duration:").parentElement).toHaveTextContent("6 hr · 10:00–16:00");
    expect(screen.getByText("Day's travel:").parentElement).toHaveTextContent("35 min · 4.2 km · walk");
    expect(screen.getByText("0 confirmed · 2 to book")).toBeInTheDocument();
    expect(screen.getByText("Travel rhythm:")).toBeInTheDocument();
    expect(screen.getByText(/4\.2 km/)).toHaveTextContent("35 min");
    expect(screen.getByRole("link", { name: "Open route" })).toHaveAttribute(
      "href",
      "https://maps.google.com/example",
    );
    expect(screen.getByLabelText("Map stop 1")).toHaveTextContent("1");
    expect(screen.getByLabelText("Map stop 2")).toHaveTextContent("2");
    expect(screen.getByLabelText("Travel from previous stop: 2.1 km, 28 min")).toBeInTheDocument();
    expect(screen.getByText("Walk from Louvre Museum to Seine cruise.")).toBeInTheDocument();
    expect(screen.getByText("Est. arrive 12:28 · 2 hr 32 min free before 15:00")).toBeInTheDocument();
    expect(screen.getByLabelText("Seine cruise rating 4.7 out of 5")).toHaveTextContent("12.5K reviews");
    expect(screen.getByText("Must-visit score 91/100")).toBeInTheDocument();
    expect(screen.getAllByText("Arrive")).toHaveLength(2);
    expect(screen.getByText("120 min visit")).toBeInTheDocument();
    expect(screen.queryByText("In trip")).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /Mark confirmed/ })).toHaveLength(2);
    expect(screen.getByLabelText("Light rain, high 18 degrees Celsius, low 12 degrees Celsius")).toHaveTextContent("18° / 12°C");
    expect(screen.getByText("65% rain")).toBeInTheDocument();
  });

  it("uses the itinerary entry point for the authoritative trip snapshot", async () => {
    render(<ItineraryPanel overview={overview} />);

    const snapshot = await screen.findByRole("region", { name: "Trip snapshot" });
    expect(snapshot).toHaveTextContent("Paris");
    expect(screen.getByLabelText("5 days")).toBeInTheDocument();
    expect(screen.getByLabelText("4 places")).toBeInTheDocument();
    expect(snapshot).toHaveTextContent("₹45,000");
    expect(snapshot).toHaveTextContent("Delhi · 2026-09-12 - 2026-09-16 · 2 travelers");
    expect(snapshot).toHaveTextContent("0 of 2 ready");
    expect(snapshot).toHaveTextContent("2 need booking");
    expect(screen.getByLabelText("0% of stops ready")).toBeInTheDocument();
    expect(snapshot).toHaveTextContent("Five easy-paced days balancing museums, river views, and neighborhood meals.");
    expect(snapshot).toHaveTextContent("Vegetarian meals");
    expect(snapshot).not.toHaveTextContent("Trip fit:");
    expect(snapshot).toHaveTextContent("Live forecast");
    expect(snapshot).toHaveTextContent("D1");
    expect(snapshot).toHaveTextContent("Compact umbrella and light rain jacket");
  });

  it("keeps summary and weather visible when an older trip has no forecast", async () => {
    render(<ItineraryPanel overview={{ ...overview, notes: "", weather: null }} />);

    const snapshot = await screen.findByRole("region", { name: "Trip snapshot" });
    expect(snapshot).toHaveTextContent("5-day Paris trip for 2 travelers with 4 planned places.");
    expect(snapshot).toHaveTextContent("Weather");
    expect(snapshot).toHaveTextContent("Forecast unavailable for this trip.");
  });

  it("combines identical hotel endpoints without changing place numbering", async () => {
    fetchItineraryMock.mockResolvedValue({
      ...itinerary,
      stats: { days: 1, stops: 5, booked: 0 },
      days: [{
        ...itinerary.days[0],
        stops: [
          { ...itinerary.days[0].stops[0], name: "Hotel Lutetia", kind: "hotel", time: "09:00" },
          itinerary.days[0].stops[0],
          { ...itinerary.days[0].stops[0], name: "Cafe de Flore", kind: "meal" },
          itinerary.days[0].stops[1],
          {
            ...itinerary.days[0].stops[0],
            name: "Hotel Lutetia",
            kind: "hotel",
            time: "20:00",
            travel_from_previous: {
              distance_km: 3.4,
              duration_min: 18,
              mode: "Taxi",
              distance_display: "3.4 km",
              duration_display: "18 min",
              detail: "Taxi from Seine cruise to Hotel Lutetia.",
            },
            expected_arrival_time: "20:00",
            note: "Collect stored bags at reception.",
            concern: "Confirm late front-desk access.",
          },
        ],
      }],
    });

    render(<ItineraryPanel />);

    expect(await screen.findAllByLabelText("Hotel circuit marker for Hotel Lutetia")).toHaveLength(1);
    expect(screen.getAllByText("Hotel Lutetia")).toHaveLength(1);
    expect(screen.getByText("Depart")).toBeInTheDocument();
    expect(screen.getByText("Return")).toBeInTheDocument();
    expect(screen.getByText("09:00")).toBeInTheDocument();
    expect(screen.getByText("20:00")).toBeInTheDocument();
    expect(screen.getByLabelText("Travel from previous stop: 3.4 km, 18 min")).toBeInTheDocument();
    expect(screen.getByText("Taxi from Seine cruise to Hotel Lutetia.")).toBeInTheDocument();
    expect(screen.getByText("Collect stored bags at reception.")).toBeInTheDocument();
    expect(screen.getByText("Confirm late front-desk access.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hotel Lutetia: Mark confirmed" })).toBeInTheDocument();
    expect(screen.getByText("3 planned stops")).toBeInTheDocument();
    expect(screen.getByLabelText("Map stop 1")).toHaveTextContent("1");
    expect(screen.getByLabelText("Map stop 2")).toHaveTextContent("2");
    expect(screen.getByLabelText("Map stop 3")).toHaveTextContent("3");
  });

  it("combines a destination hotel return after an intercity transfer", async () => {
    const baseStop = itinerary.days[0].stops[0];
    fetchItineraryMock.mockResolvedValue({
      ...itinerary,
      stats: { days: 1, stops: 5, booked: 0 },
      days: [{
        ...itinerary.days[0],
        stops: [
          { ...baseStop, name: "Trident Udaipur", kind: "hotel", note: "Check-out" },
          { ...baseStop, name: "Drive: Udaipur to Mount Abu", kind: "transport" },
          { ...baseStop, name: "Hotel Hillock Mount Abu", kind: "hotel", note: "Check-in" },
          { ...baseStop, name: "Nakki Lake", kind: "attraction" },
          {
            ...baseStop,
            name: "Hotel Hillock Mount Abu",
            kind: "hotel",
            note: "Return to hotel",
            travel_from_previous: {
              distance_km: 1.5,
              duration_min: 20,
              mode: "Walk",
              distance_display: "1.5 km",
              duration_display: "20 min",
              detail: "Walk from Nakki Lake to Hotel Hillock Mount Abu.",
            },
          },
        ],
      }],
    });

    render(<ItineraryPanel />);

    expect(await screen.findAllByText("Hotel Hillock Mount Abu")).toHaveLength(1);
    expect(screen.getByText("Trident Udaipur")).toBeInTheDocument();
    expect(screen.getByText("Check out")).toBeInTheDocument();
    expect(screen.getByLabelText("Hotel circuit marker for Hotel Hillock Mount Abu")).toBeInTheDocument();
    expect(screen.getByLabelText("Travel from previous stop: 1.5 km, 20 min")).toBeInTheDocument();
    expect(document.querySelector('[data-stop-name="hotel hillock mount abu"]')).toHaveAttribute(
      "data-stop-indexes",
      "3,5",
    );
  });

  it("keeps the combined hotel row addressable from either route endpoint", async () => {
    const hotel = { ...itinerary.days[0].stops[0], name: "Hotel Lutetia", kind: "hotel" };
    fetchItineraryMock.mockResolvedValue({
      ...itinerary,
      stats: { days: 1, stops: 3, booked: 0 },
      days: [{ ...itinerary.days[0], stops: [hotel, itinerary.days[0].stops[0], hotel] }],
    });

    render(<ItineraryPanel focusName="Hotel Lutetia" focusDay={1} focusStop={3} />);

    const marker = await screen.findByLabelText("Hotel circuit marker for Hotel Lutetia");
    expect(marker).toHaveAttribute("aria-current", "location");
    const circuitRow = document.querySelector('[data-stop-name="hotel lutetia"]');
    expect(circuitRow).toHaveAttribute("data-stop-indexes", "1,3");
    expect(scrollIntoViewMock.mock.instances[0]).toBe(circuitRow);
  });

  it("keeps different hotel endpoints as explicit checkout and checkin rows", async () => {
    fetchItineraryMock.mockResolvedValue({
      ...itinerary,
      stats: { days: 1, stops: 3, booked: 0 },
      days: [{
        ...itinerary.days[0],
        stops: [
          { ...itinerary.days[0].stops[0], name: "Hotel Lutetia", kind: "hotel", time: "09:00" },
          itinerary.days[0].stops[0],
          { ...itinerary.days[0].stops[0], name: "Le Roch Hotel", kind: "hotel", time: "18:00" },
        ],
      }],
    });

    render(<ItineraryPanel />);

    expect(await screen.findAllByLabelText("Hotel map marker")).toHaveLength(2);
    expect(screen.getByText("Hotel Lutetia")).toBeInTheDocument();
    expect(screen.getByText("Le Roch Hotel")).toBeInTheDocument();
    expect(screen.getByText("Check out")).toBeInTheDocument();
    expect(screen.getByText("Check in")).toBeInTheDocument();
  });

  it("uses the full hotel-to-hotel span for the schedule", async () => {
    fetchItineraryMock.mockResolvedValue({
      ...itinerary,
      days: [{
        ...itinerary.days[0],
        schedule: {
          ...itinerary.days[0].schedule!,
          start: "09:00",
          end: "18:00",
          duration_min: 540,
          duration_display: "9 hr",
        },
        stops: [
          { ...itinerary.days[0].stops[0], name: "Hotel Lutetia", kind: "hotel", time: "9:00 AM", duration_min: null },
          itinerary.days[0].stops[0],
          { ...itinerary.days[0].stops[0], name: "Hotel Lutetia", kind: "hotel", time: "6:00 PM", duration_min: null },
        ],
      }],
    });

    render(<ItineraryPanel />);

    expect((await screen.findByText("Schedule duration:")).parentElement).toHaveTextContent("9 hr · 09:00–18:00");
    expect(screen.getAllByText(/09:00/).length).toBeGreaterThan(0);
  });

  it("ends the schedule at a final transit arrival", async () => {
    fetchItineraryMock.mockResolvedValue({
      ...itinerary,
      days: [{
        ...itinerary.days[0],
        schedule: {
          ...itinerary.days[0].schedule!,
          start: "08:00",
          end: "13:30",
          duration_min: 330,
          duration_display: "5 hr 30 min",
        },
        stops: [
          { ...itinerary.days[0].stops[0], time: "8:00", duration_min: 120 },
          { ...itinerary.days[0].stops[1], name: "Gare du Nord", kind: "transport", time: "13:30", duration_min: 60 },
        ],
      }],
    });

    render(<ItineraryPanel />);

    expect((await screen.findByText("Schedule duration:")).parentElement).toHaveTextContent("5 hr 30 min · 08:00–13:30");
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

  it("scrolls an all-days map jump to the trip summary at the top", async () => {
    const scrollTo = vi.fn();
    Object.defineProperty(HTMLElement.prototype, "scrollTo", { configurable: true, value: scrollTo });

    render(<ItineraryPanel jumpTo={{ summary: true, token: 18 }} />);

    await screen.findByText("Museums and river");
    await waitFor(() => expect(scrollTo).toHaveBeenCalledWith({ top: 0, behavior: "smooth" }));
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

    const bookingAction = await screen.findByRole("button", { name: "Louvre Museum: Mark confirmed" });
    fireEvent.click(bookingAction);
    expect(bookingAction).toHaveAttribute("aria-pressed", "true");
    expect(bookingAction).toHaveTextContent("Confirmed");

    await waitFor(() => expect(bookingAction).toHaveAttribute("aria-pressed", "false"));
    expect(bookingAction).toHaveTextContent("Needs booking");
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
