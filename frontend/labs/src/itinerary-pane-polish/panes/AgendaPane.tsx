import { useState, type ReactNode } from "react";
import { ChevronDown, MapPin } from "lucide-react";
import { modeIcon } from "../icons";
import type { DayFacts, RowFacts } from "../model";
import { tripFacts } from "../shared";
import type { PlannerState } from "../state";
import {
  arrivalLine, BookingToggle, BudgetBlock, Checks, Concerns, CostLine, DayWeather, dayTravelText, EmptyFilters, Marker,
  NeedsBlock, Notes, OpenRoute, ReadinessBar, Signals, StopActions, StopMeta, StopName, TripLength, WeatherBlock,
} from "./common";

/**
 * D · Precise agenda. Pane body only.
 * Ledger rows — time block, content, status — with a metric table in each day
 * header and slim travel rows that carry a signed buffer or conflict badge.
 */

function Disclosure({ label, value, children }: { label: string; value: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-t border-border">
      <button type="button" aria-expanded={open} onClick={() => setOpen((current) => !current)} className="flex w-full items-center gap-2 py-1.5 text-left text-[11px]">
        <span className="w-20 shrink-0 font-semibold text-ink">{label}</span>
        <span className="min-w-0 flex-1 truncate text-muted">{value}</span>
        <ChevronDown size={13} className={`shrink-0 text-muted transition ${open ? "rotate-180" : ""}`} aria-hidden />
      </button>
      {open && <div className="pb-2.5">{children}</div>}
    </div>
  );
}

function Snapshot({ state }: { state: PlannerState }) {
  const trip = tripFacts(state);
  const highs = trip.weather?.days.map((day) => day.high_c).filter((value): value is number => value != null) ?? [];
  const rainy = trip.weather?.days.filter((day) => (day.precip_probability_pct ?? 0) >= 30).length ?? 0;
  return (
    <section aria-label="Trip snapshot" aria-current={state.allDays ? "true" : undefined} className={`border-b border-border px-4 pb-1 pt-3.5 ${state.allDays ? "bg-brand/5" : ""}`} data-lab-change="Trip snapshot">
      <div className="flex items-start justify-between gap-3">
        <button type="button" onClick={state.showAllDays} className="min-w-0 text-left" title="Show all itinerary days on map">
          <h1 className="display text-[23px] leading-none text-ink">{state.overview.destination}</h1>
          <p className="mt-1 text-[11.5px] text-muted">{trip.metaLine}</p>
        </button>
        <span className="shrink-0 rounded bg-sand px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.06em] text-muted">{state.overview.status}</span>
      </div>
      <p className="mt-2 text-[12.5px] leading-relaxed text-muted">{trip.summary}</p>
      <div className="mt-3 grid grid-cols-4 divide-x divide-border border-y border-border">
        {trip.counts.map(({ label, value }) => (
          <div key={label} aria-label={`${value} ${label}`} className="px-2 py-1.5">
            <p className="text-[9.5px] font-semibold uppercase tracking-[0.08em] text-muted">{label}</p>
            <p className="text-[15px] font-semibold tabular-nums text-ink">{value}</p>
          </div>
        ))}
      </div>
      <div className="mt-2.5 grid grid-cols-[minmax(0,1fr)_auto] items-start gap-4 pb-2.5">
        <ReadinessBar state={state} look="agenda" />
        <div className="text-right"><CostLine state={state} look="agenda" /></div>
      </div>
      <Disclosure label="Weather" value={`${highs.length ? `${Math.min(...highs)}–${Math.max(...highs)}°C` : "Forecast unavailable"}${rainy ? ` · ${rainy} rainy ${rainy === 1 ? "day" : "days"}` : ""} · packing advice`}>
        <WeatherBlock state={state} look="agenda" />
      </Disclosure>
      <Disclosure label="Trip needs" value={[...trip.familyPills, ...(state.overview.constraints ?? [])].join(" · ")}>
        <NeedsBlock state={state} look="agenda" title={false} />
      </Disclosure>
      {trip.budget && (
        <Disclosure label="Budget" value={`${trip.budget.pct}% used · ${trip.budget.remaining} ${trip.budget.remainingWord}`}>
          <BudgetBlock state={state} look="agenda" title={false} />
        </Disclosure>
      )}
    </section>
  );
}

function signedBadge(row: RowFacts): { text: string; tone: string } | null {
  const stop = row.stop;
  if (!row.travel?.arrival) return null;
  if (row.travel.buffer && stop.buffer_before_display) return { text: `+${stop.buffer_before_display}`, tone: (stop.buffer_before_min ?? 0) < 5 ? "bg-amber-50 text-amber-800" : "bg-emerald-50 text-emerald-700" };
  if (row.travel.conflict && stop.timing_conflict_display) return { text: `−${stop.timing_conflict_display}`, tone: "bg-rose-50 text-rose-700" };
  return null;
}

function Stop({ state, facts, row }: { state: PlannerState; facts: DayFacts; row: RowFacts }) {
  const day = facts.day.day;
  const active = state.isFocused(day, row);
  const ModeIcon = row.travel ? modeIcon(row.travel.mode) : null;
  const arrival = arrivalLine(row);
  const badge = signedBadge(row);
  return (
    <li id={row.rowId} data-stop-name={row.stop.name.toLowerCase()} data-stop-day={day} data-stop-index={row.index} className="group">
      {row.travel && ModeIcon && (
        <div className="grid grid-cols-[52px_minmax(0,1fr)_auto] items-start gap-x-2.5 border-b border-dashed border-border/80 bg-background/60 px-4 py-1" aria-label={row.travel.aria} title={row.travel.title}>
          <span className="flex justify-end pt-0.5 text-muted"><ModeIcon size={12} aria-hidden /></span>
          <div className="text-[11px] leading-snug">
            <p className="text-ink"><span className="capitalize">{row.travel.mode}</span> <span className="tabular-nums text-muted">· {row.travel.distance} · {row.travel.duration}</span>{row.travel.detail && <span className="text-muted"> — {row.travel.detail}</span>}</p>
            {arrival && <p className={`tabular-nums ${row.travel.conflict ? "text-rose-700" : "text-muted"}`}>{arrival}</p>}
          </div>
          {badge ? <span className={`mt-0.5 rounded px-1.5 py-[1px] text-[10px] font-semibold tabular-nums ${badge.tone}`}>{badge.text}</span> : <span />}
        </div>
      )}
      <div
        onClick={() => state.focusStop(day, row)}
        className={`grid grid-cols-[52px_minmax(0,1fr)_auto] items-start gap-x-2.5 border-b border-border px-4 py-2 transition ${active ? "bg-clay-soft/35" : row.focusable ? "cursor-pointer hover:bg-background" : ""}`}
      >
        <div className="text-right tabular-nums leading-tight">
          {row.stop.time && <p className="text-[12.5px] font-semibold text-ink">{row.stop.time}</p>}
          {row.stop.time_estimated && <p className="text-[10px] text-muted">est.</p>}
          {row.stop.departure_time && <p className="mt-0.5 text-[10.5px] text-muted">{row.stop.departure_time}</p>}
        </div>
        <div className="min-w-0">
          <div className="flex items-start gap-1.5">
            <span className="mt-[1px]"><Marker row={row} active={active} size={18} look="agenda" /></span>
            <StopName state={state} day={day} row={row} className="flex-1 text-[13px] font-semibold leading-snug" />
          </div>
          <StopMeta row={row} className="mt-0.5" />
          <Signals row={row} look="agenda" />
          <Concerns row={row} look="agenda" />
          <Notes row={row} look="agenda" />
        </div>
        <div className="flex flex-col items-end gap-1">
          <BookingToggle state={state} day={day} row={row} look="agenda" />
          <StopActions state={state} day={day} row={row} look="agenda" />
        </div>
      </div>
    </li>
  );
}

function Day({ state, facts }: { state: PlannerState; facts: DayFacts }) {
  const { day } = facts;
  const circuitActive = state.circuitDay === day.day;
  const route = day.route;
  const cell = "px-2 py-1.5";
  const label = "text-[9.5px] font-semibold uppercase tracking-[0.08em] text-muted";
  return (
    <section id={`lab-it-day-${day.day}`}>
      <div className={`sticky top-0 z-10 flex items-center gap-2 border-b border-border py-2 pl-3 pr-4 ${circuitActive ? "bg-sand" : "bg-paper/95 backdrop-blur"}`} style={{ boxShadow: `inset 3px 0 0 ${day.color}` }}>
        <button type="button" onClick={() => state.showDay(day.day)} aria-current={circuitActive ? "true" : undefined} title={`Show complete Day ${day.day} circuit on map`} className="min-w-0 flex-1 pl-1 text-left">
          <span className="block text-[9.5px] font-semibold uppercase tracking-[0.1em]" style={{ color: day.color }}>Day {day.day} · {facts.dateLabel}</span>
          <span className="block truncate text-[14px] font-semibold leading-tight text-ink">{day.title}</span>
        </button>
        <DayWeather state={state} facts={facts} compact />
      </div>
      <div className="px-4 pt-2">
        {day.weather && <p className="text-[11px] font-medium text-muted">Forecast: {day.weather.summary}</p>}
        {day.summary && <p className="mt-0.5 text-[12.5px] leading-relaxed text-muted">{day.summary}</p>}
        <dl className="mt-2 grid grid-cols-4 divide-x divide-border border-y border-border text-[11px] leading-tight">
          <div className={cell}><dt className={label}>Schedule</dt><dd className="mt-0.5 font-semibold tabular-nums text-ink">{day.schedule?.duration_display ?? "—"}</dd>{day.schedule?.start && day.schedule.end && <dd className="tabular-nums text-muted">{day.schedule.start}–{day.schedule.end}{day.schedule.estimated ? " est." : ""}</dd>}</div>
          <div className={cell}><dt className={label}>Travel</dt><dd className="mt-0.5 font-semibold tabular-nums text-ink">{route?.duration_display ?? "—"}</dd>{route && <dd className="text-muted">{dayTravelText(state, facts)?.split(" · ").slice(1).join(" · ")}</dd>}</div>
          <div className={cell}><dt className={label}>Stops</dt><dd className="mt-0.5 font-semibold tabular-nums text-ink">{facts.planned}</dd><dd className="text-muted">planned</dd></div>
          <div className={cell}><dt className={label}>Booked</dt><dd className="mt-0.5 font-semibold tabular-nums text-emerald-700">{facts.confirmed} confirmed</dd><dd className={facts.remaining > 0 ? "text-amber-700" : "text-muted"}>{facts.remaining} to book</dd></div>
        </dl>
        {day.reachability && <p className="mt-1.5 text-[11px] leading-relaxed text-muted"><strong className="font-semibold text-ink">Travel rhythm:</strong> {day.reachability}</p>}
        <div className="flex items-center justify-end gap-1 py-1">
          <button type="button" onClick={() => state.showDay(day.day)} className={`inline-flex h-7 items-center gap-1.5 rounded px-1.5 text-[11px] font-semibold ${circuitActive ? "bg-sand text-ink" : "text-muted hover:bg-sand hover:text-ink"}`}><MapPin size={12} aria-hidden /> Day on map</button>
          <OpenRoute state={state} facts={facts} className="inline-flex h-7 items-center gap-1.5 rounded px-1.5 text-[11px] font-semibold text-muted hover:bg-sand hover:text-clay" />
        </div>
      </div>
      {facts.rows.length > 0 && (
        <ul className="border-t border-border" aria-label={facts.transition ? `Transition day timeline from ${facts.transition.from} to ${facts.transition.to}` : undefined}>
          {facts.rows.map((row) => <Stop key={row.key} state={state} facts={facts} row={row} />)}
        </ul>
      )}
    </section>
  );
}

export function AgendaPane({ state }: { state: PlannerState }) {
  return (
    <div className="h-full overflow-y-auto bg-paper">
      <Snapshot state={state} />
      <div className="border-b border-border px-4 py-2"><Checks state={state} look="agenda" /></div>
      <header className="flex items-center gap-2 border-b border-border bg-background px-4 py-1">
        <h2 className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted">Day by day</h2>
        <TripLength state={state} look="agenda" />
      </header>
      <EmptyFilters state={state} />
      {state.days.map((facts) => <Day key={facts.day.day} state={state} facts={facts} />)}
    </div>
  );
}
