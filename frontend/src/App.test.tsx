import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
const { emptyView, fetchTripViewMock, selectItemMock, deselectItemMock, startNewTripMock, isAnonymousUserMock, shareActiveTripMock, resetTripMock } = vi.hoisted(() => ({
  fetchTripViewMock: vi.fn(),
  selectItemMock: vi.fn(),
  deselectItemMock: vi.fn(),
  startNewTripMock: vi.fn(),
  isAnonymousUserMock: vi.fn(() => true),
  shareActiveTripMock: vi.fn(),
  resetTripMock: vi.fn(),
  emptyView: {
  trip_id: null,
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
  fetchPreferences: vi.fn(() => Promise.resolve({
    display_currency_configured: false,
    display_currency: "USD",
    display_region: "",
    home_country: "",
  })),
  importSharedTrip: vi.fn(),
  selectItem: selectItemMock,
  deselectItem: deselectItemMock,
  startNewTrip: startNewTripMock,
  resetTrip: resetTripMock,
  shareActiveTrip: shareActiveTripMock,
  tripIcsUrl: vi.fn(() => "/api/trip/export.ics"),
  isAnonymousUser: isAnonymousUserMock,
  getDisplayName: vi.fn(() => "Munish"),
  fetchDocumentReadiness: vi.fn(() => Promise.resolve({ checks: [], blockers: 0, warnings: 0, badge: "" })),
}));

vi.mock("./components/ChatPanel", () => ({
  default: ({ hideGlobalControls, assistantRequest, layout, onChangeLayout, onHide, turnEffects, onEffectSelect, onTurnComplete, onTurnStatus }: { hideGlobalControls?: boolean; assistantRequest?: { message: string } | null; layout?: string; onChangeLayout?: (layout: "bar" | "sheet" | "full") => void; onHide?: () => void; turnEffects?: { effects: { kind: string; name: string; change: string }[] } | null; onEffectSelect?: (effect: { kind: string; name: string; day?: number; stop?: number; change: string }) => void; onTurnComplete?: (tripId?: string, context?: { proposalOnly: boolean; startedWithoutTrip: boolean; request: string; reply: string }) => void; onTurnStatus?: (status: { phase: "working" | "loading" | "complete" | "error"; message: string } | null) => void }) => (
    <div data-testid="chat-panel" data-global-controls-hidden={hideGlobalControls ? "true" : "false"} data-assistant-request={assistantRequest?.message ?? ""} data-layout={layout ?? "panel"} data-turn-effects={(turnEffects?.effects ?? []).map((effect) => `${effect.name}:${effect.change}`).join(",")}>
      <button type="button" onClick={() => onHide?.()}>Hide Chat</button>
      <button type="button" onClick={() => onChangeLayout?.("sheet")}>Conversation</button>
      <button type="button" onClick={() => onChangeLayout?.("full")}>Maximize conversation</button>
      <button type="button" onClick={() => onChangeLayout?.("bar")}>Minimize conversation</button>
      <button type="button" onClick={() => onTurnComplete?.("khandala-pune-1")}>Complete planning turn</button>
      <button type="button" onClick={() => onEffectSelect?.({ kind: "attraction", name: "Louvre Museum", day: 2, stop: 1, change: "added" })}>Open turn effect</button>
      <button type="button" onClick={() => onTurnStatus?.({ phase: "working", message: "Searching hotels. 45s elapsed. Full itinerary builds usually take about 2–4 minutes." })}>Report planning progress</button>
      <button type="button" onClick={() => {
        onTurnStatus?.({ phase: "loading", message: "Wrapping up" });
        void onTurnComplete?.("khandala-pune-1", { proposalOnly: false, startedWithoutTrip: true, request: "plan a trip", reply: "" });
      }}>Finish new itinerary</button>
      <button type="button" onClick={() => {
        onTurnStatus?.({ phase: "loading", message: "Wrapping up" });
        void onTurnComplete?.("khandala-pune-1", { proposalOnly: false, startedWithoutTrip: false, request: "rebalance day 3", reply: "" });
      }}>Finish itinerary update</button>
      <button type="button" onClick={() => {
        void onTurnComplete?.("khandala-pune-1", { proposalOnly: false, startedWithoutTrip: false, request: "total time on road?", reply: "Total estimated road time is about 20 hours 28 minutes." });
      }}>Answer a question</button>
    </div>
  ),
}));
vi.mock("./components/ItineraryPanel", () => ({
  default: ({ filters = [], onFilterToggle, reloadToken, onStopFocus, onStopMap, onDayMap, onAllDaysMap, jumpTo, overview, focusDay, focusStop, circuitFocusDay, circuitFocusToken }: { filters?: string[]; onFilterToggle?: (filter: "flight" | "road" | "train" | "hotel") => void; reloadToken: number; onStopFocus: (kind: string, name: string, day?: number, stop?: number, routeCircuitId?: string) => void; onStopMap?: (kind: string, name: string, day?: number, stop?: number, routeCircuitId?: string) => void; onDayMap?: (day: number) => void; onAllDaysMap?: () => void; jumpTo?: { day: number; name?: string } | { summary: true } | null; overview?: typeof emptyView.overview | null; focusDay?: number; focusStop?: number; circuitFocusDay?: number; circuitFocusToken?: number }) => (
    <div>
      <button
        type="button"
        data-testid="itinerary-panel"
        data-filters={filters.join(",")}
        data-reload-token={reloadToken}
        data-jump-day={jumpTo && "day" in jumpTo ? jumpTo.day : ""}
        data-jump-name={jumpTo && "day" in jumpTo ? jumpTo.name ?? "" : ""}
        data-jump-summary={jumpTo && "summary" in jumpTo ? "true" : "false"}
        data-overview-status={overview?.status ?? ""}
        data-overview-counts={overview ? `${overview.counts.days}d · ${overview.counts.hotels} stay · ${overview.counts.activities} places` : ""}
        data-overview-cost={overview?.total_cost_display ?? ""}
        data-focus-day={focusDay ?? ""}
        data-focus-stop={focusStop ?? ""}
        data-circuit-day={circuitFocusDay ?? ""}
        data-circuit-token={circuitFocusToken ?? 0}
        onClick={() => onStopFocus("attraction", "Louvre Museum", 2, 1)}
      />
      <button type="button" onClick={() => onFilterToggle?.("flight")}>Toggle Flights filter</button>
      <button type="button" onClick={() => onFilterToggle?.("hotel")}>Toggle Hotels filter</button>
      <button type="button" onClick={() => onStopFocus("hotel", "Goa Marriott", 2, 1)}>
        Focus Day 2 hotel
      </button>
      <button type="button" onClick={() => onStopMap?.("airport", "Udaipur Airport", 1, 3)}>
        Show Udaipur Airport on map
      </button>
      <button type="button" onClick={() => onStopFocus("flight", "Flight: Bengaluru to Udaipur", 1, 2)}>
        Focus inter-city flight
      </button>
      <button type="button" onClick={() => onStopMap?.("flight", "Flight: Bengaluru to Udaipur", 1, 2)}>
        Map inter-city flight
      </button>
      <button type="button" onClick={() => onStopFocus("other", "Car ride from Gangtok to Lachung", 4, 2)}>
        Focus legacy car drive
      </button>
      <button type="button" onClick={() => onStopFocus("transport", "Gangtok to Lachung", 4, 2, "drive-day-4-gangtok-to-lachung")}>
        Focus exact Gangtok drive
      </button>
      <button type="button" onClick={() => onDayMap?.(3)}>Show complete Day 3 circuit</button>
      <button type="button" onClick={() => onAllDaysMap?.()}>Show all days from snapshot</button>
    </div>
  ),
}));
vi.mock("./components/MapPanel", () => ({
  default: ({ filters = [], reloadToken, onPinFocus, onDayFocus, onAllDaysFocus, focusName, focusDay, focusToken, circuitFocusDay, circuitFocusToken, routeFocusDay, routeFocusId, routeFocusToken }: { filters?: string[]; reloadToken?: number; onPinFocus: (kind: string, name: string, day?: number, stop?: number) => void; onDayFocus?: (day: number) => void; onAllDaysFocus?: () => void; focusName?: string | null; focusDay?: number; focusToken?: number; circuitFocusDay?: number; circuitFocusToken?: number; routeFocusDay?: number; routeFocusId?: string; routeFocusToken?: number }) => (
    <div data-testid="map-panel" data-filters={filters.join(",")} data-reload-token={reloadToken ?? 0} data-focus-name={focusName ?? ""} data-focus-day={focusDay ?? ""} data-focus-token={focusToken ?? 0} data-circuit-day={circuitFocusDay ?? ""} data-circuit-token={circuitFocusToken ?? 0} data-route-day={routeFocusDay ?? ""} data-route-id={routeFocusId ?? ""} data-route-token={routeFocusToken ?? 0}>
      <button type="button" onClick={() => onPinFocus("attraction", "Louvre Museum")}>Focus pin</button>
      <button type="button" onClick={() => onPinFocus("airport", "Udaipur Airport", 1, 3)}>Focus airport pin</button>
      <button type="button" onClick={() => onDayFocus?.(2)}>Focus Day 2</button>
      <button type="button" onClick={() => onAllDaysFocus?.()}>Focus All days</button>
    </div>
  ),
}));
vi.mock("./components/TripPanel", () => ({
  default: ({ view, onSelect, onDeselect }: { view: { focus?: { name?: string } | null; items?: { name: string; selected?: boolean }[] } | null; onSelect?: (kind: string, name: string) => void; onDeselect?: (kind: string, name: string) => void }) => (
    <div data-testid="trip-panel" data-focus-name={view?.focus?.name ?? ""} data-items={(view?.items ?? []).map((item) => item.name).join(",")} data-selected={(view?.items ?? []).map((item) => String(item.selected)).join(",")}>
      <button type="button" onClick={() => onSelect?.("attraction", "Eiffel Tower")}>Add Eiffel Tower</button>
      <button type="button" onClick={() => onDeselect?.("attraction", "Eiffel Tower")}>Remove Eiffel Tower</button>
    </div>
  ),
}));
vi.mock("./components/TripSwitcher", () => ({
  default: ({ onSwitched }: { onSwitched: (tripId: string, view: unknown) => void }) => (
    <div data-testid="trip-switcher">
      <button
        type="button"
        onClick={() => onSwitched("rome-trip", {
          ...emptyView,
          has_trip: true,
          title: "Rome",
          destination: "Rome",
          items: [{ name: "Colosseum", kind: "attraction", selected: true }],
        })}
      >
        Switch to Rome
      </button>
    </div>
  ),
}));
vi.mock("./components/RightRail", () => ({
  default: () => <div data-testid="right-rail" />,
}));
vi.mock("./components/ExportModal", () => ({
  default: () => <div role="dialog" aria-label="Export itinerary dialog" />,
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
    shareActiveTripMock.mockReset().mockResolvedValue("https://example.com/shared-trip");
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
    selectItemMock.mockReset();
    deselectItemMock.mockReset();
    startNewTripMock.mockReset().mockResolvedValue(undefined);
    isAnonymousUserMock.mockReset().mockReturnValue(true);
  });

  it("shares unioned itinerary filters with the map", async () => {
    setDesktop(true);
    render(<App />);

    await screen.findByTestId("itinerary-panel");
    fireEvent.click(screen.getByRole("button", { name: "Focus Day 2" }));
    expect(screen.getByTestId("map-panel")).toHaveAttribute("data-circuit-day", "2");
    fireEvent.click(screen.getByRole("button", { name: "Toggle Flights filter" }));
    expect(screen.getByTestId("map-panel")).toHaveAttribute("data-circuit-day", "");
    fireEvent.click(screen.getByRole("button", { name: "Toggle Hotels filter" }));

    expect(screen.getByTestId("itinerary-panel")).toHaveAttribute("data-filters", "flight,hotel");
    expect(screen.getByTestId("map-panel")).toHaveAttribute("data-filters", "flight,hotel");

    fireEvent.click(screen.getByRole("button", { name: "Toggle Flights filter" }));
    expect(screen.getByTestId("itinerary-panel")).toHaveAttribute("data-filters", "hotel");
    expect(screen.getByTestId("map-panel")).toHaveAttribute("data-filters", "hotel");

    fireEvent.click(screen.getByRole("button", { name: "Switch to Rome" }));
    await waitFor(() => expect(screen.getByTestId("itinerary-panel")).toHaveAttribute("data-filters", ""));
    expect(screen.getByTestId("map-panel")).toHaveAttribute("data-filters", "");
  });

  it.each([
    ["desktop", true],
    ["mobile", false],
  ])("mounts one chat workspace on %s", async (_label, desktop) => {
    setDesktop(desktop);
    render(<App />);

    await waitFor(() => expect(screen.getAllByTestId("chat-panel")).toHaveLength(1));
  });

  it("keeps the desktop shell mounted when the backend returns no trip", async () => {
    fetchTripViewMock.mockResolvedValue({ ...emptyView, overview: null });
    setDesktop(true);
    render(<App />);

    await waitFor(() => expect(fetchTripViewMock).toHaveBeenCalledTimes(1));
    expect(screen.getByTestId("chat-panel")).toBeInTheDocument();
    expect(screen.getByTestId("trip-switcher")).toBeInTheDocument();
  });

  it("keeps the removed place focused when an older refresh resolves later", async () => {
    let resolveStaleRefresh!: (value: unknown) => void;
    const selectedView = {
      ...emptyView,
      has_trip: true,
      items: [{ name: "Eiffel Tower", kind: "attraction", selected: true }],
    };
    const focusedRemovedView = {
      ...selectedView,
      focus: { kind: "attraction", name: "Eiffel Tower" },
      items: [{ name: "Eiffel Tower", kind: "attraction", selected: false }],
    };
    fetchTripViewMock
      .mockResolvedValueOnce(selectedView)
      .mockImplementationOnce(() => new Promise((resolve) => {
        resolveStaleRefresh = resolve;
      }))
      .mockResolvedValueOnce(focusedRemovedView);
    deselectItemMock.mockResolvedValue({ view: focusedRemovedView, alerts: ["Removed Eiffel Tower."] });
    setDesktop(true);
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("trip-panel")).toHaveAttribute("data-items", "Eiffel Tower"));
    fireEvent.click(screen.getByRole("button", { name: "Focus pin" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove Eiffel Tower" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove Eiffel Tower" }));

    await waitFor(() => expect(deselectItemMock).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByTestId("trip-panel")).toHaveAttribute("data-selected", "false"));
    resolveStaleRefresh(selectedView);
    await Promise.resolve();
    expect(screen.getByTestId("trip-panel")).toHaveAttribute("data-focus-name", "Eiffel Tower");
    expect(screen.getByTestId("trip-panel")).toHaveAttribute("data-selected", "false");
  });

  it("applies the authoritative selected view immediately after add", async () => {
    const unselectedView = {
      ...emptyView,
      has_trip: true,
      items: [{ name: "Eiffel Tower", kind: "attraction", selected: false }],
    };
    const selectedView = {
      ...unselectedView,
      focus: { kind: "attraction", name: "Eiffel Tower" },
      items: [{ name: "Eiffel Tower", kind: "attraction", selected: true }],
    };
    fetchTripViewMock.mockResolvedValue(unselectedView);
    selectItemMock.mockResolvedValue({ view: selectedView, alerts: ["Added Eiffel Tower."] });
    setDesktop(true);
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("trip-panel")).toHaveAttribute("data-selected", "false"));
    fireEvent.click(screen.getByRole("button", { name: "Add Eiffel Tower" }));

    await waitFor(() => expect(screen.getByTestId("trip-panel")).toHaveAttribute("data-selected", "true"));
    expect(screen.getByTestId("trip-panel")).toHaveAttribute("data-focus-name", "Eiffel Tower");
  });

  it("retries a map add while the Assistant still owns the workspace", async () => {
    const unselectedView = {
      ...emptyView,
      has_trip: true,
      items: [{ name: "Eiffel Tower", kind: "attraction", selected: false }],
    };
    const selectedView = {
      ...unselectedView,
      focus: { kind: "attraction", name: "Eiffel Tower" },
      items: [{ name: "Eiffel Tower", kind: "attraction", selected: true }],
    };
    fetchTripViewMock.mockResolvedValue(unselectedView);
    selectItemMock
      .mockRejectedValueOnce({ status: 409, retryAfterMs: 0 })
      .mockResolvedValueOnce({ view: selectedView, alerts: ["Added Eiffel Tower."] });
    setDesktop(true);
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("trip-panel")).toHaveAttribute("data-selected", "false"));
    fireEvent.click(screen.getByRole("button", { name: "Add Eiffel Tower" }));

    await waitFor(() => expect(selectItemMock).toHaveBeenCalledTimes(2));
    expect(screen.getByTestId("trip-panel")).toHaveAttribute("data-selected", "true");
  });

  it("retries New trip while the Assistant still owns the workspace", async () => {
    startNewTripMock
      .mockRejectedValueOnce({ status: 409, retryAfterMs: 0 })
      .mockResolvedValueOnce(undefined);
    setDesktop(true);
    render(<App />);

    await screen.findByTestId("chat-panel");
    fireEvent.click(screen.getByRole("button", { name: "New trip" }));

    await waitFor(() => expect(startNewTripMock).toHaveBeenCalledTimes(2));
    expect(screen.queryByText(/Could not start a new trip/i)).not.toBeInTheDocument();
  });

  it("does not let an older details refresh overwrite a switched trip", async () => {
    let resolveOldRefresh!: (value: unknown) => void;
    const parisView = {
      ...emptyView,
      has_trip: true,
      title: "Paris",
      destination: "Paris",
      items: [{ name: "Eiffel Tower", kind: "attraction", selected: true }],
    };
    fetchTripViewMock
      .mockResolvedValueOnce(parisView)
      .mockImplementationOnce(() => new Promise((resolve) => {
        resolveOldRefresh = resolve;
      }));
    setDesktop(true);
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("trip-panel")).toHaveAttribute("data-items", "Eiffel Tower"));
    fireEvent.click(screen.getByRole("button", { name: "Focus pin" }));
    fireEvent.click(screen.getByRole("button", { name: "Switch to Rome" }));

    await waitFor(() => expect(screen.getByTestId("trip-panel")).toHaveAttribute("data-items", "Colosseum"));
    resolveOldRefresh(parisView);
    await Promise.resolve();
    expect(screen.getByTestId("trip-panel")).toHaveAttribute("data-items", "Colosseum");
    expect(screen.getByTestId("trip-panel")).toHaveAttribute("data-focus-name", "");
  });

  it("rejects a stale trip view after a new-trip turn completes", async () => {
    const parisView = {
      ...emptyView,
      trip_id: "paris-trip",
      has_trip: true,
      destination: "Paris",
      items: [{ name: "Eiffel Tower", kind: "attraction", selected: true }],
    };
    fetchTripViewMock.mockResolvedValue(parisView);
    setDesktop(true);
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("trip-panel")).toHaveAttribute("data-items", "Eiffel Tower"));
    fireEvent.click(screen.getByRole("button", { name: "Finish new itinerary" }));

    expect(await screen.findByText(/Could not load the updated itinerary/i)).toBeInTheDocument();
    expect(screen.getByTestId("trip-panel")).toHaveAttribute("data-items", "Eiffel Tower");
  });

  it("shows a headline update with the consequence underneath it", async () => {
    fetchTripViewMock.mockResolvedValue({
      ...emptyView,
      alerts: [
        "Removed Eiffel Tower and refreshed the itinerary.",
        "Day 2 was packed, so I moved Musée d'Orsay to Day 3.",
      ],
    });
    setDesktop(true);
    render(<App />);

    const status = await screen.findByRole("status");
    expect(status.parentElement).toHaveClass("mr-auto", "flex-1");
    expect(screen.getByText("Removed Eiffel Tower.")).toHaveClass("truncate");
    expect(
      screen.getByText("Day 2 was packed, so I moved Musée d'Orsay to Day 3."),
    ).toHaveClass("line-clamp-2", "whitespace-normal");
  });

  it("resets the trip only after the user confirms", async () => {
    resetTripMock.mockResolvedValue(null);
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    setDesktop(true);
    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "Reset trip" }));
    expect(resetTripMock).not.toHaveBeenCalled();

    confirm.mockReturnValue(true);
    fireEvent.click(screen.getByRole("button", { name: "Reset trip" }));
    await waitFor(() => expect(resetTripMock).toHaveBeenCalled());
    expect(await screen.findByText("Trip reset")).toBeInTheDocument();
    confirm.mockRestore();
  });

  it("keeps timely build progress in the top bar until the refreshed itinerary is ready", async () => {
    fetchTripViewMock
      .mockResolvedValueOnce(emptyView)
      .mockResolvedValueOnce({ ...emptyView, trip_id: "khandala-pune-1", has_trip: true });
    setDesktop(true);
    render(<App />);

    await waitFor(() => expect(fetchTripViewMock).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: "Report planning progress" }));
    expect(screen.getByText(/Searching hotels\. 45s elapsed/)).toHaveClass("text-brand");

    fireEvent.click(screen.getByRole("button", { name: "Finish new itinerary" }));
    expect(screen.getByText("Wrapping up")).toBeInTheDocument();
    expect(await screen.findByText(/Your itinerary is ready/)).toHaveClass("text-emerald-700");
  });

  it("does not claim an itinerary update for a turn that only answered a question", async () => {
    fetchTripViewMock.mockResolvedValue({
      ...emptyView,
      trip_id: "khandala-pune-1",
      has_trip: true,
      destination: "Madhya Pradesh",
    });
    setDesktop(true);
    render(<App />);

    await waitFor(() => expect(fetchTripViewMock).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: "Answer a question" }));

    expect(await screen.findByText(/Answered in chat/)).toBeInTheDocument();
    expect(
      screen.getByText("Total estimated road time is about 20 hours 28 minutes."),
    ).toBeInTheDocument();
  });

  it("summarizes an itinerary modification after its refreshed view loads", async () => {
    fetchTripViewMock
      .mockResolvedValueOnce({ ...emptyView, trip_id: "khandala-pune-1", has_trip: true })
      .mockResolvedValueOnce({
        ...emptyView,
        trip_id: "khandala-pune-1",
        has_trip: true,
        alerts: ["Rebalanced Day 3 itinerary around the museum closure."],
      });
    setDesktop(true);
    render(<App />);

    await waitFor(() => expect(fetchTripViewMock).toHaveBeenCalledOnce());
    fireEvent.click(screen.getByRole("button", { name: "Finish itinerary update" }));

    expect(await screen.findByText("Itinerary refreshed.")).toHaveClass("text-emerald-700");
  });

  it("keeps itinerary, map, and wider details together with accessible resize controls", async () => {
    setDesktop(true);
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("context-inspector")).toBeInTheDocument());
    expect(screen.getByTestId("itinerary-panel")).toBeInTheDocument();
    expect(screen.getByTestId("map-panel")).toBeInTheDocument();
    expect(screen.getByTestId("trip-panel")).toBeInTheDocument();
    expect(screen.getByRole("separator", { name: "Resize itinerary and map" })).toHaveAttribute("aria-valuenow", "24");
    expect(screen.getByRole("separator", { name: "Resize map and details" })).toHaveAttribute("aria-valuenow", "31");

    fireEvent.keyDown(screen.getByRole("separator", { name: "Resize map and details" }), { key: "ArrowLeft" });
    expect(screen.getByRole("separator", { name: "Resize map and details" })).toHaveAttribute("aria-valuenow", "33");
    expect(localStorage.getItem("tripplanner_inspector_pct")).toBe("33");
    expect(screen.getByRole("navigation", { name: "Workspace controls" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /New trip/ })).toBeInTheDocument();
  });

  it("lets panes use available width and allows every pane to be hidden and restored", async () => {
    setDesktop(true);
    const rendered = render(<App />);

    await waitFor(() => expect(screen.getByTestId("context-inspector")).toBeInTheDocument());
    const detailsSeparator = screen.getByRole("separator", { name: "Resize map and details" });
    for (let index = 0; index < 10; index += 1) {
      fireEvent.keyDown(detailsSeparator, { key: "ArrowLeft" });
    }
    expect(detailsSeparator).toHaveAttribute("aria-valuenow", "51");

    fireEvent.click(screen.getByRole("button", { name: "Hide Details" }));
    const itinerarySeparator = screen.getByRole("separator", { name: "Resize itinerary and map" });
    for (let index = 0; index < 20; index += 1) {
      fireEvent.keyDown(itinerarySeparator, { key: "ArrowRight" });
    }
    expect(itinerarySeparator).toHaveAttribute("aria-valuenow", "64");

    fireEvent.click(screen.getByRole("button", { name: "Hide Itinerary" }));
    fireEvent.click(screen.getByRole("button", { name: "Hide Map" }));
    fireEvent.click(screen.getByRole("button", { name: "Hide Chat" }));

    for (const title of [
      "Show or hide itinerary",
      "Show or hide map",
      "Show or hide trip details",
      "Show or hide chat",
    ]) {
      expect(screen.getByTitle(title)).toHaveAttribute("aria-pressed", "false");
    }
    expect(screen.queryByRole("separator")).not.toBeInTheDocument();

    await waitFor(() => {
      expect(localStorage.getItem("tripplanner_itinerary_open")).toBe("false");
      expect(localStorage.getItem("tripplanner_map_open")).toBe("false");
      expect(localStorage.getItem("tripplanner_details_open")).toBe("false");
      expect(localStorage.getItem("tripplanner_assistant_open")).toBe("false");
    });
    rendered.unmount();
    render(<App />);
    expect(screen.getByTitle("Show or hide map")).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(screen.getByTitle("Show or hide map"));
    expect(screen.getByTitle("Show or hide map")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("map-panel").closest("section")).not.toHaveClass("hidden");
  });

  it("supports every desktop pane visibility combination", async () => {
    setDesktop(true);
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("context-inspector")).toBeInTheDocument());
    const panes = [
      ["Show or hide itinerary", "itinerary"],
      ["Show or hide map", "map"],
      ["Show or hide trip details", "details"],
      ["Show or hide chat", "assistant"],
    ] as const;

    for (let mask = 0; mask < 16; mask += 1) {
      panes.forEach(([title], index) => {
        const shouldOpen = Boolean(mask & (1 << index));
        const control = screen.getByTitle(title);
        if ((control.getAttribute("aria-pressed") === "true") !== shouldOpen) {
          fireEvent.click(control);
        }
        expect(control).toHaveAttribute("aria-pressed", String(shouldOpen));
      });
    }
  });

  it("uses direct meaning-first controls for workspace surfaces", async () => {
    setDesktop(true);
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("context-inspector")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "New trip" })).toHaveClass("bg-brand/10", "text-brand");
    expect(screen.getByText("New trip", { selector: "nav span" })).toBeInTheDocument();
    expect(screen.getByLabelText("Pane visibility")).toBeInTheDocument();
    const itinerary = screen.getByTitle("Show or hide itinerary");
    expect(itinerary).toHaveClass("rounded-md", "bg-white", "text-slate-700");
    expect(itinerary.querySelector("svg.lucide-list")).toBeInTheDocument();
    expect(screen.getByText("Itinerary", { selector: "nav span" })).toBeInTheDocument();
    expect(screen.getByText("Map", { selector: "nav span" })).toBeInTheDocument();
    expect(screen.getByText("Details", { selector: "nav span" })).toBeInTheDocument();
    expect(screen.getByText("Chat", { selector: "nav span" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Trip actions" })).toHaveClass("text-slate-400");
    expect(screen.getByRole("button", { name: "Account settings" })).toHaveTextContent("Guest");
    expect(screen.queryByRole("button", { name: "Travel preferences" })).not.toBeInTheDocument();
  });

  it("closes Details and Assistant independently while keeping both mounted", async () => {
    setDesktop(true);
    render(<App />);

    await waitFor(() => expect(screen.getAllByTestId("chat-panel")).toHaveLength(1));
    expect(screen.getByTestId("chat-panel").closest("section")).not.toHaveClass("hidden");
    fireEvent.click(screen.getByRole("button", { name: "Hide Details" }));
    expect(screen.getAllByTestId("chat-panel")).toHaveLength(1);
    expect(screen.getByTestId("chat-panel").closest("section")).not.toHaveClass("hidden");
    expect(screen.getByTestId("trip-panel").closest("section")).toHaveClass("hidden");

    fireEvent.click(screen.getByTitle("Show or hide trip details"));
    fireEvent.click(screen.getByRole("button", { name: "Hide Chat" }));
    expect(screen.getAllByTestId("chat-panel")).toHaveLength(1);
    expect(screen.getByTestId("chat-panel").closest("section")).toHaveClass("hidden");
    expect(screen.getByTestId("trip-panel").closest("section")).not.toHaveClass("hidden");
  });

  it("uses restrained icon groups for pane-local controls", async () => {
    setDesktop(true);
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("context-inspector")).toBeInTheDocument());
    for (const label of ["Itinerary", "Map", "Details"]) {
      const controls = screen.getByRole("group", { name: `${label} pane controls` });
      expect(controls).toHaveClass("bg-slate-50", "ring-inset");
      expect(screen.getByRole("button", { name: `Hide ${label}` })).toHaveClass("rounded-[5px]");
      expect(screen.getByRole("button", { name: `Maximize ${label}` })).toHaveClass("rounded-[5px]");
    }
  });

  it("maximizes and restores Details independently", async () => {
    setDesktop(true);
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("context-inspector")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Maximize Details" }));
    expect(screen.getByRole("button", { name: "Restore Details" })).toBeInTheDocument();
    expect(screen.getByTestId("map-panel").closest("section")).toHaveClass("hidden");
    // The composer is the way out of a maximized pane, so the dock stays put.
    expect(screen.getByTestId("chat-panel").closest("section")).not.toHaveClass("hidden");

    fireEvent.click(screen.getByRole("button", { name: "Restore Details" }));
    expect(screen.getByTestId("trip-panel").closest("section")).not.toHaveClass("hidden");
    expect(screen.getByTestId("chat-panel").closest("section")).not.toHaveClass("hidden");
  });

  it("docks Assistant as a bottom row that expands over the workspace", async () => {
    setDesktop(true);
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("chat-panel")).toBeInTheDocument());
    const dock = screen.getByTestId("chat-panel").closest("section");
    const workspace = screen.getByTestId("itinerary-panel").closest("main");
    expect(workspace?.getAttribute("style") ?? "").not.toContain("23rem");
    expect(dock?.previousElementSibling).toBe(workspace);
    expect(screen.queryByTestId("assistant-modal")).not.toBeInTheDocument();
    expect(screen.getByTestId("map-panel")).toBeInTheDocument();
    expect(screen.getByTestId("context-inspector")).toBeInTheDocument();

    expect(screen.getByTestId("chat-panel")).toHaveAttribute("data-layout", "bar");
    fireEvent.click(screen.getByRole("button", { name: "Conversation" }));
    expect(screen.getByTestId("chat-panel")).toHaveAttribute("data-layout", "sheet");
    fireEvent.click(screen.getByRole("button", { name: "Maximize conversation" }));
    expect(screen.getByTestId("chat-panel")).toHaveAttribute("data-layout", "full");
    // Expanding the conversation never costs the user a pane.
    expect(screen.getByTestId("itinerary-panel").closest("section")).not.toHaveClass("hidden");
    expect(screen.getByTestId("context-inspector").parentElement).not.toHaveClass("hidden");

    fireEvent.click(screen.getByRole("button", { name: "Minimize conversation" }));
    expect(screen.getByTestId("chat-panel")).toHaveAttribute("data-layout", "bar");
  });

  it("reopens the Assistant dock at its single-row default", async () => {
    setDesktop(true);
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("chat-panel")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Maximize conversation" }));
    expect(screen.getByTestId("chat-panel")).toHaveAttribute("data-layout", "full");

    fireEvent.click(screen.getByRole("button", { name: "Hide Chat" }));
    fireEvent.click(screen.getByTitle("Show or hide chat"));
    expect(screen.getByTestId("chat-panel")).toHaveAttribute("data-layout", "bar");
  });

  it("moves the workspace to a stop named by an Assistant reply", async () => {
    setDesktop(true);
    fetchTripViewMock
      .mockResolvedValueOnce(emptyView)
      .mockResolvedValueOnce({
        ...emptyView,
        focus: { kind: "attraction", name: "Louvre Museum", day: 2, stop: 1 },
        items: [{ name: "Louvre Museum", kind: "attraction", selected: true }],
      });
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("chat-panel")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Open turn effect" }));

    await waitFor(() => expect(screen.getByTestId("map-panel")).toHaveAttribute("data-focus-name", "Louvre Museum"));
    expect(screen.getByTestId("map-panel")).toHaveAttribute("data-focus-day", "2");
    expect(screen.getByTestId("itinerary-panel")).toHaveAttribute("data-focus-stop", "1");
    expect(screen.getByTitle("Show or hide map")).toHaveAttribute("aria-pressed", "true");
  });

  it("closes and reopens Assistant from the command bar without unmounting chat", async () => {
    setDesktop(true);
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("chat-panel")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Hide Chat" }));
    expect(screen.getByTestId("chat-panel").closest("section")).toHaveClass("hidden");
    expect(screen.getAllByTestId("chat-panel")).toHaveLength(1);
    fireEvent.click(screen.getByTitle("Show or hide chat"));
    expect(screen.getByTestId("chat-panel").closest("section")).not.toHaveClass("hidden");
    expect(screen.getAllByTestId("chat-panel")).toHaveLength(1);
  });

  it("does not reload itinerary data for focus-only navigation", async () => {
    setDesktop(true);
    render(<App />);
    const itinerary = screen.getByTestId("itinerary-panel");
    expect(itinerary).toHaveAttribute("data-reload-token", "0");

    fireEvent.click(screen.getByRole("button", { name: "Focus pin" }));

    await waitFor(() => expect(fetchTripViewMock).toHaveBeenCalledTimes(2));
    expect(itinerary).toHaveAttribute("data-reload-token", "0");
  });

  it("opens airport details and keeps its exact map occurrence focused", async () => {
    setDesktop(true);
    fetchTripViewMock
      .mockResolvedValueOnce(emptyView)
      .mockResolvedValueOnce({
        ...emptyView,
        focus: { kind: "airport", name: "Udaipur Airport", day: 1, stop: 3 },
        items: [{ name: "Udaipur Airport", kind: "airport", selected: false }],
      });
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("map-panel")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Show Udaipur Airport on map" }));

    await waitFor(() => expect(screen.getByTestId("trip-panel")).toHaveAttribute("data-focus-name", "Udaipur Airport"));
    expect(screen.getByTestId("map-panel")).toHaveAttribute("data-focus-day", "1");
    expect(screen.getByText("Place details")).toBeInTheDocument();
    expect(fetchTripViewMock).toHaveBeenLastCalledWith({
      kind: "airport",
      name: "Udaipur Airport",
      day: 1,
      stop: 3,
    }, expect.any(Object));
  });

  it("retains shared occurrence focus from an airport marker", async () => {
    setDesktop(true);
    fetchTripViewMock
      .mockResolvedValueOnce(emptyView)
      .mockResolvedValueOnce({
        ...emptyView,
        focus: { kind: "airport", name: "Udaipur Airport", day: 1, stop: 3 },
        items: [{ name: "Udaipur Airport", kind: "airport", selected: false }],
      });
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("map-panel")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Focus airport pin" }));

    await waitFor(() => expect(screen.getByTestId("trip-panel")).toHaveAttribute("data-focus-name", "Udaipur Airport"));
    expect(screen.getByTestId("map-panel")).toHaveAttribute("data-focus-day", "1");
    expect(screen.getByTestId("itinerary-panel")).toHaveAttribute("data-focus-stop", "3");
    expect(fetchTripViewMock).toHaveBeenCalledTimes(2);
  });

  it("frames the complete inter-city route without opening place details", async () => {
    setDesktop(true);
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("map-panel")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("itinerary-panel"));
    expect(screen.getByTestId("map-panel")).toHaveAttribute("data-focus-name", "Louvre Museum");
    fireEvent.click(screen.getByRole("button", { name: "Focus inter-city flight" }));

    expect(screen.getByTestId("map-panel")).toHaveAttribute("data-route-day", "1");
    expect(screen.getByTestId("map-panel")).not.toHaveAttribute("data-route-token", "0");
    expect(screen.getByTestId("map-panel")).toHaveAttribute("data-focus-name", "");
    expect(screen.getByTestId("trip-panel")).toHaveAttribute("data-focus-name", "");

    const firstRouteToken = screen.getByTestId("map-panel").getAttribute("data-route-token");
    fireEvent.click(screen.getByRole("button", { name: "Map inter-city flight" }));
    expect(screen.getByTestId("map-panel")).not.toHaveAttribute("data-route-token", firstRouteToken);

    fireEvent.click(screen.getByRole("button", { name: "Focus legacy car drive" }));
    expect(screen.getByTestId("map-panel")).toHaveAttribute("data-route-day", "4");
    expect(screen.getByTestId("map-panel")).toHaveAttribute("data-focus-name", "");

    fireEvent.click(screen.getByRole("button", { name: "Focus exact Gangtok drive" }));
    expect(screen.getByTestId("map-panel")).toHaveAttribute(
      "data-route-id",
      "drive-day-4-gangtok-to-lachung",
    );
  });

  it("refreshes itinerary and map as soon as a planning turn completes", async () => {
    setDesktop(true);
    render(<App />);

    expect(screen.getByTestId("itinerary-panel")).toHaveAttribute("data-reload-token", "0");
    expect(screen.getByTestId("map-panel")).toHaveAttribute("data-reload-token", "0");

    fireEvent.click(screen.getByRole("button", { name: "Complete planning turn" }));

    expect(screen.getByTestId("itinerary-panel")).toHaveAttribute("data-reload-token", "1");
    expect(screen.getByTestId("map-panel")).toHaveAttribute("data-reload-token", "1");
  });

  it("selects the stop a reply changed across every panel", async () => {
    setDesktop(true);
    const base = { ...emptyView, trip_id: "khandala-pune-1", has_trip: true, items: [] };
    const hotelSwapped = {
      ...base,
      items: [{
        name: "Budget Inn Indore",
        kind: "hotel",
        selected: true,
        occurrences: [{ day: 2, stop: 1 }],
      }],
    };
    fetchTripViewMock.mockReset().mockResolvedValue(base);
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("itinerary-panel")).toBeInTheDocument());
    // First turn adopts the trip id; the swap itself is the turn under test.
    fireEvent.click(screen.getByRole("button", { name: "Complete planning turn" }));
    await waitFor(() => expect(screen.getByTestId("itinerary-panel")).toHaveAttribute("data-reload-token", "1"));

    fetchTripViewMock.mockResolvedValue(hotelSwapped);
    fireEvent.click(screen.getByRole("button", { name: "Complete planning turn" }));

    await waitFor(() => expect(screen.getByTestId("itinerary-panel")).toHaveAttribute("data-jump-day", "2"));
    expect(screen.getByTestId("itinerary-panel")).toHaveAttribute("data-jump-name", "Budget Inn Indore");
    expect(screen.getByTestId("itinerary-panel")).toHaveAttribute("data-jump-summary", "false");
    expect(screen.getByTestId("chat-panel")).toHaveAttribute("data-turn-effects", "Budget Inn Indore:added");
    await waitFor(() => expect(screen.getByTestId("map-panel")).toHaveAttribute("data-focus-day", "2"));
    expect(screen.getByTestId("map-panel")).toHaveAttribute("data-focus-name", "Budget Inn Indore");
  });

  it("widens the selection to the whole trip when a reply changes several days", async () => {
    setDesktop(true);
    const base = { ...emptyView, trip_id: "khandala-pune-1", has_trip: true, items: [] };
    const cityAdded = {
      ...base,
      items: [
        { name: "Mandu Fort", kind: "attraction", selected: true, occurrences: [{ day: 3, stop: 1 }] },
        { name: "Rewa Kund", kind: "attraction", selected: true, occurrences: [{ day: 4, stop: 2 }] },
      ],
    };
    fetchTripViewMock.mockReset().mockResolvedValue(base);
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("itinerary-panel")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Complete planning turn" }));
    await waitFor(() => expect(screen.getByTestId("itinerary-panel")).toHaveAttribute("data-reload-token", "1"));

    fetchTripViewMock.mockResolvedValue(cityAdded);
    fireEvent.click(screen.getByRole("button", { name: "Complete planning turn" }));

    await waitFor(() => expect(screen.getByTestId("itinerary-panel")).toHaveAttribute("data-jump-summary", "true"));
    expect(screen.getByTestId("map-panel")).toHaveAttribute("data-circuit-day", "");
  });

  it("gives a map day chip the same aggregate circuit focus as an itinerary day header", async () => {
    fetchTripViewMock.mockResolvedValue({
      ...emptyView,
      has_trip: true,
      focus: { kind: "attraction", name: "Eiffel Tower", day: 1, stop: 2 },
      items: [{ kind: "attraction", name: "Eiffel Tower", selected: true }],
    });
    setDesktop(true);
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("itinerary-panel")).toBeInTheDocument());
    expect(screen.getByTestId("trip-panel")).toHaveAttribute("data-focus-name", "Eiffel Tower");
    fireEvent.click(screen.getByRole("button", { name: "Focus Day 2" }));

    expect(screen.getByTestId("itinerary-panel")).toHaveAttribute("data-jump-day", "2");
    expect(screen.getByTestId("itinerary-panel")).toHaveAttribute("data-circuit-day", "2");
    expect(screen.getByTestId("map-panel")).toHaveAttribute("data-circuit-day", "2");
    expect(screen.getByTestId("map-panel")).toHaveAttribute("data-focus-name", "");
    expect(screen.getByTestId("trip-panel")).toHaveAttribute("data-focus-name", "");
    expect(fetchTripViewMock).toHaveBeenCalledTimes(1);
  });

  it("shows all circuits and returns itinerary focus to the trip summary", async () => {
    setDesktop(true);
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("map-panel")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Focus Day 2" }));
    expect(screen.getByTestId("map-panel")).toHaveAttribute("data-circuit-day", "2");

    fireEvent.click(screen.getByRole("button", { name: "Focus All days" }));

    expect(screen.getByTestId("map-panel")).toHaveAttribute("data-circuit-day", "");
    expect(screen.getByTestId("map-panel")).toHaveAttribute("data-focus-name", "");
    expect(screen.getByTestId("itinerary-panel")).toHaveAttribute("data-jump-summary", "true");
  });

  it("maps a Trip Snapshot click to the shared All days focus", async () => {
    setDesktop(true);
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("map-panel")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Focus Day 2" }));
    expect(screen.getByTestId("itinerary-panel")).toHaveAttribute("data-circuit-day", "2");

    fireEvent.click(screen.getByRole("button", { name: "Show all days from snapshot" }));

    expect(screen.getByTestId("itinerary-panel")).toHaveAttribute("data-circuit-day", "");
    expect(screen.getByTestId("itinerary-panel")).not.toHaveAttribute("data-circuit-token", "0");
    expect(screen.getByTestId("map-panel")).toHaveAttribute("data-circuit-day", "");
    expect(screen.getByTestId("itinerary-panel")).toHaveAttribute("data-jump-summary", "true");
  });

  it("frames an itinerary day circuit without converting it into place focus", async () => {
    setDesktop(true);
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("map-panel")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("itinerary-panel"));
    expect(screen.getByTestId("map-panel")).toHaveAttribute("data-focus-name", "Louvre Museum");
    const fetchesBeforeDayFocus = fetchTripViewMock.mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "Show complete Day 3 circuit" }));

    expect(screen.getByTestId("map-panel")).toHaveAttribute("data-circuit-day", "3");
    expect(screen.getByTestId("map-panel")).not.toHaveAttribute("data-circuit-token", "0");
    expect(screen.getByTestId("map-panel")).toHaveAttribute("data-focus-name", "");
    expect(screen.getByTestId("itinerary-panel")).toHaveAttribute("data-jump-day", "3");
    expect(fetchTripViewMock).toHaveBeenCalledTimes(fetchesBeforeDayFocus);

    fireEvent.click(screen.getByRole("button", { name: "Focus Day 2 hotel" }));
    expect(screen.getByTestId("map-panel")).toHaveAttribute("data-focus-name", "Goa Marriott");
    expect(screen.getByTestId("map-panel")).toHaveAttribute("data-circuit-day", "");
    expect(screen.getByTestId("map-panel")).toHaveAttribute("data-circuit-token", "0");
  });

  it("shows an already-loaded focused place before its refresh completes", async () => {
    const initialView = {
      ...emptyView,
      has_trip: true,
      focus: { kind: "attraction", name: "Eiffel Tower" },
      items: [
        { kind: "attraction", name: "Eiffel Tower", selected: true },
        { kind: "attraction", name: "Louvre Museum", selected: true },
      ],
    };
    fetchTripViewMock
      .mockResolvedValueOnce(initialView)
      .mockImplementationOnce(() => new Promise(() => {}));
    setDesktop(true);
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("trip-panel")).toHaveAttribute(
      "data-focus-name",
      "Eiffel Tower",
    ));
    fireEvent.click(screen.getByTestId("itinerary-panel"));

    expect(screen.getByTestId("trip-panel")).toHaveAttribute("data-focus-name", "Louvre Museum");
    expect(screen.getByTestId("trip-panel")).toHaveAttribute(
      "data-items",
      "Louvre Museum,Eiffel Tower",
    );
  });

  it("focuses a place added from details without rebuilding the trip view", async () => {
    selectItemMock.mockResolvedValue({
      view: { ...emptyView, focus: { kind: "attraction", name: "Eiffel Tower" } },
      alerts: ["Added Eiffel Tower to your trip."],
      placement: { day: 2, stop: 3, name: "Eiffel Tower" },
      placements: [],
    });
    setDesktop(true);
    render(<App />);

    await waitFor(() => expect(fetchTripViewMock).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: "Add Eiffel Tower" }));

    await waitFor(() => expect(screen.getByTestId("map-panel")).toHaveAttribute("data-focus-name", "Eiffel Tower"));
    expect(screen.getByTestId("itinerary-panel")).toHaveAttribute("data-jump-day", "2");
    expect(screen.getByTestId("itinerary-panel")).toHaveAttribute("data-jump-name", "Eiffel Tower");
    expect(fetchTripViewMock).toHaveBeenCalledTimes(1);
  });

  it("offers planner review for a material mutation and respects keep or review", async () => {
    selectItemMock.mockResolvedValue({
      view: { ...emptyView, has_trip: true, focus: { kind: "attraction", name: "Eiffel Tower" } },
      alerts: ["Added Eiffel Tower to Day 3."],
      placement: { day: 3, stop: 6, name: "Eiffel Tower" },
      planner_review: {
        severity: "warning",
        day: 3,
        summary: "Day 3 may feel crowded: 5 planned places.",
        prompt: "Review Day 3 without changing it until I approve.",
      },
    });
    setDesktop(true);
    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "Add Eiffel Tower" }));

    expect(await screen.findByText(/Added Eiffel Tower to Day 3.*may feel crowded/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Review with planner" }));
    expect(screen.getByTestId("chat-panel")).toHaveAttribute(
      "data-assistant-request",
      "Review Day 3 without changing it until I approve.",
    );
    expect(screen.queryByRole("button", { name: "Keep as is" })).not.toBeInTheDocument();
  });

  it("keeps obvious recovery controls for every desktop pane", async () => {
    setDesktop(true);
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("map-panel")).toBeInTheDocument());
    expect(screen.getByTestId("chat-panel")).toHaveAttribute("data-global-controls-hidden", "true");

    fireEvent.click(screen.getByRole("button", { name: "Hide Map" }));
    expect(screen.getByTestId("map-panel").closest("section")).toHaveClass("hidden");
    fireEvent.click(screen.getByTitle("Show or hide map"));
    expect(screen.getByTestId("map-panel")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Hide Details" }));
    expect(screen.getByTestId("trip-panel").closest("section")).toHaveClass("hidden");
    expect(screen.getByTestId("context-inspector").parentElement).toHaveClass("hidden");
    expect(screen.getByTestId("chat-panel").closest("section")).not.toHaveClass("hidden");
    fireEvent.click(screen.getByTitle("Show or hide trip details"));
    expect(screen.getByTestId("context-inspector")).toBeInTheDocument();
  });

  it("groups export, share, and calendar actions in the common bar", async () => {
    fetchTripViewMock.mockResolvedValue({ ...emptyView, has_trip: true });
    setDesktop(true);
    render(<App />);

    await waitFor(() => expect(screen.getByRole("button", { name: "Account settings" })).toHaveTextContent("Guest"));
    fireEvent.click(screen.getByRole("button", { name: "Trip actions" }));
    expect(screen.getByRole("menuitem", { name: /Share trip/ })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /Add to calendar/ })).toHaveAttribute(
      "href",
      "/api/trip/export.ics",
    );
    fireEvent.click(screen.getByRole("menuitem", { name: /Share trip/ }));
    await waitFor(() => expect(screen.getByText("Link copied")).toBeInTheDocument());
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith("https://example.com/shared-trip");

    fireEvent.click(screen.getByRole("menuitem", { name: /Export itinerary/ }));
    expect(screen.getByRole("dialog", { name: "Export itinerary dialog" })).toBeInTheDocument();
  });

  it("updates the profile status when identity changes", async () => {
    setDesktop(true);
    render(<App />);

    await waitFor(() => expect(screen.getByRole("button", { name: "Account settings" })).toHaveTextContent("Guest"));
    isAnonymousUserMock.mockReturnValue(false);
    fireEvent(window, new Event("tripplanner:identity-changed"));
    await waitFor(() => expect(screen.getByRole("button", { name: "Account settings" })).toHaveTextContent("Munish"));
  });

  it("keeps an itinerary-only stop focused in its map occurrence and details after refresh", async () => {
    const focusedView = {
      ...emptyView,
      focus: { kind: "attraction", name: "Louvre Museum", day: 2, stop: 1 },
      items: [{ kind: "attraction", name: "Louvre Museum", selected: false }],
    };
    fetchTripViewMock.mockResolvedValueOnce(emptyView).mockResolvedValueOnce(focusedView);
    setDesktop(true);
    render(<App />);

    await waitFor(() => expect(fetchTripViewMock).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByTestId("itinerary-panel"));

    await waitFor(() => expect(screen.getByTestId("trip-panel")).toHaveAttribute("data-focus-name", "Louvre Museum"));
    expect(screen.getByTestId("map-panel")).toHaveAttribute("data-focus-name", "Louvre Museum");
    expect(screen.getByTestId("map-panel")).toHaveAttribute("data-focus-day", "2");
    expect(fetchTripViewMock.mock.calls[1][0]).toEqual({
      kind: "attraction",
      name: "Louvre Museum",
      day: 2,
      stop: 1,
    });
    expect(screen.getByText("Louvre Museum")).toBeInTheDocument();
  });

  it("preserves the itinerary day when focusing a repeated hotel", async () => {
    const focusedView = {
      ...emptyView,
      focus: { kind: "hotel", name: "Goa Marriott", day: 2, stop: 1 },
    };
    fetchTripViewMock.mockResolvedValueOnce(emptyView).mockResolvedValueOnce(focusedView);
    setDesktop(true);
    render(<App />);

    await waitFor(() => expect(fetchTripViewMock).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: "Focus Day 2 hotel" }));

    await waitFor(() => expect(screen.getByTestId("map-panel")).toHaveAttribute("data-focus-name", "Goa Marriott"));
    expect(screen.getByTestId("map-panel")).toHaveAttribute("data-focus-day", "2");
    expect(screen.getByTestId("itinerary-panel")).toHaveAttribute("data-focus-day", "2");
    expect(screen.getByTestId("itinerary-panel")).toHaveAttribute("data-focus-stop", "1");
    const firstFocusToken = screen.getByTestId("map-panel").getAttribute("data-focus-token");

    fireEvent.click(screen.getByRole("button", { name: "Focus Day 2 hotel" }));
    await waitFor(() => expect(screen.getByTestId("map-panel")).not.toHaveAttribute(
      "data-focus-token",
      firstFocusToken,
    ));
    expect(fetchTripViewMock.mock.calls[1][0]).toEqual({
      kind: "hotel",
      name: "Goa Marriott",
      day: 2,
      stop: 1,
    });
  });

  it("passes lifecycle and completeness data to the itinerary snapshot", async () => {
    fetchTripViewMock.mockResolvedValue({
      ...emptyView,
      has_trip: true,
      title: "Goa escape",
      destination: "Goa",
      overview: {
        ...emptyView.overview,
        destination: "Goa",
        status: "finalized",
        counts: { flights: 1, hotels: 1, activities: 4, days: 3 },
        total_cost_display: "₹45,000",
      },
    });
    setDesktop(true);
    render(<App />);

    const itineraryPanel = await screen.findByTestId("itinerary-panel");
    expect(itineraryPanel).toHaveAttribute("data-overview-status", "finalized");
    expect(itineraryPanel).toHaveAttribute("data-overview-counts", "3d · 1 stay · 4 places");
    expect(itineraryPanel).toHaveAttribute("data-overview-cost", "₹45,000");
    expect(screen.queryByText("3d · 1 stay · 4 places")).not.toBeInTheDocument();
  });
});
