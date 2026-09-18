import { useState } from "react";
import {
  AlertTriangle, CalendarCheck2, Check, CheckCircle2, ChevronDown, Clock3, ExternalLink, Flame, Loader2, MapPin, Route, Star, Trash2,
} from "lucide-react";
import WeatherIcon from "../../../../src/components/WeatherIcon";
import { formatDistance, formatTemperature } from "../../../../src/lib/displayPreferences";
import { useUnmappedStop } from "../../../../src/lib/unmappedStops";
import { modeIcon } from "../icons";
import type { DayFacts, RowFacts } from "../model";
import { rainText, tripFacts, weatherAria } from "../shared";
import { BudgetBlock, Checks, CostLine, NeedsBlock, ReadinessBar, TripLength, WeatherBlock } from "./common";
import type { PlannerState } from "../state";

/**
 * B · Quiet timeline. Pane body only.
 * A time gutter and one continuous rail replace boxed stop cards; the travel leg
 * becomes the rail segment between two stops, so "how you get there" reads as
 * part of the day rather than as a separate line above each card.
 */

function Snapshot({ state }: { state: PlannerState }) {
  const trip = tripFacts(state);
  const [open, setOpen] = useState(false);
  const highs = trip.weather?.days.map((day) => day.high_c).filter((value): value is number => value != null) ?? [];
  const active = state.allDays;
  return (
    <section
      aria-label="Trip snapshot"
      aria-current={active ? "true" : undefined}
      className={`border-b border-border px-4 pb-3 pt-4 ${active ? "bg-brand/5" : "bg-paper"}`}
      data-lab-change="Trip snapshot"
    >
      <div className="flex items-start gap-3">
        <button type="button" onClick={state.showAllDays} className="min-w-0 flex-1 text-left" title="Show all itinerary days on map">
          <h1 className="display text-[26px] leading-none text-ink">{state.overview.destination}</h1>
          <p className="mt-1.5 text-xs text-muted">{trip.metaLine}</p>
        </button>
        <div className="shrink-0 text-right">
          <span className="inline-flex rounded-full bg-sand px-2 py-0.5 text-[11px] font-semibold capitalize text-muted ring-1 ring-border">{state.overview.status}</span>
        </div>
      </div>
      <p className="mt-2.5 text-[13px] leading-relaxed text-muted">{trip.summary}</p>
      <div className="mt-3 grid grid-cols-[minmax(0,1fr)_auto] items-start gap-3">
        <ReadinessBar state={state} look="timeline" />
        <div className="text-right"><CostLine state={state} look="timeline" /></div>
      </div>
      <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted">
        {trip.counts.map(({ label, value, Icon }) => (
          <span key={label} aria-label={`${value} ${label}`} className="inline-flex items-center gap-1"><Icon size={12} aria-hidden /><b className="font-semibold tabular-nums text-ink">{value}</b> {label}</span>
        ))}
      </p>
      <button type="button" aria-expanded={open} onClick={() => setOpen((value) => !value)} className="mt-3 flex w-full items-center gap-2 rounded-md border border-border px-2.5 py-1.5 text-left text-[11px] text-muted hover:bg-background">
        <span className="font-semibold text-ink">Weather, budget &amp; trip needs</span>
        <span className="min-w-0 flex-1 truncate">
          {highs.length > 0 && `${Math.min(...highs)}–${Math.max(...highs)}°C`}
          {trip.budget && ` · ${trip.budget.pct}% of budget`}
        </span>
        <ChevronDown size={13} className={`shrink-0 transition ${open ? "rotate-180" : ""}`} aria-hidden />
      </button>
      {open && (
        <div className="mt-2 space-y-3 rounded-md bg-background px-2.5 py-2.5">
          <WeatherBlock state={state} look="timeline" />
          <NeedsBlock state={state} look="timeline" />
          <BudgetBlock state={state} look="timeline" />
        </div>
      )}
    </section>
  );
}

function StopRow({ state, facts, row, last }: { state: PlannerState; facts: DayFacts; row: RowFacts; last: boolean }) {
  const [notesOpen, setNotesOpen] = useState(false);
  const unmapped = useUnmappedStop(row.stop.name);
  const active = state.isFocused(facts.day.day, row);
  const color = row.stop.color;
  const ModeIcon = row.travel ? modeIcon(row.travel.mode) : Route;
  return (
    <li id={row.rowId} data-stop-name={row.stop.name.toLowerCase()} data-stop-day={facts.day.day} data-stop-index={row.index} className="group">
      {row.travel && (
        <div className="grid grid-cols-[44px_22px_minmax(0,1fr)] gap-x-2" aria-label={row.travel.aria} title={row.travel.title}>
          <span />
          <span className="relative flex justify-center">
            <span className="absolute inset-y-0 left-1/2 -translate-x-1/2 border-l border-dashed" style={{ borderColor: `${color}80` }} aria-hidden />
            <span className="relative mt-1.5 grid h-4 w-4 place-items-center rounded-full bg-paper text-accent ring-1 ring-border"><ModeIcon size={10} aria-hidden /></span>
          </span>
          <div className="py-1.5 text-[11px] leading-snug">
            <p className="font-medium text-accent-600"><span className="capitalize">{row.travel.mode}</span> · {row.travel.distance} · {row.travel.duration}{row.travel.detail && <span className="font-normal text-muted"> — {row.travel.detail}</span>}</p>
            {row.travel.arrival && (
              <p className={row.travel.conflict ? "text-rose-700" : "text-muted"}>
                {row.travel.arrival}{row.travel.buffer ? ` · ${row.travel.buffer}` : row.travel.conflict ? ` · ${row.travel.conflict}` : ""}
              </p>
            )}
          </div>
        </div>
      )}
      <div
        onClick={() => state.focusStop(facts.day.day, row)}
        className={`grid grid-cols-[44px_22px_minmax(0,1fr)] gap-x-2 rounded-md py-1.5 transition ${active ? "bg-clay-soft/40" : row.focusable ? "cursor-pointer hover:bg-background" : ""}`}
      >
        <div className="pt-0.5 text-right text-[11px] leading-tight tabular-nums">
          {row.stop.time && <p className="font-semibold text-ink">{row.stop.time}</p>}
          {row.stop.time_estimated && <p className="text-[10px] text-muted">est.</p>}
        </div>
        <div className="relative flex justify-center">
          {!last && <span className="absolute bottom-[-6px] top-6 left-1/2 w-px -translate-x-1/2" style={{ backgroundColor: `${color}55` }} aria-hidden />}
          {row.mapLabel ? (
            <span
              aria-label={row.mapLabel.startsWith("H") ? "Hotel map marker" : `Map stop ${row.mapLabel}`}
              aria-current={active ? "location" : undefined}
              className="relative grid h-[22px] w-[22px] place-items-center rounded-full border-[1.5px] text-[10px] font-semibold tabular-nums"
              style={{ borderColor: color, color: active ? "white" : color, backgroundColor: active ? color : "white" }}
            >
              {row.mapLabel}
            </span>
          ) : (
            <span aria-hidden className="relative grid h-[22px] w-[22px] place-items-center rounded-full border border-border bg-sand text-[10px]">{row.kindGlyph}</span>
          )}
        </div>
        <div className="min-w-0 pr-2">
          <div className="flex items-start gap-1.5">
            <button
              type="button"
              disabled={!row.focusable}
              onClick={(event) => { event.stopPropagation(); state.focusStop(facts.day.day, row); }}
              className={`min-w-0 flex-1 text-left text-[13.5px] font-semibold leading-snug ${row.focusable ? "text-ink hover:text-brand" : "cursor-default text-ink"}`}
              title={row.focusTitle}
            >
              {row.name}
            </button>
            <div className="flex shrink-0 items-center gap-0.5 opacity-0 transition focus-within:opacity-100 group-hover:opacity-100">
              <button type="button" onClick={(event) => { event.stopPropagation(); state.showOnMap(facts.day.day, row); }} aria-label={`Show ${row.stop.name} on the map`} title={row.routeFocusable ? "Show complete route" : "Show on map"} className="grid h-6 w-6 place-items-center rounded text-muted hover:bg-sand hover:text-brand"><MapPin size={13} aria-hidden /></button>
              {row.removable && (
                <button type="button" disabled={state.isRemoving(facts.day.day, row)} onClick={(event) => { event.stopPropagation(); void state.removeStop(facts.day.day, row); }} aria-label={`Remove ${row.stop.name} from itinerary`} title="Remove from itinerary" className="grid h-6 w-6 place-items-center rounded text-muted hover:bg-sand hover:text-rose-600">
                  {state.isRemoving(facts.day.day, row) ? <Loader2 size={12} className="animate-spin" aria-hidden /> : <Trash2 size={13} aria-hidden />}
                </button>
              )}
            </div>
            {row.bookable && (
              <button
                type="button"
                aria-pressed={row.stop.booked}
                aria-label={`${row.stop.name}: ${row.stop.booked ? "Mark as needing booking" : "Mark confirmed"}`}
                onClick={(event) => { event.stopPropagation(); state.toggleBooked(facts.day.day, row); }}
                className={`inline-flex h-5 shrink-0 items-center gap-1 rounded-full px-1.5 text-[10px] font-semibold transition ${row.stop.booked ? "text-emerald-700 hover:bg-emerald-50" : "bg-amber-50 text-amber-800 ring-1 ring-amber-200 hover:ring-brand/30"}`}
              >
                {row.stop.booked ? <Check size={11} aria-hidden /> : <CalendarCheck2 size={11} aria-hidden />}
                {row.stop.booked ? "Confirmed" : "Needs booking"}
              </button>
            )}
          </div>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-1.5 text-[11px] text-muted">
            <span>{row.timingLabel}</span><span aria-hidden>·</span><span>{row.kindLabel}</span>
            {unmapped && <><span aria-hidden>·</span><span className={`font-semibold ${unmapped.tier === "anchor" ? "text-amber-600" : "text-muted"}`} title={unmapped.candidate ? `The map found “${unmapped.candidate.name}” instead. Confirm it on the map to pin this stop.` : "The map could not place this stop."}>Not on map</span></>}
            {row.durationText && <><span aria-hidden>·</span><span>{row.durationText}</span></>}
            {row.departureText && <><span aria-hidden>·</span><span className="tabular-nums">{row.departureText}</span></>}
          </p>
          {(row.rating || row.mustVisit || row.cost || row.hours) && (
            <p className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-0.5 text-[11px]">
              {row.rating && <span aria-label={row.rating.aria} className="inline-flex items-center gap-1 font-medium text-ink"><Star size={11} className="fill-amber-400 text-amber-400" aria-hidden />{row.rating.value}{row.rating.reviews && <span className="font-normal text-muted">({row.rating.reviews})</span>}</span>}
              {row.mustVisit && <span title={row.mustVisit.title} className="inline-flex items-center gap-1 font-medium text-brand"><Flame size={11} aria-hidden />Must-visit score {row.mustVisit.score}/100</span>}
              {row.cost && <span className="text-muted">{row.cost}</span>}
              {row.hours && <span className="inline-flex items-center gap-1 text-muted"><Clock3 size={11} aria-hidden />{row.hours}</span>}
            </p>
          )}
          {row.concerns.map((text) => <p key={text} className="mt-1 flex gap-1.5 text-xs font-medium text-rose-700"><AlertTriangle size={12} className="mt-0.5 shrink-0" aria-hidden />{text}</p>)}
          {row.hasNotes && (
            <>
              <button type="button" aria-expanded={notesOpen} onClick={(event) => { event.stopPropagation(); setNotesOpen((value) => !value); }} className="mt-1 inline-flex items-center gap-1 text-[11px] font-semibold text-muted hover:text-ink">
                {notesOpen ? "Hide notes" : "Notes & tips"}<ChevronDown size={12} className={`transition ${notesOpen ? "rotate-180" : ""}`} aria-hidden />
              </button>
              {notesOpen && <div className="mt-1 space-y-0.5 border-l-2 border-border pl-2.5">{[...row.notes, ...row.insights].map((text) => <p key={text} className="text-xs text-muted">{text}</p>)}</div>}
            </>
          )}
        </div>
      </div>
    </li>
  );
}

function Day({ state, facts }: { state: PlannerState; facts: DayFacts }) {
  const { day } = facts;
  const circuitActive = state.circuitDay === day.day;
  return (
    <section id={`lab-it-day-${day.day}`} className="border-b border-border last:border-b-0">
      <div className={`sticky top-0 z-10 flex items-center gap-2.5 border-b border-border/60 px-4 py-2 backdrop-blur ${circuitActive ? "bg-sand/95" : "bg-paper/95"}`}>
        <button type="button" onClick={() => state.showDay(day.day)} aria-current={circuitActive ? "true" : undefined} title={`Show complete Day ${day.day} circuit on map`} className="flex min-w-0 flex-1 items-center gap-2.5 text-left">
          <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full text-xs font-bold text-white" style={{ backgroundColor: day.color }} aria-hidden>{day.day}</span>
          <span className="min-w-0">
            <span className="block truncate text-[15px] font-semibold leading-tight text-ink">{day.title}</span>
            <span className="block text-[11px] font-medium text-brand">{facts.dateLabel}</span>
          </span>
        </button>
        {day.weather && (
          <span className="flex shrink-0 flex-col items-end text-[11px] text-muted" aria-label={weatherAria(day.weather)} title={day.weather.precip_probability_pct != null ? `${day.weather.precip_probability_pct}% chance of precipitation` : day.weather.summary}>
            <span className="inline-flex items-center gap-1 font-medium text-ink"><span className="text-accent"><WeatherIcon condition={day.weather.condition} size={14} /></span>{day.weather.high_c != null && day.weather.low_c != null && <span className="tabular-nums">{formatTemperature(day.weather.high_c, state.region)} / {formatTemperature(day.weather.low_c, state.region)}</span>}</span>
            <span>{day.weather.summary}{rainText(day.weather.precip_probability_pct) && <span className="text-sky-700"> · {rainText(day.weather.precip_probability_pct)}</span>}</span>
          </span>
        )}
      </div>
      <div className="px-4 pb-1 pt-2.5">
        {day.summary && <p className="text-[13px] leading-relaxed text-muted">{day.summary}</p>}
        <dl className="mt-2 grid grid-cols-[auto_minmax(0,1fr)] gap-x-2 gap-y-1 text-[11px]">
          {facts.scheduleText && <><dt className="inline-flex items-center gap-1 font-semibold text-ink"><Clock3 size={12} className="text-muted" aria-hidden />Schedule duration:</dt><dd className="text-muted">{facts.scheduleText}</dd></>}
          {day.route && <><dt className="inline-flex items-center gap-1 font-semibold text-ink"><MapPin size={12} className="text-muted" aria-hidden />Day&apos;s travel:</dt><dd className="text-muted">{day.route.duration_display} · {formatDistance(day.route.distance_km, state.region)} · {day.route.mode}</dd></>}
          <dt className="inline-flex items-center gap-1 font-semibold text-ink"><CheckCircle2 size={12} className="text-muted" aria-hidden />{facts.planned} planned {facts.planned === 1 ? "stop" : "stops"}</dt>
          <dd className={facts.remaining > 0 ? "text-amber-700" : "text-emerald-700"}>{facts.confirmed} confirmed · {facts.remaining} to book</dd>
        </dl>
        {day.reachability && <p className="mt-1.5 text-[11px] leading-relaxed text-muted"><strong className="font-semibold text-accent">Travel rhythm:</strong> {day.reachability}</p>}
        <div className="mt-2 flex items-center gap-1">
          <button type="button" onClick={() => state.showDay(day.day)} className={`inline-flex h-7 items-center gap-1.5 rounded-md px-2 text-[11px] font-semibold ${circuitActive ? "bg-sand text-ink" : "text-muted hover:bg-sand hover:text-ink"}`}><MapPin size={12} aria-hidden /> Day on map</button>
          {day.google_maps_url && <a href={day.google_maps_url} target="_blank" rel="noreferrer" onClick={(event) => { event.preventDefault(); state.openRoute(day.day); }} className="inline-flex h-7 items-center gap-1.5 rounded-md px-2 text-[11px] font-semibold text-muted hover:bg-sand hover:text-clay" title={`Open Day ${day.day} route in Google Maps`}><Route size={12} aria-hidden /> Open route <ExternalLink size={11} aria-hidden /></a>}
        </div>
      </div>
      {facts.rows.length > 0 && (
        <ul className="px-2 pb-3 pt-1" aria-label={facts.transition ? `Transition day timeline from ${facts.transition.from} to ${facts.transition.to}` : undefined}>
          {facts.rows.map((row, position) => <StopRow key={row.key} state={state} facts={facts} row={row} last={position === facts.rows.length - 1} />)}
        </ul>
      )}
    </section>
  );
}

export function TimelinePane({ state }: { state: PlannerState }) {
  return (
    <div className="h-full overflow-y-auto bg-paper">
      <Snapshot state={state} />
      <div className="border-b border-border px-4 py-2"><Checks state={state} look="timeline" /></div>
      <header className="flex items-center gap-2 px-4 pb-1 pt-3">
        <h2 className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted">Day by day</h2>
        <TripLength state={state} look="timeline" />
      </header>
      {state.days.length === 0 && <p className="py-8 text-center text-sm text-muted">No itinerary items match these filters.</p>}
      {state.days.map((facts) => <Day key={facts.day.day} state={state} facts={facts} />)}
    </div>
  );
}
