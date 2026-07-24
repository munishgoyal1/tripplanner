import { Maximize2, MessageCircle, Minimize2, PanelRight, X } from "lucide-react";
import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import ChatPanel from "./components/ChatPanel";
import ItineraryPanel from "./components/ItineraryPanel";
import MapPanel from "./components/MapPanel";
import TripPanel from "./components/TripPanel";
import TripSwitcher from "./components/TripSwitcher";
import RightRail from "./components/RightRail";
import { fetchTripView, importSharedTrip, selectItem, deselectItem, type SelectItemOptions } from "./api";
import type { TripView } from "./types";
import { initialWorkspaceState, workspaceReducer } from "./workspaceState";

interface NavRef {
  kind: string;
  name: string;
}

type CanvasPane = "itinerary" | "map";

function isPlaceKind(kind: string): boolean {
  return kind === "hotel" || kind === "attraction" || kind === "activity";
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
  const [maximizedPane, setMaximizedPane] = useState<CanvasPane | null>(null);
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [chatOpen, setChatOpen] = useState(true);

  const [isDesktop, setIsDesktop] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(min-width: 768px)").matches
  );
  const [isWideDesktop, setIsWideDesktop] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(min-width: 1200px)").matches
  );

  const refreshGeneration = useRef(0);
  const refreshController = useRef<AbortController | null>(null);

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
  const handleImported = async () => {
    dispatchWorkspace({ type: "trip-changed" });
    await refresh(null);
  };

  // After every chat turn: refresh the trip panel, and detect a mid-chat
  // destination switch (the agent created a NEW trip → server returns a new
  // trip_id). On a real switch we reload the chat so the fresh, carryover-seeded
  // transcript replaces the previous trip's conversation.
  const handleTurnComplete = (tripId?: string) => {
    refresh();
    if (!tripId) return;
    dispatchWorkspace({ type: "chat-trip-observed", tripId });
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
      if (focus) {
        await refresh(focus);
      } else {
        setView({ ...next.view, alerts: next.alerts });
        setNavList(next.view.items.map((it) => ({ kind: it.kind, name: it.name })));
      }
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
    try {
      setActionError(null);
      const next = await deselectItem(kind, name);
      if (focus) {
        await refresh(focus);
      } else {
        setView({ ...next.view, alerts: next.alerts });
        setNavList(next.view.items.map((it) => ({ kind: it.kind, name: it.name })));
      }
      dispatchWorkspace({ type: "trip-content-changed" });
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Could not remove the place.");
    }
  };

  const handleStopRemove = async (kind: string, name: string) => {
    const removesFocus = focus?.name.toLowerCase() === name.toLowerCase();
    if (removesFocus) {
      dispatchWorkspace({ type: "focus", place: null });
      try {
        const next = await deselectItem(kind, name);
        setView({ ...next.view, alerts: next.alerts });
        setNavList(next.view.items.map((it) => ({ kind: it.kind, name: it.name })));
        dispatchWorkspace({ type: "trip-content-changed" });
      } catch (error) {
        setActionError(error instanceof Error ? error.message : "Could not remove the place.");
        return;
      }
    } else {
      await handleDeselect(kind, name);
    }
    dispatchWorkspace({ type: "focus", place: null });
    dispatchWorkspace({ type: "jump", target: null });
  };

  const toggleMaxPane = (pane: CanvasPane) => {
    setMaximizedPane((prev) => (prev === pane ? null : pane));
  };

  const handleStopFocus = (kind: string, name: string) => {
    setMapOpen(true);
    if (isPlaceKind(kind)) {
      handleFocus(kind === "activity" ? "attraction" : kind, name);
    }
  };

  const handleStopMap = (kind: string, name: string) => {
    setMapOpen(true);
    if (isPlaceKind(kind)) {
      handleFocus(kind === "activity" ? "attraction" : kind, name);
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
            onClick={() => toggleMaxPane(pane)}
            className="ml-auto grid h-7 w-7 place-items-center rounded-full text-slate-500 transition hover:bg-slate-100 hover:text-ink"
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
    <div className={!inspectorOpen || maximizedPane ? "hidden" : "contents"}>
      <aside
        data-testid="context-inspector"
        className={`flex min-h-0 flex-col overflow-hidden bg-surface ${
          isWideDesktop
            ? "h-full rounded-2xl border border-slate-200/70 shadow-card"
            : "absolute inset-y-2 right-2 z-40 w-[min(25rem,calc(100vw-2rem))] rounded-2xl border border-slate-200 shadow-pop"
        }`}
      >
      <header className="flex h-10 shrink-0 items-center gap-2 border-b border-slate-100 bg-white px-3">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          {focus ? "Place details" : "Trip details"}
        </h2>
        {focus && <span className="min-w-0 truncate text-xs font-medium text-ink">{focus.name}</span>}
        <button
          type="button"
          onClick={() => setInspectorOpen(false)}
          className="ml-auto grid h-7 w-7 place-items-center rounded-full text-slate-500 hover:bg-slate-100 hover:text-ink"
          aria-label="Close details inspector"
        >
          <X size={15} aria-hidden />
        </button>
      </header>
      <div className="min-h-0 flex-1">
        <TripPanel {...tripPanelProps} hideSwitcher />
      </div>
        <section
          className={`relative z-10 shrink-0 overflow-hidden border-t border-slate-200 bg-white shadow-[0_-12px_30px_rgba(15,23,42,0.08)] transition-[height] duration-300 ${
            chatOpen ? (view?.has_trip ? "h-[44%] min-h-72" : "h-[62%] min-h-80") : "h-12"
          }`}
        >
          <div className={`relative h-full ${chatOpen ? "visible" : "invisible"}`}>
            <ChatPanel
              onTurnComplete={handleTurnComplete}
              reloadToken={chatReloadToken}
              tripIdHint={chatTripId}
              onNewTrip={handleNewTrip}
              onImported={handleImported}
            />
          </div>
          {chatOpen ? (
            <button
              type="button"
              onClick={() => setChatOpen(false)}
              className="absolute right-3 top-3 z-30 grid h-8 w-8 place-items-center rounded-full bg-white text-slate-500 shadow-sm ring-1 ring-slate-200 hover:text-ink"
              aria-label="Collapse assistant"
              title="Collapse assistant"
            >
              <Minimize2 size={15} aria-hidden />
            </button>
          ) : (
          <button
            type="button"
            onClick={() => setChatOpen(true)}
              className="absolute inset-0 flex h-full w-full items-center gap-2 px-4 text-sm font-semibold text-ink hover:bg-slate-50"
          >
            <MessageCircle size={17} className="text-brand" aria-hidden />
            Ask the trip assistant
            <span className="ml-auto text-xs font-normal text-slate-400">Expand</span>
          </button>
          )}
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

  return <>
    {errorBanner}
    {isDesktop ? (
      <div className="flex h-[100dvh] min-h-0 flex-col overflow-hidden bg-surface">
        <header className="flex h-12 shrink-0 items-center gap-3 border-b border-slate-100 bg-white/90 px-3 backdrop-blur">
          <TripSwitcher version={tripVersion} onSwitched={handleSwitched} />
          {view?.overview.destination && (
            <div className="min-w-0 border-l border-slate-200 pl-3">
              <p className="truncate text-sm font-semibold text-ink">{view.overview.destination}</p>
              <p className="truncate text-[11px] text-slate-500">
                {[view.overview.departure_date, view.overview.return_date].filter(Boolean).join(" - ")}
              </p>
            </div>
          )}
          {!inspectorOpen && !maximizedPane && (
            <button
              type="button"
              onClick={() => setInspectorOpen(true)}
              className="btn-ghost ml-auto"
            >
              <PanelRight size={15} aria-hidden /> Details
            </button>
          )}
          <span className={`${inspectorOpen ? "ml-auto" : ""} text-xs font-medium text-slate-400`}>Spatial planner</span>
        </header>

        <main
          className={`relative grid min-h-0 flex-1 gap-2 overflow-hidden p-2 ${
            maximizedPane
              ? "grid-cols-1"
              : isWideDesktop && inspectorOpen
                ? "grid-cols-[minmax(19rem,23rem)_minmax(0,1fr)_minmax(21rem,26rem)]"
                : "grid-cols-[minmax(18rem,22rem)_minmax(0,1fr)]"
          }`}
        >
          <section className={`min-h-0 min-w-0 ${maximizedPane === "map" ? "hidden" : ""}`}>
            {renderCanvasPane("itinerary")}
          </section>
          <section className={`min-h-0 min-w-0 ${maximizedPane === "itinerary" ? "hidden" : ""}`}>
            {renderCanvasPane("map")}
          </section>
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

