import { BedDouble, CalendarDays, CheckCircle2, Compass, Plane, RefreshCw } from "lucide-react";
import { useId, useState } from "react";
import type { Budget, TripOverview } from "../types";
import { recheckPrices } from "../api";
import WeatherIcon from "./WeatherIcon";
import { formatDate, formatSourceAmount, useDisplayPreferences, type DisplayCurrency } from "../lib/displayPreferences";

type SnapshotTab = "overview" | "weather" | "budget";

interface Props {
  overview: TripOverview;
  booked?: number;
  stops?: number;
  active?: boolean;
  onAllDaysMap?: () => void;
  onTripChanged?: () => void | Promise<void>;
}

function BudgetSummary({ budget, displayCurrency }: { budget: Budget; displayCurrency: DisplayCurrency }) {
  const hasTarget = budget.target != null && budget.target > 0;
  const pct = budget.pct_used ?? 0;
  const tone = budget.over_budget ? "bg-rose-500" : pct >= 80 ? "bg-amber-400" : "bg-sage";

  return (
    <div>
      <div className="flex items-end justify-between gap-3">
        <div>
          <p className="text-[10px] font-semibold uppercase text-muted">Trip spend</p>
          {budget.estimated && (
            <>
              <p className="text-[10px] text-amber-700">
                Final total not confirmed · {budget.all_in_coverage_pct ?? 0}% all-in coverage
              </p>
              {!!budget.required_unknown?.length && (
                <p className="mt-0.5 max-w-64 text-[10px] leading-snug text-muted">
                  Check: {budget.required_unknown.join("; ")}
                </p>
              )}
            </>
          )}
          <p className="mt-0.5 text-base font-semibold tabular-nums text-ink">
            {formatSourceAmount(budget.spent, budget.currency, displayCurrency)}
            {hasTarget && <span className="text-xs font-normal text-muted"> / {formatSourceAmount(budget.target ?? 0, budget.currency, displayCurrency)}</span>}
          </p>
        </div>
        <p className="text-right text-xs text-muted">
          {formatSourceAmount(budget.per_traveler, budget.currency, displayCurrency)} <span className="text-muted">per traveler</span>
        </p>
      </div>
      {hasTarget && (
        <>
          <div className="mt-2 h-1.5 overflow-hidden rounded-sm bg-sand">
            <div className={`h-full rounded-sm ${tone}`} style={{ width: `${Math.min(pct, 100)}%` }} />
          </div>
          <div className="mt-1 flex justify-between text-[11px] text-muted">
            <span className={budget.over_budget ? "font-medium text-rose-700" : ""}>
              {budget.remaining != null ? formatSourceAmount(Math.abs(budget.remaining), budget.currency, displayCurrency) : ""} {budget.over_budget ? "over" : "left"}
            </span>
            <span>{pct}% used</span>
          </div>
        </>
      )}
      {budget.all_in_spent != null && (
        <p className="mt-1.5 text-[11px] font-medium text-emerald-700">
          Confirmed all-in: {formatSourceAmount(budget.all_in_spent, budget.currency, displayCurrency)}
        </p>
      )}
    </div>
  );
}

/**
 * The trip's one authoritative snapshot. Identity and cost stay above the tabs;
 * Overview, Weather and Budget panels all stay mounted, and the inactive ones are
 * hidden, so every fact is one tap away without lengthening the pane.
 */
export default function TripSnapshot({
  overview,
  booked,
  stops,
  active = false,
  onAllDaysMap,
  onTripChanged,
}: Props) {
  const { currency } = useDisplayPreferences();
  const [rechecking, setRechecking] = useState(false);
  const [recheckOutcome, setRecheckOutcome] = useState("");
  const [tab, setTab] = useState<SnapshotTab>("overview");
  // useId returns ":r0:"; colons are not safe in id selectors that label lookups may use.
  const idBase = `trip-snapshot${useId().replace(/:/g, "")}`;
  const statusTone = overview.status === "booked"
    ? "border-brand/30 bg-brand/10 text-brand"
    : overview.status === "finalized"
      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
      : "border-border bg-paper text-muted";
  const countFacts = [
    { label: "days", value: overview.counts.days, icon: CalendarDays },
    { label: overview.counts.hotels === 1 ? "stay" : "stays", value: overview.counts.hotels, icon: BedDouble },
    { label: "places", value: overview.counts.activities, icon: Compass },
    { label: overview.counts.flights === 1 ? "flight" : "flights", value: overview.counts.flights, icon: Plane },
  ];
  const dateRange = [overview.departure_date, overview.return_date].filter(Boolean).map((date) => formatDate(date)).join(" - ");
  const travelersLabel = `${overview.travelers} ${Number(overview.travelers) === 1 ? "traveler" : "travelers"}`;
  const costEvidence = overview.cost_evidence ?? null;
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
  const tabs: Array<[SnapshotTab, string]> = [
    ["overview", "Overview"],
    ["weather", "Weather"],
    ...(overview.budget ? [["budget", "Budget"] as [SnapshotTab, string]] : []),
  ];

  async function runPriceRecheck() {
    setRechecking(true);
    setRecheckOutcome("");
    try {
      const result = await recheckPrices();
      const changed = result.results.filter((row) => row.delta != null && row.delta !== 0).length;
      const unavailable = result.results.filter((row) => row.status !== "live").length;
      setRecheckOutcome(
        changed > 0
          ? `Rechecked ${result.rechecked}; ${changed} price${changed === 1 ? "" : "s"} changed.`
          : unavailable > 0
            ? `Rechecked ${result.rechecked}; ${unavailable} could not be confirmed.`
            : result.message,
      );
      await onTripChanged?.();
    } catch {
      setRecheckOutcome("Could not recheck prices just now.");
    } finally {
      setRechecking(false);
    }
  }

  return (
    <section
      aria-label="Trip snapshot"
      aria-current={active ? "true" : undefined}
      tabIndex={onAllDaysMap ? 0 : undefined}
      onClick={onAllDaysMap}
      onKeyDown={(event) => {
        // Keys pressed on the tabs or the recheck action belong to those controls.
        if (!onAllDaysMap || event.target !== event.currentTarget || (event.key !== "Enter" && event.key !== " ")) return;
        event.preventDefault();
        onAllDaysMap();
      }}
      className={`border-b px-3.5 pb-3 pt-3.5 transition ${
        active
          ? "border-brand/30 bg-brand/5 ring-inset ring-2 ring-brand/20"
          : onAllDaysMap
            ? "cursor-pointer border-border bg-paper hover:bg-background"
            : "border-border bg-paper"
      }`}
      title={onAllDaysMap ? "Show all itinerary days on map" : undefined}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <span className={`inline-flex rounded border px-1.5 py-px text-[10px] font-semibold uppercase tracking-[0.06em] ${statusTone}`}>
            {overview.status}
          </span>
          <h1 className="display mt-1 text-2xl leading-tight font-normal text-ink">
            {overview.destination || "Your trip"}
          </h1>
          <p className="mt-1 text-xs leading-relaxed text-muted">
            {[overview.origin && `From ${overview.origin}`, dateRange, travelersLabel].filter(Boolean).join(" · ")}
          </p>
        </div>
        <div className="shrink-0 text-right">
          {overview.total_cost != null && (
            <p className="text-base font-semibold tabular-nums text-ink">{formatSourceAmount(overview.total_cost, overview.budget?.currency || "USD", currency)}</p>
          )}
          {costEvidence?.summary && (
            <p
              className={`mt-0.5 text-[10px] font-medium ${
                costEvidence.complete ? "text-emerald-700" : "text-amber-700"
              }`}
              title={
                costEvidence.complete
                  ? "Every item is backed by a current provider quote."
                  : "Some items are not backed by a current provider quote."
              }
            >
              {costEvidence.summary}
            </p>
          )}
          {!!overview.price_rechecks?.length && (
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                void runPriceRecheck();
              }}
              disabled={rechecking}
              className="mt-1 inline-flex items-center gap-1 text-[10px] font-semibold text-brand disabled:opacity-60"
            >
              <RefreshCw className={`h-3 w-3 ${rechecking ? "animate-spin" : ""}`} aria-hidden />
              {rechecking ? "Rechecking prices…" : "Recheck prices"}
            </button>
          )}
          {recheckOutcome && <p className="mt-1 max-w-52 text-[10px] text-muted">{recheckOutcome}</p>}
        </div>
      </div>

      <div role="tablist" aria-label="Trip snapshot sections" className="mt-3 flex gap-0.5 rounded-md bg-sand p-0.5">
        {tabs.map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            id={`${idBase}-tab-${id}`}
            aria-selected={tab === id}
            aria-controls={`${idBase}-panel-${id}`}
            onClick={(event) => {
              event.stopPropagation();
              setTab(id);
            }}
            className={`h-7 flex-1 rounded text-[12px] font-semibold transition ${
              tab === id ? "bg-paper text-ink shadow-sm ring-1 ring-border" : "text-muted hover:text-ink"
            }`}
          >
            {label}
            {id === "budget" && overview.budget?.pct_used != null && (
              <span className="ml-1 font-normal tabular-nums text-muted">{overview.budget.pct_used}%</span>
            )}
          </button>
        ))}
      </div>

      <div
        role="tabpanel"
        id={`${idBase}-panel-overview`}
        aria-labelledby={`${idBase}-tab-overview`}
        hidden={tab !== "overview"}
        className="mt-3 space-y-3"
      >
        <p className="text-[13px] leading-relaxed text-ink/80">{tripSummary}</p>
        {stops != null && booked != null && (
          <div>
            <div className="flex items-center justify-between gap-3 text-xs">
              <span className="inline-flex items-center gap-1.5 font-semibold text-ink">
                <CheckCircle2 size={13} className="text-emerald-600" aria-hidden />
                {booked} of {stops} ready
              </span>
              <span className={remainingStops ? "text-amber-700" : "text-emerald-700"}>
                {remainingStops ? `${remainingStops} need booking` : "All confirmed"}
              </span>
            </div>
            <div className="mt-1.5 h-1.5 overflow-hidden rounded-sm bg-sand" aria-label={`${readinessPct}% of stops ready`}>
              <div className="h-full rounded-sm bg-sage" style={{ width: `${readinessPct}%` }} />
            </div>
          </div>
        )}
        <div className="grid grid-cols-4 divide-x divide-border rounded-md border border-border">
          {countFacts.map(({ label, value, icon: Icon }) => (
            <div key={label} aria-label={`${value} ${label}`} className="flex min-w-0 flex-col items-center gap-0.5 py-1.5">
              <span className="inline-flex items-center gap-1 text-[13px] font-semibold tabular-nums text-ink">
                <Icon size={12} className="shrink-0 text-muted" aria-hidden />
                {value}
              </span>
              <span className="truncate text-[10px] text-muted">{label}</span>
            </div>
          ))}
        </div>
        {overview.family_pills && overview.family_pills.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {overview.family_pills.map((pill) => <span key={pill} className="chip">{pill}</span>)}
          </div>
        )}
        {overview.constraints && overview.constraints.length > 0 && (
          <p className="text-xs leading-relaxed text-muted">
            <span className="font-semibold text-ink">For this trip:</span>{" "}
            {overview.constraints.join(" · ")}
          </p>
        )}
      </div>

      <div
        role="tabpanel"
        id={`${idBase}-panel-weather`}
        aria-labelledby={`${idBase}-tab-weather`}
        hidden={tab !== "weather"}
        className="mt-3"
      >
        <div className="flex items-center justify-between gap-3">
          <p className="text-[10px] font-semibold uppercase text-muted">Weather</p>
          {overview.weather && (
            <span className="text-[10px] font-medium text-muted">{overview.weather.source_label}</span>
          )}
        </div>
        {overview.weather ? (
          <>
            <div className="mt-2 flex flex-wrap gap-1.5" aria-label={`${overview.weather.source_label} weather summary`}>
              {overview.weather.days.map((day, index) => (
                <span
                  key={day.date}
                  className="inline-flex h-7 items-center gap-1 rounded border border-border bg-paper px-2 text-[11px] font-medium text-ink"
                  title={`${day.date}: ${day.summary}${day.precip_probability_pct != null ? `, ${day.precip_probability_pct}% precipitation` : ""}`}
                >
                  <span className="text-sky-700"><WeatherIcon condition={day.condition} size={14} /></span>
                  <span>D{index + 1}</span>
                  {day.high_c != null && <span className="tabular-nums">{Math.round(day.high_c)}°</span>}
                </span>
              ))}
            </div>
            {overview.weather.packing_advice.length > 0 && (
              <p className="mt-2 text-xs leading-relaxed text-muted">
                <span className="font-semibold text-ink">Pack:</span>{" "}
                {overview.weather.packing_advice.join(". ")}.
              </p>
            )}
          </>
        ) : (
          <p className="mt-2 text-xs text-muted">Forecast unavailable for this trip.</p>
        )}
      </div>

      {overview.budget && (
        <div
          role="tabpanel"
          id={`${idBase}-panel-budget`}
          aria-labelledby={`${idBase}-tab-budget`}
          hidden={tab !== "budget"}
          className="mt-3"
        >
          <BudgetSummary budget={overview.budget} displayCurrency={currency} />
        </div>
      )}
    </section>
  );
}
