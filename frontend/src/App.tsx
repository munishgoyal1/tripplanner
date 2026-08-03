import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import AssistantModalShell from "./components/AssistantModalShell";
import CanvasPaneFrame from "./components/CanvasPaneFrame";
import ChatPanel, { type AssistantTurnContext, type AssistantTurnStatus } from "./components/ChatPanel";
import DetailsPaneShell from "./components/DetailsPaneShell";
import DesktopToolbar from "./components/DesktopToolbar";
import ErrorBanner from "./components/ErrorBanner";
import ExportModal from "./components/ExportModal";
import ItineraryPanel from "./components/ItineraryPanel";
import MapPanel from "./components/MapPanel";
import { isIntercityTravel } from "./components/map/routeDerivations";
import MobileWorkspaceShell from "./components/MobileWorkspaceShell";
import TripPanel from "./components/TripPanel";
import RightRail from "./components/RightRail";
import { trackEvent } from "./analytics";
import { fetchTripView, getDisplayName, importSharedTrip, isAnonymousUser, selectItem, deselectItem, startNewTrip, type DeselectItemOptions, type SelectItemOptions } from "./api";
import { useWorkspaceFocus } from "./hooks/useWorkspaceFocus";
import type { PlannerReview, TripView } from "./types";
import { initialWorkspaceState, workspaceReducer } from "./workspaceState";

interface NavRef {
  kind: string;
  name: string;
  day?: number;
  stop?: number;
}

type CanvasPane = "itinerary" | "map";
type WorkspacePane = CanvasPane | "details";
type ResizeTarget = "itinerary" | "inspector" | null;

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function storedPercent(key: string, fallback: number, min: number, max: number): number {
  const value = Number(localStorage.getItem(key));
  return Number.isFinite(value) && value >= min && value <= max ? value : fallback;
}

function isPlaceKind(kind: string): boolean {
  return ["hotel", "attraction", "activity", "meal", "restaurant"].includes(kind);
}

function focusKind(kind: string): string {
  if (kind === "hotel" || kind === "airport") return kind;
  return "attraction";
}

function compactStatus(status?: string): string | undefined {
  if (!status) return undefined;
  const added = status.match(/^Added (.+) to your trip\.$/i);
  if (added) return `Added ${added[1]}.`;
  const removed = status.match(/^Removed (.+) and refreshed the itinerary\.$/i);
  if (removed) return `Removed ${removed[1]}.`;
  if (/^Rebalanced .*itinerary/i.test(status)) return "Itinerary refreshed.";
  return status.length > 90 ? `${status.slice(0, 87).trimEnd()}...` : status;
}

export default function App() {
  const [view, setView] = useState<TripView | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionError, setActionError] = useState<string | null>(null);
  const [plannerReview, setPlannerReview] = useState<PlannerReview | null>(null);
  const [assistantRequest, setAssistantRequest] = useState<{ id: number; message: string; proposalOnly?: boolean } | null>(null);
  const [assistantTurnStatus, setAssistantTurnStatus] = useState<AssistantTurnStatus | null>(null);
  const [navList, setNavList] = useState<NavRef[]>([]);
  const [workspace, dispatchWorkspace] = useReducer(workspaceReducer, initialWorkspaceState);
  const {
    place: focus,
    placeToken: mapFocusToken,
    circuitDay: circuitFocusDay,
    circuitToken: circuitFocusToken,
    routeDay: routeFocusDay,
    routeToken: routeFocusToken,
    setPlace: setPlaceFocus,
    setCircuit: setCircuitFocus,
    setRoute: setRouteFocus,
    clear: clearFocus,
  } = useWorkspaceFocus(workspace.focus, dispatchWorkspace);
  const stopFocusName = focus?.name ?? null;
  const tripVersion = workspace.tripRevision;
  const chatReloadToken = workspace.chatRevision;
  const chatTripId = workspace.tripId;
  const itineraryJump = workspace.itineraryJump;

  const [mapOpen, setMapOpen] = useState<boolean>(() => {
    const saved = localStorage.getItem("tripplanner_map_open");
    return saved ? JSON.parse(saved) : true;
  });
  const [maximizedPane, setMaximizedPane] = useState<WorkspacePane | null>(null);
  const [mapHeaderTarget, setMapHeaderTarget] = useState<HTMLDivElement | null>(null);
  const [itineraryOpen, setItineraryOpen] = useState(true);
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [chatOpen, setChatOpen] = useState(true);
  const [showExport, setShowExport] = useState(false);
  const [signedIn, setSignedIn] = useState(() => !isAnonymousUser());
  const dockOpen = inspectorOpen;
  const canvasMaximized = maximizedPane === "itinerary" || maximizedPane === "map";
  const dockMaximized = maximizedPane === "details";
  const [itineraryPct, setItineraryPct] = useState(() =>
    storedPercent("tripplanner_itinerary_pct", 24, 18, 55)
  );
  const [inspectorPct, setInspectorPct] = useState(() =>
    storedPercent("tripplanner_inspector_pct", 31, 24, 40)
  );
  const [isDesktop, setIsDesktop] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(min-width: 768px)").matches
  );
  const [isWideDesktop, setIsWideDesktop] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(min-width: 1200px)").matches
  );

  const refreshGeneration = useRef(0);
  const refreshController = useRef<AbortController | null>(null);
  const pendingDeselects = useRef(new Set<string>());
  const workspaceRef = useRef<HTMLElement>(null);
  const inspectorRef = useRef<HTMLElement>(null);
  const resizeTarget = useRef<ResizeTarget>(null);

  useEffect(() => {
    const mq = window.matchMedia("(min-width: 768px)");
    const onChange = (e: MediaQueryListEvent) => setIsDesktop(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  useEffect(() => {
    if (!isDesktop || !chatOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setChatOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [chatOpen, isDesktop]);

  useEffect(() => {
    const mq = window.matchMedia("(min-width: 1200px)");
    const onChange = (e: MediaQueryListEvent) => setIsWideDesktop(e.matches);
    mq.addEventListener("change", onChange);
    return () => {
      mq.removeEventListener("change", onChange);
    };
  }, []);

  useEffect(() => {
    localStorage.setItem("tripplanner_itinerary_pct", String(Math.round(itineraryPct)));
    localStorage.setItem("tripplanner_inspector_pct", String(Math.round(inspectorPct)));
  }, [inspectorPct, itineraryPct]);

  useEffect(() => {
    const handleMouseMove = (event: MouseEvent) => {
      const target = resizeTarget.current;
      if (!target) return;

      if (!workspaceRef.current) return;
      const rect = workspaceRef.current.getBoundingClientRect();
      if (target === "itinerary") {
        const next = ((event.clientX - rect.left) / rect.width) * 100;
        setItineraryPct(clamp(next, 18, 100 - inspectorPct - 20));
      } else {
        const next = ((rect.right - event.clientX) / rect.width) * 100;
        setInspectorPct(clamp(next, 24, Math.min(40, 100 - itineraryPct - 20)));
      }
    };

    const handleMouseUp = () => {
      if (!resizeTarget.current) return;
      resizeTarget.current = null;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [inspectorPct, itineraryPct]);

  const startResize = (target: Exclude<ResizeTarget, null>) => {
    resizeTarget.current = target;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  };

  const resizeWithKeyboard = (
    target: Exclude<ResizeTarget, null>,
    key: string
  ): boolean => {
    const growing = key === "ArrowRight" || key === "ArrowDown";
    const delta = growing ? 2 : -2;
    if (target === "itinerary" && (key === "ArrowLeft" || key === "ArrowRight")) {
      setItineraryPct((value) => clamp(value + delta, 18, 100 - inspectorPct - 20));
    } else if (target === "inspector" && (key === "ArrowLeft" || key === "ArrowRight")) {
      setInspectorPct((value) =>
        clamp(value + (growing ? -2 : 2), 24, Math.min(40, 100 - itineraryPct - 20))
      );
    } else {
      return false;
    }
    return true;
  };

  const applyView = useCallback((v: TripView, f: NavRef | null) => {
    setView(v);
    if (!f) setNavList(v.items.map((it) => ({ kind: it.kind, name: it.name })));
  }, []);

  const refresh = useCallback(
    async (f: NavRef | null = focus) => {
      const generation = ++refreshGeneration.current;
      refreshController.current?.abort();
      const controller = new AbortController();
      refreshController.current = controller;
      setLoading(true);
      try {
        const v = await fetchTripView(f ?? undefined, controller.signal);
        if (generation !== refreshGeneration.current) return;
        applyView(v, f);
        setActionError(null);
        return v;
      } catch (error) {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          console.error("Could not refresh trip view", error);
          setActionError("Could not refresh the trip. Your previous view is still available.");
        }
        return null;
      } finally {
        if (generation === refreshGeneration.current) setLoading(false);
      }
    },
    [focus, applyView]
  );

  useEffect(() => {
    refresh(null);
    return () => refreshController.current?.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleIdentityChanged = useCallback(async () => {
    const nextSignedIn = !isAnonymousUser();
    setSignedIn(nextSignedIn);
    if (nextSignedIn) trackEvent("login", { method: "account" });
    setView(null);
    setLoading(true);
    dispatchWorkspace({ type: "identity-changed" });
    await refresh(null);
  }, [refresh]);

  useEffect(() => {
    const onIdentityChanged = () => {
      void handleIdentityChanged();
    };
    window.addEventListener("tripplanner:identity-changed", onIdentityChanged);
    return () => window.removeEventListener("tripplanner:identity-changed", onIdentityChanged);
  }, [handleIdentityChanged]);

  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get("share");
    if (!token) return;
    let cancelled = false;
    setLoading(true);
    importSharedTrip(token)
      .then((v) => {
        if (cancelled) return;
        applyView(v, null);
        dispatchWorkspace({ type: "trip-changed" });
        trackEvent("shared_trip_imported");
        const next = new URL(window.location.href);
        next.searchParams.delete("share");
        window.history.replaceState({}, "", next.toString());
      })
      .catch(() => {
        if (cancelled) return;
        refresh(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [applyView, refresh]);

  const handleFocus = async (kind: string, name: string, context?: DeselectItemOptions) => {
    const f = { kind, name, day: context?.day, stop: context?.stop };
    setPlaceFocus(f);
    setView((current) => {
      if (!current) return current;
      const index = current.items.findIndex((item) =>
        item.kind === kind && item.name.trim().toLowerCase() === name.trim().toLowerCase()
      );
      if (index < 0) return current;
      const items = [current.items[index], ...current.items.filter((_, itemIndex) => itemIndex !== index)];
      return { ...current, focus: f, items };
    });
    if (isDesktop) setInspectorOpen(true);
    await refresh(f);
  };

  const handleClearFocus = async () => {
    clearFocus();
    await refresh(null);
  };

  const handleSwitched = async (tripId?: string, view?: TripView | null) => {
    ++refreshGeneration.current;
    refreshController.current?.abort();
    setLoading(false);
    setPlannerReview(null);
    setAssistantTurnStatus(null);
    dispatchWorkspace({ type: "trip-changed", tripId });
    // The switcher already fetched the fresh view — reuse it instead of making
    // the server rebuild the (cache-backed) view a second time.
    if (view) {
      applyView(view, null);
    } else {
      await handleClearFocus();
    }
  };

  const handleNewTrip = async () => {
    setAssistantTurnStatus(null);
    dispatchWorkspace({ type: "trip-changed" });
    await refresh(null);
  };
  const handleStartNewTrip = async () => {
    try {
      setActionError(null);
      await startNewTrip();
      await handleNewTrip();
      setInspectorOpen(true);
      setChatOpen(true);
      trackEvent("new_trip_started", { surface: "desktop" });
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Could not start a new trip.");
    }
  };
  const handleImported = async () => {
    dispatchWorkspace({ type: "trip-changed" });
    await refresh(null);
  };

  // After every chat turn: refresh every trip pane, and detect a mid-chat
  // destination switch (the agent created a NEW trip → server returns a new
  // trip_id). On a real switch we reload the chat so the fresh, carryover-seeded
  // transcript replaces the previous trip's conversation.
  const handleTurnComplete = async (tripId?: string, context?: AssistantTurnContext) => {
    const tripChanged = Boolean(tripId && tripId !== chatTripId);
    dispatchWorkspace({ type: "trip-content-changed" });
    const refreshed = await refresh(tripChanged ? null : focus);
    if (tripId) dispatchWorkspace({ type: "chat-trip-observed", tripId });
    if (tripChanged) trackEvent("trip_created");
    if (!refreshed) {
      setAssistantTurnStatus({
        phase: "error",
        message: "The planning work finished, but the updated itinerary could not be loaded. Your previous view is still available.",
      });
      return;
    }
    if (context?.proposalOnly) {
      setAssistantTurnStatus({
        phase: "complete",
        message: "Review complete. Your itinerary is unchanged and ready for your decision.",
      });
      return;
    }
    if (context?.startedWithoutTrip) {
      setAssistantTurnStatus({
        phase: "complete",
        message: "Done building your itinerary. Your trip is ready to explore; start checking it out.",
      });
      return;
    }
    const updateSummary = compactStatus(refreshed.alerts?.[0]);
    setAssistantTurnStatus({
      phase: "complete",
      message: updateSummary
        ? `${updateSummary} Everything is loaded and ready for a look.`
        : "Done updating your itinerary. Everything is loaded and ready for a look.",
    });
  };

  const focusIndex = focus
    ? navList.findIndex((n) => n.kind === focus.kind && n.name === focus.name)
    : -1;

  const handleStep = (delta: number) => {
    if (navList.length === 0) return;
    const base = focusIndex < 0 ? (delta > 0 ? -1 : 0) : focusIndex;
    const next = (base + delta + navList.length) % navList.length;
    handleFocus(navList[next].kind, navList[next].name);
  };

  const handleSelect = async (kind: string, name: string, options?: SelectItemOptions) => {
    try {
      setAssistantTurnStatus(null);
      setActionError(null);
      const next = await selectItem(kind, name, options);
      const nextKind = focusKind(kind);
      setPlaceFocus({ kind: nextKind, name });
      ++refreshGeneration.current;
      refreshController.current?.abort();
      setLoading(false);
      setView({ ...next.view, alerts: next.alerts });
      setPlannerReview(next.planner_review ?? null);
      setNavList(next.view.items.map((it) => ({ kind: it.kind, name: it.name })));
      const placement = next.placement || (next.placements && next.placements.length > 0 ? next.placements[0] : null);
      if (placement?.day && placement?.name) {
        dispatchWorkspace({
          type: "jump",
          target: { day: placement.day, name: placement.name, token: Date.now() },
        });
      }
      dispatchWorkspace({ type: "trip-content-changed" });
      trackEvent("place_added", { exact_day: Boolean(options?.day) });
      return true;
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Could not add the place.");
      return false;
    }
  };

  const handleDeselect = async (
    kind: string,
    name: string,
    options: DeselectItemOptions = { all_occurrences: true },
  ) => {
    const mutationKey = [
      focusKind(kind),
      name.trim().toLowerCase(),
      options.all_occurrences === false ? options.day ?? "day" : "all",
      options.stop ?? "stop",
    ].join(":");
    if (pendingDeselects.current.has(mutationKey)) return false;
    pendingDeselects.current.add(mutationKey);
    try {
      setAssistantTurnStatus(null);
      setActionError(null);
      const next = await deselectItem(kind, name, options);
      const retainedFocus = {
        kind: focusKind(kind),
        name,
        day: options.all_occurrences === false ? options.day : undefined,
        stop: options.all_occurrences === false ? options.stop : undefined,
      };
      setPlaceFocus(retainedFocus);
      ++refreshGeneration.current;
      refreshController.current?.abort();
      setLoading(false);
      setView({ ...next.view, focus: retainedFocus, alerts: next.alerts });
      setPlannerReview(next.planner_review ?? null);
      setNavList(next.view.items.map((it) => ({ kind: it.kind, name: it.name })));
      dispatchWorkspace({ type: "trip-content-changed" });
      trackEvent("place_removed", { scope: options.all_occurrences === false ? "occurrence" : "all" });
      return true;
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Could not remove the place.");
      return false;
    } finally {
      pendingDeselects.current.delete(mutationKey);
    }
  };

  const handleStopRemove = async (kind: string, name: string, day: number, stop: number) => {
    await handleDeselect(kind, name, { day, stop, all_occurrences: false });
  };

  const reviewWithPlanner = () => {
    if (!plannerReview) return;
    setInspectorOpen(true);
    setChatOpen(true);
    setAssistantRequest({ id: Date.now(), message: plannerReview.prompt, proposalOnly: true });
    setPlannerReview(null);
  };

  const toggleMaxPane = (pane: WorkspacePane) => {
    setMaximizedPane((prev) => (prev === pane ? null : pane));
  };

  const setCanvasOpen = (pane: CanvasPane, open: boolean) => {
    if (!open && ((pane === "itinerary" && !mapOpen) || (pane === "map" && !itineraryOpen))) return;
    if (pane === "itinerary") setItineraryOpen(open);
    else setMapOpen(open);
    if (!open && maximizedPane === pane) setMaximizedPane(null);
  };

  const setDockPaneOpen = (pane: "details" | "assistant", open: boolean) => {
    if (pane === "details") setInspectorOpen(open);
    else setChatOpen(open);
    if (!open && pane === "details" && maximizedPane === pane) setMaximizedPane(null);
  };

  const handleStopFocus = async (kind: string, name: string, day?: number, stop?: number) => {
    setMapOpen(true);
    if (isIntercityTravel(kind, name) && day) {
      setRouteFocus(day);
      setView((current) => current ? { ...current, focus: null } : current);
      return;
    }
    if (isPlaceKind(kind) || kind === "airport") {
      await handleFocus(focusKind(kind), name, { day, stop });
    }
  };

  const handleStopMap = async (kind: string, name: string, day?: number, stop?: number) => {
    setMapOpen(true);
    if (isIntercityTravel(kind, name)) {
      await handleStopFocus(kind, name, day, stop);
      return;
    }
    if (isPlaceKind(kind) || kind === "airport") {
      await handleFocus(focusKind(kind), name, { day, stop });
    }
  };

  const handleDayFocus = (day: number) => {
    setMapOpen(true);
    setCircuitFocus(day);
    setView((current) => current ? { ...current, focus: null } : current);
    dispatchWorkspace({ type: "jump", target: { day, token: Date.now() } });
  };

  const handleMapAllDaysFocus = () => {
    setCircuitFocus(null);
    setView((current) => current ? { ...current, focus: null } : current);
    dispatchWorkspace({ type: "jump", target: { summary: true, token: Date.now() } });
  };

  const tripPanelProps = {
    view,
    loading,
    navList,
    focusIndex,
    onFocus: handleFocus,
    onClearFocus: handleClearFocus,
    onStep: handleStep,
    onSelect: handleSelect,
    onDeselect: handleDeselect,
    focusContext: focus,
    tripVersion,
    onSwitched: handleSwitched,
  };

  const railProps = {
    overview: view?.overview ?? null,
    reloadToken: tripVersion,
    tripId: chatTripId,
    focusName: stopFocusName,
    focusDay: focus?.day,
    focusStop: focus?.stop,
    focusToken: mapFocusToken,
    circuitFocusDay: circuitFocusDay ?? undefined,
    circuitFocusToken,
    routeFocusDay: routeFocusDay ?? undefined,
    routeFocusToken,
    itineraryJump,
    onStopFocus: handleStopFocus,
    onStopMap: handleStopMap,
    onDayMap: handleDayFocus,
    onMapDayFocus: handleDayFocus,
    onMapAllDaysFocus: handleMapAllDaysFocus,
    onSelect: handleSelect,
    onDeselect: handleDeselect,
    tripVersion,
    onSwitched: handleSwitched,
    mapOpen,
    onToggleMap: setMapOpen,
  };

  const renderCanvasBody = (pane: CanvasPane) => {
    if (pane === "itinerary") {
      return (
        <ItineraryPanel
          overview={view?.overview}
          reloadToken={tripVersion}
          focusName={stopFocusName}
          focusDay={focus?.day}
          focusStop={focus?.stop}
          circuitFocusDay={circuitFocusDay ?? undefined}
          circuitFocusToken={circuitFocusToken}
          jumpTo={itineraryJump}
          onStopFocus={handleStopFocus}
          onStopMap={handleStopMap}
          onDayMap={handleDayFocus}
          onAllDaysMap={handleMapAllDaysFocus}
          onStopRemove={handleStopRemove}
        />
      );
    }
    return (
      <MapPanel
        reloadToken={tripVersion}
        tripId={chatTripId}
        focusName={stopFocusName}
        focusDay={focus?.day}
        focusStop={focus?.stop}
        focusToken={mapFocusToken}
        circuitFocusDay={circuitFocusDay ?? undefined}
        circuitFocusToken={circuitFocusToken}
        routeFocusDay={routeFocusDay ?? undefined}
        routeFocusToken={routeFocusToken}
        onPinFocus={handleStopFocus}
        onDayFocus={handleDayFocus}
        onAllDaysFocus={handleMapAllDaysFocus}
        onSelect={handleSelect}
        onDeselect={handleDeselect}
        headerTarget={mapHeaderTarget}
      />
    );
  };

  const inspector = (
    <DetailsPaneShell
      open={inspectorOpen}
      canvasMaximized={canvasMaximized}
      wideLayout={isWideDesktop}
      maximized={dockMaximized}
      focused={Boolean(focus)}
      focusName={focus?.name ?? null}
      inspectorRef={inspectorRef}
      onHide={() => setDockPaneOpen("details", false)}
      onToggleMaximize={() => toggleMaxPane("details")}
    >
      <TripPanel {...tripPanelProps} hideSwitcher />
    </DetailsPaneShell>
  );

  const assistantModal = (
    <AssistantModalShell open={chatOpen} onClose={() => setDockPaneOpen("assistant", false)}>
      <ChatPanel
        onTurnComplete={handleTurnComplete}
        onTurnStatus={setAssistantTurnStatus}
        reloadToken={chatReloadToken}
        tripIdHint={chatTripId}
        hasActiveTrip={Boolean(view?.has_trip)}
        onNewTrip={handleNewTrip}
        onImported={handleImported}
        hideGlobalControls
        assistantRequest={assistantRequest}
      />
    </AssistantModalShell>
  );

  const [mobileTripOpen, setMobileTripOpen] = useState(false);
  useEffect(() => {
    if (isDesktop && mobileTripOpen) setMobileTripOpen(false);
  }, [isDesktop, mobileTripOpen]);

  const latestStatus = compactStatus(view?.alerts?.[0]);
  const visibleStatus = assistantTurnStatus?.message ?? (plannerReview
    ? [latestStatus, plannerReview.summary].filter(Boolean).join(" ")
    : latestStatus);
  return <>
    <ErrorBanner message={actionError} onDismiss={() => setActionError(null)} />
    {showExport && <ExportModal onClose={() => setShowExport(false)} />}
    {isDesktop ? (
      <div className="flex h-[100dvh] min-h-0 flex-col overflow-hidden bg-surface">
        <DesktopToolbar
          tripVersion={tripVersion}
          onTripSwitched={handleSwitched}
          visibleStatus={visibleStatus}
          statusPhase={assistantTurnStatus?.phase}
          reviewPending={plannerReview !== null}
          loading={loading}
          onReviewWithPlanner={reviewWithPlanner}
          onKeepReview={() => setPlannerReview(null)}
          onStartNewTrip={handleStartNewTrip}
          paneVisibility={{
            itinerary: itineraryOpen,
            map: mapOpen,
            details: inspectorOpen,
            assistant: chatOpen,
          }}
          onTogglePane={(pane) => {
            if (pane === "itinerary") setCanvasOpen(pane, !itineraryOpen);
            else if (pane === "map") setCanvasOpen(pane, !mapOpen);
            else if (pane === "details") setDockPaneOpen(pane, !inspectorOpen);
            else setDockPaneOpen(pane, !chatOpen);
          }}
          tripActionsDisabled={!view?.has_trip}
          onExport={() => setShowExport(true)}
          signedIn={signedIn}
          accountLabel={signedIn ? getDisplayName() || "Account" : "Guest"}
          onOpenAccount={() => window.dispatchEvent(new Event("tripplanner:open-account"))}
        />

        <main
          ref={workspaceRef}
          className="relative grid min-h-0 flex-1 overflow-hidden p-2"
          style={{
            gridTemplateColumns: maximizedPane
              ? "minmax(0, 1fr)"
              : !itineraryOpen || !mapOpen
                ? isWideDesktop && dockOpen
                  ? `minmax(0, ${100 - inspectorPct}fr) 0.375rem minmax(0, ${inspectorPct}fr)`
                  : "minmax(0, 1fr)"
              : isWideDesktop && dockOpen
                ? `${itineraryPct}fr 0.375rem ${100 - itineraryPct - inspectorPct}fr 0.375rem ${inspectorPct}fr`
                : `${itineraryPct}fr 0.375rem ${100 - itineraryPct}fr`,
          }}
        >
          <section className={`min-h-0 min-w-0 ${!itineraryOpen || maximizedPane && maximizedPane !== "itinerary" ? "hidden" : ""}`}>
            <CanvasPaneFrame
              label="Itinerary"
              maximized={maximizedPane === "itinerary"}
              hideDisabled={!mapOpen}
              onHide={() => setCanvasOpen("itinerary", false)}
              onToggleMaximize={() => toggleMaxPane("itinerary")}
            >
              {renderCanvasBody("itinerary")}
            </CanvasPaneFrame>
          </section>
          {!maximizedPane && itineraryOpen && mapOpen && (
            <div
              role="separator"
              tabIndex={0}
              aria-label="Resize itinerary and map"
              aria-orientation="vertical"
              aria-valuenow={Math.round(itineraryPct)}
              onMouseDown={() => startResize("itinerary")}
              onKeyDown={(event) => {
                if (resizeWithKeyboard("itinerary", event.key)) event.preventDefault();
              }}
              className="group relative cursor-col-resize bg-transparent hover:bg-brand/20 focus:bg-brand/20 focus:outline-none"
            >
              <span className="absolute left-1/2 top-1/2 h-12 w-1 -translate-x-1/2 -translate-y-1/2 rounded-full bg-slate-300 group-hover:bg-brand/60" />
            </div>
          )}
          <section className={`min-h-0 min-w-0 ${!mapOpen || maximizedPane && maximizedPane !== "map" ? "hidden" : ""}`}>
            <CanvasPaneFrame
              label="Map"
              maximized={maximizedPane === "map"}
              hideDisabled={!itineraryOpen}
              onHide={() => setCanvasOpen("map", false)}
              onToggleMaximize={() => toggleMaxPane("map")}
              headerTargetRef={setMapHeaderTarget}
            >
              {renderCanvasBody("map")}
            </CanvasPaneFrame>
          </section>
          {!maximizedPane && isWideDesktop && dockOpen && (itineraryOpen || mapOpen) && (
            <div
              role="separator"
              tabIndex={0}
              aria-label="Resize map and details"
              aria-orientation="vertical"
              aria-valuenow={Math.round(inspectorPct)}
              onMouseDown={() => startResize("inspector")}
              onKeyDown={(event) => {
                if (resizeWithKeyboard("inspector", event.key)) event.preventDefault();
              }}
              className="group relative cursor-col-resize bg-transparent hover:bg-brand/20 focus:bg-brand/20 focus:outline-none"
            >
              <span className="absolute left-1/2 top-1/2 h-12 w-1 -translate-x-1/2 -translate-y-1/2 rounded-full bg-slate-300 group-hover:bg-brand/60" />
            </div>
          )}
          {inspector}
          {assistantModal}
        </main>
      </div>
        ) : (
        <MobileWorkspaceShell
          chat={(
            <ChatPanel
              onTurnComplete={handleTurnComplete}
              onTurnStatus={setAssistantTurnStatus}
              reloadToken={chatReloadToken}
              tripIdHint={chatTripId}
              hasActiveTrip={Boolean(view?.has_trip)}
              onNewTrip={handleNewTrip}
              onImported={handleImported}
            />
          )}
          hasTrip={Boolean(view?.has_trip)}
          tripOpen={mobileTripOpen}
          onOpenTrip={() => setMobileTripOpen(true)}
          onCloseTrip={() => setMobileTripOpen(false)}
          tripDetails={(
            <RightRail {...railProps} photos={<TripPanel {...tripPanelProps} hideSwitcher />} />
          )}
        />
    )}
  </>;
}

