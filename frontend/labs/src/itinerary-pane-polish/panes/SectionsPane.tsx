import { useState, type ReactNode } from "react";
import { CalendarCheck2, Clock3, CornerDownRight, MapPin, Route } from "lucide-react";
import { modeIcon } from "../icons";
import type { DayFacts, RowFacts } from "../model";
import type { PlannerState } from "../state";
import { CrispSnapshot } from "./CrispPane";
import { InlineNotesToggle, NotesBody, ReadableSignals, spareTone } from "./FlowPane";
import {
  BookingToggle, Checks, Concerns, DayWeather, dayTravelText, EmptyFilters, Marker, OpenRoute, StopActions,
  StopMeta, StopName, TripLength,
} from "./common";

/**
 * G · Crisp day sections. A's pane and workspace finish, refined differently from F:
 * - every day is its own bordered section with a gap before the next, a colour
 *   bar, a 17px title and labelled stat tiles with a booking progress bar;
 * - a "Jump to day" strip at the top of Day by day scrolls the pane to a section;
 * - "how you get here" is folded into the arriving stop as a ↳ line, so travel
 *   no longer adds rows of its own;
 * - on a wide pane the rows become a table with column headings, a separate
 *   time-range column and zebra striping; on a narrow pane they stack.
 */

function Stop({ state, facts, row }: { state: PlannerState; facts: DayFacts; row: RowFacts }) {
  const day = facts.day.day;
  const active = state.isFocused(day, row);
  const ModeIcon = row.travel ? modeIcon(row.travel.mode) : null;
  const range = [row.stop.time, row.stop.departure_time].filter(Boolean).join("–");
  const [notesOpen, setNotesOpen] = useState(false);
  const hasSignals = !!(row.rating || row.mustVisit || row.cost || row.hours);
  const hasExtra = row.concerns.length > 0 || notesOpen;
  return (
    <li id={row.rowId} data-stop-name={row.stop.name.toLowerCase()} data-stop-day={day} data-stop-index={row.index} className="group">
      <div
        onClick={() => state.focusStop(day, row)}
        className={`ippg-row px-3 py-2 transition ${active ? "!bg-sand" : row.focusable ? "cursor-pointer hover:!bg-sand/70" : ""}`}
        style={active ? { boxShadow: `inset 3px 0 0 ${row.stop.color}` } : undefined}
      >
        <div className="ippg-mark"><Marker row={row} active={active} size={20} look="crisp" /></div>
        <div className="ippg-time pt-[1px] leading-tight tabular-nums">
          {row.stop.time && <p className="text-[13px] font-semibold text-ink">{row.stop.time}{row.stop.time_estimated && <span className="text-[10.5px] font-normal text-muted"> est.</span>}</p>}
          {row.stop.departure_time && <p className="text-[11.5px] text-muted">to {row.stop.departure_time}</p>}
        </div>
        <div className="ippg-main">
        <div className="ippg-name">
          <StopName state={state} day={day} row={row} className="block text-[14px] font-semibold leading-snug tracking-[-0.005em]" />
        </div>
        <div className="ippg-detail">
          <p className="ippg-time-inline text-[12px] font-semibold tabular-nums text-ink">{range}{row.stop.time_estimated ? " est." : ""}</p>
          <StopMeta row={row} className="text-[12px]" />
          {row.travel && ModeIcon && (
            <p className="mt-1 flex items-start gap-1 text-[12px] leading-snug text-muted" aria-label={row.travel.aria} title={row.travel.title}>
              <CornerDownRight size={12} className="mt-[2px] shrink-0" aria-hidden />
              <span className="min-w-0">
                <ModeIcon size={12} className="mr-1 inline -translate-y-px" aria-hidden />
                <span className="capitalize text-ink">{row.travel.mode}</span> <span className="tabular-nums">· {row.travel.distance} · {row.travel.duration}</span>
                {row.travel.detail && <span> — {row.travel.detail}</span>}
                {row.travel.arrival && <span className="block tabular-nums">{row.travel.arrival}{(row.travel.buffer || row.travel.conflict) && <span className={spareTone(row)}> · {row.travel.buffer ?? row.travel.conflict}</span>}</span>}
              </span>
            </p>
          )}
        </div>
        </div>
        <div className="ippg-sig flex flex-wrap items-center gap-1 pt-1">{(hasSignals || row.hasNotes) && <>{hasSignals && <ReadableSignals row={row} />}<InlineNotesToggle row={row} open={notesOpen} onToggle={() => setNotesOpen((value) => !value)} /></>}</div>
        <div className="ippg-status flex items-center gap-0.5">
          <StopActions state={state} day={day} row={row} look="crisp" />
          <BookingToggle state={state} day={day} row={row} look="crisp" short />
        </div>
        <div className="ippg-extra">{hasExtra && <><Concerns row={row} look="crisp" />{notesOpen && <NotesBody row={row} />}</>}</div>
      </div>
    </li>
  );
}

function Stat({ label, children, icon: Icon }: { label: string; children: ReactNode; icon: typeof Clock3 }) {
  return (
    <div className="min-w-0 rounded border border-border bg-paper px-2 py-1.5">
      <p className="flex items-center gap-1 text-[10.5px] font-medium text-muted"><Icon size={11} aria-hidden />{label}</p>
      <div className="mt-0.5 text-[12.5px] font-semibold tabular-nums text-ink">{children}</div>
    </div>
  );
}

function Day({ state, facts }: { state: PlannerState; facts: DayFacts }) {
  const { day } = facts;
  const circuitActive = state.circuitDay === day.day;
  const travel = dayTravelText(state, facts);
  const bookedPct = facts.planned ? Math.round((facts.confirmed / facts.planned) * 100) : 0;
  return (
    <section id={`lab-it-day-${day.day}`} className={`mx-2 overflow-clip rounded-md border bg-paper ${circuitActive ? "border-ink/40" : "border-border"}`} style={{ scrollMarginTop: 8 }}>
      <div className={`sticky top-0 z-10 flex items-center gap-2.5 border-b border-border py-2.5 pl-3 pr-3 ${circuitActive ? "bg-sand" : "bg-paper/95 backdrop-blur"}`} style={{ boxShadow: `inset 4px 0 0 ${day.color}` }}>
        <button type="button" onClick={() => state.showDay(day.day)} aria-current={circuitActive ? "true" : undefined} title={`Show complete Day ${day.day} circuit on map`} className="min-w-0 flex-1 pl-1.5 text-left">
          <span className="block text-[11px] font-semibold uppercase tracking-[0.08em]" style={{ color: day.color }}>Day {day.day}</span>
          <span className="block text-[17px] font-semibold leading-tight tracking-[-0.015em] text-ink">{day.title}</span>
          <span className="block text-[12px] text-muted">{facts.dateLabel}</span>
        </button>
        <div className="flex shrink-0 flex-col items-end gap-0.5 text-right">
          <DayWeather state={state} facts={facts} compact />
          {day.weather && <span className="text-[11.5px] text-muted">{day.weather.summary}</span>}
        </div>
      </div>
      <div className="px-3 pb-3 pt-2.5">
        {day.summary && <p className="text-[13px] leading-relaxed text-ink/80">{day.summary}</p>}
        <div className="mt-2.5 grid grid-cols-2 gap-1.5">
          <Stat label="Schedule duration" icon={Clock3}>{facts.scheduleText ?? "—"}</Stat>
          <Stat label="Day's travel" icon={MapPin}>{travel ?? "—"}</Stat>
          <Stat label="Stops" icon={Route}>{facts.planned} planned {facts.planned === 1 ? "stop" : "stops"}</Stat>
          <Stat label="Bookings" icon={CalendarCheck2}>
            <span className={facts.remaining > 0 ? "text-amber-700" : "text-emerald-700"}>{facts.confirmed} confirmed · {facts.remaining} to book</span>
            <span className="mt-1 block h-1 overflow-hidden rounded-full bg-sand"><span className="block h-full rounded-full bg-emerald-600" style={{ width: `${bookedPct}%` }} /></span>
          </Stat>
        </div>
        {day.reachability && <p className="mt-2 text-[12px] leading-relaxed text-muted"><strong className="font-semibold text-ink">Travel rhythm:</strong> {day.reachability}</p>}
        <div className="mt-1.5 flex items-center gap-1">
          <button type="button" onClick={() => state.showDay(day.day)} className={`inline-flex h-7 items-center gap-1.5 rounded px-1.5 text-[12px] font-semibold ${circuitActive ? "bg-ink text-white" : "text-muted hover:bg-sand hover:text-ink"}`}><MapPin size={12} aria-hidden /> Day on map</button>
          <OpenRoute state={state} facts={facts} className="inline-flex h-7 items-center gap-1.5 rounded px-1.5 text-[12px] font-semibold text-muted hover:bg-sand hover:text-ink" />
        </div>
      </div>
      {facts.rows.length > 0 && (
        <>
          <div className="ippg-head border-y border-border bg-sand/70 px-3 py-1 text-[10.5px] font-semibold uppercase tracking-[0.06em] text-muted" aria-hidden>
            <span />
            <span>Time</span>
            <span>Stop</span>
            <span>Ratings &amp; details</span>
            <span className="text-right">Status</span>
          </div>
          <ul className="ippg-list divide-y divide-border/70 border-t border-border" aria-label={facts.transition ? `Transition day timeline from ${facts.transition.from} to ${facts.transition.to}` : undefined}>
            {facts.rows.map((row) => <Stop key={row.key} state={state} facts={facts} row={row} />)}
          </ul>
        </>
      )}
    </section>
  );
}

export function SectionsPane({ state }: { state: PlannerState }) {
  const jump = (day: number) => document.getElementById(`lab-it-day-${day}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  return (
    <div className="ippx-pane h-full overflow-y-auto bg-background">
      <div className="bg-paper">
        <CrispSnapshot state={state} />
        <div className="border-b border-border px-3.5 py-2"><Checks state={state} look="crisp" /></div>
        <header className="border-b border-border px-3.5 pb-2 pt-1">
          <div className="flex items-center gap-2">
            <h2 className="text-[12px] font-semibold text-ink">Day by day</h2>
            <TripLength state={state} look="crisp" />
          </div>
          <nav aria-label="Jump to day" className="mt-1 flex gap-1 overflow-x-auto">
            {state.days.map((facts) => (
              <button key={facts.day.day} type="button" onClick={() => jump(facts.day.day)} className="inline-flex h-7 shrink-0 items-center gap-1.5 rounded border border-border px-2 text-[11.5px] text-ink hover:bg-sand" aria-label={`Jump to Day ${facts.day.day}: ${facts.day.title}`} title={`Jump to Day ${facts.day.day}`}>
                <span className="h-2 w-2 rounded-full" style={{ backgroundColor: facts.day.color }} aria-hidden />
                <b className="font-semibold">{facts.day.day}</b>
                <span className="max-w-[9rem] truncate text-muted">{facts.day.title}</span>
              </button>
            ))}
          </nav>
        </header>
      </div>
      <EmptyFilters state={state} />
      <div className="space-y-3 pb-4 pt-2.5">
        {state.days.map((facts) => <Day key={facts.day.day} state={state} facts={facts} />)}
      </div>
    </div>
  );
}
