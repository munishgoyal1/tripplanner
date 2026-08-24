import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import CanvasPaneFrame from "./components/CanvasPaneFrame";
import { openAccountSettings } from "./components/accountSettings";
import ChatPanel, { type AssistantTurnContext, type AssistantTurnStatus } from "./components/ChatPanel";
import DetailsPaneShell from "./components/DetailsPaneShell";
import DesktopToolbar from "./components/DesktopToolbar";
import ExportModal from "./components/ExportModal";
import ItineraryPanel from "./components/ItineraryPanel";
import MapPanel from "./components/MapPanel";
import { isIntercityTravel } from "./components/map/routeDerivations";
import MobileWorkspaceShell from "./components/MobileWorkspaceShell";
import { FloatingStatusBar } from "./components/StatusBar";
import TripPanel from "./components/TripPanel";
import RightRail from "./components/RightRail";
import { trackEvent } from "./analytics";
import { fetchDocumentReadiness, fetchPreferences, fetchTripView, getDisplayName, importSharedTrip, isAnonymousUser, resetTrip, selectItem, deselectItem, startNewTrip, type DeselectItemOptions, type SelectItemOptions } from "./api";
import { useWorkspaceFocus } from "./hooks/useWorkspaceFocus";
import type { ItineraryFilter } from "./lib/itineraryFilters";
import { dismissNotice, notify } from "./lib/notices";
import { completionStatus } from "./lib/turnStatus";
import type { PlannerReview, TripView, TripWorkspaceView, TurnEffect } from "./types";
import { diffTurnEffects } from "./turnEffects";
import { initialWorkspaceState, workspaceReducer } from "./workspaceState";
import { ensureInitialDisplayPreferences, normalizeDisplayLanguage, normalizeDisplayRegion, writeDisplayPreferences } from "./lib/displayPreferences";

interface NavRef {
  kind: string;
  name: string;
  day?: number;
  stop?: number;
}

type CanvasPane = "itinerary" | "map";
type WorkspacePane = CanvasPane | "details";
type ResizeTarget = "itinerary" | "inspector" | null;
// The Assistant lives in a bottom dock: a single composer row by default, an
// expanded reading sheet above it, or the full workspace height.
type AssistantView = "bar" | "sheet" | "full";

const ITINERARY_MIN_PCT = 18;
const MAP_MIN_PCT = 20;
const INSPECTOR_MIN_PCT = 24;

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function storedPercent(key: string, fallback: number, min: number, max: number): number {
  const value = Number(localStorage.getItem(key));
  return Number.isFinite(value) && value >= min && value <= max ? value : fallback;
}

function storedBoolean(key: string, fallback: boolean): boolean {
  const value = localStorage.getItem(key);
  if (value === "true") return true;
  if (value === "false") return false;
  return fallback;
}

function isPlaceKind(kind: string): boolean {
  return ["hotel", "attraction", "activity", "meal", "restaurant", "station", "bus_station"].includes(kind);
}

function focusKind(kind: string): string {
  if (["hotel", "airport", "station", "bus_station"].includes(kind)) return kind;
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

export default function App({ initialRequest = null }: { initialRequest?: string | null }) {
  useEffect(() => {
    ensureInitialDisplayPreferences();
    fetchPreferences().then((preferences) => {
      if (!isAnonymousUser() || preferences.display_currency_configured) {
        writeDisplayPreferences({
          region: normalizeDisplayRegion(preferences.display_region || preferences.home_country || ""),
          language: normalizeDisplayLanguage(preferences.display_language || "en"),
          currency: preferences.display_currency || "USD",
        });
      }
    }).catch(() => undefined);
  }, []);
  const [view, setView] = useState<TripView | null>(null);
  // Map + itinerary view-models handed over by a trip switch, so those panels
  // can render the new trip without a second and third round-trip.
  const [panelSeed, setPanelSeed] = useState<TripWorkspaceView | null>(null);
  const [loading, setLoading] = useState(true);
  const [plannerReview, setPlannerReview] = useState<PlannerReview | null>(null);
  const [assistantRequest, setAssistantRequest] = useState<{ id: number; message: string; proposalOnly?: boolean } | null>(
    // Seeded once when the public entry hands over a typed trip, so the workspace
    // opens with that run already starting.
    () => (initialRequest ? { id: Date.now(), message: initialRequest } : null)
  );
  const [assistantTurnStatus, setAssistantTurnStatus] = useState<AssistantTurnStatus | null>(null);
  const [navList, setNavList] = useState<NavRef[]>([]);
  const [workspace, dispatchWorkspace] = useReducer(workspaceReducer, initialWorkspaceState);
  const {
    place: focus,
    placeToken: mapFocusToken,
    circuitDay: circuitFocusDay,
    circuitToken: circuitFocusToken,
    routeDay: routeFocusDay,
    routeCircuitId: routeFocusId,
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

  const [mapOpen, setMapOpen] = useState(() => storedBoolean("tripplanner_map_open", true));
  const [maximizedPane, setMaximizedPane] = useState<WorkspacePane | null>(null);
  const [itineraryHeaderTarget, setItineraryHeaderTarget] = useState<HTMLDivElement | null>(null);
  const [itineraryFilters, setItineraryFilters] = useState<ItineraryFilter[]>([]);
  const [itineraryOpen, setItineraryOpen] = useState(() => (
    storedBoolean("tripplanner_itinerary_open", true)
  ));
  const [inspectorOpen, setInspectorOpen] = useState(() => (
    storedBoolean("tripplanner_details_open", true)
  ));
  const [chatOpen, setChatOpen] = useState(() => (
    storedBoolean("tripplanner_assistant_open", true)
  ));
  const [showExport, setShowExport] = useState(false);
  const [documentBadge, setDocumentBadge] = useState("");
  const [documentBadgeTone, setDocumentBadgeTone] = useState<"blocker" | "warning">("warning");
  const [documentsRevision, setDocumentsRevision] = useState(0);
  const [signedIn, setSignedIn] = useState(() => !isAnonymousUser());
  const [assistantView, setAssistantView] = useState<AssistantView>("bar");
  const [turnEffects, setTurnEffects] = useState<{ token: number; effects: TurnEffect[] } | null>(null);
  const dockOpen = inspectorOpen;
  const canvasMaximized = maximizedPane !== null && maximizedPane !== "details";
  const dockMaximized = maximizedPane === "details";
  const [itineraryPct, setItineraryPct] = useState(() =>
    storedPercent("tripplanner_itinerary_pct", 24, ITINERARY_MIN_PCT, 100 - MAP_MIN_PCT)
  );
  const [inspectorPct, setInspectorPct] = useState(() =>
    storedPercent("tripplanner_inspector_pct", 31, INSPECTOR_MIN_PCT, 100 - ITINERARY_MIN_PCT)
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
  const canvasOpen = itineraryOpen || mapOpen;
  const inspectorMaxPct = 100
    - (itineraryOpen ? ITINERARY_MIN_PCT : 0)
    - (mapOpen ? MAP_MIN_PCT : 0);
  const effectiveInspectorPct = canvasOpen
    ? clamp(inspectorPct, INSPECTOR_MIN_PCT, inspectorMaxPct)
    : 100;
  const itineraryMaxPct = 100
    - MAP_MIN_PCT
    - (isWideDesktop && dockOpen ? effectiveInspectorPct : 0);
  const effectiveItineraryPct = clamp(
    itineraryPct,
    ITINERARY_MIN_PCT,
    itineraryMaxPct,
  );

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

  // Document gaps are recomputed whenever the trip changes; the trip itself never
  // stores the details, it only surfaces what is missing.
  useEffect(() => {
    const controller = new AbortController();
    fetchDocumentReadiness(controller.signal)
      .then((readiness) => {
        setDocumentBadge(readiness.badge || "");
        setDocumentBadgeTone(readiness.badge_tone === "blocker" ? "blocker" : "warning");
      })
      .catch(() => undefined);
    return () => controller.abort();
  }, [tripVersion, documentsRevision]);

  useEffect(() => {
    const bump = () => setDocumentsRevision((value) => value + 1);
    window.addEventListener("tripplanner:documents-changed", bump);
    return () => window.removeEventListener("tripplanner:documents-changed", bump);
  }, []);

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
    localStorage.setItem("tripplanner_itinerary_open", String(itineraryOpen));
    localStorage.setItem("tripplanner_map_open", String(mapOpen));
    localStorage.setItem("tripplanner_details_open", String(inspectorOpen));
    localStorage.setItem("tripplanner_assistant_open", String(chatOpen));
  }, [chatOpen, inspectorOpen, itineraryOpen, mapOpen]);

  useEffect(() => {
    const handleMouseMove = (event: MouseEvent) => {
      const target = resizeTarget.current;
      if (!target) return;

      if (!workspaceRef.current) return;
      const rect = workspaceRef.current.getBoundingClientRect();
      if (target === "itinerary") {
        const next = ((event.clientX - rect.left) / rect.width) * 100;
        setItineraryPct(clamp(next, ITINERARY_MIN_PCT, itineraryMaxPct));
      } else {
        const next = ((rect.right - event.clientX) / rect.width) * 100;
        setInspectorPct(clamp(next, INSPECTOR_MIN_PCT, inspectorMaxPct));
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
  }, [inspectorMaxPct, itineraryMaxPct]);

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
      setItineraryPct(clamp(
        effectiveItineraryPct + delta,
        ITINERARY_MIN_PCT,
        itineraryMaxPct,
      ));
    } else if (target === "inspector" && (key === "ArrowLeft" || key === "ArrowRight")) {
      setInspectorPct(clamp(
        effectiveInspectorPct + (growing ? -2 : 2),
        INSPECTOR_MIN_PCT,
        inspectorMaxPct,
      ));
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
    async (f: NavRef | null = focus, options: { silent?: boolean } = {}) => {
      const generation = ++refreshGeneration.current;
      refreshController.current?.abort();
      const controller = new AbortController();
      refreshController.current = controller;
      // A focus change only reorders an already-rendered gallery, so it refreshes
      // silently — flipping the panel into its loading state made the round-trip
      // feel like the app had stalled.
      if (!options.silent) setLoading(true);
      try {
        const v = await fetchTripView(f ?? undefined, controller.signal);
        if (generation !== refreshGeneration.current) return;
        applyView(v, f);
        dismissNotice("action-error");
        return v;
      } catch (error) {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          console.error("Could not refresh trip view", error);
          notify({
            id: "action-error",
            tone: "error",
            message: "Could not refresh the trip. Your previous view is still available.",
          });
        }
        return null;
      } finally {
        if (generation === refreshGeneration.current && !options.silent) setLoading(false);
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
    await refresh(f, { silent: true });
  };

  const handleClearFocus = async () => {
    clearFocus();
    await refresh(null, { silent: true });
  };

  const handleSwitched = async (
    tripId?: string,
    payload?: TripWorkspaceView | TripView | null,
  ) => {
    ++refreshGeneration.current;
    refreshController.current?.abort();
    setLoading(false);
    setPlannerReview(null);
    setAssistantTurnStatus(null);
    const workspace: TripWorkspaceView | null = payload
      ? "view" in payload
        ? payload
        : { view: payload, map: null, itinerary: null }
      : null;
    dispatchWorkspace({ type: "trip-changed", tripId });
    // The switch response already carries every panel's view-model — seed them
    // all from it so the map and itinerary swap with the trip panel instead of
    // each re-fetching and settling one after another. A missing payload must
    // still drop the previous trip's seed, or a remounted panel would restore it.
    setPanelSeed(workspace);
    if (workspace) {
      applyView(workspace.view, null);
    } else {
      await handleClearFocus();
    }
  };

  const handleNewTrip = async () => {
    setAssistantTurnStatus(null);
    setPanelSeed(null);
    dispatchWorkspace({ type: "trip-changed" });
    await refresh(null);
  };
  const handleStartNewTrip = async () => {
    try {
      dismissNotice("action-error");
      await startNewTrip();
      await handleNewTrip();
      setInspectorOpen(true);
      setChatOpen(true);
      trackEvent("new_trip_started", { surface: "desktop" });
    } catch (error) {
      notify({
        id: "action-error",
        tone: "error",
        message: error instanceof Error ? error.message : "Could not start a new trip.",
      });
    }
  };
  const handleResetTrip = async () => {
    if (
      !window.confirm(
        "Reset this trip? The itinerary and everything you've picked will be cleared. " +
          "The destination, dates and travellers stay, so you can rebuild from the same brief.",
      )
    )
      return;
    try {
      dismissNotice("action-error");
      const workspace = await resetTrip();
      setAssistantTurnStatus(null);
      setPanelSeed(workspace);
      dispatchWorkspace({ type: "trip-changed" });
      await refresh(null);
      notify({
        id: "trip-reset",
        tone: "success",
        message: "Trip reset",
        detail: "The plan is empty. Your destination, dates and travellers are unchanged.",
      });
      trackEvent("trip_reset", { surface: "desktop" });
    } catch (error) {
      notify({
        id: "action-error",
        tone: "error",
        message: "Could not reset the trip",
        detail: error instanceof Error ? error.message : undefined,
      });
    }
  };
  const handleImported = async () => {
    dispatchWorkspace({ type: "trip-changed" });
    await refresh(null);
  };

  // A turn that changed the plan selects what it changed, so the Itinerary,
  // Map, and Details all land on the same subject without a manual click. The
  // scope follows the shape of the change: one touched place is selected
  // outright, a change spread across days (a new city, a reshuffle) keeps the
  // whole trip in view instead of leaving one day scoped.
  const applyTurnSelection = async (effects: TurnEffect[], tripChanged: boolean) => {
    const applied = effects.filter((effect) => effect.change !== "removed");
    if (!applied.length) {
      if (tripChanged) handleMapAllDaysFocus();
      return;
    }
    const days = new Set(
      applied.map((effect) => effect.day).filter((day): day is number => typeof day === "number"),
    );
    if (tripChanged || days.size > 1) {
      handleMapAllDaysFocus();
      return;
    }
    const primary = applied.find((effect) => effect.kind === "hotel") ?? applied[0];
    // Focus first: a focus dispatch clears any pending itinerary jump, so the
    // scroll target has to be set after the Map and Details have landed.
    await handleStopFocus(primary.kind, primary.name, primary.day, primary.stop);
    if (primary.day) {
      dispatchWorkspace({
        type: "jump",
        target: { day: primary.day, name: primary.name, token: Date.now() },
      });
    }
  };

  // After every chat turn: refresh every trip pane, and detect a mid-chat
  // destination switch (the agent created a NEW trip → server returns a new
  // trip_id). On a real switch we reload the chat so the fresh, carryover-seeded
  // transcript replaces the previous trip's conversation.
  const handleTurnComplete = async (tripId?: string, context?: AssistantTurnContext) => {
    const tripChanged = Boolean(tripId && tripId !== chatTripId);
    const beforeTurn = view;
    dispatchWorkspace({ type: "trip-content-changed" });
    const refreshed = await refresh(tripChanged ? null : focus);
    if (tripId) dispatchWorkspace({ type: "chat-trip-observed", tripId });
    if (tripChanged) trackEvent("trip_created");
    if (!refreshed || (tripId && refreshed.trip_id !== tripId)) {
      setAssistantTurnStatus({
        phase: "error",
        message: "Could not load the updated itinerary",
        detail: "The planning work finished. Your previous view is still on screen.",
      });
      return;
    }
    const effects = diffTurnEffects(tripChanged ? null : beforeTurn, refreshed);
    if (effects.length) setTurnEffects({ token: Date.now(), effects });
    if (!context?.proposalOnly) await applyTurnSelection(effects, tripChanged);
    setAssistantTurnStatus({
      phase: "complete",
      ...completionStatus({
        destination: refreshed.destination,
        startedWithoutTrip: Boolean(context?.startedWithoutTrip),
        proposalOnly: Boolean(context?.proposalOnly),
        effects,
        reply: context?.reply ?? "",
        alert: compactStatus(refreshed.alerts?.[0]),
      }),
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

  const selectWhenAvailable = async (
    kind: string,
    name: string,
    options?: SelectItemOptions,
  ) => {
    for (let attempt = 0; attempt < 90; attempt += 1) {
      try {
        return await selectItem(kind, name, options);
      } catch (error) {
        const status = typeof error === "object" && error !== null && "status" in error
          ? (error as { status?: number }).status
          : undefined;
        if (status !== 409 || attempt === 89) throw error;
        const retryAfterMs = typeof error === "object" && error !== null && "retryAfterMs" in error
          ? (error as { retryAfterMs?: number | null }).retryAfterMs
          : null;
        notify({
          id: "action-error",
          tone: "progress",
          message: "Waiting for the Assistant to finish before adding this place...",
        });
        await new Promise((resolve) => setTimeout(resolve, retryAfterMs ?? 2000));
      }
    }
    throw new Error("Could not add the place.");
  };

  const handleSelect = async (kind: string, name: string, options?: SelectItemOptions) => {
    try {
      setAssistantTurnStatus(null);
      dismissNotice("action-error");
      const next = await selectWhenAvailable(kind, name, options);
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
      notify({
        id: "action-error",
        tone: "error",
        message: error instanceof Error ? error.message : "Could not add the place.",
      });
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
      dismissNotice("action-error");
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
      notify({
        id: "action-error",
        tone: "error",
        message: error instanceof Error ? error.message : "Could not remove the place.",
      });
      return false;
    } finally {
      pendingDeselects.current.delete(mutationKey);
    }
  };

  const handleStopRemove = async (kind: string, name: string, day: number, stop: number) => {
    await handleDeselect(kind, name, { day, stop, all_occurrences: false });
  };

  const handleDecisionApplied = (next: TripView, message: string, warnings: string[]) => {
    dismissNotice("action-error");
    ++refreshGeneration.current;
    refreshController.current?.abort();
    setLoading(false);
    applyView(next, null);
    dispatchWorkspace({ type: "trip-content-changed" });
    notify({
      id: "trip-alert",
      tone: warnings.length > 0 ? "error" : "success",
      message,
      detail: warnings.join(" "),
    });
  };

  // A stale write means someone else moved the trip on. Show them that trip
  // rather than the one they were arguing with.
  const handleDecisionStale = (next: TripView | undefined, message: string) => {
    if (next) applyView(next, null);
    else void refresh(null, { silent: true });
    dispatchWorkspace({ type: "trip-content-changed" });
    notify({ id: "action-error", tone: "error", message });
  };

  const handleDecisionError = (message: string) => {
    notify({ id: "action-error", tone: "error", message });
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
    if (pane === "itinerary") setItineraryOpen(open);
    else setMapOpen(open);
    if (!open && maximizedPane === pane) setMaximizedPane(null);
  };

  const setDockPaneOpen = (pane: "details" | "assistant", open: boolean) => {
    if (pane === "details") setInspectorOpen(open);
    else setChatOpen(open);
    if (!open && maximizedPane === pane) setMaximizedPane(null);
  };

  const handleStopFocus = async (
    kind: string,
    name: string,
    day?: number,
    stop?: number,
    routeCircuitId?: string,
  ) => {
    setMapOpen(true);
    if (isIntercityTravel(kind, name) && day) {
      setRouteFocus(day, routeCircuitId);
      setView((current) => current ? { ...current, focus: null } : current);
      return;
    }
    if (isPlaceKind(kind) || kind === "airport") {
      await handleFocus(focusKind(kind), name, { day, stop });
    }
  };

  const handleStopMap = async (
    kind: string,
    name: string,
    day?: number,
    stop?: number,
    routeCircuitId?: string,
  ) => {
    setMapOpen(true);
    if (isIntercityTravel(kind, name)) {
      await handleStopFocus(kind, name, day, stop, routeCircuitId);
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

  const handleItineraryFilterToggle = (filter: ItineraryFilter) => {
    setItineraryFilters((current) => current.includes(filter)
      ? current.filter((candidate) => candidate !== filter)
      : [...current, filter]);
    clearFocus();
    setView((current) => current ? { ...current, focus: null } : current);
    dispatchWorkspace({ type: "jump", target: { summary: true, token: Date.now() } });
  };

  useEffect(() => {
    setItineraryFilters([]);
  }, [chatTripId]);

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
    onDecisionApplied: handleDecisionApplied,
    onDecisionStale: handleDecisionStale,
    onDecisionError: handleDecisionError,
  };

  const railProps = {
    filters: itineraryFilters,
    onFilterToggle: handleItineraryFilterToggle,
    overview: view?.overview ?? null,
    reloadToken: tripVersion,
    tripId: chatTripId,
    mapSeed: panelSeed?.map ?? null,
    itinerarySeed: panelSeed?.itinerary ?? null,
    focusName: stopFocusName,
    focusDay: focus?.day,
    focusStop: focus?.stop,
    focusToken: mapFocusToken,
    circuitFocusDay: circuitFocusDay ?? undefined,
    circuitFocusToken,
    routeFocusDay: routeFocusDay ?? undefined,
    routeFocusId: routeFocusId ?? undefined,
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
          filters={itineraryFilters}
          onFilterToggle={handleItineraryFilterToggle}
          headerTarget={itineraryHeaderTarget}
          overview={view?.overview}
          reloadToken={tripVersion}
          tripId={chatTripId}
          seed={panelSeed?.itinerary ?? null}
          focusName={stopFocusName}
          focusDay={focus?.day}
          focusStop={focus?.stop}
          focusToken={mapFocusToken}
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
        filters={itineraryFilters}
        reloadToken={tripVersion}
        tripId={chatTripId}
        seed={panelSeed?.map ?? null}
        focusName={stopFocusName}
        focusDay={focus?.day}
        focusStop={focus?.stop}
        focusToken={mapFocusToken}
        circuitFocusDay={circuitFocusDay ?? undefined}
        circuitFocusToken={circuitFocusToken}
        routeFocusDay={routeFocusDay ?? undefined}
        routeFocusId={routeFocusId ?? undefined}
        routeFocusToken={routeFocusToken}
        onPinFocus={handleStopFocus}
        onDayFocus={handleDayFocus}
        onAllDaysFocus={handleMapAllDaysFocus}
        onSelect={handleSelect}
        onDeselect={handleDeselect}
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

  const coreColumns = isWideDesktop && dockOpen && canvasOpen
    ? itineraryOpen && mapOpen
      ? `${effectiveItineraryPct}fr 0.375rem ${100 - effectiveItineraryPct - effectiveInspectorPct}fr 0.375rem ${effectiveInspectorPct}fr`
      : `minmax(0, ${100 - effectiveInspectorPct}fr) 0.375rem minmax(0, ${effectiveInspectorPct}fr)`
    : itineraryOpen && mapOpen
      ? `${effectiveItineraryPct}fr 0.375rem ${100 - effectiveItineraryPct}fr`
      : "minmax(0, 1fr)";
  const workspaceColumns = maximizedPane ? "minmax(0, 1fr)" : coreColumns;
  const assistantPanel = (
    <ChatPanel
      onTurnComplete={handleTurnComplete}
      onTurnStatus={setAssistantTurnStatus}
      reloadToken={chatReloadToken}
      tripIdHint={chatTripId}
      hasActiveTrip={Boolean(view?.has_trip)}
      destination={view?.destination ?? null}
      onNewTrip={handleNewTrip}
      onImported={handleImported}
      hideGlobalControls
      assistantRequest={assistantRequest}
      layout={assistantView}
      onChangeLayout={setAssistantView}
      onHide={() => setDockPaneOpen("assistant", false)}
      turnEffects={turnEffects}
      onEffectSelect={(effect) => {
        void handleStopFocus(effect.kind, effect.name, effect.day, effect.stop);
      }}
    />
  );

  // Hiding the dock must not unmount the Assistant: an in-flight turn and the
  // loaded transcript have to survive a hide/show round trip.
  const assistantDock = (
    <section
      className={`relative z-30 shrink-0 border-t border-slate-200 bg-white${chatOpen ? "" : " hidden"}`}
    >
      {assistantPanel}
    </section>
  );

  const [mobileTripOpen, setMobileTripOpen] = useState(false);
  useEffect(() => {
    if (isDesktop && mobileTripOpen) setMobileTripOpen(false);
  }, [isDesktop, mobileTripOpen]);

  // Hiding the Assistant must not leave it remembering a full-height sheet the
  // next time it is opened.
  useEffect(() => {
    if (!chatOpen) setAssistantView("bar");
  }, [chatOpen]);

  // The first alert says what happened; anything after it is the guard saying
  // what that cost. The headline stays short and the rest becomes the detail,
  // so "apply and say what it cost" survives without a wall of text.
  const latestStatus = compactStatus(view?.alerts?.[0]);
  const statusDetail = (view?.alerts ?? []).slice(1).filter(Boolean).join(" ") || undefined;
  const reviewSummary = plannerReview
    ? [latestStatus, plannerReview.summary].filter(Boolean).join(" ")
    : null;

  // One notification channel for the whole workspace: progress while long work
  // runs, the outcome when it lands, failures until dismissed, and decisions
  // until answered. Effect order matters — equal-priority notices break the tie
  // by recency, and the assistant is the most current voice.
  useEffect(() => {
    if (loading) notify({ id: "trip-refresh", tone: "progress", message: "Refreshing trip…" });
    else dismissNotice("trip-refresh");
  }, [loading]);

  useEffect(() => {
    if (latestStatus && !reviewSummary) {
      notify({ id: "trip-alert", tone: "success", message: latestStatus, detail: statusDetail });
    } else {
      dismissNotice("trip-alert");
    }
  }, [latestStatus, statusDetail, reviewSummary]);

  useEffect(() => {
    if (reviewSummary) notify({ id: "planner-review", tone: "decision", message: reviewSummary });
    else dismissNotice("planner-review");
  }, [reviewSummary]);

  useEffect(() => {
    if (!assistantTurnStatus?.message) {
      dismissNotice("assistant");
      return;
    }
    const { phase, message, detail } = assistantTurnStatus;
    notify({
      id: "assistant",
      tone:
        phase === "working" || phase === "loading"
          ? "progress"
          : phase === "error"
            ? "error"
            : "success",
      message,
      detail,
    });
  }, [assistantTurnStatus]);

  return <>
    {!isDesktop && <FloatingStatusBar />}
    {showExport && <ExportModal onClose={() => setShowExport(false)} />}
    {isDesktop ? (
      <div className="flex h-[100dvh] min-h-0 flex-col overflow-hidden bg-surface">
        <DesktopToolbar
          tripVersion={tripVersion}
          onTripSwitched={handleSwitched}
          reviewPending={plannerReview !== null}
          onReviewWithPlanner={reviewWithPlanner}
          onKeepReview={() => setPlannerReview(null)}
          onStartNewTrip={handleStartNewTrip}
          onResetTrip={handleResetTrip}
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
          onOpenAccount={() => openAccountSettings()}
          documentBadge={documentBadge}
          documentBadgeTone={documentBadgeTone}
          onOpenDocuments={() => openAccountSettings("documents")}
          onOpenWelcome={() => window.dispatchEvent(new Event("tripplanner:open-welcome"))}
          feedback={view?.feedback ?? { count: 0 }}
        />

        <main
          ref={workspaceRef}
          className="relative grid min-h-0 flex-1 overflow-hidden p-2"
          style={{ gridTemplateColumns: workspaceColumns }}
        >
          <section className={`min-h-0 min-w-0 ${!itineraryOpen || maximizedPane && maximizedPane !== "itinerary" ? "hidden" : ""}`}>
            <CanvasPaneFrame
              label="Itinerary"
              maximized={maximizedPane === "itinerary"}
              onHide={() => setCanvasOpen("itinerary", false)}
              onToggleMaximize={() => toggleMaxPane("itinerary")}
              headerTargetRef={setItineraryHeaderTarget}
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
              aria-valuemin={ITINERARY_MIN_PCT}
              aria-valuemax={Math.round(itineraryMaxPct)}
              aria-valuenow={Math.round(effectiveItineraryPct)}
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
              onHide={() => setCanvasOpen("map", false)}
              onToggleMaximize={() => toggleMaxPane("map")}
            >
              {renderCanvasBody("map")}
            </CanvasPaneFrame>
          </section>
          {!maximizedPane && isWideDesktop && dockOpen && (itineraryOpen || mapOpen) && (
            <div
              role="separator"
              tabIndex={0}
              aria-label={`Resize ${mapOpen ? "map" : "itinerary"} and details`}
              aria-orientation="vertical"
              aria-valuemin={INSPECTOR_MIN_PCT}
              aria-valuemax={Math.round(inspectorMaxPct)}
              aria-valuenow={Math.round(effectiveInspectorPct)}
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
        </main>
        {assistantDock}
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
              destination={view?.destination ?? null}
              onNewTrip={handleNewTrip}
              onImported={handleImported}
            />
          )}
          hasTrip={Boolean(view?.has_trip)}
          tripOpen={mobileTripOpen}
          onOpenTrip={() => setMobileTripOpen(true)}
          onCloseTrip={() => setMobileTripOpen(false)}
          onOpenWelcome={() => window.dispatchEvent(new Event("tripplanner:open-welcome"))}
          feedback={view?.feedback ?? { count: 0 }}
          tripDetails={(
            <RightRail {...railProps} photos={<TripPanel {...tripPanelProps} hideSwitcher />} />
          )}
        />
    )}
  </>;
}

