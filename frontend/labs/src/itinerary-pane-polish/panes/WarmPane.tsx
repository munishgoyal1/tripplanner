import { CheckCircle2, Clock3, MapPin, Route } from "lucide-react";
import { modeIcon } from "../icons";
import type { DayFacts, RowFacts } from "../model";
import { tripFacts } from "../shared";
import type { PlannerState } from "../state";
import {
  arrivalLine, BookingToggle, BudgetBlock, Checks, Concerns, CostLine, DayWeather, dayTravelText, EmptyFilters, Marker,
  NeedsBlock, Notes, OpenRoute, ReadinessBar, Signals, StopActions, StopMeta, StopName, TripLength, WeatherBlock,
} from "./common";

/**
 * C · Warm editorial harmony. Pane body plus the soft workspace finish.
 * Day covers tinted in the day's colour, serif titles, borderless tiles and
 * pill signals. Every trip fact stays visible at rest.
 */

function Snapshot({ state }: { state: PlannerState }) {
  const trip = tripFacts(state);
  return (
    <section aria-label="Trip snapshot" aria-current={state.allDays ? "true" : undefined} className="px-3 pt-3" data-lab-change="Trip snapshot">
      <div className={`rounded-2xl p-4 ${state.allDays ? "ring-2 ring-brand/25" : ""}`} style={{ background: "linear-gradient(160deg, oklch(var(--clay-soft) / 0.75), oklch(var(--paper)) 70%)" }}>
        <div className="flex items-start justify-between gap-3">
          <button type="button" onClick={state.showAllDays} className="min-w-0 text-left" title="Show all itinerary days on map">
            <h1 className="display text-[32px] leading-[0.95] text-ink">{state.overview.destination}</h1>
            <p className="mt-2 text-xs text-muted">{trip.metaLine}</p>
          </button>
          <div className="shrink-0 text-right">
            <span className="inline-flex rounded-full bg-paper/90 px-2.5 py-1 text-[11px] font-semibold capitalize text-muted shadow-sm">{state.overview.status}</span>
            <div className="mt-2"><CostLine state={state} look="warm" /></div>
          </div>
        </div>
        <p className="mt-3 text-[13px] leading-relaxed text-ink/75">{trip.summary}</p>
        <div className="mt-3 rounded-xl bg-paper/90 p-2.5 shadow-sm"><ReadinessBar state={state} look="warm" /></div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {trip.counts.map(({ label, value, Icon }) => (
            <span key={label} aria-label={`${value} ${label}`} className="inline-flex items-center gap-1 rounded-full bg-paper/90 px-2.5 py-1 text-[11px] text-muted shadow-sm"><Icon size={12} aria-hidden /><b className="font-semibold tabular-nums text-ink">{value}</b> {label}</span>
          ))}
        </div>
      </div>
      <div className="mt-2 space-y-3 rounded-2xl bg-paper p-3.5 ring-1 ring-border/60">
        <WeatherBlock state={state} look="warm" />
        <NeedsBlock state={state} look="warm" />
        <BudgetBlock state={state} look="warm" />
      </div>
    </section>
  );
}

function Stop({ state, facts, row, spaced }: { state: PlannerState; facts: DayFacts; row: RowFacts; spaced: boolean }) {
  const day = facts.day.day;
  const active = state.isFocused(day, row);
  const ModeIcon = row.travel ? modeIcon(row.travel.mode) : null;
  const arrival = arrivalLine(row);
  return (
    <li id={row.rowId} data-stop-name={row.stop.name.toLowerCase()} data-stop-day={day} data-stop-index={row.index} className={`group ${spaced ? "pt-2" : ""}`}>
      {row.travel && ModeIcon && (
        <div className="relative ml-[22px] border-l-2 border-dotted py-2 pl-4" style={{ borderColor: `${row.stop.color}66` }} aria-label={row.travel.aria} title={row.travel.title}>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-paper px-2.5 py-1 text-[11px] font-medium text-accent-600 shadow-sm ring-1 ring-border/70">
            <ModeIcon size={12} aria-hidden /><span className="capitalize">{row.travel.mode}</span><span className="text-muted">· {row.travel.distance} · {row.travel.duration}</span>
          </span>
          {row.travel.detail && <p className="mt-1 text-[11px] text-muted">{row.travel.detail}</p>}
          {arrival && <p className={`text-[11px] ${row.travel.conflict ? "font-medium text-rose-700" : "text-muted"}`}>{arrival}</p>}
        </div>
      )}
      <article
        onClick={() => state.focusStop(day, row)}
        className={`rounded-xl bg-paper p-3 transition ${active ? "shadow-card ring-2" : row.focusable ? "cursor-pointer shadow-[0_1px_2px_oklch(0.28_0.05_45/0.06)] ring-1 ring-border/60 hover:shadow-card" : "ring-1 ring-border/60"}`}
        style={active ? { ["--tw-ring-color" as string]: `${row.stop.color}66` } : undefined}
      >
        <div className="flex items-start gap-2.5">
          <Marker row={row} active={active} size={26} look="warm" />
          <div className="min-w-0 flex-1">
            <div className="flex items-start gap-1.5">
              <div className="min-w-0 flex-1">
                {row.time && <p className="text-[11px] font-semibold tabular-nums" style={{ color: row.stop.color }}>{row.time}</p>}
                <StopName state={state} day={day} row={row} className="block text-[14.5px] font-semibold leading-snug" />
              </div>
              <StopActions state={state} day={day} row={row} look="warm" />
            </div>
            <StopMeta row={row} className="mt-0.5" />
            <Signals row={row} look="warm" />
            <Concerns row={row} look="warm" />
            <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
              <Notes row={row} look="warm" />
              <span className="ml-auto"><BookingToggle state={state} day={day} row={row} look="warm" /></span>
            </div>
          </div>
        </div>
      </article>
    </li>
  );
}

function Day({ state, facts }: { state: PlannerState; facts: DayFacts }) {
  const { day } = facts;
  const circuitActive = state.circuitDay === day.day;
  const travel = dayTravelText(state, facts);
  const pill = "inline-flex items-center gap-1.5 rounded-full bg-paper/90 px-2.5 py-1 text-[11px] text-muted shadow-sm";
  return (
    <section id={`lab-it-day-${day.day}`} className="px-3 pt-4">
      <div className={`rounded-2xl p-4 transition ${circuitActive ? "ring-2" : ""}`} style={{ background: `linear-gradient(165deg, ${day.color}1f, ${day.color}08 75%)`, ["--tw-ring-color" as string]: `${day.color}55` }}>
        <button type="button" onClick={() => state.showDay(day.day)} aria-current={circuitActive ? "true" : undefined} title={`Show complete Day ${day.day} circuit on map`} className="block w-full text-left">
          <p className="flex items-center justify-between gap-2 text-[11px] font-semibold uppercase tracking-[0.1em]" style={{ color: day.color }}>
            <span>Day {day.day}</span>
            <span className="normal-case tracking-normal"><DayWeather state={state} facts={facts} /></span>
          </p>
          <h3 className="display mt-1 text-[24px] leading-tight text-ink">{day.title}</h3>
          <p className="text-[11px] font-medium text-muted">{facts.dateLabel}</p>
        </button>
        {day.summary && <p className="mt-2.5 text-[13px] leading-relaxed text-ink/75">{day.summary}</p>}
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          {facts.scheduleText && <span className={pill}><Clock3 size={12} aria-hidden /><span><b className="font-semibold text-ink">Schedule duration:</b> {facts.scheduleText}</span></span>}
          {travel && <span className={pill}><MapPin size={12} aria-hidden /><span><b className="font-semibold text-ink">Day&apos;s travel:</b> {travel}</span></span>}
          <span className={pill}><CheckCircle2 size={12} aria-hidden /><b className="font-semibold text-ink">{facts.planned} planned {facts.planned === 1 ? "stop" : "stops"}</b><span className={facts.remaining > 0 ? "text-amber-700" : "text-emerald-700"}>{facts.confirmed} confirmed · {facts.remaining} to book</span></span>
        </div>
        {day.reachability && <p className="mt-2 text-[11.5px] leading-relaxed text-muted"><strong className="font-semibold text-accent-600">Travel rhythm:</strong> {day.reachability}</p>}
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          <button type="button" onClick={() => state.showDay(day.day)} className={`inline-flex h-7 items-center gap-1.5 rounded-full px-3 text-[11px] font-semibold shadow-sm ${circuitActive ? "text-white" : "bg-paper text-ink hover:bg-paper/80"}`} style={circuitActive ? { backgroundColor: day.color } : undefined}><Route size={12} aria-hidden /> Map this day</button>
          <OpenRoute state={state} facts={facts} className="inline-flex h-7 items-center gap-1.5 rounded-full bg-paper px-3 text-[11px] font-semibold text-muted shadow-sm hover:text-clay" />
        </div>
      </div>
      {facts.rows.length > 0 && (
        <ul className="mt-2 space-y-0 pb-1" aria-label={facts.transition ? `Transition day timeline from ${facts.transition.from} to ${facts.transition.to}` : undefined}>
          {facts.rows.map((row, index) => <Stop key={row.key} state={state} facts={facts} row={row} spaced={index > 0 && !row.travel} />)}
        </ul>
      )}
    </section>
  );
}

export function WarmPane({ state }: { state: PlannerState }) {
  return (
    <div className="h-full overflow-y-auto bg-background pb-6">
      <Snapshot state={state} />
      <div className="px-3 pt-2"><Checks state={state} look="warm" /></div>
      <header className="flex items-center gap-2 px-4 pt-4">
        <h2 className="display text-[18px] leading-none text-ink">Day by day</h2>
        <TripLength state={state} look="warm" />
      </header>
      <EmptyFilters state={state} />
      {state.days.map((facts) => <Day key={facts.day.day} state={state} facts={facts} />)}
    </div>
  );
}
