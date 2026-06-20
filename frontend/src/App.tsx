import { useCallback, useEffect, useRef, useState } from "react";
import ChatPanel from "./components/ChatPanel";
import ItineraryPanel from "./components/ItineraryPanel";
import MapPanel from "./components/MapPanel";
import TripPanel, { TripSwitcher } from "./components/TripPanel";
import RightRail from "./components/RightRail";
import { fetchTripView, importSharedTrip, selectItem, deselectItem, type SelectItemOptions } from "./api";
import type { TripView } from "./types";

interface NavRef {
  kind: string;
  name: string;
}

type DragType = "main" | "leftV" | "rightV" | null;
type PaneId = "itinerary" | "chat" | "map" | "details";
type SlotId = "leftTop" | "leftBottom" | "rightTop" | "rightBottom";

type PaneVisibility = Record<PaneId, boolean>;
type PaneSlots = Record<SlotId, PaneId>;

const SLOT_ORDER: SlotId[] = ["leftTop", "leftBottom", "rightTop", "rightBottom"];

const PANE_LABEL: Record<PaneId, string> = {
  itinerary: "Itinerary",
  chat: "Chat",
  map: "Map",
  details: "Details",
};

const DEFAULT_SLOTS: PaneSlots = {
  leftTop: "map",
  leftBottom: "itinerary",
  rightTop: "details",
  rightBottom: "chat",
};

const DEFAULT_HIDDEN: PaneVisibility = {
  itinerary: false,
  chat: false,
  map: false,
  details: false,
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
  const [focus, setFocus] = useState<NavRef | null>(null);
  const [navList, setNavList] = useState<NavRef[]>([]);

  const [mapOpen, setMapOpen] = useState<boolean>(() => {
    const saved = localStorage.getItem("tripplanner_map_open");
    return saved ? JSON.parse(saved) : true;
  });
  const [stopFocusName, setStopFocusName] = useState<string | null>(null);
  const [tripVersion, setTripVersion] = useState(0);
  const [chatReloadToken, setChatReloadToken] = useState(0);
  const [chatTripId, setChatTripId] = useState<string | null>(null);
  const [itineraryJump, setItineraryJump] = useState<{ day: number; name: string; token: number } | null>(null);

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

  const [paneBySlot, setPaneBySlot] = useState<PaneSlots>(DEFAULT_SLOTS);
  const [hiddenPanes, setHiddenPanes] = useState<PaneVisibility>(DEFAULT_HIDDEN);
  const [maximizedPane, setMaximizedPane] = useState<PaneId | null>(null);

  const [isDesktop, setIsDesktop] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(min-width: 768px)").matches
  );

  const rootRef = useRef<HTMLDivElement>(null);
  const leftRef = useRef<HTMLDivElement>(null);
  const rightRef = useRef<HTMLDivElement>(null);
  const dragType = useRef<DragType>(null);

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

  const applyView = useCallback((v: TripView, f: NavRef | null) => {
    setView(v);
    setTripVersion((n) => n + 1);
    if (!f) setNavList(v.items.map((it) => ({ kind: it.kind, name: it.name })));
  }, []);

  const refresh = useCallback(
    async (f: NavRef | null = focus) => {
      setLoading(true);
      try {
        const v = await fetchTripView(f ?? undefined);
        applyView(v, f);
      } finally {
        setLoading(false);
      }
    },
    [focus, applyView]
  );

  useEffect(() => {
    refresh(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleIdentityChanged = useCallback(async () => {
    setView(null);
    setLoading(true);
    setFocus(null);
    setStopFocusName(null);
    setItineraryJump(null);
    setTripVersion((n) => n + 1);
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
        setFocus(null);
        setStopFocusName(null);
        setTripVersion((n) => n + 1);
        setChatReloadToken((n) => n + 1);
        setChatTripId(null);
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
    setFocus(f);
    if (isPlaceKind(kind)) {
      setStopFocusName(name);
    }
    await refresh(f);
  };

  const handleClearFocus = async () => {
    setFocus(null);
    await refresh(null);
  };

  const handleSwitched = async (tripId?: string, view?: TripView | null) => {
    setChatReloadToken((n) => n + 1);
    setChatTripId(tripId || null);
    setStopFocusName(null);
    setFocus(null);
    // The switcher already fetched the fresh view — reuse it instead of making
    // the server rebuild the (cache-backed) view a second time.
    if (view) {
      applyView(view, null);
    } else {
      await handleClearFocus();
    }
  };

  const handleNewTrip = async () => {
    setChatReloadToken((n) => n + 1);
    setChatTripId(null);
    setStopFocusName(null);
    await handleClearFocus();
  };
  const handleImported = async () => {
    setTripVersion((n) => n + 1);
    setChatReloadToken((n) => n + 1);
    setChatTripId(null);
    setStopFocusName(null);
    await handleClearFocus();
  };

  // After every chat turn: refresh the trip panel, and detect a mid-chat
  // destination switch (the agent created a NEW trip → server returns a new
  // trip_id). On a real switch we reload the chat so the fresh, carryover-seeded
  // transcript replaces the previous trip's conversation.
  const handleTurnComplete = (tripId?: string) => {
    refresh();
    if (!tripId) return;
    if (chatTripId && tripId !== chatTripId) {
      setChatTripId(tripId);
      setChatReloadToken((n) => n + 1);
    } else if (!chatTripId) {
      // First trip created from the general chat — keep the transcript, just
      // start tracking the new id so the next switch is detected.
      setChatTripId(tripId);
    }
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
    const next = await selectItem(kind, name, options);
    if (focus) {
      const refreshed = await fetchTripView(focus);
      setView({ ...refreshed, alerts: next.alerts });
    } else {
      setView({ ...next.view, alerts: next.alerts });
      setNavList(next.view.items.map((it) => ({ kind: it.kind, name: it.name })));
    }
    const placement = next.placement || (next.placements && next.placements.length > 0 ? next.placements[0] : null);
    if (placement?.day && placement?.name) {
      setItineraryJump({ day: placement.day, name: placement.name, token: Date.now() });
    }
    // Refresh the map + itinerary panes, which are keyed on tripVersion.
    setTripVersion((n) => n + 1);
  };

  const handleDeselect = async (kind: string, name: string) => {
    const next = await deselectItem(kind, name);
    if (focus) {
      const refreshed = await fetchTripView(focus);
      setView({ ...refreshed, alerts: next.alerts });
    } else {
      setView({ ...next.view, alerts: next.alerts });
      setNavList(next.view.items.map((it) => ({ kind: it.kind, name: it.name })));
    }
    setTripVersion((n) => n + 1);
  };

  const handleStopRemove = async (kind: string, name: string) => {
    await handleDeselect(kind, name);
    setStopFocusName(null);
    setItineraryJump(null);
  };

  const revealPane = (pane: PaneId) => {
    setHiddenPanes((prev) => ({ ...prev, [pane]: false }));
  };

  const hidePane = (pane: PaneId) => {
    setHiddenPanes((prev) => ({ ...prev, [pane]: true }));
    if (maximizedPane === pane) setMaximizedPane(null);
  };

  const toggleMaxPane = (pane: PaneId) => {
    revealPane(pane);
    setMaximizedPane((prev) => (prev === pane ? null : pane));
  };

  const slotForPane = (pane: PaneId): SlotId => {
    const found = SLOT_ORDER.find((slot) => paneBySlot[slot] === pane);
    return found ?? "leftTop";
  };

  const movePane = (pane: PaneId) => {
    const from = slotForPane(pane);
    const fromIndex = SLOT_ORDER.indexOf(from);
    const to = SLOT_ORDER[(fromIndex + 1) % SLOT_ORDER.length];
    setPaneBySlot((prev) => ({
      ...prev,
      [from]: prev[to],
      [to]: prev[from],
    }));
  };

  const resetPaneLayout = () => {
    setPaneBySlot(DEFAULT_SLOTS);
    setHiddenPanes(DEFAULT_HIDDEN);
    setLeftPct(62);
    setLeftTopPct(65);
    setRightTopPct(78);
    setMaximizedPane(null);
  };

  const handleStopFocus = (kind: string, name: string) => {
    setStopFocusName(name);
    revealPane("map");
    revealPane("details");
    setMapOpen(true);
    if (isPlaceKind(kind)) {
      handleFocus(kind === "activity" ? "attraction" : kind, name);
    }
  };

  const handleStopMap = (kind: string, name: string) => {
    setStopFocusName(name);
    revealPane("map");
    revealPane("details");
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
    if (hiddenPanes[pane]) {
      return (
        <div className="grid h-full place-items-center rounded-2xl border border-dashed border-slate-200 bg-white/50 p-6 text-center">
          <div>
            <p className="text-sm font-medium text-slate-600">{PANE_LABEL[pane]} is hidden</p>
            <button
              type="button"
              onClick={() => revealPane(pane)}
              className="mt-3 rounded-full px-4 py-1.5 text-xs font-medium text-slate-700 ring-1 ring-slate-200 hover:bg-slate-50"
            >
              Show
            </button>
          </div>
        </div>
      );
    }
    return (
      <article className="flex h-full min-h-0 flex-col rounded-2xl border border-slate-200/70 bg-white/80 shadow-card">
        <header className="flex items-center gap-2 border-b border-slate-100 px-3 py-2">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">{PANE_LABEL[pane]}</h3>
          <button
            type="button"
            onClick={() => movePane(pane)}
            className="ml-auto rounded-full px-2.5 py-1 text-xs font-medium text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50"
            title="Move pane"
          >
            Move
          </button>
          <button
            type="button"
            onClick={() => toggleMaxPane(pane)}
            className="rounded-full px-2.5 py-1 text-xs font-medium text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50"
            title={maximizedPane === pane ? "Restore" : "Maximize"}
          >
            {maximizedPane === pane ? "Restore" : "Max"}
          </button>
          <button
            type="button"
            onClick={() => hidePane(pane)}
            className="rounded-full px-2.5 py-1 text-xs font-medium text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50"
            title="Hide pane"
          >
            Hide
          </button>
        </header>
        <div className="min-h-0 flex-1">{renderPaneBody(pane)}</div>
      </article>
    );
  };

  const leftTopPane = paneBySlot.leftTop;
  const leftBottomPane = paneBySlot.leftBottom;
  const rightTopPane = paneBySlot.rightTop;
  const rightBottomPane = paneBySlot.rightBottom;

  const leftTopVisible = !hiddenPanes[leftTopPane];
  const leftBottomVisible = !hiddenPanes[leftBottomPane];
  const rightTopVisible = !hiddenPanes[rightTopPane];
  const rightBottomVisible = !hiddenPanes[rightBottomPane];

  const leftColumnVisible = leftTopVisible || leftBottomVisible;
  const rightColumnVisible = rightTopVisible || rightBottomVisible;

  const hiddenPaneList = (Object.keys(hiddenPanes) as PaneId[]).filter((pane) => hiddenPanes[pane]);

  const [mobileTripOpen, setMobileTripOpen] = useState(false);
  useEffect(() => {
    if (isDesktop && mobileTripOpen) setMobileTripOpen(false);
  }, [isDesktop, mobileTripOpen]);

  return (
    <>
      <div className="hidden min-h-screen bg-surface md:flex md:flex-col">
        <div className="flex items-center gap-2 border-b border-slate-100 bg-white/85 px-3 py-2 backdrop-blur">
          <span className="rounded-full bg-violet-50 px-3 py-1 text-xs font-semibold text-violet-700 ring-1 ring-violet-200">
            Layout C: Compact canvas
          </span>
          <TripSwitcher version={tripVersion} onSwitched={handleSwitched} />
          <button
            type="button"
            onClick={resetPaneLayout}
            className="rounded-full px-3 py-1 text-xs font-medium text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50"
            title="Reset pane layout"
          >
            Reset layout
          </button>
          {hiddenPaneList.length > 0 && (
            <div className="ml-auto flex items-center gap-2">
              <span className="text-xs font-medium text-slate-500">Hidden:</span>
              {hiddenPaneList.map((pane) => (
                <button
                  key={pane}
                  type="button"
                  onClick={() => revealPane(pane)}
                  className="rounded-full px-3 py-1 text-xs font-medium text-slate-700 ring-1 ring-slate-200 hover:bg-slate-50"
                >
                  Show {PANE_LABEL[pane]}
                </button>
              ))}
            </div>
          )}
        </div>

        <div ref={rootRef} className="flex min-h-[calc(100vh-56px)] flex-1 gap-2 overflow-y-auto p-2">
          {maximizedPane ? (
            <div className="min-h-0 flex-1">{renderPane(maximizedPane)}</div>
          ) : (
            <>
              {leftColumnVisible && (
                <section
                  ref={leftRef}
                  className="flex min-w-0 flex-col gap-2"
                  style={{ flexBasis: rightColumnVisible ? `${leftPct}%` : "100%" }}
                >
                  {leftTopVisible && leftBottomVisible ? (
                    <>
                      <section className="min-h-0" style={{ flexBasis: `${leftTopPct}%` }}>
                        {renderPane(leftTopPane)}
                      </section>
                      <div
                        onMouseDown={() => startDrag("leftV")}
                        title="Drag to resize upper/lower left panes"
                        className="group relative h-1.5 cursor-row-resize bg-transparent transition-colors hover:bg-brand/30"
                      >
                        <span className="absolute left-1/2 top-1/2 h-1 w-14 -translate-x-1/2 -translate-y-1/2 rounded-full bg-slate-200 group-hover:bg-brand/60" />
                      </div>
                      <section className="min-h-0 flex-1">{renderPane(leftBottomPane)}</section>
                    </>
                  ) : leftTopVisible ? (
                    <section className="min-h-0 flex-1">{renderPane(leftTopPane)}</section>
                  ) : (
                    <section className="min-h-0 flex-1">{renderPane(leftBottomPane)}</section>
                  )}
                </section>
              )}

              {leftColumnVisible && rightColumnVisible && (
                <div
                  onMouseDown={() => startDrag("main")}
                  title="Drag to resize left/right"
                  className="group relative w-1.5 cursor-col-resize bg-transparent transition-colors hover:bg-brand/30"
                >
                  <span className="absolute left-1/2 top-1/2 h-12 w-1 -translate-x-1/2 -translate-y-1/2 rounded-full bg-slate-200 group-hover:bg-brand/60" />
                </div>
              )}

              {rightColumnVisible && (
                <aside ref={rightRef} className="flex min-w-0 flex-1 flex-col gap-2">
                  {rightTopVisible && rightBottomVisible ? (
                    <>
                      <section className="min-h-0" style={{ flexBasis: `${rightTopPct}%` }}>
                        {renderPane(rightTopPane)}
                      </section>
                      <div
                        onMouseDown={() => startDrag("rightV")}
                        title="Drag to resize upper/lower right panes"
                        className="group relative h-1.5 cursor-row-resize bg-transparent transition-colors hover:bg-brand/30"
                      >
                        <span className="absolute left-1/2 top-1/2 h-1 w-14 -translate-x-1/2 -translate-y-1/2 rounded-full bg-slate-200 group-hover:bg-brand/60" />
                      </div>
                      <section className="min-h-0 flex-1">{renderPane(rightBottomPane)}</section>
                    </>
                  ) : rightTopVisible ? (
                    <section className="min-h-0 flex-1">{renderPane(rightTopPane)}</section>
                  ) : (
                    <section className="min-h-0 flex-1">{renderPane(rightBottomPane)}</section>
                  )}
                </aside>
              )}

              {!leftColumnVisible && !rightColumnVisible && (
                <section className="grid min-h-0 flex-1 place-items-center rounded-2xl border border-dashed border-slate-200 bg-white/50 text-sm text-slate-500">
                  All panes are hidden. Use the Show buttons in the top bar.
                </section>
              )}
            </>
          )}
        </div>
      </div>

      <section className="flex h-screen flex-col md:hidden">
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
    </>
  );
}

