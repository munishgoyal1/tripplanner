import { useState, type ReactNode } from "react";
import {
  AlertTriangle, CalendarCheck2, Check, CheckCircle2, ChevronDown, Clock3, ExternalLink, Flame, HelpCircle, Lightbulb, Loader2,
  MapPin, Minus, Plus, RefreshCw, Route, ShieldCheck, Star, Trash2, Wand2, X,
} from "lucide-react";
import WeatherIcon from "../../../../src/components/WeatherIcon";
import { formatDistance, formatTemperature } from "../../../../src/lib/displayPreferences";
import { useUnmappedStop } from "../../../../src/lib/unmappedStops";
import { kindIcon } from "../icons";
import type { DayFacts, RowFacts } from "../model";
import { checkFacts, rainText, tripFacts, useTripLength, weatherAria } from "../shared";
import type { PlannerState } from "../state";

/**
 * Blocks whose content and behaviour are identical in every option. Each option
 * passes a `look` so radius, weight and colour follow its own visual language;
 * the statements, controls and their order never change.
 */
export type Look = "timeline" | "cards" | "agenda" | "warm" | "crisp";

const radius = (look: Look) => (look === "crisp" || look === "agenda" ? "rounded" : look === "warm" ? "rounded-xl" : "rounded-md");
const kicker = (look: Look) => (look === "warm" ? "display text-[15px] text-ink" : "text-[10px] font-semibold uppercase tracking-[0.08em] text-muted");

export function Kicker({ look, children }: { look: Look; children: ReactNode }) {
  return <p className={kicker(look)}>{children}</p>;
}

export function WeatherBlock({ state, look }: { state: PlannerState; look: Look }) {
  const trip = tripFacts(state);
  return (
    <div>
      <div className="flex items-center justify-between gap-2"><Kicker look={look}>Weather</Kicker>{trip.weather && <span className="text-[10px] text-muted">{trip.weather.source_label}</span>}</div>
      {trip.weather ? (
        <>
          <div className="mt-1.5 flex flex-wrap gap-1" aria-label={`${trip.weather.source_label} weather summary`}>
            {trip.weather.days.map((day, index) => (
              <span
                key={day.date}
                className={`inline-flex h-6 items-center gap-1 px-1.5 text-[11px] font-medium text-ink ${radius(look)} ${look === "warm" ? "bg-sky-50 ring-1 ring-sky-100" : "bg-paper ring-1 ring-border"}`}
                title={`${day.date}: ${day.summary}${day.precip_probability_pct != null ? `, ${day.precip_probability_pct}% precipitation` : ""}`}
              >
                <span className="text-sky-700"><WeatherIcon condition={day.condition} size={13} /></span>D{index + 1}{day.high_c != null && <span className="tabular-nums">{Math.round(day.high_c)}°</span>}
              </span>
            ))}
          </div>
          {trip.packing && <p className="mt-1.5 text-xs leading-relaxed text-muted"><span className="font-semibold text-ink">Pack:</span> {trip.packing}</p>}
        </>
      ) : <p className="mt-1 text-xs text-muted">Forecast unavailable for this trip.</p>}
    </div>
  );
}

export function NeedsBlock({ state, look, title = true }: { state: PlannerState; look: Look; title?: boolean }) {
  const trip = tripFacts(state);
  if (!trip.familyPills.length && !trip.constraints) return null;
  const pill = look === "crisp"
    ? "inline-flex items-center rounded border border-border px-1.5 py-0.5 text-[11px] font-medium text-muted"
    : look === "warm"
      ? "inline-flex items-center rounded-full bg-sage-soft px-2.5 py-0.5 text-[11px] font-medium text-accent-600"
      : "chip";
  return (
    <div>
      {title && <Kicker look={look}>Trip needs</Kicker>}
      <div className={`${title ? "mt-1.5" : ""} flex flex-wrap gap-1`}>{trip.familyPills.map((entry) => <span key={entry} className={pill}>{entry}</span>)}</div>
      {trip.constraints && <p className="mt-1.5 text-xs leading-relaxed text-muted"><span className="font-semibold text-ink">For this trip:</span> {trip.constraints}</p>}
    </div>
  );
}

export function BudgetBlock({ state, look, title = true }: { state: PlannerState; look: Look; title?: boolean }) {
  const trip = tripFacts(state);
  const budget = trip.budget;
  if (!budget) return null;
  return (
    <div>
      <div className="flex items-end justify-between gap-2">
        <div>
          {title && <Kicker look={look}>Trip spend</Kicker>}
          {budget.estimatedText && <p className="text-[10px] text-amber-700">{budget.estimatedText}</p>}
          {budget.check && <p className="max-w-64 text-[10px] leading-snug text-muted">{budget.check}</p>}
          <p className="mt-0.5 text-sm font-semibold tabular-nums text-ink">{budget.spent}{budget.target && <span className="text-xs font-normal text-muted"> / {budget.target}</span>}</p>
        </div>
        <p className="text-right text-[11px] text-muted"><span className="tabular-nums text-ink">{budget.perTraveler}</span> per traveler</p>
      </div>
      {budget.target && (
        <>
          <div className={`mt-1.5 h-1.5 overflow-hidden bg-sand ${look === "crisp" ? "rounded-sm" : "rounded-full"}`}><div className={`h-full ${look === "crisp" ? "rounded-sm" : "rounded-full"} ${budget.tone}`} style={{ width: `${Math.min(budget.pct, 100)}%` }} /></div>
          <div className="mt-1 flex justify-between text-[11px] text-muted"><span className={budget.raw.over_budget ? "font-medium text-rose-700" : ""}>{budget.remaining} {budget.remainingWord}</span><span>{budget.pct}% used</span></div>
        </>
      )}
      {budget.allIn && <p className="mt-1 text-[11px] font-medium text-emerald-700">Confirmed all-in: {budget.allIn}</p>}
    </div>
  );
}

export function CostLine({ state, look }: { state: PlannerState; look: Look }) {
  const trip = tripFacts(state);
  return (
    <div>
      {trip.total && <p className={`font-semibold tabular-nums text-ink ${look === "warm" ? "display text-2xl font-normal" : "text-base"}`}>{trip.total}</p>}
      {trip.costEvidence?.summary && (
        <p className={`mt-0.5 text-[10px] font-medium ${trip.costEvidence.complete ? "text-emerald-700" : "text-amber-700"}`} title={trip.costEvidence.complete ? "Every item is backed by a current provider quote." : "Some items are not backed by a current provider quote."}>
          {trip.costEvidence.summary}
        </p>
      )}
      {trip.canRecheck && (
        <button type="button" onClick={(event) => { event.stopPropagation(); void state.runRecheck(); }} disabled={state.rechecking} className="mt-1 inline-flex items-center gap-1 text-[10px] font-semibold text-brand disabled:opacity-60">
          <RefreshCw size={11} className={state.rechecking ? "animate-spin" : ""} aria-hidden />
          {state.rechecking ? "Rechecking prices…" : "Recheck prices"}
        </button>
      )}
      {state.recheckOutcome && <p className="mt-0.5 max-w-52 text-[10px] text-muted">{state.recheckOutcome}</p>}
    </div>
  );
}

export function ReadinessBar({ state, look }: { state: PlannerState; look: Look }) {
  const trip = tripFacts(state);
  return (
    <div>
      <div className="flex items-center justify-between gap-3 text-xs">
        <span className="inline-flex items-center gap-1.5 font-semibold text-ink"><CheckCircle2 size={13} className="text-emerald-600" aria-hidden />{trip.readyText}</span>
        <span className={trip.remaining ? "text-amber-700" : "text-emerald-700"}>{trip.remainingText}</span>
      </div>
      <div className={`mt-1.5 h-1.5 overflow-hidden bg-sand ${look === "crisp" ? "rounded-sm" : "rounded-full"}`} aria-label={`${trip.readinessPct}% of stops ready`}>
        <div className={`h-full bg-sage ${look === "crisp" ? "rounded-sm" : "rounded-full"}`} style={{ width: `${trip.readinessPct}%` }} />
      </div>
    </div>
  );
}

export function Checks({ state, look }: { state: PlannerState; look: Look }) {
  const checks = checkFacts(state);
  const verdict = checks.report.verdict;
  const Icon = verdict === "issues" ? AlertTriangle : verdict === "clear" ? ShieldCheck : HelpCircle;
  const tone = verdict === "issues" ? "text-rose-600" : verdict === "clear" ? "text-emerald-600" : "text-amber-600";
  const surface = look === "warm"
    ? `rounded-xl px-3 py-2.5 ${verdict === "issues" ? "bg-rose-50" : verdict === "clear" ? "bg-emerald-50" : "bg-amber-50/80"}`
    : look === "cards"
      ? `rounded-lg border px-3 py-2 ${verdict === "issues" ? "border-rose-200 bg-rose-50" : verdict === "clear" ? "border-emerald-200 bg-emerald-50" : "border-amber-200 bg-amber-50"}`
      : "";
  return (
    <section aria-label="Plan checks" className={surface}>
      <button type="button" onClick={state.toggleChecks} aria-expanded={state.checksExpanded} className="flex w-full items-center gap-2 text-left text-xs">
        <Icon size={14} className={`shrink-0 ${tone}`} aria-hidden />
        <span className="font-medium text-ink">{checks.headline}</span>
        <span className="ml-auto shrink-0 text-[11px] text-muted">{checks.countsText}</span>
        <ChevronDown size={13} className={`shrink-0 text-muted transition ${state.checksExpanded ? "rotate-180" : ""}`} aria-hidden />
      </button>
      {checks.contradictions.length > 0 && (
        <div className={`mt-2 ${look === "cards" || look === "warm" ? "" : `${radius(look)} bg-rose-50 px-2.5 py-2 ring-1 ring-rose-100`}`}>
          <ul className="space-y-1">{checks.contradictions.map((item) => <li key={item.key} className="flex gap-2 text-xs text-rose-900"><AlertTriangle size={13} className="mt-0.5 shrink-0 text-rose-600" aria-hidden />{item.finding}</li>)}</ul>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <button type="button" onClick={() => void state.runRepair()} disabled={state.repairing} className={`inline-flex h-7 items-center gap-1.5 bg-ink px-2.5 text-[11px] font-semibold text-white disabled:opacity-60 ${look === "warm" ? "rounded-full" : radius(look)}`}><Wand2 size={12} aria-hidden />{state.repairing ? "Rearranging…" : "Rearrange the trip"}</button>
            <span className="text-[11px] text-muted">Only stops you have not chosen will move.</span>
          </div>
        </div>
      )}
      {state.checksOutcome.length > 0 && <ul className="mt-2 space-y-0.5 text-[11px] text-muted">{state.checksOutcome.map((line) => <li key={line}>{line}</li>)}</ul>}
      {state.checksExpanded && (
        <div className="mt-2 space-y-2.5 pb-1 text-xs">
          <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted">
            <button type="button" onClick={() => void state.runRefresh()} disabled={state.refreshing} className={`inline-flex h-7 items-center gap-1.5 border border-border bg-paper px-2 font-semibold text-ink disabled:opacity-60 ${look === "warm" ? "rounded-full" : radius(look)}`}><RefreshCw size={12} className={state.refreshing ? "animate-spin" : ""} aria-hidden />{state.refreshing ? "Rechecking…" : "Recheck place facts"}</button>
            {checks.lastChecked}
          </div>
          {checks.advisories.length > 0 && <ul className="space-y-1">{checks.advisories.map((item) => <li key={item.key} className="flex gap-2 text-muted"><HelpCircle size={13} className="mt-0.5 shrink-0 text-amber-600" aria-hidden />{item.finding}</li>)}</ul>}
          <ul className="space-y-1">
            {checks.report.checks.map((check) => {
              const StatusIcon = check.status === "passed" ? CheckCircle2 : check.status === "failed" ? AlertTriangle : HelpCircle;
              const color = check.status === "passed" ? "text-emerald-600" : check.status === "failed" ? "text-rose-600" : "text-amber-600";
              return <li key={check.code} className="flex gap-2"><StatusIcon size={13} className={`mt-0.5 shrink-0 ${color}`} aria-hidden /><span className="text-muted"><span className="font-medium text-ink">{check.rule}</span> — {check.statement}</span></li>;
            })}
          </ul>
          {checks.gaps.length > 0 && <div><p className="font-medium text-ink">Could not verify</p><ul className="mt-0.5 space-y-0.5 text-muted">{checks.gaps.map((gap) => <li key={gap}>{gap}</li>)}</ul></div>}
          {checks.holidays.length > 0 && <div><p className="font-medium text-ink">Public holidays</p><ul className="mt-0.5 space-y-0.5 text-muted">{checks.holidays.map((line) => <li key={line}>{line}</li>)}</ul></div>}
        </div>
      )}
    </section>
  );
}

export function TripLength({ state, look }: { state: PlannerState; look: Look }) {
  const length = useTripLength();
  const shape = look === "warm" ? "rounded-full" : look === "crisp" || look === "agenda" ? "rounded" : "rounded-md";
  return (
    <div className="relative ml-auto flex items-center gap-0.5">
      <button type="button" onClick={() => length.open("add")} className={`inline-flex h-7 items-center gap-1 px-2 text-[11px] font-semibold text-brand hover:bg-brand/10 ${shape}`}><Plus size={13} aria-hidden /> Add a day</button>
      <button type="button" disabled={state.stats.days <= 1} onClick={() => length.open("reduce")} className={`inline-flex h-7 items-center gap-1 px-2 text-[11px] font-semibold text-muted hover:bg-sand hover:text-ink disabled:opacity-40 ${shape}`}><Minus size={13} aria-hidden /> Reduce a day</button>
      {length.pending && (
        <section className={`absolute right-0 top-full z-40 mt-1 w-72 border border-border bg-paper p-3 text-left shadow-pop ${look === "crisp" ? "rounded-md" : "rounded-xl"}`} aria-label={length.pending === "add" ? "Add a day" : "Reduce a day"}>
          <div className="flex items-start justify-between gap-3">
            <div><h3 className="text-sm font-semibold text-ink">{length.title}</h3><p className="mt-1 text-[11px] leading-relaxed text-muted">{length.body}</p></div>
            <button type="button" onClick={length.close} className="grid h-6 w-6 shrink-0 place-items-center rounded-md text-muted hover:bg-sand" aria-label="Close day adjustment"><X size={13} aria-hidden /></button>
          </div>
          <label className="mt-3 flex cursor-pointer items-start gap-2 rounded-lg bg-sand/60 p-2 text-[11px] text-ink">
            <input type="checkbox" checked={length.replan} onChange={(event) => length.setReplan(event.target.checked)} className="mt-0.5" />
            <span><strong className="block font-semibold">Replan the whole itinerary</strong><span className="text-muted">Unchecked keeps existing days stable and makes only the changes needed.</span></span>
          </label>
          <button type="button" onClick={() => { state.adjustDays(length.pending!, length.replan); length.close(); }} className={`mt-3 inline-flex h-8 w-full items-center justify-center px-3 text-xs font-semibold text-white ${look === "crisp" ? "rounded-md bg-ink hover:bg-ink/90" : "rounded-lg bg-brand hover:bg-brand-600"}`}>{length.confirmLabel}</button>
        </section>
      )}
    </div>
  );
}

export function BookingToggle({ state, day, row, look }: { state: PlannerState; day: number; row: RowFacts; look: Look }) {
  if (!row.bookable) return null;
  const booked = row.stop.booked;
  const shape = look === "crisp" || look === "agenda" ? "rounded" : "rounded-full";
  const tone = booked
    ? look === "crisp" ? "text-emerald-700 ring-1 ring-emerald-200 bg-emerald-50/60 hover:bg-emerald-50" : "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200 hover:bg-emerald-100"
    : "bg-amber-50 text-amber-800 ring-1 ring-amber-200 hover:ring-brand/30";
  return (
    <button
      type="button"
      aria-pressed={booked}
      aria-label={`${row.stop.name}: ${booked ? "Mark as needing booking" : "Mark confirmed"}`}
      onClick={(event) => { event.stopPropagation(); state.toggleBooked(day, row); }}
      className={`inline-flex h-6 shrink-0 items-center gap-1 px-2 text-[10px] font-semibold transition ${shape} ${tone}`}
    >
      {booked ? <Check size={11} aria-hidden /> : <CalendarCheck2 size={11} aria-hidden />}
      {booked ? "Confirmed" : "Needs booking"}
    </button>
  );
}

export function StopActions({ state, day, row, look }: { state: PlannerState; day: number; row: RowFacts; look: Look }) {
  const shape = look === "crisp" || look === "agenda" ? "rounded" : "rounded-full";
  const removing = state.isRemoving(day, row);
  return (
    <div className="flex shrink-0 items-center gap-0.5 opacity-0 transition focus-within:opacity-100 group-hover:opacity-100">
      <button type="button" onClick={(event) => { event.stopPropagation(); state.showOnMap(day, row); }} aria-label={`Show ${row.stop.name} on the map`} title={row.routeFocusable ? "Show complete route" : "Show on map"} className={`grid h-6 w-6 place-items-center text-muted transition hover:bg-sand hover:text-brand ${shape}`}>
        <MapPin size={13} aria-hidden />
      </button>
      {row.removable && (
        <button type="button" disabled={removing} onClick={(event) => { event.stopPropagation(); void state.removeStop(day, row); }} aria-label={`Remove ${row.stop.name} from itinerary`} title="Remove from itinerary" className={`grid h-6 w-6 place-items-center text-muted transition hover:bg-sand hover:text-rose-600 ${shape}`}>
          {removing ? <Loader2 size={12} className="animate-spin" aria-hidden /> : <Trash2 size={13} aria-hidden />}
        </button>
      )}
    </div>
  );
}

export function StopName({ state, day, row, className }: { state: PlannerState; day: number; row: RowFacts; className: string }) {
  return (
    <button
      type="button"
      disabled={!row.focusable}
      onClick={(event) => { event.stopPropagation(); state.focusStop(day, row); }}
      className={`min-w-0 text-left ${row.focusable ? "text-ink hover:text-brand" : "cursor-default text-ink"} ${className}`}
      title={row.focusTitle}
    >
      {row.name}
    </button>
  );
}

/** "Arrive · attraction · Not on map · 1 hr visit · Leave 12:30", as production words it. */
export function StopMeta({ row, className = "", withDuration = true }: { row: RowFacts; className?: string; withDuration?: boolean }) {
  const unmapped = useUnmappedStop(row.stop.name);
  return (
    <p className={`flex flex-wrap items-center gap-x-1.5 text-[11px] text-muted ${className}`}>
      <span>{row.timingLabel}</span><span aria-hidden>·</span><span>{row.kindLabel}</span>
      {unmapped && (
        <><span aria-hidden>·</span><span className={`font-semibold ${unmapped.tier === "anchor" ? "text-amber-600" : "text-amber-700"}`} title={unmapped.candidate ? `The map found “${unmapped.candidate.name}” instead. Confirm it on the map to pin this stop.` : "The map could not place this stop."}>Not on map</span></>
      )}
      {withDuration && row.durationText && <><span aria-hidden>·</span><span>{row.durationText}</span></>}
      {withDuration && row.departureText && <><span aria-hidden>·</span><span className="tabular-nums">{row.departureText}</span></>}
    </p>
  );
}

export function Concerns({ row, look }: { row: RowFacts; look: Look }) {
  if (!row.concerns.length) return null;
  return (
    <div className={`mt-1.5 space-y-0.5 ${look === "warm" || look === "cards" ? "rounded-lg bg-rose-50 px-2.5 py-1.5" : ""}`}>
      {row.concerns.map((text) => <p key={text} className="flex gap-1.5 text-xs font-medium text-rose-700"><AlertTriangle size={12} className="mt-0.5 shrink-0" aria-hidden />{text}</p>)}
    </div>
  );
}

export function Notes({ row, look }: { row: RowFacts; look: Look }) {
  const [open, setOpen] = useState(false);
  if (!row.hasNotes) return null;
  return (
    <div>
      <button type="button" aria-expanded={open} onClick={(event) => { event.stopPropagation(); setOpen((value) => !value); }} className="mt-1.5 inline-flex items-center gap-1 text-[11px] font-semibold text-muted transition hover:text-ink">
        {look === "warm" && <Lightbulb size={12} className="text-ochre" aria-hidden />}
        {open ? "Hide notes" : "Notes & tips"}
        <ChevronDown size={12} className={`transition ${open ? "rotate-180" : ""}`} aria-hidden />
      </button>
      {open && (
        <div className={`mt-1 space-y-0.5 ${look === "warm" ? "rounded-lg bg-ochre/10 px-2.5 py-1.5" : "border-l-2 border-border pl-2.5"}`}>
          {[...row.notes, ...row.insights].map((text) => <p key={text} className="text-xs leading-relaxed text-muted">{text}</p>)}
        </div>
      )}
    </div>
  );
}

export function Marker({ row, active, size = 22, look }: { row: RowFacts; active: boolean; size?: number; look: Look }) {
  const color = row.stop.color;
  if (row.mapLabel) {
    const filled = active || look === "warm";
    return (
      <span
        aria-label={row.mapLabel.startsWith("H") ? "Hotel map marker" : `Map stop ${row.mapLabel}`}
        aria-current={active ? "location" : undefined}
        className={`grid shrink-0 place-items-center rounded-full border-[1.5px] font-semibold tabular-nums transition ${active ? "scale-110 shadow-sm" : ""}`}
        style={{ width: size, height: size, fontSize: size > 20 ? 10 : 9, borderColor: color, color: filled ? "white" : color, backgroundColor: filled ? color : "white" }}
      >
        {row.mapLabel}
      </span>
    );
  }
  if (look === "crisp" || look === "warm") {
    const Icon = kindIcon(row.stop);
    return <span aria-hidden className={`grid shrink-0 place-items-center text-muted ${look === "crisp" ? "rounded bg-sand ring-1 ring-border" : "rounded-full bg-sand"}`} style={{ width: size, height: size }}><Icon size={size > 20 ? 12 : 11} /></span>;
  }
  return <span aria-hidden className="grid shrink-0 place-items-center rounded-full border border-border bg-sand text-[10px]" style={{ width: size, height: size }}>{row.kindGlyph}</span>;
}

/** Rating and must-visit, the two signals the owner named, in each option's shape. */
export function Signals({ row, look }: { row: RowFacts; look: Look }) {
  if (!row.rating && !row.mustVisit && !row.cost && !row.hours) return null;
  const tag = look === "crisp"
    ? "inline-flex items-center gap-1 rounded border border-border bg-paper px-1.5 py-[1px] text-[10.5px] font-medium text-muted"
    : look === "warm"
      ? "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium"
      : "inline-flex items-center gap-1 text-[11px]";
  return (
    <div className={`mt-1.5 flex flex-wrap items-center ${look === "crisp" || look === "warm" ? "gap-1" : "gap-x-2.5 gap-y-0.5"}`}>
      {row.rating && (
        <span aria-label={row.rating.aria} className={`${tag} ${look === "warm" ? "bg-amber-50 text-ink" : "text-ink"}`}>
          <Star size={11} className="fill-amber-400 text-amber-400" aria-hidden /><b className="font-semibold">{row.rating.value}</b>
          {row.rating.reviews && <span className="text-muted">· {row.rating.reviews}</span>}
        </span>
      )}
      {row.mustVisit && (
        <span title={row.mustVisit.title} className={`${tag} ${look === "warm" ? "bg-clay-soft/70 text-brand-600" : "text-brand"}`}>
          <Flame size={11} aria-hidden />Must-visit score <b className="font-semibold tabular-nums">{row.mustVisit.score}/100</b>
        </span>
      )}
      {row.cost && <span className={`${tag} ${look === "warm" ? "bg-sand text-muted" : "text-muted"}`}>{row.cost}</span>}
      {row.hours && <span className={`${tag} ${look === "warm" ? "bg-sand text-muted" : "text-muted"}`}><Clock3 size={11} aria-hidden />{row.hours}</span>}
    </div>
  );
}

/** Estimated arrival with buffer or conflict, worded exactly as production. */
export function arrivalLine(row: RowFacts): string | null {
  const travel = row.travel;
  if (!travel?.arrival) return null;
  return `${travel.arrival}${travel.buffer ? ` · ${travel.buffer}` : travel.conflict ? ` · ${travel.conflict}` : ""}`;
}

export function DayWeather({ state, facts, compact = false }: { state: PlannerState; facts: DayFacts; compact?: boolean }) {
  const weather = facts.day.weather;
  if (!weather) return null;
  const rain = rainText(weather.precip_probability_pct);
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-muted" aria-label={weatherAria(weather)} title={weather.precip_probability_pct != null ? `${weather.precip_probability_pct}% chance of precipitation` : weather.summary}>
      <span className="text-accent"><WeatherIcon condition={weather.condition} size={14} /></span>
      {!compact && <span>{weather.summary}</span>}
      {weather.high_c != null && weather.low_c != null && <span className="tabular-nums text-ink">{formatTemperature(weather.high_c, state.region)} / {formatTemperature(weather.low_c, state.region)}</span>}
      {rain && <span className="text-sky-700">{rain}</span>}
      {compact && <span className="sr-only">{weather.summary}</span>}
    </span>
  );
}

export function dayTravelText(state: PlannerState, facts: DayFacts): string | null {
  const route = facts.day.route;
  return route ? `${route.duration_display} · ${formatDistance(route.distance_km, state.region)} · ${route.mode}` : null;
}

export function OpenRoute({ state, facts, className }: { state: PlannerState; facts: DayFacts; className: string }) {
  if (!facts.day.google_maps_url) return null;
  return (
    <a
      href={facts.day.google_maps_url}
      target="_blank"
      rel="noreferrer"
      onClick={(event) => { event.preventDefault(); event.stopPropagation(); state.openRoute(facts.day.day); }}
      className={className}
      title={`Open Day ${facts.day.day} route in Google Maps`}
    >
      <Route size={12} aria-hidden /> Open route <ExternalLink size={11} aria-hidden />
    </a>
  );
}

export function EmptyFilters({ state }: { state: PlannerState }) {
  return state.days.length === 0 ? <p className="py-8 text-center text-sm text-muted">No itinerary items match these filters.</p> : null;
}
