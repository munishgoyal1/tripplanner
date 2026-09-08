import {
  BedDouble,
  CalendarDays,
  ChevronDown,
  Cloud,
  CloudRain,
  Compass,
  Plane,
  Sun,
} from "lucide-react";
import { useState } from "react";
import { bookingTotals, days, trip } from "../shared/tripFixture";
import type { Weather } from "../shared/tripFixture";

const WeatherGlyph = ({ condition, size = 14 }: { condition: Weather["condition"]; size?: number }) =>
  condition === "rain" ? <CloudRain size={size} aria-hidden /> : condition === "cloud" ? <Cloud size={size} aria-hidden /> : <Sun size={size} aria-hidden />;

const counts = [
  { label: "days", value: trip.counts.days, Icon: CalendarDays },
  { label: "stay", value: trip.counts.stays, Icon: BedDouble },
  { label: "places", value: trip.counts.places, Icon: Compass },
  { label: "flights", value: trip.counts.flights, Icon: Plane },
];

const readiness = Math.round((bookingTotals.booked / bookingTotals.stops) * 100);
const remaining = bookingTotals.stops - bookingTotals.booked;

/** Today's production presentation: every fact stacked, always expanded. */
export function TodayTripHeader() {
  return (
    <section className="border-b border-slate-200 bg-white px-4 py-4">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase text-brand">Trip snapshot</p>
          <h1 className="display mt-0.5 truncate text-xl font-semibold text-ink">{trip.destination}</h1>
          <p className="mt-1 truncate text-xs text-slate-500">
            From {trip.origin} · {trip.dateRange} · {trip.travelers} travelers
          </p>
        </div>
        <div className="shrink-0 text-right">
          <span className="inline-flex rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-semibold capitalize text-slate-600 ring-1 ring-slate-200">
            {trip.status}
          </span>
          <p className="mt-1.5 text-sm font-semibold text-ink">{trip.totalCost}</p>
        </div>
      </div>
      <p className="mt-3 text-sm leading-relaxed text-slate-600">{trip.summary}</p>
      <div className="mt-3 border-t border-slate-200 pt-3">
        <div className="flex items-center justify-between gap-3 text-xs">
          <span className="font-semibold text-ink">{bookingTotals.booked} of {bookingTotals.stops} ready</span>
          <span className="text-amber-700">{remaining} need booking</span>
        </div>
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100">
          <div className="h-full rounded-full bg-emerald-500" style={{ width: `${readiness}%` }} />
        </div>
      </div>
      <div className="mt-3 grid grid-cols-4 divide-x divide-slate-200 border-y border-slate-200 py-1.5">
        {counts.map(({ label, value, Icon }) => (
          <div key={label} className="flex min-w-0 items-center justify-center gap-1 px-1.5">
            <Icon size={12} className="shrink-0 text-slate-400" aria-hidden />
            <p className="text-xs font-semibold tabular-nums text-ink">{value}</p>
            <span className="truncate text-[9px] font-medium uppercase text-slate-400">{label}</span>
          </div>
        ))}
      </div>
      <div className="mt-3 border-t border-slate-200 pt-3">
        <div className="flex items-center justify-between gap-3">
          <p className="text-[10px] font-semibold uppercase text-slate-400">Weather</p>
          <span className="text-[10px] font-medium text-slate-500">{trip.weatherSource}</span>
        </div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {days.map((day, index) => (
            <span
              key={day.day}
              className="inline-flex h-7 items-center gap-1 rounded-md bg-sky-50 px-2 text-[11px] font-medium text-slate-700 ring-1 ring-sky-100"
            >
              <span className="text-sky-700"><WeatherGlyph condition={day.weather.condition} /></span>
              <span>D{index + 1}</span>
              <span className="tabular-nums">{day.weather.high}°</span>
            </span>
          ))}
        </div>
        <p className="mt-2 text-xs leading-relaxed text-slate-600">
          <span className="font-semibold text-slate-700">Pack:</span> {trip.packing}.
        </p>
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {trip.familyPills.map((pill) => <span key={pill} className="chip">{pill}</span>)}
      </div>
      <p className="mt-3 text-xs leading-relaxed text-slate-500">
        <span className="font-semibold text-slate-700">For this trip:</span> {trip.constraints.join(" · ")}
      </p>
      <div className="mt-3 border-t border-slate-200 pt-3">
        <div className="flex items-end justify-between gap-3">
          <div>
            <p className="text-[10px] font-semibold uppercase text-slate-400">Trip spend</p>
            <p className="mt-0.5 text-base font-semibold text-ink">
              {trip.budget.spent}<span className="text-xs font-normal text-slate-400"> / {trip.budget.target}</span>
            </p>
          </div>
          <p className="text-right text-xs text-slate-500">
            {trip.budget.perTraveler} <span className="text-slate-400">per traveler</span>
          </p>
        </div>
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100">
          <div className="h-full rounded-full bg-amber-400" style={{ width: `${trip.budget.pct}%` }} />
        </div>
        <div className="mt-1 flex justify-between text-[11px] text-slate-500">
          <span>{trip.budget.remaining}</span>
          <span>{trip.budget.pct}% used</span>
        </div>
      </div>
    </section>
  );
}

/**
 * Reimagined header. The four facts the owner acts on stay permanently visible;
 * every remaining production fact moves one keystroke away behind Trip context,
 * so nothing is dropped and the agenda starts near the top of the pane.
 */
export function TripHeader({ editorial = false }: { editorial?: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <section
      data-lab-change="Trip header"
      className="sticky top-0 z-20 border-b border-slate-200/80 bg-white/90 px-5 py-4 backdrop-blur"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className={`display truncate font-semibold text-ink ${editorial ? "text-[1.7rem] leading-tight" : "text-2xl"}`}>
            {trip.destination}
          </h1>
          <p className="mt-1 truncate text-xs text-slate-500">
            {trip.dateRange.replace(" - ", " – ")} · {trip.travelers} travelers · from {trip.origin}
          </p>
        </div>
        <div className="shrink-0 text-right">
          <p className="text-base font-semibold tabular-nums text-ink">{trip.totalCost}</p>
          <p className="text-[11px] text-slate-400">of {trip.budget.target}</p>
        </div>
      </div>

      <div className="mt-3 flex items-center gap-3">
        <div className="h-1 flex-1 overflow-hidden rounded-full bg-slate-100" role="img" aria-label={`${readiness}% of stops ready`}>
          <div className="h-full rounded-full bg-emerald-500 transition-[width]" style={{ width: `${readiness}%` }} />
        </div>
        <p className="shrink-0 text-[11px] font-semibold text-ink">
          {bookingTotals.booked}<span className="font-normal text-slate-400">/{bookingTotals.stops} ready</span>
        </p>
        <span className="shrink-0 rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-700">
          {remaining} to book
        </span>
      </div>

      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="mt-3 flex w-full items-center gap-2 rounded-xl px-2 py-1.5 text-left text-[11px] font-medium text-slate-500 transition hover:bg-slate-50"
      >
        <span className="flex items-center gap-2.5">
          {counts.map(({ label, value, Icon }) => (
            <span key={label} className="inline-flex items-center gap-1 tabular-nums text-slate-600">
              <Icon size={12} className="text-slate-400" aria-hidden />
              {value}
              <span className="text-slate-400">{label}</span>
            </span>
          ))}
        </span>
        <span className="ml-auto inline-flex items-center gap-1 text-slate-400">
          Trip context
          <ChevronDown size={13} className={`transition ${open ? "rotate-180" : ""}`} aria-hidden />
        </span>
      </button>

      {open && (
        <div className="mt-2 space-y-3 rounded-2xl bg-surface p-3 ring-1 ring-slate-200">
          <p className="text-xs leading-relaxed text-slate-600">{trip.summary}</p>
          <div>
            <div className="flex items-center justify-between">
              <p className="text-[10px] font-bold uppercase text-slate-400">Weather</p>
              <span className="text-[10px] text-slate-400">{trip.weatherSource}</span>
            </div>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {days.map((day, index) => (
                <span
                  key={day.day}
                  title={`${day.date}: ${day.weather.summary}, ${day.weather.precip}% precipitation`}
                  className="inline-flex h-7 items-center gap-1 rounded-lg bg-white px-2 text-[11px] font-medium text-slate-700 ring-1 ring-slate-200"
                >
                  <span className="text-accent"><WeatherGlyph condition={day.weather.condition} /></span>
                  D{index + 1}
                  <span className="tabular-nums text-slate-500">{day.weather.high}° / {day.weather.low}°</span>
                </span>
              ))}
            </div>
            <p className="mt-1.5 text-xs leading-relaxed text-slate-600">
              <span className="font-semibold text-slate-700">Pack:</span> {trip.packing}.
            </p>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {trip.familyPills.map((pill) => <span key={pill} className="chip">{pill}</span>)}
          </div>
          <p className="text-xs leading-relaxed text-slate-500">
            <span className="font-semibold text-slate-700">For this trip:</span> {trip.constraints.join(" · ")}
          </p>
          <div className="border-t border-slate-200 pt-2.5">
            <div className="flex items-end justify-between gap-3">
              <p className="text-sm font-semibold text-ink">
                {trip.budget.spent}<span className="text-xs font-normal text-slate-400"> / {trip.budget.target}</span>
              </p>
              <p className="text-[11px] text-slate-500">{trip.budget.perTraveler} per traveler</p>
            </div>
            <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-slate-200">
              <div className="h-full rounded-full bg-amber-400" style={{ width: `${trip.budget.pct}%` }} />
            </div>
            <div className="mt-1 flex justify-between text-[11px] text-slate-500">
              <span>{trip.budget.remaining}</span>
              <span>{trip.budget.pct}% used</span>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
