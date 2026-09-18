import { useState } from "react";
import { BedDouble, CalendarDays, Compass, Plane } from "lucide-react";
import { formatDate, formatSourceAmount } from "../../../src/lib/displayPreferences";
import { verificationHeadline } from "./fixture";
import type { PlannerState } from "./state";

/** Trip-level facts shared by every option's snapshot, derived as TripSnapshot does. */
export function tripFacts(state: PlannerState) {
  const { overview, stats, currency } = state;
  const travelersLabel = `${overview.travelers} ${Number(overview.travelers) === 1 ? "traveler" : "travelers"}`;
  const dateRange = [overview.departure_date, overview.return_date].filter(Boolean).map((date) => formatDate(date)).join(" - ");
  const remaining = Math.max(stats.stops - stats.booked, 0);
  const budget = overview.budget ?? null;
  return {
    travelersLabel,
    dateRange,
    metaLine: [overview.origin && `From ${overview.origin}`, dateRange, travelersLabel].filter(Boolean).join(" · "),
    summary: overview.notes.trim(),
    readinessPct: stats.stops ? Math.round((stats.booked / stats.stops) * 100) : 0,
    remaining,
    readyText: `${stats.booked} of ${stats.stops} ready`,
    remainingText: remaining ? `${remaining} need booking` : "All confirmed",
    total: overview.total_cost != null ? formatSourceAmount(overview.total_cost, overview.budget?.currency || "USD", currency) : null,
    costEvidence: overview.cost_evidence ?? null,
    canRecheck: !!overview.price_rechecks?.length,
    counts: [
      { label: "days", value: overview.counts.days, Icon: CalendarDays },
      { label: overview.counts.hotels === 1 ? "stay" : "stays", value: overview.counts.hotels, Icon: BedDouble },
      { label: "places", value: overview.counts.activities, Icon: Compass },
      { label: overview.counts.flights === 1 ? "flight" : "flights", value: overview.counts.flights, Icon: Plane },
    ],
    budget: budget && {
      raw: budget,
      spent: formatSourceAmount(budget.spent, budget.currency, currency),
      target: budget.target != null && budget.target > 0 ? formatSourceAmount(budget.target, budget.currency, currency) : null,
      perTraveler: formatSourceAmount(budget.per_traveler, budget.currency, currency),
      pct: budget.pct_used ?? 0,
      remaining: budget.remaining != null ? formatSourceAmount(Math.abs(budget.remaining), budget.currency, currency) : "",
      remainingWord: budget.over_budget ? "over" : "left",
      allIn: budget.all_in_spent != null ? formatSourceAmount(budget.all_in_spent, budget.currency, currency) : null,
      estimatedText: budget.estimated ? `Final total not confirmed · ${budget.all_in_coverage_pct ?? 0}% all-in coverage` : null,
      check: budget.estimated && budget.required_unknown?.length ? `Check: ${budget.required_unknown.join("; ")}` : null,
      tone: budget.over_budget ? "bg-rose-500" : (budget.pct_used ?? 0) >= 80 ? "bg-amber-400" : "bg-sage",
    },
    weather: overview.weather ?? null,
    packing: overview.weather?.packing_advice.length ? `${overview.weather.packing_advice.join(". ")}.` : null,
    familyPills: overview.family_pills ?? [],
    constraints: overview.constraints?.length ? overview.constraints.join(" · ") : null,
  };
}

export function checkFacts(state: PlannerState) {
  const report = state.verification;
  return {
    report,
    headline: verificationHeadline[report.verdict],
    countsText: `${report.counts.passed} passed${report.counts.failed > 0 ? ` · ${report.counts.failed} failed` : ""}${report.counts.unverified > 0 ? ` · ${report.counts.unverified} unverified` : ""}`,
    contradictions: report.checks.filter((check) => check.status === "failed" && check.severity === "contradiction").flatMap((check) => check.findings.map((finding) => ({ key: `${check.code}-${finding}`, finding }))),
    advisories: report.checks.filter((check) => check.status === "failed" && check.severity === "advisory").flatMap((check) => check.findings.map((finding) => ({ key: `${check.code}-${finding}`, finding: `${finding} (estimated travel time)` }))),
    holidays: report.days.filter((day) => day.holiday).map((day) => `Day ${day.day} · ${day.holiday} — opening hours may differ`),
    gaps: report.unverified_stops.map((gap) => `Day ${gap.day} · ${gap.name} — no ${gap.missing.join(", no ")}`),
    lastChecked: report.freshness?.checked_at ? `Last checked ${new Date(report.freshness.checked_at).toLocaleString()}` : null,
  };
}

/** The add/reduce-day confirmation shared by all options; only its surface differs. */
export function useTripLength() {
  const [pending, setPending] = useState<"add" | "reduce" | null>(null);
  const [replan, setReplan] = useState(false);
  return {
    pending,
    replan,
    setReplan,
    open: (direction: "add" | "reduce") => {
      setReplan(false);
      setPending(direction);
    },
    close: () => setPending(null),
    title: pending === "add" ? "Add one more day" : "Remove one day",
    body: pending === "add"
      ? "Dates, hotel nights and departure plans will update automatically with minimal changes."
      : "Dates, hotel nights and the remaining stops will be adjusted coherently with minimal changes.",
    confirmLabel: pending === "add" ? "Add day and update trip" : "Reduce day and update trip",
  };
}

export function rainText(pct: number | null | undefined): string | null {
  return pct != null && pct >= 30 ? `${Math.round(pct)}% rain` : null;
}

export function weatherAria(day: { summary: string; high_c: number | null; low_c: number | null }) {
  return `${day.summary}, high ${day.high_c ?? "unknown"} degrees Celsius, low ${day.low_c ?? "unknown"} degrees Celsius`;
}
