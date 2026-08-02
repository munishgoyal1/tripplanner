import { BedDouble, CalendarDays, CheckCircle2, Compass, Plane } from "lucide-react";
import type { Budget, TripOverview } from "../types";
import WeatherIcon from "./WeatherIcon";

interface Props {
  overview: TripOverview;
  booked?: number;
  stops?: number;
  active?: boolean;
  onAllDaysMap?: () => void;
}

function BudgetSummary({ budget }: { budget: Budget }) {
  const hasTarget = budget.target != null && budget.target > 0;
  const pct = budget.pct_used ?? 0;
  const tone = budget.over_budget ? "bg-rose-500" : pct >= 80 ? "bg-amber-400" : "bg-emerald-500";

  return (
    <div className="border-t border-slate-200 pt-3">
      <div className="flex items-end justify-between gap-3">
        <div>
          <p className="text-[10px] font-semibold uppercase text-slate-400">Trip spend</p>
          <p className="mt-0.5 text-base font-semibold text-ink">
            {budget.spent_display}
            {hasTarget && <span className="text-xs font-normal text-slate-400"> / {budget.target_display}</span>}
          </p>
        </div>
        <p className="text-right text-xs text-slate-500">
          {budget.per_traveler_display} <span className="text-slate-400">per traveler</span>
        </p>
      </div>
      {hasTarget && (
        <>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100">
            <div className={`h-full rounded-full ${tone}`} style={{ width: `${Math.min(pct, 100)}%` }} />
          </div>
          <div className="mt-1 flex justify-between text-[11px] text-slate-500">
            <span className={budget.over_budget ? "font-medium text-rose-700" : ""}>
              {budget.remaining_display} {budget.over_budget ? "over" : "left"}
            </span>
            <span>{pct}% used</span>
          </div>
        </>
      )}
    </div>
  );
}

export default function TripSnapshot({ overview, booked, stops, active = false, onAllDaysMap }: Props) {
  const statusTone = overview.status === "booked"
    ? "bg-brand/10 text-brand ring-brand/20"
    : overview.status === "finalized"
      ? "bg-emerald-50 text-emerald-700 ring-emerald-200"
      : "bg-slate-100 text-slate-600 ring-slate-200";
  const countFacts = [
    { label: "days", value: overview.counts.days, icon: CalendarDays },
    { label: overview.counts.hotels === 1 ? "stay" : "stays", value: overview.counts.hotels, icon: BedDouble },
    { label: "places", value: overview.counts.activities, icon: Compass },
    { label: overview.counts.flights === 1 ? "flight" : "flights", value: overview.counts.flights, icon: Plane },
  ];
  const dateRange = [overview.departure_date, overview.return_date].filter(Boolean).join(" - ");
  const travelersLabel = `${overview.travelers} ${Number(overview.travelers) === 1 ? "traveler" : "travelers"}`;
  const remainingStops = stops != null && booked != null ? Math.max(stops - booked, 0) : null;
  const readinessPct = stops ? Math.round(((booked ?? 0) / stops) * 100) : 0;
  const tripSummary = overview.notes.trim() || [
    overview.counts.days > 0 ? `${overview.counts.days}-day` : "Planned",
    overview.destination,
    `trip for ${travelersLabel}`,
    overview.counts.activities > 0
      ? `with ${overview.counts.activities} planned ${overview.counts.activities === 1 ? "place" : "places"}.`
      : "with itinerary details still being planned.",
  ].filter(Boolean).join(" ");

  return (
    <section
      aria-label="Trip snapshot"
      aria-current={active ? "true" : undefined}
      tabIndex={onAllDaysMap ? 0 : undefined}
      onClick={onAllDaysMap}
      onKeyDown={(event) => {
        if (!onAllDaysMap || (event.key !== "Enter" && event.key !== " ")) return;
        event.preventDefault();
        onAllDaysMap();
      }}
      className={`border-b px-4 py-4 transition ${
        active
          ? "border-brand/30 bg-brand/5 ring-inset ring-2 ring-brand/20"
          : onAllDaysMap
            ? "cursor-pointer border-slate-200 bg-white hover:bg-slate-50"
            : "border-slate-200 bg-white"
      }`}
      title={onAllDaysMap ? "Show all itinerary days on map" : undefined}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase text-brand">Trip snapshot</p>
          <h1 className="display mt-0.5 truncate text-xl font-semibold text-ink">
            {overview.destination || "Your trip"}
          </h1>
          <p className="mt-1 truncate text-xs text-slate-500">
            {[overview.origin && `From ${overview.origin}`, dateRange, travelersLabel].filter(Boolean).join(" · ")}
          </p>
        </div>
        <div className="shrink-0 text-right">
          <span className={`inline-flex rounded-full px-2.5 py-1 text-[11px] font-semibold capitalize ring-1 ${statusTone}`}>
            {overview.status}
          </span>
          {overview.total_cost_display && (
            <p className="mt-1.5 text-sm font-semibold text-ink">{overview.total_cost_display}</p>
          )}
        </div>
      </div>

      <p className="mt-3 text-sm leading-relaxed text-slate-600">{tripSummary}</p>

      {stops != null && booked != null && (
        <div className="mt-3 border-t border-slate-200 pt-3">
          <div className="flex items-center justify-between gap-3 text-xs">
            <span className="inline-flex items-center gap-1.5 font-semibold text-ink">
              <CheckCircle2 size={13} className="text-emerald-600" aria-hidden />
              {booked} of {stops} ready
            </span>
            <span className={remainingStops ? "text-amber-700" : "text-emerald-700"}>
              {remainingStops ? `${remainingStops} need booking` : "All confirmed"}
            </span>
          </div>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100" aria-label={`${readinessPct}% of stops ready`}>
            <div className="h-full rounded-full bg-emerald-500" style={{ width: `${readinessPct}%` }} />
          </div>
        </div>
      )}

      <div className="mt-3 grid grid-cols-4 divide-x divide-slate-200 border-y border-slate-200 py-1.5">
        {countFacts.map(({ label, value, icon: Icon }) => (
          <div key={label} aria-label={`${value} ${label}`} className="flex min-w-0 items-center justify-center gap-1 px-1.5">
            <Icon size={12} className="shrink-0 text-slate-400" aria-hidden />
            <p className="text-xs font-semibold tabular-nums text-ink">{value}</p>
            <span className="truncate text-[9px] font-medium uppercase text-slate-400">{label}</span>
          </div>
        ))}
      </div>

      <div className="mt-3 border-t border-slate-200 pt-3">
        <div className="flex items-center justify-between gap-3">
          <p className="text-[10px] font-semibold uppercase text-slate-400">Weather</p>
          {overview.weather && (
            <span className="text-[10px] font-medium text-slate-500">{overview.weather.source_label}</span>
          )}
        </div>
        {overview.weather ? (
          <>
          <div className="mt-2 flex flex-wrap gap-1.5" aria-label={`${overview.weather.source_label} weather summary`}>
            {overview.weather.days.map((day, index) => (
              <span
                key={day.date}
                className="inline-flex h-7 items-center gap-1 rounded-md bg-sky-50 px-2 text-[11px] font-medium text-slate-700 ring-1 ring-sky-100"
                title={`${day.date}: ${day.summary}${day.precip_probability_pct != null ? `, ${day.precip_probability_pct}% precipitation` : ""}`}
              >
                <span className="text-sky-700"><WeatherIcon condition={day.condition} size={14} /></span>
                <span>D{index + 1}</span>
                {day.high_c != null && <span className="tabular-nums">{Math.round(day.high_c)}°</span>}
              </span>
            ))}
          </div>
          {overview.weather.packing_advice.length > 0 && (
            <p className="mt-2 text-xs leading-relaxed text-slate-600">
              <span className="font-semibold text-slate-700">Pack:</span>{" "}
              {overview.weather.packing_advice.join(". ")}.
            </p>
          )}
          </>
        ) : (
          <p className="mt-2 text-xs text-slate-500">Forecast unavailable for this trip.</p>
        )}
      </div>

      {overview.family_pills && overview.family_pills.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {overview.family_pills.map((pill) => <span key={pill} className="chip">{pill}</span>)}
        </div>
      )}
      {overview.constraints && overview.constraints.length > 0 && (
        <p className="mt-3 text-xs leading-relaxed text-slate-500">
          <span className="font-semibold text-slate-700">For this trip:</span>{" "}
          {overview.constraints.join(" · ")}
        </p>
      )}
      {overview.budget && <div className="mt-3"><BudgetSummary budget={overview.budget} /></div>}
    </section>
  );
}