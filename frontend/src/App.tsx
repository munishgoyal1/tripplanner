import { useCallback, useEffect, useRef, useState } from "react";
import ChatPanel from "./components/ChatPanel";
import TripPanel from "./components/TripPanel";
import { fetchTripView, selectItem, deselectItem } from "./api";
import type { TripView } from "./types";

interface NavRef {
  kind: string;
  name: string;
}

export default function App() {
  const [view, setView] = useState<TripView | null>(null);
  const [loading, setLoading] = useState(true);
  const [focus, setFocus] = useState<NavRef | null>(null);
  const [navList, setNavList] = useState<NavRef[]>([]);

  // --- resizable split between chat and the trip/photos panel ---------------
  const [chatPct, setChatPct] = useState<number>(() => {
    const saved = Number(localStorage.getItem("multiagent_chat_pct"));
    return saved >= 25 && saved <= 75 ? saved : 52;
  });
  const [isDesktop, setIsDesktop] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(min-width: 768px)").matches
  );
  const containerRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);
  const chatPctRef = useRef(chatPct);
  chatPctRef.current = chatPct;

  useEffect(() => {
    const mq = window.matchMedia("(min-width: 768px)");
    const onChange = (e: MediaQueryListEvent) => setIsDesktop(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  useEffect(() => {
    function onMove(e: MouseEvent) {
      if (!dragging.current || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const pct = ((e.clientX - rect.left) / rect.width) * 100;
      setChatPct(Math.min(75, Math.max(25, pct)));
    }
    function onUp() {
      if (!dragging.current) return;
      dragging.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      localStorage.setItem("multiagent_chat_pct", String(Math.round(chatPctRef.current)));
    }
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, []);

  const startDrag = () => {
    dragging.current = true;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  };

  // --- trip view loading ----------------------------------------------------
  const refresh = useCallback(
    async (f: NavRef | null = focus) => {
      setLoading(true);
      try {
        const v = await fetchTripView(f ?? undefined);
        setView(v);
        if (!f) {
          setNavList(v.items.map((it) => ({ kind: it.kind, name: it.name })));
        }
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

  // --- mobile bottom-sheet for the trip panel -------------------------------
  const [mobileTripOpen, setMobileTripOpen] = useState(false);
  // Auto-close the sheet when we cross into desktop layout.
  useEffect(() => {
    if (isDesktop && mobileTripOpen) setMobileTripOpen(false);
  }, [isDesktop, mobileTripOpen]);
  // Close on Escape so keyboard users can dismiss.
  useEffect(() => {
    if (!mobileTripOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMobileTripOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mobileTripOpen]);

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
  };

  return (
    <div ref={containerRef} className="flex h-screen bg-surface">
      <section
        className="flex w-full min-w-0 flex-col md:w-auto"
        style={isDesktop ? { flexBasis: `${chatPct}%` } : undefined}
      >
        <ChatPanel onTurnComplete={() => refresh()} />
      </section>

      <div
        onMouseDown={startDrag}
        title="Drag to resize"
        className="group relative hidden w-1.5 flex-shrink-0 cursor-col-resize bg-transparent transition-colors hover:bg-brand/30 md:block"
      >
        <span className="absolute left-1/2 top-1/2 h-12 w-1 -translate-x-1/2 -translate-y-1/2 rounded-full bg-slate-200 group-hover:bg-brand/60" />
      </div>

      <aside className="hidden min-w-0 flex-1 md:block">
        <TripPanel {...tripPanelProps} />
      </aside>

      {/* Mobile-only: floating button + bottom-sheet for the trip panel. */}
      {!isDesktop && view?.has_trip && !mobileTripOpen && (
        <button
          type="button"
          onClick={() => setMobileTripOpen(true)}
          aria-label="Open trip details"
          className="fixed bottom-4 right-4 z-30 inline-flex items-center gap-2 rounded-full bg-ink px-4 py-2.5 text-sm font-medium text-white shadow-pop ring-1 ring-black/10 transition active:scale-95 md:hidden"
        >
          <span>{"\uD83E\uDDF3"}</span>
          <span>Trip details</span>
        </button>
      )}
      {!isDesktop && (
        <>
          <div
            onClick={() => setMobileTripOpen(false)}
            aria-hidden={!mobileTripOpen}
            className={`fixed inset-0 z-40 bg-black/40 backdrop-blur-sm transition-opacity md:hidden ${
              mobileTripOpen ? "opacity-100" : "pointer-events-none opacity-0"
            }`}
          />
          <section
            role="dialog"
            aria-modal="true"
            aria-label="Trip details"
            className={`fixed inset-x-0 bottom-0 z-50 flex h-[88vh] flex-col rounded-t-3xl bg-surface shadow-pop transition-transform duration-300 md:hidden ${
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
              <TripPanel {...tripPanelProps} />
            </div>
          </section>
        </>
      )}
    </div>
  );
}
