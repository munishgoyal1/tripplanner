import { useCallback, useEffect, useRef, useState } from "react";
import ChatPanel from "./components/ChatPanel";
import ItineraryPanel from "./components/ItineraryPanel";
import MapPanel from "./components/MapPanel";
import TripPanel, { TripSwitcher } from "./components/TripPanel";
import RightRail from "./components/RightRail";
import { fetchTripView, selectItem, deselectItem } from "./api";
import type { TripView } from "./types";

interface NavRef {
  kind: string;
  name: string;
}

type DragType = "main" | "leftV" | "rightV" | null;

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

  const [mapOpen, setMapOpen] = useState(true);
  const [stopFocusName, setStopFocusName] = useState<string | null>(null);
  const [tripVersion, setTripVersion] = useState(0);
  const [chatReloadToken, setChatReloadToken] = useState(0);
  const [chatTripId, setChatTripId] = useState<string | null>(null);

  // Desktop split state: left/right + vertical splits inside each side.
  const [leftPct, setLeftPct] = useState<number>(() => {
    const saved = Number(localStorage.getItem("multiagent_left_pct"));
    return saved >= 30 && saved <= 70 ? saved : 50;
  });
  const [leftTopPct, setLeftTopPct] = useState<number>(() => {
    const saved = Number(localStorage.getItem("multiagent_left_top_pct"));
    return saved >= 15 && saved <= 85 ? saved : 50;
  });
  const [rightTopPct, setRightTopPct] = useState<number>(() => {
    const saved = Number(localStorage.getItem("multiagent_right_top_pct"));
    return saved >= 15 && saved <= 85 ? saved : 50;
  });

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
        setLeftPct(clamp(pct, 30, 70));
        return;
      }
      if (dragType.current === "leftV" && leftRef.current) {
        const rect = leftRef.current.getBoundingClientRect();
        const pct = ((e.clientY - rect.top) / rect.height) * 100;
        setLeftTopPct(clamp(pct, 15, 85));
        return;
      }
      if (dragType.current === "rightV" && rightRef.current) {
        const rect = rightRef.current.getBoundingClientRect();
        const pct = ((e.clientY - rect.top) / rect.height) * 100;
        setRightTopPct(clamp(pct, 15, 85));
      }
    }

    function onUp() {
      if (!dragType.current) return;
      dragType.current = null;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      localStorage.setItem("multiagent_left_pct", String(Math.round(leftPct)));
      localStorage.setItem("multiagent_left_top_pct", String(Math.round(leftTopPct)));
      localStorage.setItem("multiagent_right_top_pct", String(Math.round(rightTopPct)));
    }

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [leftPct, leftTopPct, rightTopPct]);

  const startDrag = (type: DragType) => {
    dragType.current = type;
    document.body.style.cursor = type === "main" ? "col-resize" : "row-resize";
    document.body.style.userSelect = "none";
  };

  const refresh = useCallback(
    async (f: NavRef | null = focus) => {
      setLoading(true);
      try {
        const v = await fetchTripView(f ?? undefined);
        setView(v);
        setTripVersion((n) => n + 1);
        if (!f) setNavList(v.items.map((it) => ({ kind: it.kind, name: it.name })));
      } finally {
        setLoading(false);
      }
    },
    [focus]
  );

  useEffect(() => {
    refresh(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleFocus = async (kind: string, name: string) => {
    const f = { kind, name };
    setFocus(f);
    await refresh(f);
  };

  const handleClearFocus = async () => {
    setFocus(null);
    await refresh(null);
  };

  const handleSwitched = async (tripId?: string) => {
    setChatReloadToken((n) => n + 1);
    setChatTripId(tripId || null);
    setStopFocusName(null);
    await handleClearFocus();
  };

  const handleNewTrip = async () => {
    setChatReloadToken((n) => n + 1);
    setChatTripId(null);
    setStopFocusName(null);
    await handleClearFocus();
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

  const handleSelect = async (kind: string, name: string) => {
    const next = await selectItem(kind, name);
    setView(focus ? await fetchTripView(focus) : next);
    if (!focus) setNavList(next.items.map((it) => ({ kind: it.kind, name: it.name })));
  };

  const handleDeselect = async (kind: string, name: string) => {
    const next = await deselectItem(kind, name);
    setView(focus ? await fetchTripView(focus) : next);
    if (!focus) setNavList(next.items.map((it) => ({ kind: it.kind, name: it.name })));
  };

  // Itinerary click: always show on map and in details section.
  const handleStopFocus = (kind: string, name: string) => {
    setStopFocusName(name);
    setMapOpen(true);
    if (isPlaceKind(kind)) {
      handleFocus(kind === "activity" ? "attraction" : kind, name);
    }
  };

  // Map pin button from itinerary: open map and also load details when possible.
  const handleStopMap = (kind: string, name: string) => {
    setStopFocusName(name);
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
    tripVersion,
    onSwitched: handleSwitched,
    mapOpen,
    onToggleMap: setMapOpen,
  };

  // Mobile keeps the existing compact flow.
  const [mobileTripOpen, setMobileTripOpen] = useState(false);
  useEffect(() => {
    if (isDesktop && mobileTripOpen) setMobileTripOpen(false);
  }, [isDesktop, mobileTripOpen]);

  return (
    <>
      <div ref={rootRef} className="hidden h-screen bg-surface md:flex">
        <section
          ref={leftRef}
          className="flex min-w-0 flex-col"
          style={{ flexBasis: `${leftPct}%` }}
        >
          <div className="flex items-center gap-2 border-b border-slate-100 bg-white/85 px-3 py-2 backdrop-blur">
            <TripSwitcher version={tripVersion} onSwitched={handleSwitched} />
            <button
              type="button"
              onClick={() => setLeftTopPct((p) => (p > 70 ? 50 : 80))}
              className="ml-auto rounded-full px-3 py-1 text-xs font-medium text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50"
              title="Maximize itinerary area"
            >
              Itinerary ⤢
            </button>
            <button
              type="button"
              onClick={() => setLeftTopPct((p) => (p < 30 ? 50 : 20))}
              className="rounded-full px-3 py-1 text-xs font-medium text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50"
              title="Maximize chat area"
            >
              Chat ⤢
            </button>
          </div>

          <div className="flex min-h-0 flex-1 flex-col">
            <section
              className="min-h-0 border-b border-slate-100"
              style={{ flexBasis: `${leftTopPct}%` }}
            >
              <ItineraryPanel
                reloadToken={tripVersion}
                focusName={stopFocusName}
                onStopFocus={handleStopFocus}
                onStopMap={handleStopMap}
              />
            </section>

            <div
              onMouseDown={() => startDrag("leftV")}
              title="Drag to resize itinerary/chat"
              className="group relative h-1.5 cursor-row-resize bg-transparent transition-colors hover:bg-brand/30"
            >
              <span className="absolute left-1/2 top-1/2 h-1 w-14 -translate-x-1/2 -translate-y-1/2 rounded-full bg-slate-200 group-hover:bg-brand/60" />
            </div>

            <section className="min-h-0 flex-1">
              <ChatPanel
                onTurnComplete={() => refresh()}
                reloadToken={chatReloadToken}
                tripIdHint={chatTripId}
                onNewTrip={handleNewTrip}
              />
            </section>
          </div>
        </section>

        <div
          onMouseDown={() => startDrag("main")}
          title="Drag to resize left/right"
          className="group relative w-1.5 cursor-col-resize bg-transparent transition-colors hover:bg-brand/30"
        >
          <span className="absolute left-1/2 top-1/2 h-12 w-1 -translate-x-1/2 -translate-y-1/2 rounded-full bg-slate-200 group-hover:bg-brand/60" />
        </div>

        <aside ref={rightRef} className="flex min-w-0 flex-1 flex-col">
          <div className="flex items-center gap-2 border-b border-slate-100 bg-white/85 px-3 py-2 backdrop-blur">
            <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Map & details
            </span>
            <button
              type="button"
              onClick={() => setMapOpen((o) => !o)}
              className={`ml-auto rounded-full px-3 py-1 text-xs font-medium transition ${
                mapOpen
                  ? "bg-ink text-white"
                  : "text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50"
              }`}
              title={mapOpen ? "Hide map" : "Show map"}
            >
              {mapOpen ? "Hide map" : "Show map"}
            </button>
            <button
              type="button"
              onClick={() => setRightTopPct((p) => (p > 70 ? 50 : 80))}
              className="rounded-full px-3 py-1 text-xs font-medium text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50"
              title="Maximize map"
            >
              Map ⤢
            </button>
            <button
              type="button"
              onClick={() => setRightTopPct((p) => (p < 30 ? 50 : 20))}
              className="rounded-full px-3 py-1 text-xs font-medium text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50"
              title="Maximize details"
            >
              Details ⤢
            </button>
          </div>

          <div className="flex min-h-0 flex-1 flex-col">
            {mapOpen ? (
              <>
                <section
                  className="min-h-0 border-b border-slate-100"
                  style={{ flexBasis: `${rightTopPct}%` }}
                >
                  <MapPanel reloadToken={tripVersion} focusName={stopFocusName} />
                </section>
                <div
                  onMouseDown={() => startDrag("rightV")}
                  title="Drag to resize map/details"
                  className="group relative h-1.5 cursor-row-resize bg-transparent transition-colors hover:bg-brand/30"
                >
                  <span className="absolute left-1/2 top-1/2 h-1 w-14 -translate-x-1/2 -translate-y-1/2 rounded-full bg-slate-200 group-hover:bg-brand/60" />
                </div>
              </>
            ) : (
              <section className="grid h-12 place-items-center border-b border-slate-100 text-xs text-slate-500">
                Map hidden
              </section>
            )}

            <section className="min-h-0 flex-1">
              <TripPanel {...tripPanelProps} hideSwitcher />
            </section>
          </div>
        </aside>
      </div>

      <section className="flex h-screen flex-col md:hidden">
        <ChatPanel
          onTurnComplete={() => refresh()}
          reloadToken={chatReloadToken}
          tripIdHint={chatTripId}
          onNewTrip={handleNewTrip}
        />

        {view?.has_trip && !mobileTripOpen && (
          <button
            type="button"
            onClick={() => setMobileTripOpen(true)}
            aria-label="Open trip details"
            className="fixed bottom-4 right-4 z-30 inline-flex items-center gap-2 rounded-full bg-ink px-4 py-2.5 text-sm font-medium text-white shadow-pop ring-1 ring-black/10 transition active:scale-95"
          >
            <span>{"\uD83E\uDDF3"}</span>
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
              <span className="text-xl leading-none">×</span>
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
