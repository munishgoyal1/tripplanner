import {
  Bus,
  Car,
  Check,
  ChevronDown,
  CalendarCheck2,
  ExternalLink,
  Footprints,
  MapPin,
  Plane,
  Route,
  Ship,
  TramFront,
  TrainFront,
  Trash2,
} from "lucide-react";
import { useState } from "react";
import { days, dayTotals } from "../shared/tripFixture";
import type { Day, Stop, TravelLeg } from "../shared/tripFixture";
import { kindMeta } from "../shared/WorkspaceFrame";
import { TodayTripHeader, TripHeader } from "./TripHeader";

export type ItineraryOption = "spine" | "cards" | "editorial";

const filters = ["All", "Stays", "Places", "Food", "Travel", "To book"];

function modeIcon(mode: string) {
  if (/walk/i.test(mode)) return Footprints;
  if (/tram/i.test(mode)) return TramFront;
  if (/ferry|boat/i.test(mode)) return Ship;
  if (/rail|train/i.test(mode)) return TrainFront;
  if (/taxi|car|drive/i.test(mode)) return Car;
  if (/fl(y|ight)/i.test(mode)) return Plane;
  return Bus;
}

function reviewLabel(count: number) {
  return new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(count);
}

function partOfDay(time?: string) {
  const hour = Number((time || "12:00").slice(0, 2));
  if (hour < 12) return "Morning";
  if (hour < 17) return "Afternoon";
  return "Evening";
}

function FilterRow() {
  return (
    <div className="flex items-center gap-1 overflow-x-auto border-b border-slate-200 bg-white px-5 py-2">
      {filters.map((filter, index) => (
        <button
          key={filter}
          type="button"
          className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold transition ${
            index === 0 ? "bg-ink text-white" : "text-slate-500 hover:bg-slate-100 hover:text-ink"
          }`}
        >
          {filter}
        </button>
      ))}
    </div>
  );
}

function StatusPill({ booked, compact = false }: { booked: boolean; compact?: boolean }) {
  return (
    <span
      className={`inline-flex h-6 shrink-0 items-center gap-1 rounded-full px-2 text-[10px] font-semibold ring-1 ${
        booked
          ? "bg-emerald-50 text-emerald-700 ring-emerald-200"
          : "bg-amber-50 text-amber-800 ring-amber-200"
      }`}
    >
      {booked ? <Check size={11} aria-hidden /> : <CalendarCheck2 size={11} aria-hidden />}
      {compact ? (booked ? "Confirmed" : "To book") : booked ? "Confirmed" : "Needs booking"}
    </span>
  );
}

function StopChips({ stop }: { stop: Stop }) {
  return (
    <>
      {stop.cost && <span className="chip">{stop.cost}</span>}
      {stop.operational && <span className="chip">{stop.operational}</span>}
      {typeof stop.rating === "number" && (
        <span className="chip">
          ★ {stop.rating.toFixed(1)}
          {stop.reviews ? ` · ${reviewLabel(stop.reviews)} reviews` : ""}
        </span>
      )}
      {typeof stop.score === "number" && (
        <span className="chip" title="Estimated from Google rating and review volume">
          Must-visit {stop.score}/100
        </span>
      )}
    </>
  );
}

function StopNotes({ stop }: { stop: Stop }) {
  if (!stop.concern && !stop.note && !stop.insight) return null;
  return (
    <div className="mt-1.5 space-y-1">
      {stop.concern && <p className="text-xs font-medium text-rose-700">{stop.concern}</p>}
      {stop.note && <p className="text-xs text-slate-500">{stop.note}</p>}
      {stop.insight && <p className="text-xs text-slate-600">{stop.insight}</p>}
    </div>
  );
}

function RowActions({ removable }: { removable?: boolean }) {
  return (
    <div className="flex shrink-0 items-center gap-0.5 opacity-0 transition group-hover:opacity-100 focus-within:opacity-100">
      <button type="button" title="Show on map" className="grid h-7 w-7 place-items-center rounded-full text-slate-400 transition hover:bg-slate-100 hover:text-brand">
        <MapPin size={14} aria-hidden />
      </button>
      {removable && (
        <button type="button" title="Remove from itinerary" className="grid h-7 w-7 place-items-center rounded-full text-slate-400 transition hover:bg-slate-100 hover:text-rose-600">
          <Trash2 size={13} aria-hidden />
        </button>
      )}
    </div>
  );
}

function TravelChip({ travel, tone = "line" }: { travel: TravelLeg; tone?: "line" | "inline" }) {
  const Icon = modeIcon(travel.mode);
  return (
    <div
      className={`flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[11px] font-medium text-accent ${
        tone === "line" ? "" : "mb-1"
      }`}
    >
      <Icon size={12} aria-hidden />
      <span className="capitalize">{travel.mode}</span>
      <span className="text-slate-400" aria-hidden>·</span>
      <span className="tabular-nums">{travel.duration}</span>
      <span className="text-slate-400" aria-hidden>·</span>
      <span className="tabular-nums">{travel.distance}</span>
      {travel.detail && <span className="basis-full font-normal text-slate-500">{travel.detail}</span>}
      {travel.arrival && (
        <span className="basis-full font-normal text-slate-500">
          Est. arrive {travel.arrival}
          {travel.buffer ? ` · ${travel.buffer} free before` : travel.conflict ? ` · ${travel.conflict} too tight` : ""}
        </span>
      )}
    </div>
  );
}

function DayMeta({ day, dense = false }: { day: Day; dense?: boolean }) {
  const totals = dayTotals(day);
  return (
    <div className={`flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-500 ${dense ? "" : "mt-2"}`}>
      <span className="font-semibold text-ink">{totals.planned} planned stops</span>
      <span className="inline-flex items-center gap-1 tabular-nums">
        {day.schedule.duration} · {day.schedule.start}–{day.schedule.end}{day.schedule.estimated ? " est." : ""}
      </span>
      <span className="inline-flex items-center gap-1 tabular-nums">
        <Route size={11} aria-hidden />
        {day.route.duration} · {day.route.distance} · {day.route.mode}
      </span>
      <span className={totals.toBook > 0 ? "font-medium text-amber-700" : "font-medium text-emerald-700"}>
        {totals.confirmed} confirmed · {totals.toBook} to book
      </span>
    </div>
  );
}

function DayHeader({ day, sticky = true }: { day: Day; sticky?: boolean }) {
  return (
    <header
      data-lab-change="Day header"
      className={`${sticky ? "sticky top-[6.5rem] z-10" : ""} border-y border-slate-200/70 bg-white/92 px-5 py-2.5 backdrop-blur`}
    >
      <div className="flex items-start gap-3">
        <span
          className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-xl text-xs font-bold text-white"
          style={{ backgroundColor: day.color }}
        >
          {day.day}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[10px] font-bold uppercase tracking-wide text-slate-400">
            {day.weekday} · {day.date}
          </p>
          <h2 className="display truncate text-base font-semibold text-ink">{day.title}</h2>
        </div>
        <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-sky-50 px-2 py-1 text-[11px] font-medium text-sky-800 ring-1 ring-sky-100">
          {day.weather.summary} {day.weather.high}°/{day.weather.low}°
          {day.weather.precip >= 30 ? ` · ${day.weather.precip}% rain` : ""}
        </span>
        <a
          href={day.routeUrl}
          target="_blank"
          rel="noreferrer"
          title={`Open Day ${day.day} route in Google Maps`}
          className="grid h-7 w-7 shrink-0 place-items-center rounded-full text-slate-400 transition hover:bg-slate-100 hover:text-brand"
        >
          <ExternalLink size={13} aria-hidden />
        </a>
      </div>
      <p className="mt-1.5 text-xs leading-relaxed text-slate-600">{day.summary}</p>
      <DayMeta day={day} />
      <p className="mt-1 text-[11px] text-slate-500">
        <span className="font-semibold text-accent">Travel rhythm:</span> {day.rhythm}
      </p>
    </header>
  );
}

/* ---------------------------------- A · Spine --------------------------------- */

function SpineStop({ stop }: { stop: Stop }) {
  const { Icon } = kindMeta[stop.kind];
  return (
    <li data-lab-change="Stop row" className="group relative pb-4">
      {stop.travel && (
        <div className="relative mb-2 pl-[4.75rem]">
          <TravelChip travel={stop.travel} />
        </div>
      )}
      <div className="relative flex gap-3">
        <div className="w-14 shrink-0 pt-0.5 text-right">
          <p className="text-[10px] font-bold uppercase text-slate-400">{stop.timing}</p>
          {stop.time && (
            <p className="text-sm font-semibold tabular-nums text-ink">
              {stop.time}{stop.estimated ? "*" : ""}
            </p>
          )}
          {stop.durationLabel && <p className="mt-0.5 text-[10px] text-slate-500">{stop.durationLabel}</p>}
          {stop.leaveLabel && <p className="mt-0.5 text-[10px] tabular-nums text-slate-600">{stop.leaveLabel}</p>}
        </div>
        <div className="relative flex w-6 shrink-0 justify-center">
          <span
            className="z-10 mt-1 grid h-6 w-6 place-items-center rounded-full bg-white text-[10px] font-bold ring-2"
            style={{ color: stop.marker ? "#0f172a" : "#94a3b8", boxShadow: `0 0 0 2px ${stop.marker ? "#ffffff" : "transparent"}` }}
          >
            <span
              className="grid h-6 w-6 place-items-center rounded-full border-2 bg-white"
              style={{ borderColor: stop.marker ? "currentColor" : "#cbd5e1" }}
            >
              {stop.marker ?? <Icon size={11} aria-hidden />}
            </span>
          </span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-start gap-2">
            <div className="min-w-0 flex-1">
              <p className="text-[10px] font-bold uppercase text-slate-400">{kindMeta[stop.kind].label}</p>
              <button type="button" className="block max-w-full truncate text-left text-sm font-semibold text-ink transition hover:text-brand">
                {stop.name}
              </button>
            </div>
            {stop.bookable && <StatusPill booked={!!stop.booked} compact />}
            <RowActions removable={stop.planned} />
          </div>
          <div className="mt-1.5 flex flex-wrap items-center gap-1">
            <StopChips stop={stop} />
          </div>
          <StopNotes stop={stop} />
        </div>
      </div>
    </li>
  );
}

function SpineOption() {
  return (
    <div className="h-full overflow-y-auto bg-white">
      <TripHeader />
      <FilterRow />
      {days.map((day) => (
        <section key={day.day}>
          <DayHeader day={day} />
          <ol className="relative px-5 pb-2 pt-4 before:absolute before:bottom-6 before:left-[5.4rem] before:top-6 before:w-px before:bg-slate-200">
            {day.stops.map((stop) => <SpineStop key={stop.id} stop={stop} />)}
          </ol>
        </section>
      ))}
    </div>
  );
}

/* ---------------------------------- B · Cards --------------------------------- */

function CardStop({ stop }: { stop: Stop }) {
  const [open, setOpen] = useState(false);
  const { Icon } = kindMeta[stop.kind];
  const hasDetail = !!(stop.note || stop.insight);
  return (
    <li data-lab-change="Stop row" className="group">
      {stop.travel && (
        <div className="flex items-start gap-2 py-1.5 pl-3">
          <span className="mt-1.5 h-px w-4 bg-slate-200" aria-hidden />
          <TravelChip travel={stop.travel} />
        </div>
      )}
      <article
        className={`rounded-2xl bg-white p-3 shadow-card ring-1 transition ${
          stop.concern ? "ring-rose-200" : "ring-slate-200/80 hover:ring-slate-300"
        }`}
      >
        <div className="flex items-start gap-2.5">
          <span
            className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full border text-[10px] font-bold tabular-nums"
            style={{ borderColor: stop.marker ? "#cbd5e1" : "#e2e8f0", color: "#334155" }}
          >
            {stop.marker ?? <Icon size={12} aria-hidden />}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex items-baseline gap-2">
              {stop.time && (
                <span className="text-sm font-semibold tabular-nums text-ink">
                  {stop.time}{stop.estimated ? "*" : ""}
                </span>
              )}
              <span className="truncate text-sm font-semibold text-ink">{stop.name}</span>
            </div>
            <p className="mt-0.5 text-[11px] text-slate-500">
              {stop.timing} · {kindMeta[stop.kind].label}
              {stop.durationLabel ? ` · ${stop.durationLabel}` : ""}
              {stop.leaveLabel ? ` · ${stop.leaveLabel}` : ""}
            </p>
          </div>
          {stop.bookable && <StatusPill booked={!!stop.booked} compact />}
          <RowActions removable={stop.planned} />
        </div>
        {(stop.cost || stop.operational || stop.rating) && (
          <div className="mt-2 flex flex-wrap items-center gap-1 pl-[2.4rem]">
            <StopChips stop={stop} />
          </div>
        )}
        {stop.concern && <p className="mt-2 pl-[2.4rem] text-xs font-medium text-rose-700">{stop.concern}</p>}
        {hasDetail && (
          <div className="pl-[2.4rem]">
            <button
              type="button"
              onClick={() => setOpen((value) => !value)}
              aria-expanded={open}
              className="mt-1.5 inline-flex items-center gap-1 text-[11px] font-semibold text-slate-500 transition hover:text-ink"
            >
              {open ? "Hide notes" : "Notes & tips"}
              <ChevronDown size={12} className={`transition ${open ? "rotate-180" : ""}`} aria-hidden />
            </button>
            {open && (
              <div className="mt-1 space-y-1 border-l-2 border-slate-100 pl-2.5">
                {stop.note && <p className="text-xs text-slate-500">{stop.note}</p>}
                {stop.insight && <p className="text-xs text-slate-600">{stop.insight}</p>}
              </div>
            )}
          </div>
        )}
      </article>
    </li>
  );
}

function CardsOption() {
  return (
    <div className="h-full overflow-y-auto bg-surface">
      <TripHeader />
      <FilterRow />
      {days.map((day) => (
        <section key={day.day}>
          <DayHeader day={day} />
          <ol className="space-y-1 px-4 py-3">
            {day.stops.map((stop) => <CardStop key={stop.id} stop={stop} />)}
          </ol>
        </section>
      ))}
    </div>
  );
}

/* -------------------------------- C · Editorial ------------------------------- */

function EditorialStop({ stop }: { stop: Stop }) {
  return (
    <li data-lab-change="Stop row" className="group border-t border-slate-100 py-3 first:border-t-0">
      {stop.travel && <TravelChip travel={stop.travel} tone="inline" />}
      <div className="flex items-baseline gap-3">
        <span className="w-12 shrink-0 text-sm font-semibold tabular-nums text-slate-400">
          {stop.time}{stop.estimated ? "*" : ""}
        </span>
        <div className="min-w-0 flex-1">
          <h4 className="display truncate text-[15px] font-semibold text-ink">{stop.name}</h4>
          <p className="mt-0.5 text-[11px] text-slate-500">
            {[
              stop.timing,
              kindMeta[stop.kind].label,
              stop.durationLabel,
              stop.leaveLabel,
              stop.operational,
              stop.cost,
              typeof stop.rating === "number"
                ? `★ ${stop.rating.toFixed(1)}${stop.reviews ? ` (${reviewLabel(stop.reviews)})` : ""}`
                : null,
              typeof stop.score === "number" ? `Must-visit ${stop.score}/100` : null,
            ].filter(Boolean).join(" · ")}
          </p>
        </div>
        {stop.bookable && <StatusPill booked={!!stop.booked} compact />}
        <RowActions removable={stop.planned} />
      </div>
      {(stop.concern || stop.note || stop.insight) && (
        <div className="mt-1.5 space-y-1 pl-[3.75rem]">
          {stop.concern && <p className="text-xs font-medium text-rose-700">{stop.concern}</p>}
          {stop.note && <p className="text-xs italic text-slate-500">{stop.note}</p>}
          {stop.insight && <p className="text-xs italic text-slate-600">{stop.insight}</p>}
        </div>
      )}
    </li>
  );
}

function EditorialOption() {
  return (
    <div className="h-full overflow-y-auto bg-white">
      <TripHeader editorial />
      <FilterRow />
      {days.map((day) => {
        const groups = ["Morning", "Afternoon", "Evening"].map((part) => ({
          part,
          stops: day.stops.filter((stop) => partOfDay(stop.time) === part),
        })).filter((group) => group.stops.length > 0);
        return (
          <section key={day.day} className="px-6 pb-6 pt-6">
            <div data-lab-change="Day header">
              <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-brand">
                Day {day.day} · {day.weekday} {day.date}
              </p>
              <h2 className="display mt-1 text-2xl font-semibold leading-tight text-ink">{day.title}</h2>
              <p className="mt-2 max-w-prose text-sm leading-relaxed text-slate-600">{day.summary}</p>
              <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-slate-100 pt-2.5">
                <span
                  className="inline-flex h-5 items-center rounded-full px-2 text-[10px] font-bold uppercase text-white"
                  style={{ backgroundColor: day.color }}
                >
                  Day {day.day}
                </span>
                <DayMeta day={day} dense />
                <span className="inline-flex items-center gap-1 text-[11px] text-sky-800">
                  {day.weather.summary} {day.weather.high}°/{day.weather.low}°
                  {day.weather.precip >= 30 ? ` · ${day.weather.precip}% rain` : ""}
                </span>
                <a href={day.routeUrl} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[11px] font-semibold text-brand">
                  Open route <ExternalLink size={11} aria-hidden />
                </a>
              </div>
              <p className="mt-1 text-[11px] text-slate-500">
                <span className="font-semibold text-accent">Travel rhythm:</span> {day.rhythm}
              </p>
            </div>
            {groups.map((group) => (
              <div key={group.part} className="mt-4">
                <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">{group.part}</p>
                <ol className="mt-1">
                  {group.stops.map((stop) => <EditorialStop key={stop.id} stop={stop} />)}
                </ol>
              </div>
            ))}
          </section>
        );
      })}
    </div>
  );
}

/* ---------------------------------- Baseline ---------------------------------- */

function TodayStop({ stop }: { stop: Stop }) {
  return (
    <li className="grid grid-cols-[3.75rem_minmax(0,1fr)] gap-2 px-1 py-1.5">
      <div className="pt-0.5">
        <p className="text-[10px] font-bold uppercase text-slate-400">{stop.timing}</p>
        {stop.time && <p className="text-xs font-bold tabular-nums text-ink">{stop.time}{stop.estimated ? " est." : ""}</p>}
        {stop.durationLabel && <p className="mt-0.5 text-[10px] text-slate-500">{stop.durationLabel}</p>}
        {stop.leaveLabel && <p className="mt-0.5 text-[10px] tabular-nums text-slate-600">{stop.leaveLabel}</p>}
      </div>
      <div className="min-w-0">
        {stop.travel && <TravelChip travel={stop.travel} tone="inline" />}
        <div className="flex items-start gap-1.5">
          {stop.marker && (
            <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full border bg-white text-[10px] font-semibold tabular-nums text-slate-600">
              {stop.marker}
            </span>
          )}
          <div className="min-w-0 flex-1">
            <p className="text-[10px] font-bold uppercase text-slate-400">{stop.kind}</p>
            <p className="truncate text-sm font-semibold text-ink">{stop.name}</p>
          </div>
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-1">
          {stop.bookable && <StatusPill booked={!!stop.booked} />}
          <StopChips stop={stop} />
          {stop.planned && (
            <button type="button" className="grid h-6 w-6 place-items-center rounded-full bg-slate-50 text-slate-600 ring-1 ring-slate-200">
              <Trash2 size={12} aria-hidden />
            </button>
          )}
          <button type="button" className="grid h-6 w-6 place-items-center rounded-full text-slate-400">
            <MapPin size={13} aria-hidden />
          </button>
        </div>
        <StopNotes stop={stop} />
      </div>
    </li>
  );
}

function TodayOption() {
  return (
    <div className="h-full overflow-y-auto bg-white">
      <TodayTripHeader />
      <FilterRow />
      <div className="space-y-3 px-4 py-4">
        {days.map((day) => {
          const totals = dayTotals(day);
          return (
            <section key={day.day} className="overflow-hidden rounded-md bg-white shadow-card ring-1 ring-slate-200">
              <div className="px-3 py-2.5">
                <div className="flex items-start gap-3">
                  <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full text-sm font-bold text-white" style={{ backgroundColor: day.color }}>
                    {day.day}
                  </span>
                  <div className="min-w-0">
                    <p className="text-[11px] font-bold uppercase text-brand">{day.weekday} {day.date}</p>
                    <h3 className="display truncate text-lg font-semibold text-ink">{day.title}</h3>
                    <p className="mt-1 text-xs font-medium text-slate-600">
                      {day.weather.summary} · {day.weather.high}° / {day.weather.low}°C
                      {day.weather.precip >= 30 ? ` · ${day.weather.precip}% rain` : ""}
                    </p>
                  </div>
                </div>
                <p className="mt-2 text-xs leading-relaxed text-slate-600">{day.summary}</p>
                <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 border-t border-slate-100 pt-1.5 text-[11px] text-slate-500">
                  <strong className="text-ink">{totals.planned} planned stops</strong>
                  <span className="basis-full">
                    <strong className="font-semibold text-ink">Schedule duration:</strong> {day.schedule.duration} · {day.schedule.start}–{day.schedule.end}{day.schedule.estimated ? " est." : ""}
                  </span>
                  <span className="inline-flex basis-full items-center gap-1">
                    <MapPin size={12} aria-hidden />
                    <strong className="font-semibold text-ink">Day&apos;s travel:</strong> {day.route.duration} · {day.route.distance} · {day.route.mode}
                  </span>
                  <span className={totals.toBook > 0 ? "text-amber-700" : "text-emerald-700"}>
                    {totals.confirmed} confirmed · {totals.toBook} to book
                  </span>
                  <p className="basis-full text-slate-500">
                    <strong className="font-semibold text-accent">Travel rhythm:</strong> {day.rhythm}
                  </p>
                </div>
                <a href={day.routeUrl} target="_blank" rel="noreferrer" className="mt-2 inline-flex h-8 items-center gap-1.5 rounded-full bg-brand px-3 text-xs font-semibold text-white">
                  <Route size={13} aria-hidden /> Open route <ExternalLink size={11} aria-hidden />
                </a>
              </div>
              <ul className="divide-y divide-slate-100 border-t border-slate-200 bg-surface px-3">
                {day.stops.map((stop) => <TodayStop key={stop.id} stop={stop} />)}
              </ul>
            </section>
          );
        })}
      </div>
    </div>
  );
}

export function ItineraryCanvas({ option }: { option: ItineraryOption | "today" }) {
  if (option === "today") return <TodayOption />;
  if (option === "spine") return <SpineOption />;
  if (option === "editorial") return <EditorialOption />;
  return <CardsOption />;
}
