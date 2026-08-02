import { ArrowRight, Clock3 } from "lucide-react";
import type { LabDisposition, LabRecord, LabSelectionState } from "./labRecords";

const stateLabels: Record<LabDisposition, string> = {
  ready: "In progress",
  "implemented-review": "Implemented - To be reviewed",
  parked: "Parked",
  completed: "Completed",
  discarded: "Discarded",
};

function formatDate(value: string): string {
  const date = /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(`${value}T00:00:00Z`) : new Date(value);
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }).format(date);
}

export function LabRecordCard({
  lab,
  completed = false,
  index,
  compact = false,
  state,
  selection,
}: {
  lab: LabRecord;
  completed?: boolean;
  index?: number;
  compact?: boolean;
  state?: LabDisposition;
  selection?: LabSelectionState;
}) {
  const Icon = lab.icon;
  const stateDate = state === lab.defaultDisposition && lab.defaultStateChangedAt
    ? lab.defaultStateChangedAt
    : selection?.stateChangedAt || selection?.updatedAt || lab.defaultStateChangedAt;
  const stateLabel = state ? stateLabels[state] : "In evaluation";
  if (compact) {
    return (
      <a href={lab.href} className="group grid grid-cols-[2.5rem_minmax(0,1fr)_auto] items-center gap-3 border-b border-slate-200 bg-white px-3 py-3 transition last:border-b-0 hover:bg-slate-50">
        <span className="text-center font-mono text-sm font-semibold text-slate-300 group-hover:text-brand">{String(index ?? 0).padStart(2, "0")}</span>
        <span className="min-w-0">
          <span className="flex flex-wrap items-center gap-2 text-[10px] font-bold uppercase text-brand">
            {lab.category}
            <span className={state === "parked" ? "text-amber-700" : state === "implemented-review" ? "text-sky-700" : state === "ready" ? "text-orange-700" : "text-slate-500"}>{stateLabel}</span>
          </span>
          <span className="mt-0.5 block text-sm font-semibold text-ink">{lab.title}</span>
          <span className="mt-0.5 block text-xs text-slate-500">{lab.description}</span>
          <span className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-slate-400">
            <span>Created {formatDate(lab.createdAt)}</span>
            {stateDate && <span>{stateLabel} {formatDate(stateDate)}</span>}
          </span>
        </span>
        <ArrowRight size={16} className="shrink-0 text-slate-400 transition group-hover:translate-x-0.5 group-hover:text-brand" aria-hidden />
      </a>
    );
  }
  return (
    <a href={lab.href} className="block rounded-md bg-white p-4 shadow-card ring-1 ring-slate-200 transition hover:-translate-y-0.5 hover:shadow-pop hover:ring-brand/30">
      <div className="flex items-start gap-3">
        <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-md ${completed ? "bg-emerald-50 text-emerald-700" : "bg-brand-50 text-brand"}`}><Icon size={17} aria-hidden /></span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold text-ink">{lab.title}</h3>
            <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ring-1 ${completed ? "bg-emerald-50 text-emerald-700 ring-emerald-200" : "bg-amber-50 text-amber-700 ring-amber-200"}`}>{lab.status}</span>
          </div>
          <p className="mt-1 text-[10px] font-bold uppercase text-slate-400">{lab.category}</p>
          <p className="mt-1 text-xs leading-relaxed text-slate-500">{lab.description}</p>
        </div>
        <ArrowRight size={16} className="mt-1 shrink-0 text-slate-400" aria-hidden />
      </div>
      <div className="mt-4 border-t border-slate-100 pt-3">
        <p className="text-xs font-medium text-slate-700">{lab.decision}</p>
        <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-slate-400">
          <span className="flex items-center gap-1"><Clock3 size={11} aria-hidden /> Created {formatDate(lab.createdAt)}</span>
          {stateDate && <span>{stateLabel} {formatDate(stateDate)}</span>}
        </div>
      </div>
    </a>
  );
}