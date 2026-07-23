import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import ChatPanel from "./components/ChatPanel";
import ItineraryPanel from "./components/ItineraryPanel";
import MapPanel from "./components/MapPanel";
import TripPanel, { TripSwitcher } from "./components/TripPanel";
import RightRail from "./components/RightRail";
import { fetchTripView, importSharedTrip, selectItem, deselectItem, type SelectItemOptions } from "./api";
import type { TripView } from "./types";
import { initialWorkspaceState, workspaceReducer } from "./workspaceState";

interface NavRef {
  kind: string;
  name: string;
}

type DragType = "main" | "leftV" | "rightV" | null;
type PaneId = "itinerary" | "chat" | "map" | "details";

const PANE_LABEL: Record<PaneId, string> = {
  itinerary: "Itinerary",
  chat: "Chat",
  map: "Map",
  details: "Details",
};

function clamp(v: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, v));
}

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
  const [leftPct, setLeftPct] = useState<number>(() => {
    const saved = Number(localStorage.getItem("tripplanner_left_pct"));
    // Layout C: left column (map+itinerary) ~62%, right column (details+chat) ~38%
    return saved >= 25 && saved <= 75 ? saved : 62;
  });
  const [leftTopPct, setLeftTopPct] = useState<number>(() => {
    const saved = Number(localStorage.getItem("tripplanner_left_top_pct"));
    // Map occupies ~65% of left height; itinerary gets ~35%
    return saved >= 15 && saved <= 85 ? saved : 65;
  });
  const [rightTopPct, setRightTopPct] = useState<number>(() => {
    const saved = Number(localStorage.getItem("tripplanner_right_top_pct"));
    // Details occupies ~78% of right height; chat strip gets ~22%
    return saved >= 15 && saved <= 85 ? saved : 78;
  });

  const [maximizedPane, setMaximizedPane] = useState<PaneId | null>(null);

  const [isDesktop, setIsDesktop] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(min-width: 768px)").matches
  );

  const rootRef = useRef<HTMLDivElement>(null);
  const leftRef = useRef<HTMLDivElement>(null);
  const rightRef = useRef<HTMLDivElement>(null);
  const dragType = useRef<DragType>(null);
  const refreshGeneration = useRef(0);
  const refreshController = useRef<AbortController | null>(null);

  useEffect(() => {
    const mq = window.matchMedia("(min-width: 768px)");
    const onChange = (e: MediaQueryListEvent) => setIsDesktop(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  useEffect(() => {
    function onMove(e: MouseEvent) {
      if (!dragType.current) return;
      if (dragType.current === "main" && rootRef.current) {
        const rect = rootRef.current.getBoundingClientRect();
        const pct = ((e.clientX - rect.left) / rect.width) * 100;
        setLeftPct(clamp(pct, 20, 80));
        return;
      }
      if (dragType.current === "leftV" && leftRef.current) {
        const rect = leftRef.current.getBoundingClientRect();
        const pct = ((e.clientY - rect.top) / rect.height) * 100;
        setLeftTopPct(clamp(pct, 10, 90));
        return;
      }
      if (dragType.current === "rightV" && rightRef.current) {
        const rect = rightRef.current.getBoundingClientRect();
        const pct = ((e.clientY - rect.top) / rect.height) * 100;
        setRightTopPct(clamp(pct, 10, 90));
      }
    }

    function onUp() {
      if (!dragType.current) return;
      dragType.current = null;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      localStorage.setItem("tripplanner_left_pct", String(Math.round(leftPct)));
      localStorage.setItem("tripplanner_left_top_pct", String(Math.round(leftTopPct)));
      localStorage.setItem("tripplanner_right_top_pct", String(Math.round(rightTopPct)));
      localStorage.setItem("tripplanner_map_open", JSON.stringify(mapOpen));
    }

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [leftPct, leftTopPct, rightTopPct, mapOpen]);

  const startDrag = (type: DragType) => {
    dragType.current = type;
    document.body.style.cursor = type === "main" ? "col-resize" : "row-resize";
    document.body.style.userSelect = "none";
  };

  const resizeWithKeyboard = (type: Exclude<DragType, null>, key: string) => {
    const delta = key === "ArrowRight" || key === "ArrowDown" ? 3 : -3;
    if (type === "main" && (key === "ArrowLeft" || key === "ArrowRight")) {
      setLeftPct((value) => clamp(value + delta, 20, 80));
    } else if (type === "leftV" && (key === "ArrowUp" || key === "ArrowDown")) {
      setLeftTopPct((value) => clamp(value + delta, 10, 90));
    } else if (type === "rightV" && (key === "ArrowUp" || key === "ArrowDown")) {
      setRightTopPct((value) => clamp(value + delta, 10, 90));
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

  const toggleMaxPane = (pane: PaneId) => {
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

  const renderPaneBody = (pane: PaneId) => {
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
    if (pane === "chat") {
      return (
        <ChatPanel
          onTurnComplete={handleTurnComplete}
          reloadToken={chatReloadToken}
          tripIdHint={chatTripId}
          onNewTrip={handleNewTrip}
          onImported={handleImported}
        />
      );
    }
    if (pane === "map") {
      return (
        <MapPanel
          reloadToken={tripVersion}
          focusName={stopFocusName}
          onPinFocus={handleStopFocus}
          onSelect={handleSelect}
          onDeselect={handleDeselect}
        />
      );
    }
    return <TripPanel {...tripPanelProps} hideSwitcher />;
  };

  const renderPane = (pane: PaneId) => {
    return (
      <article className="flex h-full min-h-0 flex-col rounded-2xl border border-slate-200/70 bg-white/80 shadow-card">
        <header className="flex items-center gap-2 border-b border-slate-100 px-3 py-2">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">{PANE_LABEL[pane]}</h3>
          <button
            type="button"
            onClick={() => toggleMaxPane(pane)}
            className="ml-auto rounded-full px-2.5 py-1 text-xs font-medium text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50"
            title={maximizedPane === pane ? "Restore" : "Maximize"}
          >
            {maximizedPane === pane ? "Restore" : "Max"}
          </button>
        </header>
        <div className="min-h-0 flex-1">{renderPaneBody(pane)}</div>
      </article>
    );
  };

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
      <div className="flex min-h-screen flex-col bg-surface">
        <div className="flex items-center gap-2 border-b border-slate-100 bg-white/85 px-3 py-2 backdrop-blur">
          <TripSwitcher version={tripVersion} onSwitched={handleSwitched} />
          <span className="ml-auto text-xs font-medium text-slate-400">Trip workspace</span>
        </div>

        <div ref={rootRef} className="flex min-h-[calc(100vh-56px)] flex-1 gap-2 overflow-y-auto p-2">
          {maximizedPane ? (
            <div className="min-h-0 flex-1">{renderPane(maximizedPane)}</div>
          ) : (
            <>
              <section ref={leftRef} className="flex min-w-0 flex-col gap-2" style={{ flexBasis: `${leftPct}%` }}>
                <section className="min-h-0" style={{ flexBasis: `${leftTopPct}%` }}>
                  {renderPane("map")}
                </section>
                <div
                  role="separator"
                  tabIndex={0}
                  aria-label="Resize map and itinerary"
                  aria-orientation="horizontal"
                  aria-valuenow={Math.round(leftTopPct)}
                  onMouseDown={() => startDrag("leftV")}
                  onKeyDown={(event) => {
                    if (resizeWithKeyboard("leftV", event.key)) event.preventDefault();
                  }}
                  title="Drag or use arrow keys to resize map and itinerary"
                  className="group relative h-1.5 cursor-row-resize bg-transparent transition-colors hover:bg-brand/30 focus:bg-brand/30 focus:outline-none"
                >
                  <span className="absolute left-1/2 top-1/2 h-1 w-14 -translate-x-1/2 -translate-y-1/2 rounded-full bg-slate-200 group-hover:bg-brand/60" />
                </div>
                <section className="min-h-0 flex-1">{renderPane("itinerary")}</section>
              </section>

              <div
                role="separator"
                tabIndex={0}
                aria-label="Resize trip canvas and details"
                aria-orientation="vertical"
                aria-valuenow={Math.round(leftPct)}
                onMouseDown={() => startDrag("main")}
                onKeyDown={(event) => {
                  if (resizeWithKeyboard("main", event.key)) event.preventDefault();
                }}
                title="Drag or use arrow keys to resize trip canvas and details"
                className="group relative w-1.5 cursor-col-resize bg-transparent transition-colors hover:bg-brand/30 focus:bg-brand/30 focus:outline-none"
              >
                <span className="absolute left-1/2 top-1/2 h-12 w-1 -translate-x-1/2 -translate-y-1/2 rounded-full bg-slate-200 group-hover:bg-brand/60" />
              </div>

              <aside ref={rightRef} className="flex min-w-0 flex-1 flex-col gap-2">
                <section className="min-h-0" style={{ flexBasis: `${rightTopPct}%` }}>
                  {renderPane("details")}
                </section>
                <div
                  role="separator"
                  tabIndex={0}
                  aria-label="Resize details and chat"
                  aria-orientation="horizontal"
                  aria-valuenow={Math.round(rightTopPct)}
                  onMouseDown={() => startDrag("rightV")}
                  onKeyDown={(event) => {
                    if (resizeWithKeyboard("rightV", event.key)) event.preventDefault();
                  }}
                  title="Drag or use arrow keys to resize details and chat"
                  className="group relative h-1.5 cursor-row-resize bg-transparent transition-colors hover:bg-brand/30 focus:bg-brand/30 focus:outline-none"
                >
                  <span className="absolute left-1/2 top-1/2 h-1 w-14 -translate-x-1/2 -translate-y-1/2 rounded-full bg-slate-200 group-hover:bg-brand/60" />
                </div>
                <section className="min-h-0 flex-1">{renderPane("chat")}</section>
              </aside>
            </>
          )}
        </div>
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

