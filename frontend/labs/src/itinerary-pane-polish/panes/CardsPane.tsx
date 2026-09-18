import { useEffect, useState, type ReactNode } from "react";
import { ChevronDown, Clock3, Flame, MapPin, Star, Ticket } from "lucide-react";
import { modeIcon } from "../icons";
import type { DayFacts, RowFacts } from "../model";
import { tripFacts } from "../shared";
import type { PlannerState } from "../state";
import {
  arrivalLine, BookingToggle, BudgetBlock, Checks, Concerns, CostLine, DayWeather, dayTravelText, EmptyFilters, Marker,
  NeedsBlock, Notes, OpenRoute, ReadinessBar, StopActions, StopMeta, StopName, TripLength, WeatherBlock,
} from "./common";

/**
 * E · Clean stop cards. Pane body only.
 * Today's card model with structure: labelled fact grids, a must-visit meter,
 * travel connector pills, and days that fold to their header facts.
 */

function Snapshot({ state }: { state: PlannerState }) {
  const trip = tripFacts(state);
  return (
    <section aria-label="Trip snapshot" aria-current={state.allDays ? "true" : undefined} className="space-y-2 px-3 pt-3" data-lab-change="Trip snapshot">
      <div className={`rounded-xl border bg-paper p-3.5 shadow-sm ${state.allDays ? "border-brand/40 ring-2 ring-brand/15" : "border-border"}`}>
        <div className="flex items-start justify-between gap-3">
          <button type="button" onClick={state.showAllDays} className="min-w-0 text-left" title="Show all itinerary days on map">
            <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-brand">Trip snapshot</p>
            <h1 className="display mt-0.5 text-2xl leading-tight text-ink">{state.overview.destination}</h1>
            <p className="mt-1 text-xs text-muted">{trip.metaLine}</p>
          </button>
          <div className="shrink-0 text-right">
            <span className="inline-flex rounded-full bg-sand px-2.5 py-0.5 text-[11px] font-semibold capitalize text-muted ring-1 ring-border">{state.overview.status}</span>
            <div className="mt-1.5"><CostLine state={state} look="cards" /></div>
          </div>
        </div>
        <p className="mt-2.5 text-[13px] leading-relaxed text-muted">{trip.summary}</p>
        <div className="mt-3 grid grid-cols-4 gap-1.5">
          {trip.counts.map(({ label, value, Icon }) => (
            <div key={label} aria-label={`${value} ${label}`} className="flex flex-col items-center gap-0.5 rounded-lg bg-sand/70 py-2">
              <Icon size={13} className="text-muted" aria-hidden />
              <span className="text-sm font-semibold tabular-nums text-ink">{value}</span>
              <span className="text-[9.5px] font-medium uppercase text-muted">{label}</span>
            </div>
          ))}
        </div>
        <div className="mt-3"><ReadinessBar state={state} look="cards" /></div>
      </div>
      <div className="rounded-xl border border-border bg-paper p-3.5 shadow-sm"><WeatherBlock state={state} look="cards" /></div>
      <div className="space-y-3 rounded-xl border border-border bg-paper p-3.5 shadow-sm">
        <NeedsBlock state={state} look="cards" />
        <BudgetBlock state={state} look="cards" />
      </div>
    </section>
  );
}

function Fact({ label, children, className = "" }: { label: string; children: ReactNode; className?: string }) {
  return (
    <div className={`min-w-0 ${className}`}>
      <p className="text-[9.5px] font-semibold uppercase tracking-[0.08em] text-muted">{label}</p>
      <div className="mt-0.5 text-[11.5px] text-ink">{children}</div>
    </div>
  );
}

function Stop({ state, facts, row, spaced }: { state: PlannerState; facts: DayFacts; row: RowFacts; spaced: boolean }) {
  const day = facts.day.day;
  const active = state.isFocused(day, row);
  const ModeIcon = row.travel ? modeIcon(row.travel.mode) : null;
  const arrival = arrivalLine(row);
  const hasFacts = row.rating || row.mustVisit || row.cost || row.hours;
  return (
    <li id={row.rowId} data-stop-name={row.stop.name.toLowerCase()} data-stop-day={day} data-stop-index={row.index} className={`group ${spaced ? "pt-1.5" : ""}`}>
      {row.travel && ModeIcon && (
        <div className="flex items-stretch gap-3 py-1 pl-[22px]" aria-label={row.travel.aria} title={row.travel.title}>
          <span className="w-px bg-border" aria-hidden />
          <div className="py-1">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-sage-soft px-2.5 py-0.5 text-[11px] font-semibold text-accent-600">
              <ModeIcon size={12} aria-hidden /><span className="capitalize">{row.travel.mode}</span> · {row.travel.distance} · {row.travel.duration}
            </span>
            {row.travel.detail && <p className="mt-1 text-[11px] text-muted">{row.travel.detail}</p>}
            {arrival && <p className={`text-[11px] ${row.travel.conflict ? "font-medium text-rose-700" : "text-muted"}`}>{arrival}</p>}
          </div>
        </div>
      )}
      <article
        onClick={() => state.focusStop(day, row)}
        className={`rounded-lg border bg-paper p-3 transition ${active ? "border-clay/50 shadow-card ring-1 ring-clay/15" : row.focusable ? "cursor-pointer border-border hover:border-clay/40 hover:shadow-sm" : "border-border"}`}
      >
        <div className="flex items-start gap-2.5">
          <Marker row={row} active={active} size={24} look="cards" />
          <div className="min-w-0 flex-1">
            <div className="flex items-start gap-1.5">
              <StopName state={state} day={day} row={row} className="flex-1 text-[14px] font-semibold leading-snug" />
              <StopActions state={state} day={day} row={row} look="cards" />
            </div>
            <StopMeta row={row} className="mt-0.5" withDuration={false} />
          </div>
          <BookingToggle state={state} day={day} row={row} look="cards" />
        </div>
        {(row.time || row.durationText || row.departureText) && (
          <p className="mt-2 flex flex-wrap items-center gap-x-2 rounded-md bg-sand/60 px-2 py-1 text-[11px] tabular-nums text-muted">
            <Clock3 size={12} aria-hidden />
            {row.time && <b className="font-semibold text-ink">{row.time}</b>}
            {row.durationText && <span>{row.durationText}</span>}
            {row.departureText && <span>{row.departureText}</span>}
          </p>
        )}
        {hasFacts && (
          <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-2">
            {row.rating && <Fact label="Rating"><span aria-label={row.rating.aria} className="inline-flex items-center gap-1"><Star size={12} className="fill-amber-400 text-amber-400" aria-hidden /><b className="font-semibold">{row.rating.value}</b>{row.rating.reviews && <span className="text-muted">· {row.rating.reviews}</span>}</span></Fact>}
            {row.mustVisit && (
              <Fact label="Must-visit score">
                <span title={row.mustVisit.title} className="flex items-center gap-1.5">
                  <Flame size={12} className="shrink-0 text-brand" aria-hidden />
                  <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-sand"><span className="block h-full rounded-full bg-brand" style={{ width: `${row.mustVisit.score}%` }} /></span>
                  <b className="font-semibold tabular-nums">{row.mustVisit.score}/100</b>
                </span>
              </Fact>
            )}
            {row.cost && <Fact label="Cost"><span className="inline-flex items-center gap-1"><Ticket size={12} className="text-muted" aria-hidden />{row.cost}</span></Fact>}
            {row.hours && <Fact label="Opening hours"><span className="inline-flex items-center gap-1 tabular-nums"><Clock3 size={12} className="text-muted" aria-hidden />{row.hours}</span></Fact>}
          </div>
        )}
        <Concerns row={row} look="cards" />
        <Notes row={row} look="cards" />
      </article>
    </li>
  );
}

function Day({ state, facts, open, onToggle }: { state: PlannerState; facts: DayFacts; open: boolean; onToggle: () => void }) {
  const { day } = facts;
  const circuitActive = state.circuitDay === day.day;
  const travel = dayTravelText(state, facts);
  return (
    <section id={`lab-it-day-${day.day}`} className={`overflow-hidden rounded-xl border bg-paper shadow-sm ${circuitActive ? "border-clay/40" : "border-border"}`}>
      <div className="h-1" style={{ backgroundColor: day.color }} aria-hidden />
      <div className={`px-3.5 pb-3 pt-3 ${circuitActive ? "bg-sand" : ""}`}>
        <div className="flex items-start gap-2.5">
          <button type="button" onClick={() => state.showDay(day.day)} aria-current={circuitActive ? "true" : undefined} title={`Show complete Day ${day.day} circuit on map`} className="flex min-w-0 flex-1 items-start gap-2.5 text-left">
            <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full text-sm font-bold text-white" style={{ backgroundColor: day.color }} aria-hidden>{day.day}</span>
            <span className="min-w-0">
              <span className="block text-[10.5px] font-semibold uppercase text-brand">{facts.dateLabel}</span>
              <span className="display block text-[20px] leading-tight text-ink">{day.title}</span>
            </span>
          </button>
          <button type="button" onClick={onToggle} aria-expanded={open} aria-label={open ? `Collapse Day ${day.day} stops` : `Expand Day ${day.day} stops`} className="grid h-7 w-7 shrink-0 place-items-center rounded-full text-muted ring-1 ring-border hover:bg-sand hover:text-ink">
            <ChevronDown size={14} className={`transition ${open ? "rotate-180" : ""}`} aria-hidden />
          </button>
        </div>
        <div className="mt-1.5"><DayWeather state={state} facts={facts} /></div>
        {day.summary && <p className="mt-2 text-xs leading-relaxed text-muted">{day.summary}</p>}
        <div className="mt-2.5 grid grid-cols-2 gap-1.5">
          <div className="rounded-lg bg-sand/70 px-2.5 py-1.5"><Fact label="Schedule duration"><span className="tabular-nums">{facts.scheduleText ?? "—"}</span></Fact></div>
          <div className="rounded-lg bg-sand/70 px-2.5 py-1.5"><Fact label="Day's travel"><span className="tabular-nums">{travel ?? "—"}</span></Fact></div>
          <div className="rounded-lg bg-sand/70 px-2.5 py-1.5"><Fact label="Stops"><b className="font-semibold">{facts.planned} planned {facts.planned === 1 ? "stop" : "stops"}</b></Fact></div>
          <div className="rounded-lg bg-sand/70 px-2.5 py-1.5"><Fact label="Bookings"><span className={facts.remaining > 0 ? "text-amber-700" : "text-emerald-700"}>{facts.confirmed} confirmed · {facts.remaining} to book</span></Fact></div>
        </div>
        {day.reachability && <p className="mt-2 text-[11px] leading-relaxed text-muted"><strong className="font-semibold text-accent">Travel rhythm:</strong> {day.reachability}</p>}
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <button type="button" onClick={() => state.showDay(day.day)} className="inline-flex h-7 items-center gap-1.5 rounded-md border border-border bg-paper px-2.5 text-[11px] font-medium text-muted hover:border-clay/40 hover:text-clay"><MapPin size={12} aria-hidden /> Day on map</button>
          <OpenRoute state={state} facts={facts} className="inline-flex h-7 items-center gap-1.5 rounded-md border border-border bg-paper px-2.5 text-[11px] font-medium text-muted hover:border-clay/40 hover:text-clay" />
          {!open && facts.rows.length > 0 && <button type="button" onClick={onToggle} className="ml-auto text-[11px] font-semibold text-brand hover:underline">Show {facts.rows.length} stops</button>}
        </div>
      </div>
      {open && facts.rows.length > 0 && (
        <ul className="space-y-0 border-t border-border bg-surface/60 px-3 py-3" aria-label={facts.transition ? `Transition day timeline from ${facts.transition.from} to ${facts.transition.to}` : undefined}>
          {facts.rows.map((row, index) => (
            <Stop key={row.key} state={state} facts={facts} row={row} spaced={index > 0 && !row.travel} />
          ))}
        </ul>
      )}
    </section>
  );
}

export function CardsPane({ state }: { state: PlannerState }) {
  const focusDay = state.circuitDay ?? state.focus?.day ?? 1;
  const [openDays, setOpenDays] = useState<Set<number>>(() => new Set([focusDay]));
  useEffect(() => {
    setOpenDays((current) => current.has(focusDay) ? current : new Set([...current, focusDay]));
  }, [focusDay]);
  return (
    <div className="h-full overflow-y-auto bg-sidebar pb-6">
      <Snapshot state={state} />
      <div className="px-3 pt-2"><Checks state={state} look="cards" /></div>
      <header className="flex items-center gap-2 px-4 pb-2 pt-4">
        <h2 className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted">Day by day</h2>
        <button
          type="button"
          onClick={() => setOpenDays((current) => current.size === state.days.length ? new Set() : new Set(state.days.map((facts) => facts.day.day)))}
          className="text-[11px] font-semibold text-muted hover:text-ink"
        >
          {openDays.size === state.days.length ? "Collapse all" : "Expand all"}
        </button>
        <TripLength state={state} look="cards" />
      </header>
      <EmptyFilters state={state} />
      <div className="space-y-3 px-3">
        {state.days.map((facts) => (
          <Day
            key={facts.day.day}
            state={state}
            facts={facts}
            open={openDays.has(facts.day.day)}
            onToggle={() => setOpenDays((current) => {
              const next = new Set(current);
              if (next.has(facts.day.day)) next.delete(facts.day.day);
              else next.add(facts.day.day);
              return next;
            })}
          />
        ))}
      </div>
    </div>
  );
}
