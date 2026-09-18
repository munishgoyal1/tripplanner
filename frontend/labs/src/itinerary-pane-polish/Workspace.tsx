import type { ReactNode } from "react";
import {
  Bell, BusFront, ChevronDown, ChevronUp, Compass, Download, EyeOff, Hotel, House, LayoutDashboard, List, ListChecks,
  MapPin, Maximize2, MessageCircle, Minimize2, PanelRight, Plane, Plus, RotateCcw, Route, Send, Settings, Sparkles,
  ThumbsDown, ThumbsUp, TrainFront,
} from "lucide-react";
import type { ItineraryFilter } from "../../../src/lib/itineraryFilters";
import type { PlannerState } from "./state";

/** Surrounding workspace chrome. Only the two harmonised options may restyle it. */
export type Chrome = "today" | "soft" | "crisp" | "crisp2";

/** "crisp2" is A's crisp finish plus the F/G refinements: stronger text contrast,
 * dated day-bar chips with booking counts, and readiness in the itinerary header. */
const isCrisp = (chrome: Chrome): boolean => chrome === "crisp" || chrome === "crisp2";
export type PaneWidth = "narrow" | "default" | "wide" | "half" | "maximized";

const FILTERS = [
  { value: "flight", label: "Flights", Icon: Plane },
  { value: "road", label: "Inter-city Road", Icon: BusFront },
  { value: "train", label: "Inter-city Train", Icon: TrainFront },
  { value: "hotel", label: "Hotels", Icon: Hotel },
] as const;

const COLUMNS: Record<PaneWidth, string> = {
  narrow: "340px minmax(0,1fr) 25%",
  default: "27% minmax(0,1fr) 25%",
  wide: "38% minmax(0,1fr) 23%",
  half: "50% minmax(0,1fr) 20%",
  maximized: "minmax(0,1fr)",
};

function FilterGroup({ state, chrome }: { state: PlannerState; chrome: Chrome }) {
  return (
    <div
      role="group"
      aria-label="Filter itinerary and map"
      className={`flex min-w-0 items-center gap-0.5 p-0.5 ${isCrisp(chrome) ? "rounded-md border border-border bg-paper" : "rounded-full border border-border bg-sand"}`}
    >
      {FILTERS.map(({ value, label, Icon }) => {
        const active = state.filters.includes(value as ItineraryFilter);
        return (
          <button
            key={value}
            type="button"
            onClick={() => state.toggleFilter(value as ItineraryFilter)}
            aria-label={`Filter by ${label}`}
            aria-pressed={active}
            title={label}
            className={`grid h-7 w-7 shrink-0 place-items-center transition ${isCrisp(chrome) ? "rounded" : "rounded-full"} ${
              active
                ? isCrisp(chrome) ? "bg-ink text-white" : "bg-paper text-ink shadow-sm ring-1 ring-border"
                : "text-muted hover:bg-paper hover:text-ink"
            }`}
          >
            <Icon size={14} aria-hidden />
          </button>
        );
      })}
    </div>
  );
}

function ReadyHint({ state }: { state: PlannerState }) {
  return <span className="shrink-0 text-[11px] font-medium tabular-nums text-muted" title="Planned stops confirmed">{state.stats.booked}/{state.stats.stops} ready</span>;
}

function PaneHeader({ chrome, label, context, Icon, maximized, onToggleMaximize, children }: {
  chrome: Chrome;
  label: string;
  context: string;
  Icon: typeof List;
  maximized: boolean;
  onToggleMaximize: () => void;
  children?: ReactNode;
}) {
  const controls = (
    <div role="group" aria-label={`${label} pane controls`} className={`ml-auto flex shrink-0 items-center p-0.5 ${isCrisp(chrome) ? "gap-0.5" : "rounded-full bg-sand ring-1 ring-inset ring-border"}`}>
      <button type="button" className={`grid h-7 w-7 place-items-center text-muted transition hover:text-ink ${isCrisp(chrome) ? "rounded hover:bg-sand" : "rounded-full hover:bg-paper hover:shadow-sm"}`} aria-label={`Hide ${label}`} title={`Hide ${label}`}>
        <EyeOff size={14} aria-hidden />
      </button>
      <button type="button" onClick={onToggleMaximize} className={`grid h-7 w-7 place-items-center text-muted transition hover:text-ink ${isCrisp(chrome) ? "rounded hover:bg-sand" : "rounded-full hover:bg-paper hover:shadow-sm"}`} aria-label={maximized ? `Restore ${label}` : `Maximize ${label}`} title={maximized ? "Restore" : "Maximize"}>
        {maximized ? <Minimize2 size={14} aria-hidden /> : <Maximize2 size={14} aria-hidden />}
      </button>
    </div>
  );
  if (chrome === "today") {
    return (
      <header className="flex h-10 shrink-0 items-center gap-2.5 border-b border-border bg-sidebar/70 px-3">
        <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-paper text-brand shadow-sm ring-1 ring-border" aria-hidden><Icon size={14} /></span>
        <span className="flex shrink-0 flex-col leading-none">
          <span className="text-[9px] font-bold uppercase tracking-[0.09em] text-muted">{context}</span>
          <h2 className="mt-1 text-sm font-semibold text-ink">{label}</h2>
        </span>
        <div className="min-w-0 flex-1">{children}</div>
        {controls}
      </header>
    );
  }
  if (chrome === "soft") {
    return (
      <header className="flex h-11 shrink-0 items-center gap-2 px-3.5" data-lab-change="Pane header">
        <Icon size={15} className="shrink-0 text-brand" aria-hidden />
        <h2 className="display shrink-0 text-[17px] leading-none text-ink" title={context}>{label}</h2>
        <div className="min-w-0 flex-1 pl-1">{children}</div>
        {controls}
      </header>
    );
  }
  return (
    <header className="flex h-9 shrink-0 items-center gap-2 border-b border-border px-2.5" data-lab-change="Pane header">
      <Icon size={14} className="shrink-0 text-muted" aria-hidden />
      <h2 className="shrink-0 text-[13px] font-semibold tracking-[-0.01em] text-ink">{label}</h2>
      <div className="flex min-w-0 flex-1 items-center justify-between gap-2 pl-1">{children}</div>
      {controls}
    </header>
  );
}

function paneShell(chrome: Chrome) {
  if (chrome === "soft") return "flex h-full min-h-0 flex-col overflow-hidden rounded-xl bg-paper shadow-[0_1px_2px_oklch(0.28_0.05_45/0.05),0_6px_20px_-14px_oklch(0.28_0.05_45/0.25)] ring-1 ring-border/70";
  if (isCrisp(chrome)) return "flex h-full min-h-0 flex-col overflow-hidden rounded-md border border-border bg-paper";
  return "flex h-full min-h-0 flex-col overflow-hidden rounded-lg border border-border bg-paper shadow-card";
}

function Toolbar({ chrome }: { chrome: Chrome }) {
  const toggle = (active: boolean) => isCrisp(chrome)
    ? `inline-flex h-7 items-center gap-1 rounded px-2 text-xs font-semibold transition ${active ? "bg-paper text-ink shadow-sm ring-1 ring-border" : "text-muted hover:text-ink"}`
    : chrome === "soft"
      ? `inline-flex h-7 items-center gap-1 rounded-full px-2.5 text-xs font-medium transition ${active ? "bg-paper text-ink shadow-sm" : "text-muted hover:text-ink"}`
      : `inline-flex h-7 items-center justify-center gap-1 rounded-full px-2 text-xs font-semibold transition ${active ? "bg-clay-soft text-ink shadow-sm ring-1 ring-clay/20" : "text-muted hover:bg-paper hover:text-ink"}`;
  const group = isCrisp(chrome) ? "flex items-center gap-0.5 rounded-md bg-sand p-0.5" : "flex items-center gap-0.5 rounded-full border border-border bg-sand p-0.5";
  return (
    <header className="relative z-20 flex h-10 shrink-0 items-center gap-2.5 border-b border-border bg-paper px-4" data-lab-change={chrome === "today" ? undefined : "Toolbar finish"}>
      <span className="inline-flex shrink-0 items-center gap-2">
        <Compass size={17} className="text-brand" aria-hidden />
        <span className={isCrisp(chrome) ? "text-[15px] font-semibold tracking-[-0.01em] text-ink" : "display text-lg text-ink"}>AI Tripplanner</span>
      </span>
      <button type="button" className={`inline-flex h-7 items-center gap-1.5 px-2.5 text-xs font-semibold text-ink ${isCrisp(chrome) ? "rounded-md border border-border" : "rounded-full border border-border bg-paper"}`}>
        <MapPin size={13} className="text-brand" aria-hidden /> Jaipur &amp; Udaipur <span className="font-normal text-muted">(4)</span> <ChevronDown size={13} aria-hidden />
      </button>
      <div className="h-6 w-px shrink-0 bg-border" aria-hidden />
      <nav className="ml-auto flex shrink-0 items-center gap-2" aria-label="Workspace controls">
        {chrome !== "crisp" && <span className="hidden items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted xl:inline-flex"><LayoutDashboard size={14} className="text-brand" aria-hidden /> Workspace</span>}
        <div role="group" className={group} aria-label="Pane visibility">
          <button type="button" className={toggle(true)} aria-pressed><List size={15} aria-hidden /> Itinerary</button>
          <button type="button" className={toggle(true)} aria-pressed><MapPin size={15} aria-hidden /> Map</button>
          <button type="button" className={toggle(true)} aria-pressed><PanelRight size={15} aria-hidden /> Guide</button>
          <button type="button" className={toggle(true)} aria-pressed><MessageCircle size={15} aria-hidden /> Assistant</button>
        </div>
        <div role="group" className={isCrisp(chrome) ? "flex items-center gap-0.5" : "flex items-center gap-0.5 rounded-full border border-border bg-paper p-0.5"} aria-label="Rate this trip">
          <button type="button" className="grid h-7 w-7 place-items-center rounded-full text-muted hover:text-ink" title="Helpful"><ThumbsUp size={14} aria-hidden /></button>
          <button type="button" className="grid h-7 w-7 place-items-center rounded-full text-muted hover:text-ink" title="Not helpful"><ThumbsDown size={14} aria-hidden /></button>
        </div>
        <div role="group" className={isCrisp(chrome) ? "flex items-center gap-0.5 rounded-md border border-border p-0.5" : "flex items-center gap-0.5 rounded-full border border-border bg-paper p-0.5"} aria-label="Trip actions">
          <button type="button" className="grid h-7 w-7 place-items-center rounded-full text-muted hover:text-ink" title="Export"><Download size={14} aria-hidden /></button>
          <span className="h-4 w-px bg-border" aria-hidden />
          <button type="button" className="inline-flex h-7 items-center gap-1.5 rounded-full px-2 text-xs font-semibold text-ink"><Plus size={14} className="text-clay" aria-hidden /> New trip</button>
          <span className="h-4 w-px bg-border" aria-hidden />
          <button type="button" className="grid h-7 w-7 place-items-center rounded-full text-muted hover:text-ink" title="Reset trip"><RotateCcw size={14} aria-hidden /></button>
        </div>
        <span className="h-5 w-px bg-border" aria-hidden />
        <button type="button" className="grid h-7 w-7 place-items-center rounded-full text-muted" title="Home"><House size={15} aria-hidden /></button>
        <button type="button" className="grid h-7 w-7 place-items-center rounded-full border border-border text-muted" title="Settings"><Settings size={15} aria-hidden /></button>
        <button type="button" className={`inline-flex h-7 items-center px-3 text-xs font-semibold text-white shadow-sm ${isCrisp(chrome) ? "rounded-md bg-ink" : "rounded-full bg-brand"}`}>Sign in</button>
      </nav>
    </header>
  );
}

const NOTICE = "All changes saved.";

function NoticeStrip({ chrome }: { chrome: Chrome }) {
  if (chrome === "soft") {
    return (
      <div aria-label="Workspace notifications" className="flex h-7 shrink-0 items-center gap-2 bg-background px-3" data-lab-change="Notification strip">
        <span className="inline-flex h-5 items-center gap-1.5 rounded-full bg-ochre/15 px-2.5 text-[11px] font-medium text-ink"><Bell size={12} className="text-ochre" aria-hidden /> {NOTICE}</span>
      </div>
    );
  }
  if (isCrisp(chrome)) {
    return (
      <div aria-label="Workspace notifications" className="flex h-7 shrink-0 items-center gap-2 border-b border-border bg-paper px-4 text-xs text-muted" data-lab-change="Notification strip">
        <span className="h-1.5 w-1.5 rounded-full bg-ochre" aria-hidden /> <span className="truncate">{NOTICE}</span>
      </div>
    );
  }
  return (
    <div aria-label="Workspace notifications" className="flex h-7 shrink-0 items-center gap-x-3 border-b border-ochre/20 bg-ochre/15 px-3">
      <div className="flex min-w-0 items-center gap-2 text-xs font-medium text-muted" role="status"><Bell size={13} className="shrink-0 text-ochre" aria-hidden /> <span className="truncate">{NOTICE}</span></div>
    </div>
  );
}

function DayBarExtra({ day, selected }: { day: PlannerState["itinerary"]["days"][number]; selected: boolean }) {
  const planned = day.stops.filter((stop) => !["hotel", "airport", "origin"].includes(stop.kind));
  const booked = planned.filter((stop) => stop.booked).length;
  const date = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: "UTC" }).format(new Date(`${day.date}T00:00:00Z`));
  return (
    <>
      <span className={`font-normal ${selected ? "text-white/75" : "text-muted"}`}>{date}</span>
      <span className={`rounded px-1 text-[10px] font-semibold tabular-nums ${selected ? "bg-white/15 text-white" : booked === planned.length ? "bg-emerald-50 text-emerald-700" : "bg-sand text-muted"}`} title={`${booked} of ${planned.length} planned stops confirmed`}>{booked}/{planned.length}</span>
    </>
  );
}

function DayBar({ chrome, state }: { chrome: Chrome; state: PlannerState }) {
  const days = state.itinerary.days;
  const active = state.circuitDay ?? state.focus?.day ?? null;
  const groupClass = isCrisp(chrome) ? "flex items-center gap-0.5" : "flex items-center gap-0.5 rounded-full bg-sand p-0.5 ring-1 ring-inset ring-border";
  return (
    <nav aria-label="Trip days and stop sequence" className={`relative z-10 flex h-8 shrink-0 items-center gap-2 px-3 ${chrome === "soft" ? "bg-background" : "border-b border-border bg-paper"}`} data-lab-change={chrome === "today" ? undefined : "Day bar"}>
      <div className={groupClass}>
        <button type="button" onClick={state.showAllDays} className={`h-6 px-2.5 text-[11px] font-semibold transition ${isCrisp(chrome) ? "rounded" : "rounded-full"} ${state.allDays || active == null ? isCrisp(chrome) ? "bg-ink text-white" : "bg-paper text-ink shadow-sm" : "text-muted hover:text-ink"}`}>All days</button>
        {days.map((day) => {
          const selected = !state.allDays && active === day.day;
          if (chrome === "today") {
            return <button key={day.day} type="button" onClick={() => state.showDay(day.day)} className={`h-6 rounded-full px-2.5 text-[11px] font-semibold transition ${selected ? "text-white shadow-sm" : "text-muted hover:bg-paper hover:text-ink"}`} style={selected ? { backgroundColor: day.color } : undefined}>Day {day.day}</button>;
          }
          return (
            <button key={day.day} type="button" onClick={() => state.showDay(day.day)} className={`inline-flex h-6 items-center gap-1.5 px-2.5 text-[11px] font-semibold transition ${isCrisp(chrome) ? `rounded ${selected ? "bg-ink text-white" : "text-muted hover:bg-sand hover:text-ink"}` : `rounded-full ${selected ? "bg-paper text-ink shadow-sm" : "text-muted hover:text-ink"}`}`}>
              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: day.color }} aria-hidden />
              Day {day.day}
              {chrome === "crisp2" && <DayBarExtra day={day} selected={selected} />}
            </button>
          );
        })}
      </div>
      <span className="h-5 w-px bg-border" aria-hidden />
      <button type="button" className="inline-flex h-6 items-center gap-1 rounded-md px-2 text-[11px] font-semibold text-muted hover:text-ink"><Route size={13} aria-hidden /> Sequence <ChevronUp size={12} className="hidden" aria-hidden /><ChevronDown size={12} aria-hidden /></button>
    </nav>
  );
}

const PIN_LAYOUT: Record<number, Array<[number, number]>> = {
  1: [[12, 14], [22, 20], [30, 30], [36, 24], [40, 32], [44, 40], [28, 12], [30, 30]],
  2: [[30, 30], [26, 8], [22, 12], [34, 16], [24, 10], [42, 36], [46, 42], [52, 58], [30, 30]],
  3: [[30, 30], [40, 48], [58, 66], [72, 78], [80, 86]],
  4: [[80, 86], [76, 82], [72, 80], [70, 74], [88, 70], [94, 60]],
};

function MapCanvas({ state }: { state: PlannerState }) {
  const shownDays = state.circuitDay != null ? state.itinerary.days.filter((day) => day.day === state.circuitDay) : state.itinerary.days;
  return (
    <div className="relative h-full w-full overflow-hidden bg-[#eef1ea]">
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 h-full w-full" aria-hidden>
        <path d="M0 62 C 18 58, 30 70, 48 64 S 80 50, 100 56" stroke="#d7dccd" strokeWidth="3" fill="none" />
        <path d="M8 0 L 30 40 L 60 70 L 100 92" stroke="#ffffff" strokeWidth="1.4" fill="none" />
        <path d="M0 28 L 100 34" stroke="#ffffff" strokeWidth="0.9" fill="none" />
        <ellipse cx="84" cy="84" rx="9" ry="5" fill="#bcd6e2" />
        {shownDays.map((day) => {
          const points = (PIN_LAYOUT[day.day] || []).slice(0, day.stops.length);
          return <polyline key={day.day} points={points.map(([x, y]) => `${x},${y}`).join(" ")} fill="none" stroke={day.color} strokeWidth="0.6" strokeDasharray="1.4 0.8" opacity={state.circuitDay == null ? 0.55 : 0.95} />;
        })}
      </svg>
      {shownDays.flatMap((day) => day.stops.map((stop, index) => {
        const [x, y] = (PIN_LAYOUT[day.day] || [])[index] || [50, 50];
        const focused = state.focus?.day === day.day && state.focus.index === index + 1;
        return (
          <span
            key={`${day.day}-${index}`}
            className={`absolute grid -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border-2 border-white text-[9px] font-bold text-white shadow transition ${focused ? "z-10 h-7 w-7 ring-4 ring-white/70" : "h-4 w-4"}`}
            style={{ left: `${x}%`, top: `${y}%`, backgroundColor: day.color }}
            title={stop.name}
          >
            {focused ? "●" : ""}
          </span>
        );
      }))}
      <div className="absolute bottom-3 left-3 rounded-full bg-paper/95 px-3 py-1 text-[11px] font-semibold text-ink shadow-sm ring-1 ring-border">
        {state.circuitDay != null ? `Day ${state.circuitDay} circuit` : state.focus ? state.focus.name : "All days"}
      </div>
    </div>
  );
}

function DetailsBody({ chrome, state }: { chrome: Chrome; state: PlannerState }) {
  // Details shows Hawa Mahal until a stop is chosen, so the frame never opens empty.
  const target = state.focus ?? { day: 1, index: 4 };
  const focused = state.itinerary.days.find((day) => day.day === target.day)?.stops[target.index - 1];
  const chip = isCrisp(chrome)
    ? "inline-flex items-center gap-1 rounded border border-border px-1.5 py-0.5 text-[11px] font-medium text-muted"
    : chrome === "soft"
      ? "inline-flex items-center gap-1 rounded-full border border-border/80 bg-paper px-2.5 py-0.5 text-[11px] font-medium text-muted"
      : "chip";
  if (!focused) return <p className="p-4 text-xs text-muted">Choose a stop to see its details.</p>;
  return (
    <div className="p-4" data-lab-change={chrome === "today" ? undefined : "Details finish"}>
      <div className={`h-32 w-full ${isCrisp(chrome) ? "rounded-md" : "rounded-xl"}`} style={{ background: "linear-gradient(135deg,#f6d9c4 0%,#e9b99a 45%,#c9d8c5 100%)" }} aria-hidden />
      <p className={`mt-3 text-[10px] font-bold uppercase tracking-[0.08em] ${isCrisp(chrome) ? "text-muted" : "text-brand"}`}>{focused.kind}</p>
      <h3 className={isCrisp(chrome) ? "mt-0.5 text-base font-semibold tracking-[-0.01em] text-ink" : "display mt-0.5 text-xl leading-tight text-ink"}>{focused.name}</h3>
      <div className="mt-2 flex flex-wrap gap-1">
        {typeof focused.rating === "number" && <span className={chip}>★ {focused.rating.toFixed(1)}{focused.review_count ? ` · ${new Intl.NumberFormat("en", { notation: "compact" }).format(focused.review_count)} reviews` : ""}</span>}
        {focused.cost_display && <span className={chip}>{focused.cost_display}</span>}
        {focused.opening_hours && <span className={chip}>{focused.opening_hours}</span>}
      </div>
      {(focused.insight || focused.note) && <p className="mt-3 text-xs leading-relaxed text-muted">{focused.insight || focused.note}</p>}
      <div className="mt-4 grid grid-cols-3 gap-1.5">
        {["#e8d5c4", "#d6e0cf", "#efe1d2"].map((color) => <span key={color} className={`h-14 ${isCrisp(chrome) ? "rounded" : "rounded-lg"}`} style={{ background: color }} aria-hidden />)}
      </div>
      <p className={`mt-4 text-[10px] font-bold uppercase tracking-[0.08em] ${isCrisp(chrome) ? "text-muted" : "text-muted"}`}>Recent reviews</p>
      <p className="mt-1 text-xs leading-relaxed text-muted">“Worth every minute — go early and the light on the sandstone is unforgettable.”</p>
    </div>
  );
}

function AssistantDock({ chrome }: { chrome: Chrome }) {
  return (
    <div className={`absolute bottom-3 right-3 z-20 flex w-[min(25%,360px)] items-center gap-2 bg-paper p-1.5 pl-3 ${isCrisp(chrome) ? "rounded-md border border-border shadow-sm" : "rounded-full shadow-pop ring-1 ring-border"}`}>
      <Sparkles size={14} className="shrink-0 text-brand" aria-hidden />
      <span className="min-w-0 flex-1 truncate text-xs text-muted">Ask the Assistant to change this trip…</span>
      <span className="hidden text-[10px] text-muted xl:inline">Default preferences</span>
      <button type="button" className={`grid h-7 w-7 place-items-center text-white ${isCrisp(chrome) ? "rounded bg-ink" : "rounded-full bg-brand"}`} aria-label="Send"><Send size={13} aria-hidden /></button>
    </div>
  );
}

/** The itinerary pane alone, at a fixed pane width, for side-by-side comparison. */
export function PaneFrame({ chrome, state, children }: { chrome: Chrome; state: PlannerState; children: ReactNode }) {
  const themeClass = chrome === "crisp2" ? "ipp-crisp ipp-readable" : isCrisp(chrome) ? "ipp-crisp" : chrome === "soft" ? "ipp-soft" : "";
  return (
    <div className={`h-full w-full bg-background p-1.5 text-ink ${themeClass}`} style={{ fontFamily: '"Work Sans", ui-sans-serif, system-ui, sans-serif' }}>
      <article className={paneShell(chrome)}>
        <PaneHeader chrome={chrome} label="Itinerary" context="Read and refine" Icon={ListChecks} maximized={false} onToggleMaximize={() => undefined}>
          <FilterGroup state={state} chrome={chrome} />
          {chrome === "crisp2" && <ReadyHint state={state} />}
        </PaneHeader>
        <div className="min-h-0 flex-1">{children}</div>
      </article>
    </div>
  );
}

export function Workspace({ chrome, state, width, onWidth, itinerary }: {
  chrome: Chrome;
  state: PlannerState;
  width: PaneWidth;
  onWidth: (width: PaneWidth) => void;
  itinerary: ReactNode;
}) {
  const maximized = width === "maximized";
  const themeClass = chrome === "crisp2" ? "ipp-crisp ipp-readable" : isCrisp(chrome) ? "ipp-crisp" : chrome === "soft" ? "ipp-soft" : "";
  return (
    <div className={`ipp-workspace relative flex h-[900px] w-[1440px] flex-col overflow-hidden bg-sand text-ink ${themeClass}`} style={{ fontFamily: '"Work Sans", ui-sans-serif, system-ui, sans-serif' }}>
      <Toolbar chrome={chrome} />
      <NoticeStrip chrome={chrome} />
      <DayBar chrome={chrome} state={state} />
      <main className={`grid min-h-0 flex-1 overflow-hidden bg-background ${chrome === "soft" ? "gap-2 p-2" : isCrisp(chrome) ? "gap-1.5 p-1.5" : "gap-1.5 p-1.5"}`} style={{ gridTemplateColumns: COLUMNS[width] }}>
        <section className="min-h-0 min-w-0">
          <article className={paneShell(chrome)}>
            <PaneHeader chrome={chrome} label="Itinerary" context="Read and refine" Icon={ListChecks} maximized={maximized} onToggleMaximize={() => onWidth(maximized ? "default" : "maximized")}>
              <FilterGroup state={state} chrome={chrome} />
              {chrome === "crisp2" && <ReadyHint state={state} />}
            </PaneHeader>
            <div className="min-h-0 flex-1" data-lab-change="Itinerary pane body">{itinerary}</div>
          </article>
        </section>
        {!maximized && (
          <section className="min-h-0 min-w-0">
            <article className={paneShell(chrome)}>
              <PaneHeader chrome={chrome} label="Map" context="Explore and route" Icon={MapPin} maximized={false} onToggleMaximize={() => undefined} />
              <div className="min-h-0 flex-1"><MapCanvas state={state} /></div>
            </article>
          </section>
        )}
        {!maximized && (
          <aside className={paneShell(chrome)}>
            <PaneHeader chrome={chrome} label="Place details" context="Selected stop" Icon={MapPin} maximized={false} onToggleMaximize={() => undefined} />
            <div className="min-h-0 flex-1 overflow-y-auto"><DetailsBody chrome={chrome} state={state} /></div>
          </aside>
        )}
      </main>
      <AssistantDock chrome={chrome} />
    </div>
  );
}
