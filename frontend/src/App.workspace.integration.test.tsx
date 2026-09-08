import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const mocks = vi.hoisted(() => ({
  fetchTripView: vi.fn(),
  fetchWorkspace: vi.fn(),
  fetchItinerary: vi.fn(),
  fetchMapView: vi.fn(),
  deselectItem: vi.fn(),
}));

vi.mock("./api", () => ({
  fetchTripView: mocks.fetchTripView,
  fetchWorkspace: mocks.fetchWorkspace,
  fetchItinerary: mocks.fetchItinerary,
  fetchMapView: mocks.fetchMapView,
  fetchMapsConfig: vi.fn(() => Promise.resolve({ enabled: false, places_enabled: false, key: "" })),
  fetchPreferences: vi.fn(() => Promise.resolve({
    display_currency_configured: false,
    display_currency: "USD",
    display_region: "",
    home_country: "",
  })),
  fetchDocumentReadiness: vi.fn(() => Promise.resolve({ checks: [], blockers: 0, warnings: 0, badge: "" })),
  fetchVerification: vi.fn(() => Promise.resolve(null)),
  getCachedOverview: vi.fn(() => null),
  fetchDestinationOverview: vi.fn(() => Promise.reject(new Error("not loaded in workspace test"))),
  setStopBooked: vi.fn(),
  repairTrip: vi.fn(),
  confirmStopPlace: vi.fn(),
  importSharedTrip: vi.fn(),
  selectItem: vi.fn(),
  deselectItem: mocks.deselectItem,
  startNewTrip: vi.fn(),
  resetTrip: vi.fn(),
  shareActiveTrip: vi.fn(),
  tripIcsUrl: vi.fn(() => "/api/trip/export.ics"),
  isAnonymousUser: vi.fn(() => true),
  getDisplayName: vi.fn(() => "Munish"),
  getUserId: vi.fn(() => "web-test"),
}));

vi.mock("./components/ChatPanel", () => ({
  default: () => <div data-testid="chat-panel" />,
}));
vi.mock("./components/DestinationGuide", () => ({
  default: () => <div data-testid="destination-guide" />,
}));
vi.mock("./components/TripSwitcher", () => ({
  default: ({ onSwitched }: { onSwitched: (tripId: string, workspace: unknown) => void }) => (
    <button type="button" onClick={() => onSwitched("rome-trip", romeWorkspace)}>
      Switch to Rome
    </button>
  ),
}));
vi.mock("./components/RightRail", () => ({ default: () => <div /> }));
vi.mock("./components/ExportModal", () => ({ default: () => <div /> }));

const overview = (destination: string) => ({
  destination,
  origin: "Delhi",
  departure_date: "2026-09-12",
  return_date: "2026-09-16",
  travelers: 2,
  status: "draft",
  notes: "",
  counts: { flights: 0, hotels: 0, activities: 1, days: 1 },
  total_cost: null,
  total_cost_display: "",
});

const tripView = (destination: string, place: string, selected = true) => ({
  trip_id: `${destination.toLowerCase()}-trip`,
  has_trip: true,
  title: destination,
  destination,
  focus: null,
  is_fallback: false,
  empty_message: "",
  available_days: [1],
  alerts: [],
  overview: overview(destination),
  items: [{
    kind: "attraction",
    name: place,
    selected,
    rating: 4.7,
    review_count: 100,
    address: `${destination} center`,
    summary: "",
    website: "",
    photos: [],
    reviews: [],
    occurrences: [{ day: 1, stop: 1, time: "10:00" }],
  }],
});

const itinerary = (destination: string, place: string, includeStop = true) => ({
  has_itinerary: true,
  destination,
  currency: "EUR",
  stats: { days: 1, stops: includeStop ? 1 : 0, booked: 0 },
  days: [{
    day: 1,
    date: "2026-09-12",
    title: destination === "Paris" ? "Museums and river" : "Ancient Rome",
    summary: "A compact day in the city.",
    color: "#2563eb",
    reachability: "All stops are nearby.",
    google_maps_url: "",
    route: {
      distance_km: 2,
      duration_min: 20,
      mode: "walk",
      distance_display: "2 km",
      duration_display: "20 min",
    },
    schedule: {
      start: "10:00",
      end: "12:00",
      duration_min: 120,
      duration_display: "2 hr",
      travel_duration_min: 20,
      travel_duration_display: "20 min",
      estimated: false,
    },
    stops: includeStop ? [{
      name: place,
      kind: "attraction",
      time: "10:00",
      duration_min: 120,
      note: "",
      booked: false,
      selected: true,
      color: "#2563eb",
    }] : [],
  }],
});

const mapView = (destination: string, place: string) => ({
  enabled: false,
  destination,
  center: null,
  pins: [{
    id: place.toLowerCase().replaceAll(" ", "-"),
    name: place,
    kind: "attraction",
    selected: true,
    day: 1,
    lat: 0,
    lng: 0,
    rating: 4.7,
    address: `${destination} center`,
    photo: null,
    occurrences: [{ day: 1, stop: 1, time: "10:00" }],
  }],
  days: [{
    day: 1,
    label: "Day 1",
    color: "#2563eb",
    pin_ids: [place.toLowerCase().replaceAll(" ", "-")],
    route: {
      distance_km: 2,
      duration_min: 20,
      mode: "walk",
      distance_display: "2 km",
      duration_display: "20 min",
    },
  }],
  available_days: [1],
  unscheduled_pin_ids: [],
  airport: null,
  empty_message: "Map unavailable in tests.",
});

const parisView = tripView("Paris", "Louvre Museum");
const parisWorkspace = {
  view: parisView,
  itinerary: itinerary("Paris", "Louvre Museum"),
  map: mapView("Paris", "Louvre Museum"),
};
const romeWorkspace = {
  view: tripView("Rome", "Colosseum"),
  itinerary: itinerary("Rome", "Colosseum"),
  map: mapView("Rome", "Colosseum"),
};

function setDesktop() {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: vi.fn(() => ({
      matches: true,
      media: "(min-width: 768px)",
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  return { promise: new Promise<T>((done) => { resolve = done; }), resolve };
}

describe("App real workspace panes", () => {
  beforeEach(() => {
    localStorage.clear();
    window.history.replaceState({}, "", "/");
    setDesktop();
    mocks.fetchWorkspace.mockReset().mockResolvedValue(parisWorkspace);
    mocks.fetchTripView.mockReset();
    mocks.fetchItinerary.mockReset().mockResolvedValue(parisWorkspace.itinerary);
    mocks.fetchMapView.mockReset().mockResolvedValue(parisWorkspace.map);
    mocks.deselectItem.mockReset();
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: vi.fn(),
    });
  });

  it("keeps real panes on the authoritative removal after an older focus refresh resolves", async () => {
    const staleFocus = deferred<typeof parisView>();
    mocks.fetchTripView.mockReturnValue(staleFocus.promise);
    mocks.fetchItinerary
      .mockResolvedValueOnce(parisWorkspace.itinerary)
      .mockResolvedValue(itinerary("Paris", "Louvre Museum", false));
    mocks.deselectItem.mockResolvedValue({
      view: {
        ...parisView,
        focus: { kind: "attraction", name: "Louvre Museum", day: 1, stop: 1 },
        items: [{ ...parisView.items[0], selected: false }],
      },
      alerts: ["Removed Louvre Museum."],
    });
    render(<App />);

    const day = await screen.findByRole("heading", { name: "Museums and river" });
    fireEvent.click(within(day.closest("section")!).getByRole("button", { name: "Louvre Museum" }));
    expect(await screen.findByRole("heading", { name: "Louvre Museum" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Remove Louvre Museum from itinerary" }));

    await waitFor(() => expect(mocks.deselectItem).toHaveBeenCalledTimes(1));
    expect(await screen.findByRole("button", { name: "+ Add to trip" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove Louvre Museum from trip" }))
      .not.toBeInTheDocument();
    staleFocus.resolve(parisView);
    await Promise.resolve();

    expect(screen.getByRole("heading", { name: "Louvre Museum" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "+ Add to trip" })).toBeInTheDocument();
    expect(screen.getByText("Museums and river")).toBeInTheDocument();
  });

  it("keeps all real panes on a switched trip after an older focus refresh resolves", async () => {
    const staleFocus = deferred<typeof parisView>();
    mocks.fetchTripView.mockReturnValue(staleFocus.promise);
    render(<App />);

    const parisDay = await screen.findByRole("heading", { name: "Museums and river" });
    fireEvent.click(within(parisDay.closest("section")!).getByRole("button", { name: "Louvre Museum" }));
    expect(await screen.findByRole("heading", { name: "Louvre Museum" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Switch to Rome" }));

    expect(await screen.findByRole("heading", { name: "Ancient Rome" })).toBeInTheDocument();
    expect(screen.getByText("Rome")).toBeInTheDocument();
    staleFocus.resolve(parisView);
    await Promise.resolve();

    expect(screen.getByRole("heading", { name: "Ancient Rome" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Louvre Museum" })).not.toBeInTheDocument();
  });
});
