import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import RightRail from "./RightRail";

vi.mock("./ItineraryPanel", () => ({
  default: () => <div data-testid="itinerary-panel" />,
}));

const mapPanelProps = vi.fn();
vi.mock("./MapPanel", () => ({
  default: (props: Record<string, unknown>) => {
    mapPanelProps(props);
    return <div data-testid="map-panel" />;
  },
}));

vi.mock("./TripSwitcher", () => ({
  default: () => <div data-testid="trip-switcher" />,
}));

const overview = {
  destination: "",
  origin: "",
  departure_date: "",
  return_date: "",
  travelers: 1,
  status: "draft" as const,
  notes: "",
  counts: { flights: 0, hotels: 0, activities: 0, days: 0 },
  total_cost: 0,
  total_cost_display: "",
};

const route = {
  distance_km: 4,
  duration_min: 20,
  mode: "Walk",
  distance_display: "4 km",
  duration_display: "20 min",
};

const days = [
  { day: 1, label: "Day 1", color: "#bd542f", pin_ids: ["one"], route },
  { day: 2, label: "Day 2", color: "#668064", pin_ids: ["two"], route },
];

function baseProps(overrides: Partial<React.ComponentProps<typeof RightRail>> = {}) {
  return {
    filters: [],
    onFilterToggle: vi.fn(),
    overview,
    photos: <div data-testid="photos" />,
    reloadToken: 0,
    itineraryJump: null,
    hasTrip: true,
    days,
    sequenceOpen: false,
    onToggleSequence: vi.fn(),
    focusName: null,
    onStopFocus: vi.fn(),
    onStopMap: vi.fn(),
    onDayMap: vi.fn(),
    onMapDayFocus: vi.fn(),
    onMapAllDaysFocus: vi.fn(),
    tripVersion: 0,
    onSwitched: vi.fn(),
    mapOpen: true,
    onToggleMap: vi.fn(),
    ...overrides,
  };
}

describe("RightRail", () => {
  it("shows the shared day bar as soon as the itinerary has a trip, independent of the map", () => {
    render(<RightRail {...baseProps()} />);

    expect(
      screen.getByRole("navigation", { name: "Trip days and stop sequence" }),
    ).toBeInTheDocument();
  });

  it("hides the day bar when there is no active trip yet", () => {
    render(<RightRail {...baseProps({ hasTrip: false })} />);

    expect(
      screen.queryByRole("navigation", { name: "Trip days and stop sequence" }),
    ).not.toBeInTheDocument();
  });

  it("routes day-bar clicks through the same handlers the map uses", () => {
    const onMapDayFocus = vi.fn();
    const onMapAllDaysFocus = vi.fn();
    render(<RightRail {...baseProps({ onMapDayFocus, onMapAllDaysFocus })} />);

    fireEvent.click(screen.getByRole("button", { name: "Day 2" }));
    fireEvent.click(screen.getByRole("button", { name: "All days" }));

    expect(onMapDayFocus).toHaveBeenCalledWith(2);
    expect(onMapAllDaysFocus).toHaveBeenCalled();
  });

  it("tells MapPanel to suppress its own private day row since the shared bar replaces it", () => {
    render(<RightRail {...baseProps()} />);

    expect(mapPanelProps).toHaveBeenCalled();
    const props = mapPanelProps.mock.calls[mapPanelProps.mock.calls.length - 1]?.[0];
    expect(props.showWorkspaceNavigation).toBe(false);
  });

  it("keeps the map's sequence toggle in sync with the shared bar's state", () => {
    const onToggleSequence = vi.fn();
    render(<RightRail {...baseProps({ sequenceOpen: true, onToggleSequence })} />);

    const props = mapPanelProps.mock.calls[mapPanelProps.mock.calls.length - 1]?.[0];
    expect(props.sequenceOpen).toBe(true);
    props.onSequenceOpenChange(false);
    expect(onToggleSequence).toHaveBeenCalled();
  });
});
