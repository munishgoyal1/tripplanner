import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
const { emptyView, fetchTripViewMock, selectItemMock, deselectItemMock, isAnonymousUserMock } = vi.hoisted(() => ({
  fetchTripViewMock: vi.fn(),
  selectItemMock: vi.fn(),
  deselectItemMock: vi.fn(),
  isAnonymousUserMock: vi.fn(() => true),
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
  isAnonymousUser: isAnonymousUserMock,
  getDisplayName: vi.fn(() => "Munish"),
}));

vi.mock("./components/ChatPanel", () => ({
  default: ({ hideGlobalControls }: { hideGlobalControls?: boolean }) => (
    <div data-testid="chat-panel" data-global-controls-hidden={hideGlobalControls ? "true" : "false"} />
  ),
}));
vi.mock("./components/ItineraryPanel", () => ({
  default: ({ reloadToken, onStopFocus, jumpTo }: { reloadToken: number; onStopFocus: (kind: string, name: string) => void; jumpTo?: { day: number; name?: string } | null }) => (
    <button
      type="button"
      data-testid="itinerary-panel"
      data-reload-token={reloadToken}
      data-jump-day={jumpTo?.day ?? ""}
      data-jump-name={jumpTo?.name ?? ""}
      onClick={() => onStopFocus("attraction", "Louvre Museum")}
    />
  ),
}));
vi.mock("./components/MapPanel", () => ({
  default: ({ onPinFocus, onDayFocus, focusName }: { onPinFocus: (kind: string, name: string) => void; onDayFocus?: (day: number, place?: { kind: string; name: string }) => void; focusName?: string | null }) => (
    <div data-testid="map-panel" data-focus-name={focusName ?? ""}>
      <button type="button" onClick={() => onPinFocus("attraction", "Louvre Museum")}>Focus pin</button>
      <button type="button" onClick={() => onDayFocus?.(2, { kind: "attraction", name: "Eiffel Tower" })}>Focus Day 2</button>
    </div>
  ),
}));
vi.mock("./components/TripPanel", () => ({
  default: ({ view, onSelect, onDeselect }: { view: { focus?: { name?: string } | null; items?: { name: string }[] } | null; onSelect?: (kind: string, name: string) => void; onDeselect?: (kind: string, name: string) => void }) => (
    <div data-testid="trip-panel" data-focus-name={view?.focus?.name ?? ""} data-items={(view?.items ?? []).map((item) => item.name).join(",")}>
      <button type="button" onClick={() => onSelect?.("attraction", "Eiffel Tower")}>Add Eiffel Tower</button>
      <button type="button" onClick={() => onDeselect?.("attraction", "Eiffel Tower")}>Remove Eiffel Tower</button>
    </div>
  ),
}));
vi.mock("./components/TripSwitcher", () => ({
  default: () => <div data-testid="trip-switcher" />,
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

  it("keeps a successful removal when an older refresh resolves later", async () => {
    let resolveStaleRefresh!: (value: unknown) => void;
    const selectedView = {
      ...emptyView,
      has_trip: true,
      items: [{ name: "Eiffel Tower", kind: "attraction", selected: true }],
    };
    const removedView = { ...selectedView, items: [] };
    fetchTripViewMock
      .mockResolvedValueOnce(selectedView)
      .mockImplementationOnce(() => new Promise((resolve) => {
        resolveStaleRefresh = resolve;
      }));
    deselectItemMock.mockResolvedValue({ view: removedView, alerts: ["Removed Eiffel Tower."] });
    setDesktop(true);
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("trip-panel")).toHaveAttribute("data-items", "Eiffel Tower"));
    fireEvent.click(screen.getByRole("button", { name: "Focus pin" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove Eiffel Tower" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove Eiffel Tower" }));

    await waitFor(() => expect(deselectItemMock).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByTestId("trip-panel")).toHaveAttribute("data-items", ""));
    resolveStaleRefresh(selectedView);
    await Promise.resolve();
    expect(screen.getByTestId("trip-panel")).toHaveAttribute("data-items", "");
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

  it("syncs a map day filter to the matching itinerary day", async () => {
    fetchTripViewMock
      .mockResolvedValueOnce(emptyView)
      .mockResolvedValueOnce({ ...emptyView, focus: { kind: "attraction", name: "Eiffel Tower" } });
    setDesktop(true);
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("itinerary-panel")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Focus Day 2" }));

    expect(screen.getByTestId("itinerary-panel")).toHaveAttribute("data-jump-day", "2");
    await waitFor(() => expect(screen.getByTestId("trip-panel")).toHaveAttribute("data-focus-name", "Eiffel Tower"));
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

  it("shows guest identity status and opens export from the common bar", async () => {
    fetchTripViewMock.mockResolvedValue({ ...emptyView, has_trip: true });
    setDesktop(true);
    render(<App />);

    await waitFor(() => expect(screen.getByRole("button", { name: "Guest - sign in" })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Export itinerary" }));
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

  it("surfaces lifecycle and completeness status in the workspace command bar", async () => {
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

    await waitFor(() => expect(screen.getByText("finalized")).toBeInTheDocument());
    expect(screen.getByText("3d · 1 stay · 4 places")).toBeInTheDocument();
    expect(screen.getByText("₹45,000")).toBeInTheDocument();
  });
});
