import { AlertTriangle, CheckCircle2, HelpCircle, ShieldCheck, Wand2 } from "lucide-react";
import { useEffect, useState } from "react";
import { fetchVerification, repairTrip } from "../api";
import type { TripVerification, VerificationStatus } from "../types";

const TONE: Record<VerificationStatus, { icon: typeof CheckCircle2; className: string }> = {
  passed: { icon: CheckCircle2, className: "text-emerald-600" },
  failed: { icon: AlertTriangle, className: "text-rose-600" },
  unverified: { icon: HelpCircle, className: "text-amber-600" },
};

const HEADLINE: Record<TripVerification["verdict"], string> = {
  clear: "Everything we can check, checks out",
  partial: "Checked, with gaps we could not confirm",
  advisories: "Checked — a couple of days look tight",
  issues: "This plan contradicts itself",
  unverified: "Nothing to check yet",
};

/** What the planner verified on this trip, including what it could not verify.
 *
 * The unverified column is the point: an itinerary nobody could check must not
 * look like one that passed.
 */
export default function TripVerificationCard({
  revision,
  onRepaired,
}: {
  revision?: number;
  onRepaired?: () => void;
}) {
  const [report, setReport] = useState<TripVerification | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [repairing, setRepairing] = useState(false);
  const [outcome, setOutcome] = useState<string[]>([]);

  useEffect(() => {
    const controller = new AbortController();
    fetchVerification(controller.signal)
      .then(setReport)
      .catch(() => {
        /* a missing report is not worth interrupting the itinerary for */
      });
    return () => controller.abort();
  }, [revision]);

  async function runRepair() {
    setRepairing(true);
    try {
      const result = await repairTrip();
      setOutcome(
        result.changed
          ? result.moves.map(
              (move) => `Moved ${move.name} to Day ${move.to_day} at ${move.time}.`,
            )
          : [result.message],
      );
      if (result.verification) setReport(result.verification);
      if (result.changed) onRepaired?.();
    } catch {
      setOutcome(["Could not rearrange the trip just now."]);
    } finally {
      setRepairing(false);
    }
  }

  if (!report || report.counts.total === 0) return null;

  const { counts, verdict } = report;
  const failed = report.checks.filter(
    (check) => check.status === "failed" && check.severity === "contradiction",
  );
  const advisories = report.checks.filter(
    (check) => check.status === "failed" && check.severity === "advisory",
  );
  const Icon = verdict === "issues" ? AlertTriangle : verdict === "clear" ? ShieldCheck : HelpCircle;
  const tone =
    verdict === "issues"
      ? "border-rose-200 bg-rose-50"
      : verdict === "clear"
        ? "border-emerald-200 bg-emerald-50"
        : "border-amber-200 bg-amber-50";

  return (
    <section className={`rounded-lg border px-3 py-2 text-sm ${tone}`} aria-label="Plan checks">
      <button
        type="button"
        className="flex w-full items-center gap-2 text-left"
        onClick={() => setExpanded((open) => !open)}
        aria-expanded={expanded}
      >
        <Icon className="h-4 w-4 shrink-0" aria-hidden />
        <span className="font-medium">{HEADLINE[verdict]}</span>
        <span className="ml-auto text-xs text-slate-600">
          {counts.passed} passed
          {counts.failed > 0 && ` · ${counts.failed} failed`}
          {counts.unverified > 0 && ` · ${counts.unverified} unverified`}
        </span>
      </button>

      {failed.length > 0 && (
        <ul className="mt-2 space-y-1">
          {failed.flatMap((check) =>
            check.findings.map((finding) => (
              <li key={`${check.code}-${finding}`} className="flex gap-2 text-slate-800">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-rose-600" aria-hidden />
                <span>{finding}</span>
              </li>
            )),
          )}
        </ul>
      )}

      {failed.length > 0 && (
        <div className="mt-2 flex items-center gap-2">
          <button
            type="button"
            onClick={runRepair}
            disabled={repairing}
            className="inline-flex items-center gap-1.5 rounded-md bg-slate-900 px-2.5 py-1 text-xs font-medium text-white disabled:opacity-60"
          >
            <Wand2 className="h-3.5 w-3.5" aria-hidden />
            {repairing ? "Rearranging…" : "Rearrange the trip"}
          </button>
          <span className="text-xs text-slate-500">Only stops you have not chosen will move.</span>
        </div>
      )}

      {outcome.length > 0 && (
        <ul className="mt-2 space-y-0.5 text-xs text-slate-700">
          {outcome.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      )}

      {expanded && advisories.length > 0 && (
        <ul className="mt-2 space-y-1 text-xs">
          {advisories.flatMap((check) =>
            check.findings.map((finding) => (
              <li key={`${check.code}-${finding}`} className="flex gap-2 text-slate-600">
                <HelpCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600" aria-hidden />
                <span>{finding} (estimated travel time)</span>
              </li>
            )),
          )}
        </ul>
      )}

      {expanded && (
        <div className="mt-3 space-y-3 border-t border-white/60 pt-2 text-xs">
          <ul className="space-y-1">
            {report.checks.map((check) => {
              const { icon: StatusIcon, className } = TONE[check.status];
              return (
                <li key={check.code} className="flex gap-2">
                  <StatusIcon className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${className}`} aria-hidden />
                  <span className="text-slate-700">
                    <span className="font-medium">{check.rule}</span> — {check.statement}
                  </span>
                </li>
              );
            })}
          </ul>

          {report.unverified_stops.length > 0 && (
            <div>
              <p className="font-medium text-slate-700">Could not verify</p>
              <ul className="mt-1 space-y-0.5 text-slate-600">
                {report.unverified_stops.map((gap) => (
                  <li key={`${gap.day}-${gap.name}`}>
                    Day {gap.day} · {gap.name} — no {gap.missing.join(", no ")}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {report.days.some((day) => day.holiday) && (
            <div>
              <p className="font-medium text-slate-700">Public holidays</p>
              <ul className="mt-1 space-y-0.5 text-slate-600">
                {report.days
                  .filter((day) => day.holiday)
                  .map((day) => (
                    <li key={day.day}>
                      Day {day.day} · {day.holiday} — opening hours may differ
                    </li>
                  ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
