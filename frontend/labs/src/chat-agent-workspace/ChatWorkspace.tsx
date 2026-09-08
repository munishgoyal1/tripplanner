import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  ArrowDown,
  Bed,
  Clock3,
  CornerDownLeft,
  Landmark,
  MapPin,
  Maximize2,
  MessageSquare,
  Minimize2,
  Sparkles,
  Timer,
  UtensilsCrossed,
  X,
} from "lucide-react";
import { dayBrief, scriptedReply, stops, trip, turns as fixtureTurns, type Stop, type Turn, type TurnEffect, type VariantId } from "./fixture";

type View = "option" | "baseline";

interface WorkspaceProps {
  variant: VariantId;
  view: View;
  height?: string;
}

const kindIcon = {
  hotel: Bed,
  attraction: Landmark,
  restaurant: UtensilsCrossed,
  station: MapPin,
} as const;

function markerProps(view: View, label: string): Record<string, string> {
  return view === "option" ? { "data-lab-change": label } : {};
}

/* ------------------------------------------------------------------ chrome */

function CommandBar({ focusDay, onDay }: { focusDay: number; onDay: (day: number) => void }) {
  return (
    <header className="flex shrink-0 items-center gap-3 border-b border-slate-200 bg-white px-3 py-2">
      <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-brand text-[11px] font-bold text-white">TP</span>
      <div className="min-w-0">
        <p className="truncate text-[13px] font-semibold text-ink">{trip.title}</p>
        <p className="truncate text-[10px] text-slate-500">{trip.dates} · {trip.travellers}</p>
      </div>
      <div className="ml-2 flex items-center gap-1 overflow-hidden">
        {trip.days.map((day) => (
          <button
            key={day.day}
            type="button"
            onClick={() => onDay(day.day)}
            aria-pressed={focusDay === day.day}
            className={`h-6 shrink-0 rounded-sm px-2 text-[11px] font-semibold transition ${
              focusDay === day.day ? "bg-ink text-white" : "bg-slate-100 text-slate-600 hover:text-ink"
            }`}
          >
            {day.label}
          </button>
        ))}
      </div>
      <div className="ml-auto flex shrink-0 items-center gap-1.5">
        <span className="hidden rounded-sm bg-slate-100 px-2 py-1 text-[10px] font-semibold text-slate-600 lg:inline">Itinerary</span>
        <span className="hidden rounded-sm bg-slate-100 px-2 py-1 text-[10px] font-semibold text-slate-600 lg:inline">Map</span>
        <span className="hidden rounded-sm bg-slate-100 px-2 py-1 text-[10px] font-semibold text-slate-600 lg:inline">Details</span>
        <span className="h-6 w-6 rounded-full bg-slate-200" aria-hidden />
      </div>
    </header>
  );
}

function ItineraryRail({
  focusDay,
  focusStopId,
  onFocus,
  width,
}: {
  focusDay: number;
  focusStopId: string;
  onFocus: (stop: Stop) => void;
  width: string;
}) {
  return (
    <section className={`${width} flex min-h-0 shrink-0 flex-col border-r border-slate-200 bg-white`} aria-label="Itinerary">
      <div className="border-b border-slate-100 px-3 py-2">
        <p className="text-[10px] font-bold uppercase text-slate-400">Day 3 · Thursday</p>
        <p className="mt-0.5 text-[13px] font-semibold text-ink">Sanchi and Udayagiri</p>
        <p className="mt-1 text-[10px] leading-relaxed text-slate-500">{dayBrief.headline}</p>
        <p className="mt-1 text-[10px] leading-relaxed text-slate-500">{dayBrief.rhythm}</p>
        {focusDay !== 3 && (
          <p className="mt-1.5 rounded-sm bg-slate-100 px-1.5 py-1 text-[10px] text-slate-500">
            Day {focusDay} is in this fixture's trip, but only Day 3 has authored stop detail.
          </p>
        )}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
        {stops.map((stop) => {
          const Icon = kindIcon[stop.kind];
          const active = focusStopId === stop.id;
          return (
            <div key={stop.id}>
              {stop.travel && (
                <p className="py-1 pl-[3.6rem] text-[10px] text-slate-400">{stop.travel}</p>
              )}
              <button
                type="button"
                onClick={() => onFocus(stop)}
                className={`flex w-full gap-2 rounded-sm px-1.5 py-1.5 text-left transition ${
                  active ? "bg-brand/5 ring-1 ring-brand/30" : "hover:bg-slate-50"
                }`}
              >
                <span className="w-11 shrink-0 pt-0.5 text-right">
                  <span className="block text-[9px] font-bold uppercase tracking-wide text-slate-400">{stop.timingLabel}</span>
                  <span className="block text-[12px] font-semibold text-ink">{stop.time}</span>
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-1.5">
                    <Icon size={12} className="shrink-0 text-slate-400" aria-hidden />
                    <span className="truncate text-[12px] font-semibold text-ink">{stop.name}</span>
                  </span>
                  <span className="mt-0.5 block truncate text-[10px] text-slate-500">{stop.meta}</span>
                  {stop.booked && (
                    <span className="mt-1 inline-flex rounded-sm bg-emerald-50 px-1.5 py-0.5 text-[9px] font-bold uppercase text-emerald-700">Confirmed</span>
                  )}
                </span>
              </button>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function MapCanvas({
  focusStopId,
  onFocus,
  overlay,
}: {
  focusStopId: string;
  onFocus: (stop: Stop) => void;
  overlay?: ReactNode;
}) {
  const unique = stops.filter((stop, index) => stops.findIndex((item) => item.id === stop.id || (item.x === stop.x && item.y === stop.y)) === index);
  const path = stops.map((stop) => `${stop.x},${stop.y}`).join(" ");
  return (
    <section className="relative min-h-0 min-w-0 flex-1 bg-[#eef2f4]" aria-label="Map">
      <svg viewBox="0 0 400 300" preserveAspectRatio="xMidYMid slice" className="h-full w-full">
        <rect x="0" y="0" width="400" height="300" fill="#e9eff0" />
        <path d="M0 240 C 90 210, 130 250, 210 232 S 340 250, 400 226" fill="none" stroke="#cfe0dd" strokeWidth="26" />
        <path d="M60 300 C 110 200, 150 140, 250 60" fill="none" stroke="#ffffff" strokeWidth="7" />
        <path d="M120 300 C 170 210, 210 170, 400 120" fill="none" stroke="#ffffff" strokeWidth="4" />
        <circle cx="70" cy="238" r="34" fill="#d7e7ef" />
        <polyline points={path} fill="none" stroke="#e11d48" strokeWidth="2.5" strokeDasharray="7 5" strokeLinecap="round" opacity="0.75" />
        {unique.map((stop, index) => {
          const active = focusStopId === stop.id || (stop.id === "hotel-out" && focusStopId === "hotel-in");
          return (
            <g key={stop.id} onClick={() => onFocus(stop)} className="cursor-pointer">
              <circle cx={stop.x} cy={stop.y} r={active ? 11 : 8} fill={active ? "#e11d48" : "#1f2937"} stroke="#ffffff" strokeWidth="2.5" />
              <text x={stop.x} y={stop.y + 3.2} textAnchor="middle" fontSize="8.5" fontWeight="700" fill="#ffffff">{index + 1}</text>
            </g>
          );
        })}
      </svg>
      <div className="pointer-events-none absolute left-3 top-3 rounded-sm bg-white/95 px-2 py-1 text-[10px] font-semibold text-slate-600 shadow-card">
        Day 3 · 96 km · 4 stops
      </div>
      {overlay}
    </section>
  );
}

function DetailsBody({ stop }: { stop: Stop }) {
  return (
    <>
      <div className="h-20 bg-[linear-gradient(120deg,#dbeafe,#fce7f3)]" />
      <div className="px-3 py-2.5">
        <p className="text-[13px] font-semibold text-ink">{stop.name}</p>
        <p className="mt-0.5 text-[10px] text-slate-500">{stop.rating}</p>
        <p className="mt-2 text-[11px] leading-relaxed text-slate-600">{stop.blurb}</p>
        <p className="mt-2 text-[10px] text-slate-500">{stop.hours}</p>
        <div className="mt-2.5 flex gap-1.5">
          <span className="rounded-sm bg-ink px-2 py-1 text-[10px] font-semibold text-white">Replace stop</span>
          <span className="rounded-sm bg-white px-2 py-1 text-[10px] font-semibold text-slate-600 ring-1 ring-slate-200">Nearby</span>
        </div>
      </div>
    </>
  );
}

function DetailsRail({ stop, width }: { stop: Stop; width: string }) {
  return (
    <section className={`${width} flex min-h-0 shrink-0 flex-col overflow-y-auto border-l border-slate-200 bg-white`} aria-label="Details">
      <DetailsBody stop={stop} />
    </section>
  );
}

/* ------------------------------------------------------------- conversation */

function DurationBadge({ seconds, live }: { seconds: number; live?: boolean }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1 rounded-sm px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide ${
        live ? "bg-amber-50 text-amber-700 ring-1 ring-amber-200" : "bg-slate-100 text-slate-500"
      }`}
      title={live ? "This turn is still running" : "Time this reply took, kept with the turn"}
    >
      {live ? <Timer size={9} aria-hidden /> : <Clock3 size={9} aria-hidden />}
      {seconds}s
    </span>
  );
}

function TurnBlock({
  turn,
  view,
  onEffect,
  showTools,
}: {
  turn: Turn;
  view: View;
  onEffect: (effect: TurnEffect) => void;
  showTools: boolean;
}) {
  return (
    <article className="space-y-1.5">
      <div className="flex justify-end">
        <p className="max-w-[85%] rounded-md rounded-br-sm bg-ink px-2.5 py-1.5 text-[11px] leading-relaxed text-white">{turn.user}</p>
      </div>
      <div className={view === "option" ? "rounded-md bg-white p-2.5 shadow-card ring-1 ring-slate-200" : "max-w-[92%]"}>
        <div className="flex items-center gap-1.5">
          <Sparkles size={11} className="shrink-0 text-brand" aria-hidden />
          <span className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Assistant</span>
          <span className="text-[10px] text-slate-400">{turn.at}</span>
          {view === "option" && <span className="ml-auto"><DurationBadge seconds={turn.seconds} /></span>}
        </div>
        <p className="mt-1.5 text-[11px] leading-relaxed text-slate-700">{turn.assistant}</p>
        {view === "option" && showTools && turn.tools && (
          <p className="mt-1.5 text-[10px] text-slate-400">
            {turn.tools.map((tool) => `${tool.name} ${tool.seconds}s`).join(" · ")}
          </p>
        )}
        {view === "option" && turn.effects && (
          <div className="mt-2 flex flex-wrap gap-1">
            {turn.effects.map((effect) => (
              <button
                key={`${turn.id}-${effect.label}`}
                type="button"
                onClick={() => onEffect(effect)}
                className="inline-flex items-center gap-1 rounded-sm bg-slate-50 px-1.5 py-0.5 text-[10px] font-semibold text-slate-600 ring-1 ring-slate-200 transition hover:bg-white hover:text-brand hover:ring-brand/30"
              >
                <MapPin size={9} aria-hidden /> {effect.label}
              </button>
            ))}
          </div>
        )}
      </div>
    </article>
  );
}

interface TranscriptProps {
  view: View;
  turns: Turn[];
  pending: { user: string } | null;
  elapsed: number;
  onEffect: (effect: TurnEffect) => void;
  showTools: boolean;
  reading?: boolean;
}

function Transcript({ view, turns, pending, elapsed, onEffect, showTools, reading }: TranscriptProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const atBottomRef = useRef(true);
  const [detached, setDetached] = useState(false);

  const onScroll = useCallback(() => {
    const node = scrollRef.current;
    if (!node) return;
    const bottom = node.scrollHeight - node.scrollTop - node.clientHeight < 32;
    atBottomRef.current = bottom;
    if (bottom) setDetached(false);
  }, []);

  useLayoutEffect(() => {
    const node = scrollRef.current;
    if (!node) return;
    // Today: every update yanks the reader back to the newest message.
    // Option: the reading position is authoritative until the reader returns.
    if (view === "baseline" || atBottomRef.current) {
      node.scrollTop = node.scrollHeight;
    } else {
      setDetached(true);
    }
  }, [turns, pending, elapsed, view]);

  const jump = () => {
    const node = scrollRef.current;
    if (!node) return;
    node.scrollTop = node.scrollHeight;
    atBottomRef.current = true;
    setDetached(false);
  };

  let lastGroup = "";
  return (
    <div className="relative min-h-0 flex-1">
      <div
        ref={scrollRef}
        onScroll={onScroll}
        className={`h-full space-y-3 overflow-y-auto px-3 py-3 ${view === "option" ? "bg-slate-50/70" : "bg-white"}`}
      >
        {view === "option" ? (
          <p className="sticky top-0 z-10 -mx-3 -mt-3 mb-1 bg-white/95 px-3 py-1.5 text-[10px] font-semibold text-slate-500 backdrop-blur">
            {turns.length} turns in this session · complete, nothing dropped
          </p>
        ) : (
          <p className="rounded-sm bg-amber-50 px-2 py-1.5 text-[10px] leading-relaxed text-amber-800 ring-1 ring-amber-200">
            Older turns beyond the last 80 are not kept, and there is no way back to a specific earlier answer.
          </p>
        )}
        <div className={reading ? "mx-auto max-w-3xl space-y-3" : "space-y-3"}>
          {turns.map((turn) => {
            const separator = view === "option" && turn.group !== lastGroup ? turn.group : null;
            lastGroup = turn.group;
            return (
              <div key={turn.id} className="space-y-3">
                {separator && (
                  <p className="flex items-center gap-2 pt-1 text-[9px] font-bold uppercase tracking-wide text-slate-400">
                    <span className="h-px flex-1 bg-slate-200" /> {separator} <span className="h-px flex-1 bg-slate-200" />
                  </p>
                )}
                <TurnBlock turn={turn} view={view} onEffect={onEffect} showTools={showTools} />
              </div>
            );
          })}
          {pending && (
            <article className="space-y-1.5">
              <div className="flex justify-end">
                <p className="max-w-[85%] rounded-md rounded-br-sm bg-ink px-2.5 py-1.5 text-[11px] leading-relaxed text-white">{pending.user}</p>
              </div>
              <div className={view === "option" ? "rounded-md bg-white p-2.5 shadow-card ring-1 ring-slate-200" : "max-w-[92%]"}>
                <div className="flex items-center gap-1.5">
                  <Sparkles size={11} className="shrink-0 animate-pulse text-brand" aria-hidden />
                  <span className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Working</span>
                  {view === "option" ? (
                    <span className="ml-auto"><DurationBadge seconds={elapsed} live /></span>
                  ) : (
                    <span className="ml-auto text-[10px] text-slate-400">{elapsed}s elapsed</span>
                  )}
                </div>
                <p className="mt-1.5 text-[11px] leading-relaxed text-slate-500">Checking what is open near Udayagiri...</p>
              </div>
            </article>
          )}
        </div>
      </div>
      {detached && view === "option" && (
        <button
          type="button"
          onClick={jump}
          className="absolute bottom-3 left-1/2 z-20 inline-flex -translate-x-1/2 items-center gap-1.5 rounded-full bg-ink px-3 py-1.5 text-[10px] font-semibold text-white shadow-pop"
        >
          <ArrowDown size={11} aria-hidden /> New reply · jump to latest
        </button>
      )}
    </div>
  );
}

function Composer({
  onSend,
  busy,
  variant,
}: {
  onSend: (text: string) => void;
  busy: boolean;
  variant: "panel" | "bar";
}) {
  const [value, setValue] = useState("");
  const submit = () => {
    const text = value.trim() || "Anywhere to stop for tea before the drive back?";
    setValue("");
    onSend(text);
  };
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (!busy) submit();
      }}
      className={variant === "bar" ? "flex w-full items-center gap-2" : "flex shrink-0 items-center gap-2 border-t border-slate-200 bg-white px-3 py-2.5"}
    >
      <input
        value={value}
        onChange={(event) => setValue(event.target.value)}
        placeholder="Anywhere to stop for tea before the drive back?"
        aria-label="Message the assistant"
        className="h-9 min-w-0 flex-1 rounded-sm border border-slate-200 bg-white px-2.5 text-[11px] text-ink outline-none placeholder:text-slate-400 focus:border-brand"
      />
      <button
        type="submit"
        disabled={busy}
        className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-sm bg-brand px-3 text-[11px] font-semibold text-white disabled:opacity-50"
      >
        <CornerDownLeft size={12} aria-hidden /> Send
      </button>
    </form>
  );
}

/* ------------------------------------------------------------------- shell */

export function ChatWorkspace({ variant, view, height = "h-[44rem]" }: WorkspaceProps) {
  const [focusDay, setFocusDay] = useState(3);
  const [focusStopId, setFocusStopId] = useState("sanchi-stupa");
  const [turns, setTurns] = useState<Turn[]>(fixtureTurns);
  const [pending, setPending] = useState<{ user: string } | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [cornerOpen, setCornerOpen] = useState(true);
  const [detailsOpen, setDetailsOpen] = useState(false);

  const focusStop = useMemo(() => stops.find((stop) => stop.id === focusStopId) ?? stops[1], [focusStopId]);

  useEffect(() => {
    if (!pending) return;
    const tick = window.setInterval(() => setElapsed((value) => value + 1), 1000);
    const finish = window.setTimeout(() => {
      setTurns((current) => [
        ...current,
        {
          id: `live-${current.length}`,
          group: "Just now",
          at: "now",
          user: pending.user,
          assistant: scriptedReply.assistant,
          seconds: scriptedReply.seconds,
          tools: scriptedReply.tools,
          effects: scriptedReply.effects,
        },
      ]);
      setPending(null);
      setElapsed(0);
    }, 4200);
    return () => {
      window.clearInterval(tick);
      window.clearTimeout(finish);
    };
  }, [pending]);

  const send = useCallback((text: string) => {
    setElapsed(0);
    setPending({ user: text });
  }, []);

  const onEffect = useCallback((effect: TurnEffect) => {
    setFocusDay(effect.day);
    if (effect.stopId) {
      setFocusStopId(effect.stopId);
      setDetailsOpen(true);
    }
  }, []);

  const onFocusStop = useCallback((stop: Stop) => {
    setFocusStopId(stop.id);
    setDetailsOpen(true);
  }, []);

  const transcript = (reading?: boolean) => (
    <Transcript
      view={view}
      turns={turns}
      pending={pending}
      elapsed={elapsed}
      onEffect={onEffect}
      showTools={variant === "turn-thread"}
      reading={reading}
    />
  );

  const assistantHeader = (extra?: ReactNode) => (
    <div className="flex shrink-0 items-center gap-2 border-b border-slate-200 bg-white px-3 py-2">
      <MessageSquare size={13} className="text-brand" aria-hidden />
      <p className="text-[12px] font-semibold text-ink">Assistant</p>
      {view === "option" && <span className="rounded-sm bg-emerald-50 px-1.5 py-0.5 text-[9px] font-bold uppercase text-emerald-700">History kept</span>}
      <div className="ml-auto flex items-center gap-1.5">{extra}</div>
    </div>
  );

  const detailsOverlay =
    detailsOpen ? (
      <div className="absolute bottom-3 left-3 w-64 overflow-hidden rounded-md bg-white shadow-pop ring-1 ring-slate-200">
        <button
          type="button"
          onClick={() => setDetailsOpen(false)}
          aria-label="Close details"
          className="absolute right-1.5 top-1.5 z-10 grid h-6 w-6 place-items-center rounded-full bg-white/90 text-slate-500 shadow-card"
        >
          <X size={12} aria-hidden />
        </button>
        <DetailsBody stop={focusStop} />
      </div>
    ) : null;

  const body = () => {
    if (view === "baseline") {
      return (
        <div className="relative flex min-h-0 flex-1">
          <ItineraryRail focusDay={focusDay} focusStopId={focusStopId} onFocus={onFocusStop} width="w-[17rem]" />
          <MapCanvas focusStopId={focusStopId} onFocus={onFocusStop} />
          <DetailsRail stop={focusStop} width="w-[18rem]" />
          {cornerOpen ? (
            <div className="absolute bottom-0 right-[18rem] flex h-[64%] w-[30rem] flex-col border-l border-t border-slate-200 bg-white shadow-pop">
              {assistantHeader(
                <button type="button" onClick={() => setCornerOpen(false)} aria-label="Close assistant" className="text-slate-400 hover:text-ink">
                  <X size={13} aria-hidden />
                </button>,
              )}
              {transcript()}
              <Composer onSend={send} busy={Boolean(pending)} variant="panel" />
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setCornerOpen(true)}
              className="absolute bottom-4 right-[19rem] inline-flex items-center gap-2 rounded-full bg-brand px-3.5 py-2 text-[11px] font-semibold text-white shadow-pop"
            >
              <MessageSquare size={13} aria-hidden /> Assistant
            </button>
          )}
        </div>
      );
    }

    if (variant === "conversation-dock") {
      return (
        <div className="flex min-h-0 flex-1">
          <section
            className="flex w-[22rem] min-h-0 shrink-0 flex-col border-r border-slate-200 bg-white"
            aria-label="Assistant"
            {...markerProps(view, "Assistant as a resident column")}
          >
            {assistantHeader(<span className="text-[10px] text-slate-400">Always open</span>)}
            {transcript()}
            <Composer onSend={send} busy={Boolean(pending)} variant="panel" />
          </section>
          <ItineraryRail focusDay={focusDay} focusStopId={focusStopId} onFocus={onFocusStop} width="w-[16rem]" />
          <MapCanvas focusStopId={focusStopId} onFocus={onFocusStop} />
          <DetailsRail stop={focusStop} width="w-[17rem]" />
        </div>
      );
    }

    if (variant === "focus-composer") {
      return (
        <div className="relative flex min-h-0 flex-1 flex-col">
          <div className="flex min-h-0 flex-1">
            <ItineraryRail focusDay={focusDay} focusStopId={focusStopId} onFocus={onFocusStop} width="w-[18rem]" />
            <MapCanvas focusStopId={focusStopId} onFocus={onFocusStop} />
            <DetailsRail stop={focusStop} width="w-[20rem]" />
          </div>
          <div
            className="relative z-20 flex shrink-0 items-center gap-3 border-t border-slate-200 bg-white px-3 py-2.5"
            {...markerProps(view, "Assistant as a command line")}
          >
            <button
              type="button"
              onClick={() => setSheetOpen((open) => !open)}
              className="inline-flex shrink-0 items-center gap-1.5 rounded-sm bg-slate-100 px-2.5 py-1.5 text-[11px] font-semibold text-slate-700 hover:text-ink"
            >
              {sheetOpen ? <Minimize2 size={12} aria-hidden /> : <Maximize2 size={12} aria-hidden />}
              {sheetOpen ? "Hide conversation" : `Conversation · ${turns.length}`}
            </button>
            <p className="hidden min-w-0 flex-1 truncate text-[11px] text-slate-500 lg:block">
              <span className="font-semibold text-slate-600">Last reply</span> · {turns[turns.length - 1].assistant}
            </p>
            {view === "option" && <DurationBadge seconds={turns[turns.length - 1].seconds} />}
            <div className="w-[26rem] shrink-0">
              <Composer onSend={send} busy={Boolean(pending)} variant="bar" />
            </div>
          </div>
          {sheetOpen && (
            <div
              className="absolute inset-x-0 bottom-[3.6rem] top-[26%] z-10 flex flex-col border-t border-slate-200 bg-white/95 shadow-pop backdrop-blur"
              {...markerProps(view, "Transcript as a reading sheet")}
            >
              {assistantHeader(
                <button type="button" onClick={() => setSheetOpen(false)} aria-label="Close conversation" className="text-slate-400 hover:text-ink">
                  <X size={13} aria-hidden />
                </button>,
              )}
              {transcript(true)}
            </div>
          )}
        </div>
      );
    }

    return (
      <div className="flex min-h-0 flex-1">
        <ItineraryRail focusDay={focusDay} focusStopId={focusStopId} onFocus={onFocusStop} width="w-[17rem]" />
        <MapCanvas focusStopId={focusStopId} onFocus={onFocusStop} overlay={detailsOverlay} />
        <section
          className="flex w-[26rem] min-h-0 shrink-0 flex-col border-l border-slate-200 bg-white"
          aria-label="Assistant"
          {...markerProps(view, "Turn cards with timing and effects")}
        >
          {assistantHeader(<span className="text-[10px] text-slate-400">Details opens on the map</span>)}
          {transcript()}
          <Composer onSend={send} busy={Boolean(pending)} variant="panel" />
        </section>
      </div>
    );
  };

  return (
    <div className={`${height} flex min-h-[32rem] flex-col overflow-hidden bg-surface`}>
      <CommandBar focusDay={focusDay} onDay={setFocusDay} />
      {body()}
    </div>
  );
}
