import { ArrowRight, Clock3 } from "lucide-react";
import type { LabRecord } from "./labRecords";

export function LabRecordCard({ lab, completed = false }: { lab: LabRecord; completed?: boolean }) {
  const Icon = lab.icon;
  return (
    <a href={lab.href} className="block rounded-md bg-white p-4 shadow-card ring-1 ring-slate-200 transition hover:-translate-y-0.5 hover:shadow-pop hover:ring-brand/30">
      <div className="flex items-start gap-3">
        <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-md ${completed ? "bg-emerald-50 text-emerald-700" : "bg-brand-50 text-brand"}`}><Icon size={17} aria-hidden /></span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold text-ink">{lab.title}</h3>
            <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ring-1 ${completed ? "bg-emerald-50 text-emerald-700 ring-emerald-200" : "bg-amber-50 text-amber-700 ring-amber-200"}`}>{lab.status}</span>
          </div>
          <p className="mt-1 text-xs leading-relaxed text-slate-500">{lab.description}</p>
        </div>
        <ArrowRight size={16} className="mt-1 shrink-0 text-slate-400" aria-hidden />
      </div>
      <div className="mt-4 border-t border-slate-100 pt-3">
        <p className="text-xs font-medium text-slate-700">{lab.decision}</p>
        <p className="mt-1 flex items-center gap-1 text-[11px] text-slate-400"><Clock3 size={11} aria-hidden /> {lab.date}</p>
      </div>
    </a>
  );
}