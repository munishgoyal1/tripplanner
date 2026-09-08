import { Check, Sparkles, X } from "lucide-react";
import type { ProfileSuggestion } from "../api";

/** One tiny confirm-or-save moment for a fact the planner noticed in chat. */
export default function ProfileSuggestionCard({
  suggestion,
  remaining,
  busy,
  onResolve,
}: {
  suggestion: ProfileSuggestion;
  remaining: number;
  busy: boolean;
  onResolve: (id: string, action: "save" | "dismiss") => void;
}) {
  return (
    <div className="mt-3 rounded-xl bg-amber-50/70 p-3 ring-1 ring-amber-200">
      <div className="flex items-start gap-2">
        <span className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-md bg-amber-200/70 text-amber-800">
          <Sparkles size={13} aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[10px] font-bold uppercase tracking-wide text-amber-700">
            {suggestion.label} · not saved yet
          </p>
          <p className="mt-0.5 text-xs font-semibold leading-relaxed text-ink">{suggestion.summary}</p>
          {suggestion.source_text && (
            <p className="mt-1 truncate text-[11px] italic text-slate-500">“{suggestion.source_text}”</p>
          )}
        </div>
      </div>
      <div className="mt-2.5 flex items-center gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => onResolve(suggestion.id, "save")}
          className="inline-flex h-8 items-center gap-1.5 rounded-full bg-ink px-3 text-xs font-semibold text-white transition hover:bg-ink/90 disabled:opacity-40"
        >
          <Check size={13} aria-hidden /> Remember this
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => onResolve(suggestion.id, "dismiss")}
          className="inline-flex h-8 items-center gap-1.5 rounded-full px-3 text-xs font-semibold text-slate-500 ring-1 ring-slate-200 transition hover:bg-white disabled:opacity-40"
        >
          <X size={13} aria-hidden /> Not now
        </button>
        {remaining > 1 && (
          <span className="ml-auto text-[11px] text-slate-500">{remaining - 1} more noticed</span>
        )}
      </div>
    </div>
  );
}
