import { Check, RotateCcw, Undo2 } from "lucide-react";
import { useState } from "react";
import { overrideDecision, restoreDecision } from "../api";
import type {
  CostBaseline,
  Decision,
  DecisionOption,
  ProvenanceRow,
  TripView,
} from "../types";
import { formatSourceAmount, useDisplayPreferences, type DisplayCurrency } from "../lib/displayPreferences";

interface Props {
  decisions: Decision[];
  updatedAt?: string | null;
  baseline?: CostBaseline | null;
  provenance?: ProvenanceRow[];
  onApplied: (view: TripView, message: string, warnings: string[]) => void;
  onStale: (view: TripView | undefined, message: string) => void;
  onError: (message: string) => void;
}

function priceLabel(option: DecisionOption, displayCurrency: DisplayCurrency): string {
  if (!option.price) return "No price";
  const { amount, currency, amount_max } = option.price;
  const one = formatSourceAmount(amount, currency, displayCurrency);
  if (amount_max && amount_max > amount) {
    return `${one}–${formatSourceAmount(amount_max, currency, displayCurrency)}`;
  }
  return one;
}

// The absence of a price is a fact about our sources, not about the option.
const UNPRICED_TEXT: Record<string, string> = {
  no_source: "We have no fare source for this",
  source_failed: "The fare source did not answer",
  out_of_coverage: "Outside our fare coverage",
};

function durationLabel(minutes?: number | null): string {
  if (!minutes || minutes <= 0) return "";
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return h ? (m ? `${h}h ${m}m` : `${h}h`) : `${m}m`;
}

function OptionRow({
  option,
  active,
  isAgentPick,
  busy,
  onTake,
}: {
  option: DecisionOption;
  active: boolean;
  isAgentPick: boolean;
  busy: boolean;
  onTake: () => void;
}) {
  const { currency: displayCurrency } = useDisplayPreferences();
  const door = durationLabel(option.door_to_door_min ?? option.duration_min);
  return (
    <li
      className={`flex items-start gap-2.5 rounded-lg px-2.5 py-2 ring-1 ${
        active ? "bg-brand/5 ring-brand/20" : "bg-white ring-slate-200"
      }`}
    >
      <span className="mt-0.5 grid h-4 w-4 shrink-0 place-items-center">
        {active ? <Check size={13} className="text-brand" aria-hidden /> : null}
      </span>
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-baseline gap-x-2 text-[13px] font-semibold text-ink">
          <span>{option.label}</span>
          {door && <span className="text-[11px] font-normal text-slate-500">{door} door to door</span>}
          {isAgentPick && !active && (
            <span className="text-[10px] font-semibold uppercase text-slate-400">Original pick</span>
          )}
        </p>
        {option.detail && <p className="mt-0.5 text-[11px] text-slate-500">{option.detail}</p>}
        {!active && option.rejected_because && (
          <p className="mt-0.5 text-[11px] text-slate-500">{option.rejected_because}</p>
        )}
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1">
        <span className={`text-[13px] font-semibold ${option.priced ? "text-ink" : "text-slate-400"}`}>
          {option.priced ? priceLabel(option, displayCurrency) : "—"}
        </span>
        {!option.priced && (
          <span className="text-right text-[10px] leading-tight text-slate-400">
            {UNPRICED_TEXT[option.unpriced_reason ?? "no_source"]}
          </span>
        )}
        {!active && (
          <button
            type="button"
            disabled={busy}
            onClick={onTake}
            className="rounded-md bg-slate-50 px-2 py-1 text-[11px] font-semibold text-slate-600 ring-1 ring-slate-200 transition hover:bg-slate-100 hover:text-ink disabled:opacity-50"
          >
            Take this
          </button>
        )}
      </div>
    </li>
  );
}

function DecisionCard({
  decision,
  busy,
  onTake,
  onUndo,
}: {
  decision: Decision;
  busy: boolean;
  onTake: (optionId: string) => void;
  onUndo: () => void;
}) {
  const activeId = decision.override?.option_id || decision.chosen_option_id;
  const agentId = decision.agent_option_id || decision.chosen_option_id;
  const overruled = decision.state === "overruled";
  const warnings = decision.override?.warnings ?? [];

  return (
    <article className="rounded-xl bg-slate-50/70 p-3 ring-1 ring-slate-200">
      <header className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-[13px] font-semibold text-ink">{decision.subject}</p>
          <p className="mt-0.5 text-[11px] text-slate-500">
            {overruled ? "You chose this." : decision.rule.text}
          </p>
        </div>
        {overruled && (
          <button
            type="button"
            disabled={busy}
            onClick={onUndo}
            className="inline-flex shrink-0 items-center gap-1 rounded-md bg-white px-2 py-1 text-[11px] font-semibold text-slate-600 ring-1 ring-slate-200 transition hover:text-ink disabled:opacity-50"
          >
            <Undo2 size={11} aria-hidden /> Use the original
          </button>
        )}
      </header>
      <ul className="mt-2 space-y-1.5">
        {decision.options.map((option) => (
          <OptionRow
            key={option.id}
            option={option}
            active={option.id === activeId}
            isAgentPick={option.id === agentId}
            busy={busy}
            onTake={() => onTake(option.id)}
          />
        ))}
      </ul>
      {warnings.length > 0 && (
        <ul className="mt-2 space-y-1">
          {warnings.map((warning) => (
            <li
              key={warning}
              className="rounded-md bg-amber-50 px-2.5 py-1.5 text-[11px] font-medium text-amber-800 ring-1 ring-amber-100"
            >
              {warning}
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}

export default function DecisionPanel({
  decisions,
  updatedAt,
  baseline,
  provenance,
  onApplied,
  onStale,
  onError,
}: Props) {
  const [busyId, setBusyId] = useState<string | null>(null);
  const checks = provenance ?? [];
  if (decisions.length === 0 && checks.length === 0) return null;

  const run = async (decisionId: string, optionId: string | null) => {
    setBusyId(decisionId);
    try {
      const result = optionId
        ? await overrideDecision(decisionId, optionId, updatedAt)
        : await restoreDecision(decisionId, updatedAt);
      if (result.stale) {
        onStale(result.view, result.message);
        return;
      }
      if (!result.ok || !result.view) {
        onError(result.message || "Could not change this leg.");
        return;
      }
      onApplied(result.view, result.message, result.warnings ?? []);
    } catch (error) {
      onError(error instanceof Error ? error.message : "Could not change this leg.");
    } finally {
      setBusyId(null);
    }
  };

  const moved = baseline && Math.abs(baseline.saved) > 0.005;

  return (
    <section className="border-t border-slate-100 px-4 py-4">
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="display text-sm font-semibold text-ink">Why it's planned this way</h3>
        {moved && (
          <p className="flex items-center gap-1 text-[11px] font-medium text-slate-500">
            <RotateCcw size={11} aria-hidden />
            {baseline.saved > 0
              ? `${baseline.saved_display} under the first plan`
              : `${baseline.saved_display} over the first plan`}
          </p>
        )}
      </div>
      <p className="mt-1 text-[11px] text-slate-500">
        Every comparison the planner actually ran. Change any of them — the plan follows.
      </p>
      <div className="mt-3 space-y-2.5">
        {decisions.map((decision) => (
          <DecisionCard
            key={decision.id}
            decision={decision}
            busy={busyId === decision.id}
            onTake={(optionId) => run(decision.id, optionId)}
            onUndo={() => run(decision.id, null)}
          />
        ))}
      </div>
      {checks.length > 0 && (
        <ul className="mt-3 space-y-1 border-t border-slate-100 pt-2.5">
          {checks.map((check) => (
            <li
              key={`${check.kind}:${check.provider}`}
              className={`text-[11px] ${check.current ? "text-slate-500" : "text-amber-700"}`}
            >
              {check.text}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
