import { Layers, Plus, Route, Search, X } from "lucide-react";
import { useState } from "react";
import { StylizedMap } from "../shared/StylizedMap";
import { days, dayTotals } from "../shared/tripFixture";
import type { Day, Stop } from "../shared/tripFixture";

export type MapOption = "deck" | "dock" | "ribbon";

const findStop = (id: string | null) => {
  for (const day of days) {
    const stop = day.stops.find((candidate) => candidate.id === id);
    if (stop) return { stop, day };
  }
  return null;
};

function dayFactsLine(day: Day | null) {
  if (!day) return "Choose a day for its schedule and route-only travel.";
  return `Schedule ${day.schedule.duration}, ${day.schedule.start}–${day.schedule.end}${
    day.schedule.estimated ? " est." : ""
  } · Travel ${day.route.duration}, ${day.route.distance}, ${day.route.mode}`;
}

function DayScope({
  activeDay,
  onChange,
  variant = "solid",
}: {
  activeDay: number | null;
  onChange: (day: number | null) => void;
  variant?: "solid" | "glass";
}) {
  const base = "shrink-0 rounded-lg px-2.5 py-1 text-[11px] font-semibold transition";
  return (
    <div className="flex min-w-0 items-center gap-1 overflow-x-auto" aria-label="Map day scope">
      <button
        type="button"
        onClick={() => onChange(null)}
        className={`${base} ${
          activeDay === null
            ? "bg-ink text-white"
            : variant === "glass"
              ? "text-slate-600 hover:bg-white"
              : "text-slate-500 hover:bg-slate-100 hover:text-ink"
        }`}
      >
        All days
      </button>
      {days.map((day) => (
        <button
          key={day.day}
          type="button"
          onClick={() => onChange(day.day)}
          style={activeDay === day.day ? { backgroundColor: day.color } : undefined}
          className={`${base} ${
            activeDay === day.day
              ? "text-white"
              : variant === "glass"
                ? "text-slate-600 hover:bg-white"
                : "text-slate-500 hover:bg-slate-100 hover:text-ink"
          }`}
        >
          Day {day.day}
        </button>
      ))}
    </div>
  );
}

/** The three add-stop controls production needs: query, optional type, target day. */
function AddStop({ compact = false }: { compact?: boolean }) {
  const [open, setOpen] = useState(!compact);
  if (compact && !open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-full bg-brand px-3.5 text-xs font-semibold text-white shadow-sm transition hover:bg-brand-600"
      >
        <Plus size={14} aria-hidden /> Add a place
      </button>
    );
  }
  return (
    <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
      <div className="relative min-w-[9rem] flex-1">
        <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" aria-hidden />
        <input
          type="text"
          placeholder="Search places on this map…"
          className="h-9 w-full rounded-full border border-slate-200 bg-white pl-8 pr-3 text-xs text-slate-700 placeholder:text-slate-400"
        />
      </div>
      <select
        aria-label="Stop type (optional)"
        className="h-9 rounded-full border border-slate-200 bg-white px-3 text-xs text-slate-500"
      >
        <option>Type (optional)</option>
        <option>Attraction</option>
        <option>Hotel</option>
        <option>Restaurant</option>
      </select>
      <select
        aria-label="Add stop to day"
        className="h-9 rounded-full border border-slate-200 bg-white px-3 text-xs text-slate-600"
      >
        <option>Best day</option>
        {days.map((day) => <option key={day.day}>Day {day.day}</option>)}
      </select>
      <button
        type="button"
        className="inline-flex h-9 shrink-0 items-center gap-1 rounded-full bg-brand px-3.5 text-xs font-semibold text-white"
      >
        <Plus size={14} aria-hidden /> Add
      </button>
      {compact && (
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="grid h-9 w-9 shrink-0 place-items-center rounded-full text-slate-400 hover:bg-slate-100"
          title="Close search"
        >
          <X size={14} aria-hidden />
        </button>
      )}
    </div>
  );
}

function PinCard({ stop, day, onClose }: { stop: Stop; day: Day; onClose: () => void }) {
  return (
    <aside className="w-[19rem] rounded-2xl border border-slate-200 bg-white/95 p-3 shadow-pop backdrop-blur">
      <div
        className="mb-2 h-24 w-full rounded-xl"
        style={{ background: "linear-gradient(135deg,#fde7ea 0%,#f7d7c6 45%,#cfe6e2 100%)" }}
        aria-hidden
      />
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[10px] font-bold uppercase" style={{ color: day.color }}>
            Day {day.day} · {stop.timing} {stop.time}
          </p>
          <p className="truncate text-sm font-semibold text-ink">{stop.name}</p>
          {typeof stop.rating === "number" && (
            <p className="text-xs text-slate-500">★ {stop.rating.toFixed(1)}</p>
          )}
          <p className="mt-0.5 line-clamp-2 text-[11px] text-slate-500">
            {stop.operational ? `${stop.operational} · ` : ""}Lisboa, Portugal
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="grid h-7 w-7 shrink-0 place-items-center rounded-full text-slate-400 hover:bg-slate-100 hover:text-slate-700"
          title="Close"
        >
          <X size={14} aria-hidden />
        </button>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <button type="button" className="btn-ghost h-8 px-3 text-xs">Open details</button>
        {stop.planned ? (
          <>
            <select aria-label="Move to day" className="h-8 rounded-full border border-slate-200 bg-white px-2.5 text-xs text-slate-600">
              {days.map((entry) => <option key={entry.day}>Day {entry.day}</option>)}
            </select>
            <button type="button" className="h-8 rounded-full px-3 text-xs font-semibold text-rose-600 ring-1 ring-rose-200">
              Remove
            </button>
          </>
        ) : (
          <>
            <select aria-label="Add to day" className="h-8 rounded-full border border-slate-200 bg-white px-2.5 text-xs text-slate-600">
              <option>Best day</option>
              {days.map((entry) => <option key={entry.day}>Day {entry.day}</option>)}
            </select>
            <button type="button" className="btn-primary h-8 px-3 text-xs">+ Add to trip</button>
          </>
        )}
      </div>
    </aside>
  );
}

function ContextCard({ day }: { day: Day }) {
  const totals = dayTotals(day);
  return (
    <aside className="w-[19rem] rounded-2xl border border-slate-200 bg-white/95 p-3 shadow-pop backdrop-blur">
      <p className="text-[10px] font-bold uppercase" style={{ color: day.color }}>Day {day.day} circuit</p>
      <p className="truncate text-sm font-semibold text-ink">{day.title}</p>
      <p className="mt-1 text-[11px] text-slate-600">
        Schedule {day.schedule.duration}, {day.schedule.start}–{day.schedule.end}{day.schedule.estimated ? " est." : ""}
      </p>
      <p className="text-[11px] text-slate-600">
        Travel {day.route.duration}, {day.route.distance}, {day.route.mode}
      </p>
      <p className="mt-1 text-[11px] text-slate-500">
        {totals.planned} planned · {totals.confirmed} confirmed · {totals.toBook} to book
      </p>
    </aside>
  );
}

/* --------------------------------- A · Deck ---------------------------------- */

function DeckOption({ activeDay, setActiveDay, selected, setSelected }: OptionProps) {
  const active = days.find((day) => day.day === activeDay) ?? null;
  const picked = findStop(selected);
  return (
    <div className="relative h-full">
      <StylizedMap activeDay={activeDay} selectedId={selected} onSelect={(stop) => setSelected(stop.id)} />
      <div data-lab-change="Map commands" className="pointer-events-none absolute inset-x-0 top-0 z-30 p-3">
        <div className="pointer-events-auto flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1 rounded-full bg-white/90 p-1 shadow-pop ring-1 ring-slate-200 backdrop-blur">
            <DayScope activeDay={activeDay} onChange={setActiveDay} variant="glass" />
          </div>
          <div className="ml-auto flex items-center gap-2 rounded-full bg-white/90 p-1 pl-1.5 shadow-pop ring-1 ring-slate-200 backdrop-blur">
            <AddStop compact />
          </div>
        </div>
      </div>
      <div className="pointer-events-none absolute inset-x-0 bottom-0 z-20 flex items-end justify-between gap-3 p-3">
        <div className="pointer-events-auto rounded-2xl bg-white/90 px-3 py-2 shadow-pop ring-1 ring-slate-200 backdrop-blur">
          <p className="text-[11px] font-semibold text-ink">
            {active ? `Day ${active.day} · ${active.title}` : "All days"}
          </p>
          <p className="text-[11px] text-slate-600">{dayFactsLine(active)}</p>
        </div>
        <button type="button" className="pointer-events-auto grid h-9 w-9 place-items-center rounded-full bg-white/90 text-slate-500 shadow-pop ring-1 ring-slate-200 backdrop-blur" title="Map layers">
          <Layers size={15} aria-hidden />
        </button>
      </div>
      {picked && (
        <div className="absolute right-3 top-16 z-30">
          <PinCard stop={picked.stop} day={picked.day} onClose={() => setSelected(null)} />
        </div>
      )}
      {!picked && active && <div className="absolute right-3 top-16 z-20"><ContextCard day={active} /></div>}
    </div>
  );
}

/* --------------------------------- B · Dock ---------------------------------- */

function DockOption({ activeDay, setActiveDay, selected, setSelected }: OptionProps) {
  const active = days.find((day) => day.day === activeDay) ?? null;
  const picked = findStop(selected);
  const totals = active ? dayTotals(active) : null;
  return (
    <div className="relative flex h-full flex-col">
      <div className="relative min-h-0 flex-1">
        <StylizedMap activeDay={activeDay} selectedId={selected} onSelect={(stop) => setSelected(stop.id)} />
        <div className="pointer-events-none absolute inset-x-0 top-0 z-30 flex items-start gap-2 p-3">
          <div className="pointer-events-auto ml-auto flex items-center gap-2 rounded-full bg-white/90 p-1 pl-1.5 shadow-pop ring-1 ring-slate-200 backdrop-blur">
            <AddStop compact />
          </div>
        </div>
        {picked && (
          <div className="absolute right-3 top-16 z-30">
            <PinCard stop={picked.stop} day={picked.day} onClose={() => setSelected(null)} />
          </div>
        )}
      </div>

      <div data-lab-change="Map commands" className="z-20 shrink-0 border-t border-slate-200 bg-white/95 backdrop-blur">
        <div className="flex items-center gap-2 px-3 py-1.5">
          <DayScope activeDay={activeDay} onChange={setActiveDay} />
          <span className="ml-auto shrink-0 text-[11px] text-slate-500">
            {active ? `${totals?.planned} planned · ${totals?.confirmed} confirmed · ${totals?.toBook} to book` : "5 days planned"}
          </span>
        </div>
        <div className="flex items-center gap-1.5 border-t border-slate-100 px-3 py-1 text-[11px] text-slate-600">
          {active ? (
            <>
              <span className="font-semibold text-ink">Day {active.day} · {active.title}</span>
              <span className="text-slate-300" aria-hidden>|</span>
              <Route size={11} aria-hidden />
              <span>{dayFactsLine(active)}</span>
            </>
          ) : (
            <span>{dayFactsLine(null)}</span>
          )}
        </div>
        {active && (
          <ol className="flex items-stretch gap-1 overflow-x-auto border-t border-slate-100 px-3 py-2">
            {active.stops.map((stop, index) => (
              <li key={stop.id} className="flex shrink-0 items-center gap-1">
                {index > 0 && stop.travel && (
                  <span className="whitespace-nowrap px-1 text-[10px] font-medium text-accent">
                    {stop.travel.duration}
                  </span>
                )}
                <button
                  type="button"
                  onClick={() => setSelected(stop.id)}
                  className={`flex min-w-[7.5rem] max-w-[11rem] items-center gap-1.5 rounded-xl border px-2 py-1.5 text-left transition ${
                    selected === stop.id ? "border-transparent bg-ink text-white" : "border-slate-200 bg-white hover:border-slate-300"
                  }`}
                >
                  <span
                    className="grid h-5 w-5 shrink-0 place-items-center rounded-full border text-[10px] font-bold"
                    style={{ borderColor: active.color, color: selected === stop.id ? "#fff" : active.color }}
                  >
                    {stop.marker ?? "•"}
                  </span>
                  <span className="min-w-0">
                    <span className={`block text-[10px] tabular-nums ${selected === stop.id ? "text-white/70" : "text-slate-400"}`}>
                      {stop.time}{stop.estimated ? "*" : ""}
                    </span>
                    <span className="block truncate text-[11px] font-semibold">{stop.name}</span>
                  </span>
                  {stop.bookable && (
                    <span
                      className={`ml-auto h-1.5 w-1.5 shrink-0 rounded-full ${stop.booked ? "bg-emerald-500" : "bg-amber-400"}`}
                      title={stop.booked ? "Confirmed" : "Needs booking"}
                    />
                  )}
                </button>
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}

/* -------------------------------- C · Ribbon --------------------------------- */

function RibbonOption({ activeDay, setActiveDay, selected, setSelected }: OptionProps) {
  const active = days.find((day) => day.day === activeDay) ?? null;
  const picked = findStop(selected);
  return (
    <div className="flex h-full flex-col">
      <div data-lab-change="Map commands" className="shrink-0 border-b border-slate-200 bg-white">
        <div className="flex flex-wrap items-center gap-2 px-3 py-2">
          <DayScope activeDay={activeDay} onChange={setActiveDay} />
          <span className="mx-1 hidden h-5 w-px bg-slate-200 lg:block" aria-hidden />
          <AddStop />
        </div>
        <div
          className="flex flex-wrap items-center gap-x-2 gap-y-0.5 border-t border-slate-100 px-3 py-1.5 text-[11px] text-slate-600"
          style={active ? { boxShadow: `inset 3px 0 0 ${active.color}` } : undefined}
        >
          {active ? (
            <>
              <span className="font-semibold text-ink">Day {active.day} · {active.title}</span>
              <span className="text-slate-300" aria-hidden>·</span>
              <span>{dayFactsLine(active)}</span>
              <span className="text-slate-300" aria-hidden>·</span>
              <span className="text-accent">{active.rhythm}</span>
            </>
          ) : (
            <span>{dayFactsLine(null)}</span>
          )}
        </div>
      </div>
      <div className="relative min-h-0 flex-1">
        <StylizedMap activeDay={activeDay} selectedId={selected} onSelect={(stop) => setSelected(stop.id)} />
        {picked && (
          <div className="absolute right-3 top-3 z-30">
            <PinCard stop={picked.stop} day={picked.day} onClose={() => setSelected(null)} />
          </div>
        )}
        {!picked && active && <div className="absolute right-3 top-3 z-20"><ContextCard day={active} /></div>}
      </div>
    </div>
  );
}

/* --------------------------------- Baseline ---------------------------------- */

function TodayOption({ activeDay, setActiveDay, selected, setSelected }: OptionProps) {
  const active = days.find((day) => day.day === activeDay) ?? null;
  const picked = findStop(selected);
  return (
    <div className="flex h-full flex-col">
      <div className="shrink-0 border-b border-slate-200 bg-white/95">
        <div className="border-b border-slate-100 px-3 py-1.5">
          <div className="flex min-w-0 items-center gap-1 overflow-x-auto">
            <button
              type="button"
              onClick={() => setActiveDay(null)}
              className={`shrink-0 rounded-md px-2 py-1 text-[11px] font-semibold ${activeDay === null ? "bg-ink text-white" : "text-slate-500"}`}
            >
              All days
            </button>
            {days.map((day) => (
              <button
                key={day.day}
                type="button"
                onClick={() => setActiveDay(day.day)}
                style={activeDay === day.day ? { backgroundColor: day.color } : undefined}
                className={`shrink-0 rounded-md px-2 py-1 text-[11px] font-semibold ${activeDay === day.day ? "text-white" : "text-slate-500"}`}
              >
                Day {day.day}
              </button>
            ))}
          </div>
        </div>
        <div className="px-3 py-2">
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative min-w-[9rem] flex-1">
              <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" aria-hidden />
              <input
                type="text"
                placeholder="Search places on this map…"
                className="w-full rounded-md border border-slate-200 py-1.5 pl-8 pr-3 text-xs text-slate-700 placeholder:text-slate-400"
              />
            </div>
            <select className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-500" aria-label="Stop type (optional)">
              <option>Type (optional)</option>
            </select>
            <select className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-600" aria-label="Add stop to day">
              <option>Best day</option>
              {days.map((day) => <option key={day.day}>Day {day.day}</option>)}
            </select>
            <button type="button" className="inline-flex items-center gap-1 rounded-md bg-brand px-3 py-1.5 text-xs font-semibold text-white">
              <Plus className="h-3.5 w-3.5" aria-hidden /> Add
            </button>
          </div>
        </div>
        <div className="flex min-h-6 items-center gap-1.5 border-t border-slate-100 px-3 py-1 text-[10px] text-slate-500">
          {active ? (
            <>
              <span className="font-semibold text-slate-700">Day {active.day}</span>
              <span aria-hidden>·</span>
              <span>Schedule {active.schedule.duration}, {active.schedule.start}–{active.schedule.end}{active.schedule.estimated ? " est." : ""}</span>
              <span aria-hidden>·</span>
              <span>Travel {active.route.duration}, {active.route.distance}, {active.route.mode}</span>
            </>
          ) : (
            <span>Choose a day for schedule and route-only travel.</span>
          )}
        </div>
      </div>
      <div className="relative min-h-0 flex-1">
        <StylizedMap activeDay={activeDay} selectedId={selected} onSelect={(stop) => setSelected(stop.id)} />
        {picked && (
          <div className="absolute right-3 top-3 z-30">
            <PinCard stop={picked.stop} day={picked.day} onClose={() => setSelected(null)} />
          </div>
        )}
      </div>
    </div>
  );
}

interface OptionProps {
  activeDay: number | null;
  setActiveDay: (day: number | null) => void;
  selected: string | null;
  setSelected: (id: string | null) => void;
}

export function MapCanvas({ option, showError = false }: { option: MapOption | "today"; showError?: boolean }) {
  const [activeDay, setActiveDay] = useState<number | null>(3);
  const [selected, setSelected] = useState<string | null>(null);
  const props: OptionProps = { activeDay, setActiveDay, selected, setSelected };
  const body =
    option === "today" ? <TodayOption {...props} />
    : option === "deck" ? <DeckOption {...props} />
    : option === "ribbon" ? <RibbonOption {...props} />
    : <DockOption {...props} />;

  return (
    <div className="relative h-full">
      {body}
      {showError && (
        <div className="absolute bottom-3 left-3 z-40 flex items-center gap-2 rounded-full bg-rose-50 px-3 py-1.5 text-[11px] font-medium text-rose-700 shadow-pop ring-1 ring-rose-200">
          Could not load places for this area.
          <button type="button" className="rounded-full bg-white px-2 py-0.5 font-semibold text-rose-700 ring-1 ring-rose-200">
            Retry
          </button>
        </div>
      )}
    </div>
  );
}
