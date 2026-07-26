import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
const { emptyView, fetchTripViewMock, selectItemMock, deselectItemMock, isAnonymousUserMock, shareActiveTripMock } = vi.hoisted(() => ({
  fetchTripViewMock: vi.fn(),
  selectItemMock: vi.fn(),
  deselectItemMock: vi.fn(),
  isAnonymousUserMock: vi.fn(() => true),
  shareActiveTripMock: vi.fn(),
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
  selectItem: selectItemMock,
  deselectItem: deselectItemMock,
  startNewTrip: vi.fn(),
  shareActiveTrip: shareActiveTripMock,
  tripIcsUrl: vi.fn(() => "/api/trip/export.ics"),
  isAnonymousUser: isAnonymousUserMock,
  getDisplayName: vi.fn(() => "Munish"),
}));

vi.mock("./components/ChatPanel", () => ({
  default: ({ hideGlobalControls, assistantRequest }: { hideGlobalControls?: boolean; assistantRequest?: { message: string } | null }) => (
    <div data-testid="chat-panel" data-global-controls-hidden={hideGlobalControls ? "true" : "false"} data-assistant-request={assistantRequest?.message ?? ""} />
  ),
}));
vi.mock("./components/ItineraryPanel", () => ({
  default: ({ reloadToken, onStopFocus, onDayMap, jumpTo, overview, focusDay, focusStop }: { reloadToken: number; onStopFocus: (kind: string, name: string, day?: number, stop?: number) => void; onDayMap?: (day: number) => void; jumpTo?: { day: number; name?: string } | null; overview?: typeof emptyView.overview | null; focusDay?: number; focusStop?: number }) => (
    <div>
      <button
        type="button"
        data-testid="itinerary-panel"
        data-reload-token={reloadToken}
        data-jump-day={jumpTo?.day ?? ""}
        data-jump-name={jumpTo?.name ?? ""}
        data-overview-status={overview?.status ?? ""}
        data-overview-counts={overview ? `${overview.counts.days}d · ${overview.counts.hotels} stay · ${overview.counts.activities} places` : ""}
        data-overview-cost={overview?.total_cost_display ?? ""}
        data-focus-day={focusDay ?? ""}
        data-focus-stop={focusStop ?? ""}
        onClick={() => onStopFocus("attraction", "Louvre Museum")}
      />
      <button type="button" onClick={() => onStopFocus("hotel", "Goa Marriott", 2, 1)}>
        Focus Day 2 hotel
      </button>
      <button type="button" onClick={() => onDayMap?.(3)}>Show complete Day 3 circuit</button>
    </div>
  ),
}));
vi.mock("./components/MapPanel", () => ({
  default: ({ onPinFocus, onDayFocus, focusName, focusDay, focusToken, circuitFocusDay, circuitFocusToken }: { onPinFocus: (kind: string, name: string) => void; onDayFocus?: (day: number) => void; focusName?: string | null; focusDay?: number; focusToken?: number; circuitFocusDay?: number; circuitFocusToken?: number }) => (
    <div data-testid="map-panel" data-focus-name={focusName ?? ""} data-focus-day={focusDay ?? ""} data-focus-token={focusToken ?? 0} data-circuit-day={circuitFocusDay ?? ""} data-circuit-token={circuitFocusToken ?? 0}>
      <button type="button" onClick={() => onPinFocus("attraction", "Louvre Museum")}>Focus pin</button>
      <button type="button" onClick={() => onDayFocus?.(2)}>Focus Day 2</button>
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
    isAnonymousUserMock.mockReset().mockReturnValue(true);
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

  it("shows a concise wrapping update near the trip identity", async () => {
    fetchTripViewMock.mockResolvedValue({
      ...emptyView,
      alerts: ["Removed Eiffel Tower and refreshed the itinerary."],
    });
    setDesktop(true);
    render(<App />);

    const status = await screen.findByRole("status");
    expect(status.parentElement).toHaveClass("mr-auto", "flex-1");
    expect(screen.getByText("Removed Eiffel Tower.")).toHaveClass(
      "line-clamp-2",
      "whitespace-normal",
    );
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
    expect(screen.getByRole("separator", { name: "Resize details and chat" })).toHaveAttribute("aria-valuenow", "46");

    fireEvent.keyDown(screen.getByRole("separator", { name: "Resize map and details" }), { key: "ArrowLeft" });
    expect(screen.getByRole("separator", { name: "Resize map and details" })).toHaveAttribute("aria-valuenow", "33");
    expect(localStorage.getItem("tripplanner_inspector_pct")).toBe("33");
    expect(screen.getByRole("navigation", { name: "Workspace controls" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /New trip/ })).toBeInTheDocument();
  });

  it("hides Details and Assistant independently while keeping both mounted", async () => {
    setDesktop(true);
    render(<App />);

    await waitFor(() => expect(screen.getAllByTestId("chat-panel")).toHaveLength(1));
    fireEvent.click(screen.getByRole("button", { name: "Hide Details" }));
    expect(screen.getAllByTestId("chat-panel")).toHaveLength(1);
    expect(screen.getByTestId("chat-panel").closest("section")).not.toHaveClass("hidden");
    expect(screen.getByTestId("trip-panel").closest("section")).toHaveClass("hidden");

    fireEvent.click(screen.getByTitle("Show or hide trip details"));
    fireEvent.click(screen.getByRole("button", { name: "Hide Assistant" }));
    expect(screen.getAllByTestId("chat-panel")).toHaveLength(1);
    expect(screen.getByTestId("chat-panel").closest("section")).toHaveClass("hidden");
    expect(screen.getByTestId("trip-panel").closest("section")).not.toHaveClass("hidden");
  });

  it("maximizes and restores Details and Assistant independently", async () => {
    setDesktop(true);
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("context-inspector")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Maximize Details" }));
    expect(screen.getByRole("button", { name: "Restore Details" })).toBeInTheDocument();
    expect(screen.getByTestId("map-panel").closest("section")).toHaveClass("hidden");
    expect(screen.getByTestId("chat-panel").closest("section")).toHaveClass("hidden");

    fireEvent.click(screen.getByRole("button", { name: "Restore Details" }));
    fireEvent.click(screen.getByRole("button", { name: "Maximize Assistant" }));
    expect(screen.getByRole("button", { name: "Restore Assistant" })).toBeInTheDocument();
    expect(screen.getByTestId("trip-panel").closest("section")).toHaveClass("hidden");
    expect(screen.getByTestId("chat-panel").closest("section")).not.toHaveClass("hidden");
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
    expect(screen.getByTestId("map-panel")).toHaveAttribute("data-circuit-day", "2");
    expect(screen.getByTestId("map-panel")).toHaveAttribute("data-focus-name", "");
    expect(screen.getByTestId("trip-panel")).toHaveAttribute("data-focus-name", "");
    expect(fetchTripViewMock).toHaveBeenCalledTimes(1);
  });

  it("frames an itinerary day circuit without converting it into place focus", async () => {
    setDesktop(true);
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("map-panel")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Focus Day 2 hotel" }));
    expect(screen.getByTestId("map-panel")).toHaveAttribute("data-focus-name", "Goa Marriott");
    const fetchesBeforeDayFocus = fetchTripViewMock.mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "Show complete Day 3 circuit" }));

    expect(screen.getByTestId("map-panel")).toHaveAttribute("data-circuit-day", "3");
    expect(screen.getByTestId("map-panel")).not.toHaveAttribute("data-circuit-token", "0");
    expect(screen.getByTestId("map-panel")).toHaveAttribute("data-focus-name", "");
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
    expect(screen.getByTestId("context-inspector").parentElement).not.toHaveClass("hidden");
    fireEvent.click(screen.getByTitle("Show or hide trip details"));
    expect(screen.getByTestId("context-inspector")).toBeInTheDocument();
  });

  it("groups export, share, and calendar actions in the common bar", async () => {
    fetchTripViewMock.mockResolvedValue({ ...emptyView, has_trip: true });
    setDesktop(true);
    render(<App />);

    await waitFor(() => expect(screen.getByRole("button", { name: "Guest - sign in" })).toBeInTheDocument());
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

    await waitFor(() => expect(screen.getByRole("button", { name: "Guest - sign in" })).toBeInTheDocument());
    isAnonymousUserMock.mockReturnValue(false);
    fireEvent(window, new Event("tripplanner:identity-changed"));
    await waitFor(() => expect(screen.getByRole("button", { name: "Signed in as Munish" })).toBeInTheDocument());
  });

  it("loads itinerary place focus into both the map state and details pane", async () => {
    const focusedView = {
      ...emptyView,
      focus: { kind: "attraction", name: "Louvre Museum" },
    };
    fetchTripViewMock.mockResolvedValueOnce(emptyView).mockResolvedValueOnce(focusedView);
    setDesktop(true);
    render(<App />);

    await waitFor(() => expect(fetchTripViewMock).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByTestId("itinerary-panel"));

    await waitFor(() => expect(screen.getByTestId("trip-panel")).toHaveAttribute("data-focus-name", "Louvre Museum"));
    expect(fetchTripViewMock.mock.calls[1][0]).toEqual({ kind: "attraction", name: "Louvre Museum" });
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
