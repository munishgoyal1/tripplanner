import { useState } from "react";
import { ChevronDown, Clock3, Flame, MapPin, Route, Star } from "lucide-react";
import { modeIcon } from "../icons";
import type { DayFacts, RowFacts } from "../model";
import type { PlannerState } from "../state";
import { CrispSnapshot } from "./CrispPane";
import {
  BookingToggle, Checks, Concerns, DayWeather, dayTravelText, EmptyFilters, Marker, OpenRoute, StopActions,
  StopMeta, StopName, TripLength,
} from "./common";

/**
 * F · Crisp flow rows. A's pane and workspace finish, refined:
 * - rows are a responsive grid on the pane's own width, so a wider pane puts
 *   signals and status on the stop's line and rows get shorter;
 * - the time sits in a slim gutter and the marker moves inline, freeing width;
 * - each day opens with a sticky, day-tinted band and a larger title, with a
 *   visible gap before the next day;
 * - travel legs are one line whose arrival and spare time move to the right
 *   when there is room, coloured by how tight the connection is;
 * - a Comfortable / Compact density switch changes spacing only.
 */

type Density = "comfortable" | "compact";

export function spareTone(row: RowFacts): string {
  if (row.travel?.conflict) return "font-medium text-rose-700";
  const spare = row.stop.buffer_before_min;
  if (spare != null && spare < 5) return "font-medium text-amber-700";
  return "text-emerald-700";
}

export function ReadableSignals({ row }: { row: RowFacts }) {
  const tag = "inline-flex items-center gap-1 whitespace-nowrap rounded border border-border bg-paper px-1.5 py-[1px] text-[11.5px] text-muted";
  return (
    <>
      {row.rating && (
        <span aria-label={row.rating.aria} className={tag}>
          <Star size={11} className="fill-amber-400 text-amber-400" aria-hidden /><b className="font-semibold text-ink">{row.rating.value}</b>
          {row.rating.reviews && <span>· {row.rating.reviews}</span>}
        </span>
      )}
      {row.mustVisit && (
        <span title={row.mustVisit.title} className={`${tag} text-brand`}>
          <Flame size={11} aria-hidden />Must-visit score <b className="font-semibold tabular-nums">{row.mustVisit.score}/100</b>
        </span>
      )}
      {row.cost && <span className={tag}>{row.cost}</span>}
      {row.hours && <span className={`${tag} tabular-nums`}><Clock3 size={11} aria-hidden />{row.hours}</span>}
    </>
  );
}

/** Notes & tips sits at the end of the tag row instead of taking a line of its own. */
export function InlineNotesToggle({ row, open, onToggle }: { row: RowFacts; open: boolean; onToggle: () => void }) {
  if (!row.hasNotes) return null;
  return (
    <button type="button" aria-expanded={open} onClick={(event) => { event.stopPropagation(); onToggle(); }} className="inline-flex h-[22px] items-center gap-1 whitespace-nowrap rounded px-1.5 text-[11.5px] font-semibold text-muted hover:bg-sand hover:text-ink">
      {open ? "Hide notes" : "Notes & tips"}<ChevronDown size={12} className={`transition ${open ? "rotate-180" : ""}`} aria-hidden />
    </button>
  );
}

export function NotesBody({ row }: { row: RowFacts }) {
  return <div className="mt-1.5 space-y-0.5 border-l-2 border-border pl-2.5">{[...row.notes, ...row.insights].map((text) => <p key={text} className="text-[12.5px] leading-relaxed text-muted">{text}</p>)}</div>;
}

function Stop({ state, facts, row, density }: { state: PlannerState; facts: DayFacts; row: RowFacts; density: Density }) {
  const day = facts.day.day;
  const active = state.isFocused(day, row);
  const [notesOpen, setNotesOpen] = useState(false);
  const ModeIcon = row.travel ? modeIcon(row.travel.mode) : null;
  const pad = density === "compact" ? "py-1.5" : "py-2.5";
  const hasSignals = !!(row.rating || row.mustVisit || row.cost || row.hours);
  const hasExtra = row.concerns.length > 0 || notesOpen;
  return (
    <li id={row.rowId} data-stop-name={row.stop.name.toLowerCase()} data-stop-day={day} data-stop-index={row.index} className="group">
      {row.travel && ModeIcon && (
        <div className="ippf-leg px-3" aria-label={row.travel.aria} title={row.travel.title}>
          <span className="flex justify-center"><span className="w-px bg-border" aria-hidden /></span>
          <p className="ippf-leg-text min-w-0 py-1 text-[12px] leading-snug text-muted">
            <span className="min-w-0">
              <ModeIcon size={13} className="mr-1.5 inline -translate-y-px text-muted" aria-hidden />
              <span className="capitalize text-ink">{row.travel.mode}</span>
              <span className="tabular-nums"> · {row.travel.distance} · {row.travel.duration}</span>
              {row.travel.detail && <span> — {row.travel.detail}</span>}
            </span>
            {row.travel.arrival && (
              <span className="ippf-leg-arrival tabular-nums">
                {row.travel.arrival}
                {(row.travel.buffer || row.travel.conflict) && <span className={spareTone(row)}> · {row.travel.buffer ?? row.travel.conflict}</span>}
              </span>
            )}
          </p>
        </div>
      )}
      <div
        onClick={() => state.focusStop(day, row)}
        className={`ippf-stop px-3 transition ${pad} ${active ? "bg-sand" : row.focusable ? "cursor-pointer hover:bg-sand/60" : ""}`}
        style={active ? { boxShadow: `inset 3px 0 0 ${row.stop.color}` } : undefined}
      >
        <div className="ippf-time pt-[1px] text-right leading-tight tabular-nums">
          {row.stop.time && <p className="text-[13px] font-semibold text-ink">{row.stop.time}</p>}
          {row.stop.time_estimated && <p className="text-[10.5px] text-muted">est.</p>}
        </div>
        <div className="ippf-main">
          <div className="ippf-name flex items-start gap-2">
            <span className="mt-[1px] flex"><Marker row={row} active={active} size={20} look="crisp" /></span>
            <StopName state={state} day={day} row={row} className="flex-1 text-[14px] font-semibold leading-snug tracking-[-0.005em]" />
          </div>
          <div className="ippf-detail"><StopMeta row={row} className="mt-0.5 pl-7 text-[12px]" /></div>
        </div>
        <div className="ippf-sig flex flex-wrap items-center gap-1 pl-7 pt-1.5">{(hasSignals || row.hasNotes) && <>{hasSignals && <ReadableSignals row={row} />}<InlineNotesToggle row={row} open={notesOpen} onToggle={() => setNotesOpen((value) => !value)} /></>}</div>
        <div className="ippf-status flex items-center gap-0.5">
          <StopActions state={state} day={day} row={row} look="crisp" />
          <BookingToggle state={state} day={day} row={row} look="crisp" short />
        </div>
        <div className="ippf-extra pl-7">{hasExtra && <><Concerns row={row} look="crisp" />{notesOpen && <NotesBody row={row} />}</>}</div>
      </div>
    </li>
  );
}

function Day({ state, facts, density }: { state: PlannerState; facts: DayFacts; density: Density }) {
  const { day } = facts;
  const circuitActive = state.circuitDay === day.day;
  const travel = dayTravelText(state, facts);
  const bookedPct = facts.planned ? Math.round((facts.confirmed / facts.planned) * 100) : 0;
  return (
    <section id={`lab-it-day-${day.day}`} className="bg-paper">
      <div
        className="sticky top-0 z-10 flex items-center gap-3 border-b border-border px-3 py-2.5 backdrop-blur"
        style={{ borderTop: `3px solid ${day.color}`, background: circuitActive ? `${day.color}24` : `color-mix(in oklch, ${day.color} 7%, oklch(var(--paper)) )` }}
      >
        <button type="button" onClick={() => state.showDay(day.day)} aria-current={circuitActive ? "true" : undefined} title={`Show complete Day ${day.day} circuit on map`} className="flex min-w-0 flex-1 items-center gap-2.5 text-left">
          <span className="grid h-8 w-8 shrink-0 place-items-center rounded-md text-[13px] font-bold text-white" style={{ backgroundColor: day.color }} aria-hidden>{day.day}</span>
          <span className="min-w-0">
            <span className="block text-[16.5px] font-semibold leading-tight tracking-[-0.015em] text-ink">{day.title}</span>
            <span className="block text-[12px] text-muted">{facts.dateLabel}</span>
          </span>
        </button>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <DayWeather state={state} facts={facts} compact />
          <span className="flex items-center gap-1.5 text-[11px] tabular-nums text-muted" title={`${facts.confirmed} of ${facts.planned} planned stops confirmed`}>
            <span className="h-1 w-12 overflow-hidden rounded-full bg-border"><span className="block h-full rounded-full bg-emerald-600" style={{ width: `${bookedPct}%` }} /></span>
            {facts.confirmed}/{facts.planned}
          </span>
        </div>
      </div>
      <div className="px-3 pb-2.5 pt-2.5">
        {day.summary && <p className="text-[13px] leading-relaxed text-ink/80">{day.summary}</p>}
        <p className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[12px] text-muted">
          {day.weather && <span>{day.weather.summary}</span>}
          {facts.scheduleText && <span className="inline-flex items-center gap-1 tabular-nums"><Clock3 size={12} aria-hidden /><b className="font-medium text-ink">Schedule duration:</b> {facts.scheduleText}</span>}
          {travel && <span className="inline-flex items-center gap-1 tabular-nums"><MapPin size={12} aria-hidden /><b className="font-medium text-ink">Day&apos;s travel:</b> {travel}</span>}
          <span><b className="font-medium text-ink">{facts.planned} planned {facts.planned === 1 ? "stop" : "stops"}</b> · <span className={facts.remaining > 0 ? "text-amber-700" : "text-emerald-700"}>{facts.confirmed} confirmed · {facts.remaining} to book</span></span>
        </p>
        {day.reachability && <p className="mt-1.5 text-[12px] leading-relaxed text-muted"><strong className="font-semibold text-ink">Travel rhythm:</strong> {day.reachability}</p>}
        <div className="mt-1.5 flex items-center gap-1">
          <button type="button" onClick={() => state.showDay(day.day)} className={`inline-flex h-7 items-center gap-1.5 rounded px-1.5 text-[12px] font-semibold ${circuitActive ? "bg-ink text-white" : "text-muted hover:bg-sand hover:text-ink"}`}><Route size={12} aria-hidden /> Day on map</button>
          <OpenRoute state={state} facts={facts} className="inline-flex h-7 items-center gap-1.5 rounded px-1.5 text-[12px] font-semibold text-muted hover:bg-sand hover:text-ink" />
        </div>
      </div>
      {facts.rows.length > 0 && (
        <ul className="divide-y divide-border/70 border-t border-border pb-1" aria-label={facts.transition ? `Transition day timeline from ${facts.transition.from} to ${facts.transition.to}` : undefined}>
          {facts.rows.map((row) => <Stop key={row.key} state={state} facts={facts} row={row} density={density} />)}
        </ul>
      )}
    </section>
  );
}

export function FlowPane({ state }: { state: PlannerState }) {
  const [density, setDensity] = useState<Density>("comfortable");
  return (
    <div className="ippx-pane h-full overflow-y-auto bg-background">
      <div className="bg-paper">
        <CrispSnapshot state={state} />
        <div className="border-b border-border px-3.5 py-2"><Checks state={state} look="crisp" /></div>
        <header className="flex items-center gap-2 border-b border-border px-3.5 py-1">
          <h2 className="text-[12px] font-semibold text-ink">Day by day</h2>
          <div role="group" aria-label="Row density" className="flex items-center gap-0.5 rounded bg-sand p-0.5">
            {(["comfortable", "compact"] as const).map((value) => (
              <button key={value} type="button" aria-pressed={density === value} onClick={() => setDensity(value)} className={`h-6 rounded px-1.5 text-[11px] font-semibold capitalize ${density === value ? "bg-paper text-ink shadow-sm" : "text-muted hover:text-ink"}`}>{value}</button>
            ))}
          </div>
          <TripLength state={state} look="crisp" />
        </header>
      </div>
      <EmptyFilters state={state} />
      <div className="space-y-2 pb-4 pt-2">
        {state.days.map((facts) => <Day key={facts.day.day} state={state} facts={facts} density={density} />)}
      </div>
    </div>
  );
}
