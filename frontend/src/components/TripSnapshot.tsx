import { BedDouble, CalendarDays, CheckCircle2, Compass, Plane, Users } from "lucide-react";
import type { Budget, TripOverview } from "../types";

interface Props {
  overview: TripOverview;
  booked?: number;
  stops?: number;
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

export default function TripSnapshot({ overview, booked, stops }: Props) {
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

  return (
    <section aria-label="Trip snapshot" className="border-b border-slate-200 bg-white px-4 py-4">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase text-brand">Trip snapshot</p>
          <h1 className="display mt-0.5 truncate text-xl font-semibold text-ink">
            {overview.destination || "Your trip"}
          </h1>
          <p className="mt-1 truncate text-xs text-slate-500">
            {[overview.origin && `From ${overview.origin}`, dateRange].filter(Boolean).join(" · ")}
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

      <div className="mt-4 grid grid-cols-4 divide-x divide-slate-200 border-y border-slate-200 py-2.5">
        {countFacts.map(({ label, value, icon: Icon }) => (
          <div key={label} aria-label={`${value} ${label}`} className="min-w-0 px-2 first:pl-0 last:pr-0">
            <div className="flex items-center gap-1.5 text-slate-400">
              <Icon size={13} aria-hidden />
              <span className="truncate text-[10px] uppercase">{label}</span>
            </div>
            <p className="mt-0.5 text-base font-semibold tabular-nums text-ink">{value}</p>
          </div>
        ))}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-slate-600">
        <span className="inline-flex items-center gap-1.5">
          <Users size={13} className="text-slate-400" aria-hidden />
          {overview.travelers} {Number(overview.travelers) === 1 ? "traveler" : "travelers"}
        </span>
        {stops != null && booked != null && (
          <span className="inline-flex items-center gap-1.5">
            <CheckCircle2 size={13} className="text-slate-400" aria-hidden />
            {booked}/{stops} stops booked
          </span>
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