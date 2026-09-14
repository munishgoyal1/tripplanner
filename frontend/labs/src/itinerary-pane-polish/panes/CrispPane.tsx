import { useState } from "react";
import { MapPin } from "lucide-react";
import { modeIcon } from "../icons";
import type { DayFacts, RowFacts } from "../model";
import { tripFacts } from "../shared";
import type { PlannerState } from "../state";
import {
  arrivalLine, BookingToggle, BudgetBlock, Checks, Concerns, CostLine, DayWeather, dayTravelText, EmptyFilters, Marker,
  NeedsBlock, Notes, OpenRoute, ReadinessBar, Signals, StopActions, StopMeta, StopName, TripLength, WeatherBlock,
} from "./common";

/**
 * A · Crisp workspace harmony. Pane body plus the workspace finish in Workspace.tsx.
 * Hairline list rows, line icons, bordered tags, a tabbed snapshot and a sticky
 * day header; decoration is removed rather than added.
 */

type Tab = "overview" | "weather" | "budget";

function Snapshot({ state }: { state: PlannerState }) {
  const trip = tripFacts(state);
  const [tab, setTab] = useState<Tab>("overview");
  return (
    <section aria-label="Trip snapshot" aria-current={state.allDays ? "true" : undefined} className={`border-b border-border px-3.5 pb-3 pt-3.5 ${state.allDays ? "bg-brand/5" : ""}`} data-lab-change="Trip snapshot">
      <div className="flex items-start gap-3">
        <button type="button" onClick={state.showAllDays} className="min-w-0 flex-1 text-left" title="Show all itinerary days on map">
          <span className="inline-flex rounded border border-border px-1.5 py-[1px] text-[9.5px] font-semibold uppercase tracking-[0.06em] text-muted">{state.overview.status}</span>
          <h1 className="display mt-1 text-[24px] leading-none text-ink">{state.overview.destination}</h1>
          <span className="mt-1.5 block text-[11.5px] text-muted">{trip.metaLine}</span>
        </button>
        <div className="shrink-0 text-right"><CostLine state={state} look="crisp" /></div>
      </div>
      <div role="tablist" aria-label="Trip snapshot sections" className="mt-3 grid grid-cols-3 gap-0.5 rounded-md bg-sand p-0.5">
        {([["overview", "Overview"], ["weather", "Weather"], ["budget", "Budget"]] as const).map(([id, label]) => (
          <button key={id} type="button" role="tab" aria-selected={tab === id} onClick={() => setTab(id)} className={`h-7 rounded text-[11.5px] font-semibold transition ${tab === id ? "bg-paper text-ink shadow-sm ring-1 ring-border" : "text-muted hover:text-ink"}`}>
            {label}
            {id === "budget" && trip.budget && <span className="ml-1 font-normal tabular-nums text-muted">{trip.budget.pct}%</span>}
          </button>
        ))}
      </div>
      <div className="mt-3 space-y-3" role="tabpanel">
        {tab === "overview" && (
          <>
            <p className="text-[12.5px] leading-relaxed text-muted">{trip.summary}</p>
            <ReadinessBar state={state} look="crisp" />
            <div className="grid grid-cols-4 divide-x divide-border rounded-md border border-border">
              {trip.counts.map(({ label, value, Icon }) => (
                <div key={label} aria-label={`${value} ${label}`} className="flex flex-col items-center gap-0.5 py-1.5">
                  <span className="inline-flex items-center gap-1 text-[13px] font-semibold tabular-nums text-ink"><Icon size={12} className="text-muted" aria-hidden />{value}</span>
                  <span className="text-[10px] text-muted">{label}</span>
                </div>
              ))}
            </div>
            <NeedsBlock state={state} look="crisp" title={false} />
          </>
        )}
        {tab === "weather" && <WeatherBlock state={state} look="crisp" />}
        {tab === "budget" && <BudgetBlock state={state} look="crisp" />}
      </div>
    </section>
  );
}

function Stop({ state, facts, row }: { state: PlannerState; facts: DayFacts; row: RowFacts }) {
  const day = facts.day.day;
  const active = state.isFocused(day, row);
  const ModeIcon = row.travel ? modeIcon(row.travel.mode) : null;
  const arrival = arrivalLine(row);
  return (
    <li id={row.rowId} data-stop-name={row.stop.name.toLowerCase()} data-stop-day={day} data-stop-index={row.index} className="group">
      {row.travel && ModeIcon && (
        <div className="flex gap-2.5 pl-3.5 pr-3" aria-label={row.travel.aria} title={row.travel.title}>
          <span className="flex w-[22px] shrink-0 justify-center"><span className="w-px bg-border" aria-hidden /></span>
          <div className="flex min-w-0 gap-1.5 py-1 text-[11px] leading-snug">
            <ModeIcon size={12} className="mt-[1px] shrink-0 text-muted" aria-hidden />
            <div className="min-w-0">
              <p className="text-ink"><span className="font-medium capitalize">{row.travel.mode}</span> <span className="tabular-nums text-muted">· {row.travel.distance} · {row.travel.duration}</span>{row.travel.detail && <span className="text-muted"> — {row.travel.detail}</span>}</p>
              {arrival && <p className={`tabular-nums ${row.travel.conflict ? "font-medium text-rose-700" : "text-muted"}`}>{arrival}</p>}
            </div>
          </div>
        </div>
      )}
      <div
        onClick={() => state.focusStop(day, row)}
        className={`relative flex gap-2.5 py-2.5 pl-3.5 pr-3 transition ${active ? "bg-sand" : row.focusable ? "cursor-pointer hover:bg-sand/60" : ""}`}
        style={active ? { boxShadow: `inset 3px 0 0 ${row.stop.color}` } : undefined}
      >
        <Marker row={row} active={active} look="crisp" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <p className="min-w-0 flex-1 truncate text-[11px] tabular-nums text-muted">
              {[row.time, row.durationText, row.departureText].filter(Boolean).map((part, index) => (
                <span key={part}>{index > 0 && " · "}{index === 0 && row.time ? <b className="font-semibold text-ink">{part}</b> : part}</span>
              ))}
            </p>
            <StopActions state={state} day={day} row={row} look="crisp" />
            <BookingToggle state={state} day={day} row={row} look="crisp" />
          </div>
          <StopName state={state} day={day} row={row} className="mt-0.5 block text-[13.5px] font-semibold leading-snug tracking-[-0.005em]" />
          <StopMeta row={row} className="mt-0.5" withDuration={false} />
          <Signals row={row} look="crisp" />
          <Concerns row={row} look="crisp" />
          <Notes row={row} look="crisp" />
        </div>
      </div>
    </li>
  );
}

function Day({ state, facts }: { state: PlannerState; facts: DayFacts }) {
  const { day } = facts;
  const circuitActive = state.circuitDay === day.day;
  const travel = dayTravelText(state, facts);
  return (
    <section id={`lab-it-day-${day.day}`} className="border-b border-border">
      <div className={`sticky top-0 z-10 flex items-center gap-2.5 border-b border-border px-3.5 py-2 ${circuitActive ? "bg-sand" : "bg-paper/95 backdrop-blur"}`}>
        <button type="button" onClick={() => state.showDay(day.day)} aria-current={circuitActive ? "true" : undefined} title={`Show complete Day ${day.day} circuit on map`} className="flex min-w-0 flex-1 items-center gap-2.5 text-left">
          <span className="grid h-6 w-6 shrink-0 place-items-center rounded text-[11px] font-bold text-white" style={{ backgroundColor: day.color }} aria-hidden>{day.day}</span>
          <span className="min-w-0">
            <span className="block truncate text-[14px] font-semibold leading-tight tracking-[-0.01em] text-ink">{day.title}</span>
            <span className="block text-[10.5px] text-muted">{facts.dateLabel}</span>
          </span>
        </button>
        <DayWeather state={state} facts={facts} compact />
      </div>
      <div className="px-3.5 pb-2 pt-2.5">
        {day.weather && <p className="mb-1 text-[11px] font-medium text-muted">Forecast: {day.weather.summary}</p>}
        {day.summary && <p className="text-[12.5px] leading-relaxed text-muted">{day.summary}</p>}
        <dl className="mt-2 grid grid-cols-2 overflow-hidden rounded-md border border-border text-[11px]">
          <div className="border-b border-r border-border px-2 py-1.5"><dt className="text-[10px] text-muted">Schedule duration</dt><dd className="font-medium tabular-nums text-ink">{facts.scheduleText ?? "—"}</dd></div>
          <div className="border-b border-border px-2 py-1.5"><dt className="text-[10px] text-muted">Day&apos;s travel</dt><dd className="font-medium tabular-nums text-ink">{travel ?? "—"}</dd></div>
          <div className="border-r border-border px-2 py-1.5"><dt className="text-[10px] text-muted">Stops</dt><dd className="font-medium text-ink">{facts.planned} planned {facts.planned === 1 ? "stop" : "stops"}</dd></div>
          <div className="px-2 py-1.5"><dt className="text-[10px] text-muted">Bookings</dt><dd className={`font-medium ${facts.remaining > 0 ? "text-amber-700" : "text-emerald-700"}`}>{facts.confirmed} confirmed · {facts.remaining} to book</dd></div>
        </dl>
        {day.reachability && <p className="mt-2 text-[11px] leading-relaxed text-muted"><strong className="font-semibold text-ink">Travel rhythm:</strong> {day.reachability}</p>}
        <div className="mt-1.5 flex items-center gap-1">
          <button type="button" onClick={() => state.showDay(day.day)} className={`inline-flex h-7 items-center gap-1.5 rounded px-1.5 text-[11px] font-semibold ${circuitActive ? "bg-ink text-white" : "text-muted hover:bg-sand hover:text-ink"}`}><MapPin size={12} aria-hidden /> Day on map</button>
          <OpenRoute state={state} facts={facts} className="inline-flex h-7 items-center gap-1.5 rounded px-1.5 text-[11px] font-semibold text-muted hover:bg-sand hover:text-ink" />
        </div>
      </div>
      {facts.rows.length > 0 && (
        <ul className="divide-y divide-border/70 border-t border-border/70 pb-1" aria-label={facts.transition ? `Transition day timeline from ${facts.transition.from} to ${facts.transition.to}` : undefined}>
          {facts.rows.map((row) => <Stop key={row.key} state={state} facts={facts} row={row} />)}
        </ul>
      )}
    </section>
  );
}

export function CrispPane({ state }: { state: PlannerState }) {
  return (
    <div className="h-full overflow-y-auto bg-paper">
      <Snapshot state={state} />
      <div className="border-b border-border px-3.5 py-2"><Checks state={state} look="crisp" /></div>
      <header className="flex items-center gap-2 border-b border-border px-3.5 py-1">
        <h2 className="text-[11px] font-semibold text-muted">Day by day</h2>
        <TripLength state={state} look="crisp" />
      </header>
      <EmptyFilters state={state} />
      {state.days.map((facts) => <Day key={facts.day.day} state={state} facts={facts} />)}
    </div>
  );
}
