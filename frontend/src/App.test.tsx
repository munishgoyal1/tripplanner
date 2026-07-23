import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
const { emptyView, fetchTripViewMock } = vi.hoisted(() => ({
  fetchTripViewMock: vi.fn(),
  emptyView: {
  has_trip: false,
  title: "",
  destination: "",
  focus: null,
  is_fallback: false,
  empty_message: "",
  overview: {
    destination: "",
    origin: "",
    departure_date: "",
    return_date: "",
    travelers: 1,
    status: "draft",
    notes: "",
    counts: { flights: 0, hotels: 0, activities: 0, days: 0 },
    total_cost: null,
    total_cost_display: "",
  },
  items: [],
  },
}));

vi.mock("./api", () => ({
  fetchTripView: fetchTripViewMock,
  importSharedTrip: vi.fn(),
  selectItem: vi.fn(),
  deselectItem: vi.fn(),
}));

vi.mock("./components/ChatPanel", () => ({
  default: () => <div data-testid="chat-panel" />,
}));
vi.mock("./components/ItineraryPanel", () => ({
  default: ({ reloadToken }: { reloadToken: number }) => (
    <div data-testid="itinerary-panel" data-reload-token={reloadToken} />
  ),
}));
vi.mock("./components/MapPanel", () => ({
  default: ({ onPinFocus }: { onPinFocus: (kind: string, name: string) => void }) => (
    <button type="button" data-testid="map-panel" onClick={() => onPinFocus("attraction", "Louvre Museum")} />
  ),
}));
vi.mock("./components/TripPanel", () => ({
  default: () => <div data-testid="trip-panel" />,
}));
vi.mock("./components/TripSwitcher", () => ({
  default: () => <div data-testid="trip-switcher" />,
}));
vi.mock("./components/RightRail", () => ({
  default: () => <div data-testid="right-rail" />,
}));

function setDesktop(matches: boolean) {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: vi.fn().mockImplementation(() => ({
      matches,
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

describe("App responsive workspace", () => {
  beforeEach(() => {
    localStorage.clear();
    window.history.replaceState({}, "", "/");
    fetchTripViewMock.mockReset().mockResolvedValue(emptyView);
  });

  it.each([
    ["desktop", true],
    ["mobile", false],
  ])("mounts one chat workspace on %s", async (_label, desktop) => {
    setDesktop(desktop);
    render(<App />);

    await waitFor(() => expect(screen.getAllByTestId("chat-panel")).toHaveLength(1));
  });

  it("resizes the desktop canvas with arrow keys", () => {
    setDesktop(true);
    render(<App />);
    const separator = screen.getByRole("separator", { name: "Resize trip canvas and details" });

    expect(separator).toHaveAttribute("aria-valuenow", "62");
    fireEvent.keyDown(separator, { key: "ArrowRight" });
    expect(separator).toHaveAttribute("aria-valuenow", "65");
  });

  it("does not reload itinerary data for focus-only navigation", async () => {
    setDesktop(true);
    render(<App />);
    const itinerary = screen.getByTestId("itinerary-panel");
    expect(itinerary).toHaveAttribute("data-reload-token", "0");

    fireEvent.click(screen.getByTestId("map-panel"));

    await waitFor(() => expect(fetchTripViewMock).toHaveBeenCalledTimes(2));
    expect(itinerary).toHaveAttribute("data-reload-token", "0");
  });
});
