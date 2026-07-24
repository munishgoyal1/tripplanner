import { EyeOff, FileDown, Map, Maximize2, MessageCircle, Minimize2, PanelLeft, PanelRight, Plus, Settings, UserRound } from "lucide-react";
import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import ChatPanel from "./components/ChatPanel";
import ExportModal from "./components/ExportModal";
import ItineraryPanel from "./components/ItineraryPanel";
import MapPanel from "./components/MapPanel";
import TripPanel from "./components/TripPanel";
import TripSwitcher from "./components/TripSwitcher";
import RightRail from "./components/RightRail";
import { fetchTripView, getDisplayName, importSharedTrip, isAnonymousUser, selectItem, deselectItem, startNewTrip, type SelectItemOptions } from "./api";
import type { TripView } from "./types";
import { initialWorkspaceState, workspaceReducer } from "./workspaceState";

interface NavRef {
  kind: string;
  name: string;
}

type CanvasPane = "itinerary" | "map";
type WorkspacePane = CanvasPane | "details" | "assistant";
type ResizeTarget = "itinerary" | "inspector" | "chat" | null;

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
  return kind === "hotel" ? "hotel" : "attraction";
}

export default function App() {
  const [view, setView] = useState<TripView | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionError, setActionError] = useState<string | null>(null);
  const [navList, setNavList] = useState<NavRef[]>([]);
  const [workspace, dispatchWorkspace] = useReducer(workspaceReducer, initialWorkspaceState);
  const focus = workspace.activePlace;
  const stopFocusName = workspace.activePlace?.name ?? null;
  const tripVersion = workspace.tripRevision;
  const chatReloadToken = workspace.chatRevision;
  const chatTripId = workspace.tripId;
  const itineraryJump = workspace.itineraryJump;

  const [mapOpen, setMapOpen] = useState<boolean>(() => {
    const saved = localStorage.getItem("tripplanner_map_open");
    return saved ? JSON.parse(saved) : true;
  });
  const [maximizedPane, setMaximizedPane] = useState<WorkspacePane | null>(null);
  const [itineraryOpen, setItineraryOpen] = useState(true);
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [chatOpen, setChatOpen] = useState(true);
  const [showExport, setShowExport] = useState(false);
  const [signedIn, setSignedIn] = useState(() => !isAnonymousUser());
  const dockOpen = inspectorOpen || chatOpen;
  const canvasMaximized = maximizedPane === "itinerary" || maximizedPane === "map";
  const dockMaximized = maximizedPane === "details" || maximizedPane === "assistant";
  const [itineraryPct, setItineraryPct] = useState(() =>
    storedPercent("tripplanner_itinerary_pct", 24, 18, 38)
  );
  const [inspectorPct, setInspectorPct] = useState(() =>
    storedPercent("tripplanner_inspector_pct", 31, 24, 40)
  );
  const [chatPct, setChatPct] = useState(() =>
    storedPercent("tripplanner_chat_pct", 46, 30, 65)
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
    localStorage.setItem("tripplanner_chat_pct", String(Math.round(chatPct)));
  }, [chatPct, inspectorPct, itineraryPct]);

  useEffect(() => {
    const handleMouseMove = (event: MouseEvent) => {
      const target = resizeTarget.current;
      if (!target) return;

      if (target === "chat" && inspectorRef.current) {
        const rect = inspectorRef.current.getBoundingClientRect();
        setChatPct(clamp(((rect.bottom - event.clientY) / rect.height) * 100, 30, 65));
        return;
      }

      if (!workspaceRef.current) return;
      const rect = workspaceRef.current.getBoundingClientRect();
      if (target === "itinerary") {
        const next = ((event.clientX - rect.left) / rect.width) * 100;
        setItineraryPct(clamp(next, 18, 100 - inspectorPct - 30));
      } else {
        const next = ((rect.right - event.clientX) / rect.width) * 100;
        setInspectorPct(clamp(next, 24, Math.min(40, 100 - itineraryPct - 30)));
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
  }, [chatPct, inspectorPct, itineraryPct]);

  const startResize = (target: Exclude<ResizeTarget, null>) => {
    resizeTarget.current = target;
    document.body.style.cursor = target === "chat" ? "row-resize" : "col-resize";
    document.body.style.userSelect = "none";
  };

  const resizeWithKeyboard = (
    target: Exclude<ResizeTarget, null>,
    key: string
  ): boolean => {
    const growing = key === "ArrowRight" || key === "ArrowDown";
    const delta = growing ? 2 : -2;
    if (target === "itinerary" && (key === "ArrowLeft" || key === "ArrowRight")) {
      setItineraryPct((value) => clamp(value + delta, 18, 100 - inspectorPct - 30));
    } else if (target === "inspector" && (key === "ArrowLeft" || key === "ArrowRight")) {
      setInspectorPct((value) =>
        clamp(value + (growing ? -2 : 2), 24, Math.min(40, 100 - itineraryPct - 30))
      );
    } else if (target === "chat" && (key === "ArrowUp" || key === "ArrowDown")) {
      setChatPct((value) => clamp(value + (key === "ArrowUp" ? 2 : -2), 30, 65));
    } else {
      return false;
    }
    return true;
  };

  const applyView = useCallback((v: TripView, f: NavRef | null) => {
    setView(v);
    if (!f) setNavList(v.items.map((it) => ({ kind: it.kind, name: it.name })));
  }, []);

  const applyMutationView = useCallback(
    (v: TripView, f: NavRef | null) => {
      ++refreshGeneration.current;
      refreshController.current?.abort();
      setLoading(false);
      applyView(v, f);
    },
    [applyView]
  );

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
      } catch (error) {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          console.error("Could not refresh trip view", error);
          setActionError("Could not refresh the trip. Your previous view is still available.");
        }
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
    setSignedIn(!isAnonymousUser());
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

  const handleFocus = async (kind: string, name: string) => {
    const f = { kind, name };
    dispatchWorkspace({ type: "focus", place: f });
    if (isDesktop) setInspectorOpen(true);
    await refresh(f);
  };

  const handleClearFocus = async () => {
    dispatchWorkspace({ type: "focus", place: null });
    await refresh(null);
  };

  const handleSwitched = async (tripId?: string, view?: TripView | null) => {
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
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Could not start a new trip.");
    }
  };
  const handleImported = async () => {
    dispatchWorkspace({ type: "trip-changed" });
    await refresh(null);
  };

  // After every chat turn: refresh the trip panel, and detect a mid-chat
  // destination switch (the agent created a NEW trip → server returns a new
  // trip_id). On a real switch we reload the chat so the fresh, carryover-seeded
  // transcript replaces the previous trip's conversation.
  const handleTurnComplete = (tripId?: string) => {
    const tripChanged = Boolean(tripId && tripId !== chatTripId);
    refresh(tripChanged ? null : focus);
    if (tripId) dispatchWorkspace({ type: "chat-trip-observed", tripId });
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
      setActionError(null);
      const next = await selectItem(kind, name, options);
      const nextKind = focusKind(kind);
      dispatchWorkspace({ type: "focus", place: { kind: nextKind, name } });
      setView({ ...next.view, alerts: next.alerts });
      setNavList(next.view.items.map((it) => ({ kind: it.kind, name: it.name })));
      const placement = next.placement || (next.placements && next.placements.length > 0 ? next.placements[0] : null);
      if (placement?.day && placement?.name) {
        dispatchWorkspace({
          type: "jump",
          target: { day: placement.day, name: placement.name, token: Date.now() },
        });
      }
      dispatchWorkspace({ type: "trip-content-changed" });
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Could not add the place.");
    }
  };

  const handleDeselect = async (kind: string, name: string) => {
    const mutationKey = `${focusKind(kind)}:${name.trim().toLowerCase()}`;
    if (pendingDeselects.current.has(mutationKey)) return false;
    pendingDeselects.current.add(mutationKey);
    try {
      setActionError(null);
      const next = await deselectItem(kind, name);
      const removesFocus = focus?.kind === focusKind(kind)
        && focus.name.toLowerCase() === name.toLowerCase();
      if (removesFocus) {
        dispatchWorkspace({ type: "focus", place: null });
        dispatchWorkspace({ type: "jump", target: null });
      }
      applyMutationView({ ...next.view, alerts: next.alerts }, null);
      setNavList(next.view.items.map((it) => ({ kind: it.kind, name: it.name })));
      dispatchWorkspace({ type: "trip-content-changed" });
      if (!removesFocus && focus) void refresh(focus);
      return true;
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Could not remove the place.");
      return false;
    } finally {
      pendingDeselects.current.delete(mutationKey);
    }
  };

  const handleStopRemove = async (kind: string, name: string) => {
    if (!(await handleDeselect(kind, name))) return;
    dispatchWorkspace({ type: "focus", place: null });
    dispatchWorkspace({ type: "jump", target: null });
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
    if (!open && maximizedPane === pane) setMaximizedPane(null);
  };

  const handleStopFocus = async (kind: string, name: string) => {
    setMapOpen(true);
    if (isPlaceKind(kind)) {
      await handleFocus(focusKind(kind), name);
    }
  };

  const handleStopMap = async (kind: string, name: string) => {
    setMapOpen(true);
    if (isPlaceKind(kind)) {
      await handleFocus(focusKind(kind), name);
    }
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
    tripVersion,
    onSwitched: handleSwitched,
  };

  const railProps = {
    reloadToken: tripVersion,
    focusName: stopFocusName,
    onStopFocus: handleStopFocus,
    onStopMap: handleStopMap,
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
          reloadToken={tripVersion}
          focusName={stopFocusName}
          jumpTo={itineraryJump}
          onStopFocus={handleStopFocus}
          onStopMap={handleStopMap}
          onStopRemove={handleStopRemove}
        />
      );
    }
    return (
      <MapPanel
        reloadToken={tripVersion}
        focusName={stopFocusName}
        onPinFocus={handleStopFocus}
        onDayFocus={(day, place) => {
          dispatchWorkspace({ type: "jump", target: { day, token: Date.now() } });
          if (place) void handleFocus(focusKind(place.kind), place.name);
        }}
        onSelect={handleSelect}
        onDeselect={handleDeselect}
      />
    );
  };

  const renderCanvasPane = (pane: CanvasPane) => {
    const label = pane === "itinerary" ? "Itinerary" : "Map";
    return (
      <article className="flex h-full min-h-0 flex-col overflow-hidden rounded-2xl border border-slate-200/70 bg-white shadow-card">
        <header className="flex h-10 shrink-0 items-center gap-2 border-b border-slate-100 px-3">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</h2>
          <button
            type="button"
            onClick={() => setCanvasOpen(pane, false)}
            className="ml-auto grid h-7 w-7 place-items-center rounded-full text-slate-500 transition hover:bg-slate-100 hover:text-ink disabled:opacity-30"
            aria-label={`Hide ${label}`}
            title={`Hide ${label}`}
            disabled={(pane === "itinerary" && !mapOpen) || (pane === "map" && !itineraryOpen)}
          >
            <EyeOff size={15} aria-hidden />
          </button>
          <button
            type="button"
            onClick={() => toggleMaxPane(pane)}
            className="grid h-7 w-7 place-items-center rounded-full text-slate-500 transition hover:bg-slate-100 hover:text-ink"
            aria-label={maximizedPane === pane ? `Restore ${label}` : `Maximize ${label}`}
            title={maximizedPane === pane ? "Restore" : "Maximize"}
          >
            {maximizedPane === pane ? <Minimize2 size={15} aria-hidden /> : <Maximize2 size={15} aria-hidden />}
          </button>
        </header>
        <div className="min-h-0 flex-1">{renderCanvasBody(pane)}</div>
      </article>
    );
  };

  const inspector = (
    <div className={!dockOpen || canvasMaximized ? "hidden" : "contents"}>
      <aside
        ref={inspectorRef}
        data-testid="context-inspector"
        className={`flex min-h-0 flex-col overflow-hidden bg-surface ${
          isWideDesktop || dockMaximized
            ? "h-full rounded-2xl border border-slate-200/70 shadow-card"
            : "absolute inset-y-2 right-2 z-40 w-[min(27rem,calc(100vw-2rem))] rounded-2xl border border-slate-200 shadow-pop"
        }`}
      >
        <section className={`min-h-0 flex-col ${inspectorOpen && maximizedPane !== "assistant" ? "flex" : "hidden"} ${chatOpen && !dockMaximized ? "flex-1" : "h-full"}`}>
          <header className="flex h-10 shrink-0 items-center gap-2 border-b border-slate-100 bg-white px-3">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              {focus ? "Place details" : "Trip details"}
            </h2>
            {focus && <span className="min-w-0 truncate text-xs font-medium text-ink">{focus.name}</span>}
            <button
              type="button"
              onClick={() => setDockPaneOpen("details", false)}
              className="ml-auto grid h-7 w-7 place-items-center rounded-full text-slate-500 hover:bg-slate-100 hover:text-ink"
              aria-label="Hide Details"
              title="Hide Details"
            >
              <EyeOff size={15} aria-hidden />
            </button>
            <button
              type="button"
              onClick={() => toggleMaxPane("details")}
              className="grid h-7 w-7 place-items-center rounded-full text-slate-500 hover:bg-slate-100 hover:text-ink"
              aria-label={maximizedPane === "details" ? "Restore Details" : "Maximize Details"}
              title={maximizedPane === "details" ? "Restore" : "Maximize"}
            >
              {maximizedPane === "details" ? <Minimize2 size={15} aria-hidden /> : <Maximize2 size={15} aria-hidden />}
            </button>
          </header>
          <div className="min-h-0 flex-1">
            <TripPanel {...tripPanelProps} hideSwitcher />
          </div>
        </section>
        {inspectorOpen && chatOpen && !dockMaximized && (
          <div
            role="separator"
            tabIndex={0}
            aria-label="Resize details and chat"
            aria-orientation="horizontal"
            aria-valuenow={Math.round(chatPct)}
            onMouseDown={() => startResize("chat")}
            onKeyDown={(event) => {
              if (resizeWithKeyboard("chat", event.key)) event.preventDefault();
            }}
            className="group relative z-20 h-1.5 shrink-0 cursor-row-resize bg-transparent hover:bg-brand/20 focus:bg-brand/20 focus:outline-none"
          >
            <span className="absolute left-1/2 top-1/2 h-1 w-12 -translate-x-1/2 -translate-y-1/2 rounded-full bg-slate-300 group-hover:bg-brand/60" />
          </div>
        )}
        <section
          className={`relative z-10 min-h-0 overflow-hidden border-t border-slate-200 bg-white shadow-[0_-12px_30px_rgba(15,23,42,0.08)] ${chatOpen && maximizedPane !== "details" ? "flex flex-col" : "hidden"} ${inspectorOpen && !dockMaximized ? "shrink-0" : "h-full flex-1"}`}
          style={{ height: inspectorOpen && !dockMaximized ? `${chatPct}%` : "100%" }}
        >
          <div className="relative min-h-0 flex-1">
            <ChatPanel
              onTurnComplete={handleTurnComplete}
              reloadToken={chatReloadToken}
              tripIdHint={chatTripId}
              onNewTrip={handleNewTrip}
              onImported={handleImported}
              hideGlobalControls
            />
          </div>
          <button
            type="button"
            onClick={() => setDockPaneOpen("assistant", false)}
            className="absolute right-3 top-3 z-30 grid h-8 w-8 place-items-center rounded-full bg-white text-slate-500 shadow-sm ring-1 ring-slate-200 hover:text-ink"
            aria-label="Hide Assistant"
            title="Hide Assistant"
          >
            <EyeOff size={15} aria-hidden />
          </button>
          <button
            type="button"
            onClick={() => toggleMaxPane("assistant")}
            className="absolute right-12 top-3 z-30 grid h-8 w-8 place-items-center rounded-full bg-white text-slate-500 shadow-sm ring-1 ring-slate-200 hover:text-ink"
            aria-label={maximizedPane === "assistant" ? "Restore Assistant" : "Maximize Assistant"}
            title={maximizedPane === "assistant" ? "Restore" : "Maximize"}
          >
            {maximizedPane === "assistant" ? <Minimize2 size={15} aria-hidden /> : <Maximize2 size={15} aria-hidden />}
          </button>
        </section>
      </aside>
    </div>
  );

  const [mobileTripOpen, setMobileTripOpen] = useState(false);
  useEffect(() => {
    if (isDesktop && mobileTripOpen) setMobileTripOpen(false);
  }, [isDesktop, mobileTripOpen]);

  const errorBanner = actionError ? (
    <div role="alert" className="fixed left-1/2 top-3 z-[70] flex max-w-[calc(100vw-2rem)] -translate-x-1/2 items-center gap-3 rounded-xl bg-rose-50 px-4 py-2 text-sm text-rose-800 shadow-pop ring-1 ring-rose-200">
      <span>{actionError}</span>
      <button type="button" onClick={() => setActionError(null)} className="font-semibold" aria-label="Dismiss error">
        x
      </button>
    </div>
  ) : null;
  const latestStatus = view?.alerts?.[view.alerts.length - 1];
  const statusTone = view?.overview?.status === "booked"
    ? "bg-brand/10 text-brand ring-brand/20"
    : view?.overview?.status === "finalized"
      ? "bg-emerald-50 text-emerald-700 ring-emerald-200"
      : "bg-slate-100 text-slate-600 ring-slate-200";

  return <>
    {errorBanner}
    {showExport && <ExportModal onClose={() => setShowExport(false)} />}
    {isDesktop ? (
      <div className="flex h-[100dvh] min-h-0 flex-col overflow-hidden bg-surface">
        <header className="relative z-50 flex h-12 shrink-0 items-center gap-2 overflow-visible border-b border-slate-100 bg-white/95 px-3 shadow-sm backdrop-blur">
          <TripSwitcher version={tripVersion} onSwitched={handleSwitched} />
          {view?.overview?.destination && (
            <div className="hidden min-w-0 border-l border-slate-200 pl-3 lg:block">
              <p className="truncate text-sm font-semibold text-ink">{view.overview.destination}</p>
              <p className="truncate text-[11px] text-slate-500">
                {[view.overview.departure_date, view.overview.return_date].filter(Boolean).join(" - ")}
              </p>
            </div>
          )}
          {view?.has_trip && view.overview && (
            <div className="hidden items-center gap-1.5 xl:flex">
              <span className={`chip capitalize ring-1 ${statusTone}`}>{view.overview.status}</span>
              <span className="chip bg-white text-slate-600 ring-1 ring-slate-200">
                {view.overview.counts.days}d · {view.overview.counts.hotels} stay · {view.overview.counts.activities} places
              </span>
              {view.overview.total_cost_display && (
                <span className="chip bg-white font-semibold text-ink ring-1 ring-slate-200">
                  {view.overview.total_cost_display}
                </span>
              )}
            </div>
          )}
          <div className="ml-auto min-w-0" aria-live="polite">
            {latestStatus ? (
              <p className="max-w-72 truncate text-xs font-medium text-emerald-700" title={latestStatus}>
                {latestStatus}
              </p>
            ) : loading ? (
              <p className="text-xs text-slate-400">Refreshing trip…</p>
            ) : null}
          </div>
          <nav className="flex shrink-0 items-center gap-1" aria-label="Workspace controls">
            <button
              type="button"
              onClick={handleStartNewTrip}
              className="btn-ghost"
              title="Start a new trip"
            >
              <Plus size={15} aria-hidden /> <span className="hidden xl:inline">New trip</span>
            </button>
            <button
              type="button"
              onClick={() => setCanvasOpen("itinerary", !itineraryOpen)}
              className={`btn-ghost ${itineraryOpen ? "bg-slate-100 text-ink" : ""}`}
              aria-pressed={itineraryOpen}
              title="Show or hide itinerary"
            >
              <PanelLeft size={15} aria-hidden /> <span className="hidden 2xl:inline">Itinerary</span>
            </button>
            <button
              type="button"
              onClick={() => setCanvasOpen("map", !mapOpen)}
              className={`btn-ghost ${mapOpen ? "bg-slate-100 text-ink" : ""}`}
              aria-pressed={mapOpen}
              title="Show or hide map"
            >
              <Map size={15} aria-hidden /> <span className="hidden 2xl:inline">Map</span>
            </button>
            <button
              type="button"
              onClick={() => setDockPaneOpen("details", !inspectorOpen)}
              className={`btn-ghost ${inspectorOpen ? "bg-slate-100 text-ink" : ""}`}
              aria-pressed={inspectorOpen}
              title="Show or hide trip details"
            >
              <PanelRight size={15} aria-hidden /> <span className="hidden xl:inline">Details</span>
            </button>
            <button
              type="button"
              onClick={() => setDockPaneOpen("assistant", !chatOpen)}
              className={`btn-ghost ${chatOpen ? "bg-slate-100 text-ink" : ""}`}
              aria-pressed={chatOpen}
              title="Show or hide the trip assistant"
            >
              <MessageCircle size={15} aria-hidden /> <span className="hidden xl:inline">Assistant</span>
            </button>
            <button
              type="button"
              onClick={() => setShowExport(true)}
              disabled={!view?.has_trip}
              className="btn-ghost disabled:opacity-40"
              title="Export itinerary with photos, PDF, print, or email"
              aria-label="Export itinerary"
            >
              <FileDown size={15} aria-hidden /> <span className="hidden 2xl:inline">Export</span>
            </button>
            <button
              type="button"
              onClick={() => window.dispatchEvent(new Event("tripplanner:open-account"))}
              className="btn-ghost"
              title={signedIn ? `Signed in as ${getDisplayName() || "user"}` : "Guest - sign in to sync trips"}
              aria-label={signedIn ? `Signed in as ${getDisplayName() || "user"}` : "Guest - sign in"}
            >
              <span className="relative">
                <UserRound size={15} aria-hidden />
                <span className={`absolute -bottom-1 -right-1 h-2 w-2 rounded-full ring-2 ring-white ${signedIn ? "bg-emerald-500" : "bg-slate-400"}`} aria-hidden />
              </span>
            </button>
            <button
              type="button"
              onClick={() => window.dispatchEvent(new Event("tripplanner:open-settings"))}
              className="btn-ghost"
              title="Travel preferences"
              aria-label="Travel preferences"
            >
              <Settings size={15} aria-hidden />
            </button>
          </nav>
        </header>

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
            {renderCanvasPane("itinerary")}
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
            {renderCanvasPane("map")}
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
        </main>
      </div>
        ) : (
        <section className="flex h-screen flex-col">
        <ChatPanel
          onTurnComplete={handleTurnComplete}
          reloadToken={chatReloadToken}
          tripIdHint={chatTripId}
          onNewTrip={handleNewTrip}
          onImported={handleImported}
        />

        {view?.has_trip && !mobileTripOpen && (
          <button
            type="button"
            onClick={() => setMobileTripOpen(true)}
            aria-label="Open trip details"
            className="fixed bottom-4 right-4 z-30 inline-flex items-center gap-2 rounded-full bg-ink px-4 py-2.5 text-sm font-medium text-white shadow-pop ring-1 ring-black/10 transition active:scale-95"
          >
            <span>Trip details</span>
          </button>
        )}

        <div
          onClick={() => setMobileTripOpen(false)}
          aria-hidden={!mobileTripOpen}
          className={`fixed inset-0 z-40 bg-black/40 backdrop-blur-sm transition-opacity ${
            mobileTripOpen ? "opacity-100" : "pointer-events-none opacity-0"
          }`}
        />
        <section
          role="dialog"
          aria-modal="true"
          aria-label="Trip details"
          className={`fixed inset-x-0 bottom-0 z-50 flex h-[88vh] flex-col rounded-t-3xl bg-surface shadow-pop transition-transform duration-300 ${
            mobileTripOpen ? "translate-y-0" : "translate-y-full"
          }`}
        >
          <div className="flex items-center justify-between px-4 pt-2 pb-1">
            <button
              type="button"
              onClick={() => setMobileTripOpen(false)}
              aria-label="Close trip details"
              className="-ml-2 grid h-10 w-10 place-items-center rounded-full text-slate-500 transition hover:bg-slate-100 hover:text-ink"
            >
              <span className="text-xl leading-none">x</span>
            </button>
            <div
              onClick={() => setMobileTripOpen(false)}
              className="mx-auto -ml-10 h-1.5 w-12 cursor-pointer rounded-full bg-slate-300"
              aria-hidden
            />
            <span className="w-10" aria-hidden />
          </div>
          <div className="min-h-0 flex-1">
            <RightRail {...railProps} photos={<TripPanel {...tripPanelProps} hideSwitcher />} />
          </div>
        </section>
      </section>
    )}
  </>;
}

