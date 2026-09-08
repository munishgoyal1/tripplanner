import { Check, Send, Star, ThumbsDown, ThumbsUp, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { submitTripFeedback, type TripFeedbackRollup } from "../api";

interface Props {
  disabled?: boolean;
  initial: TripFeedbackRollup;
  mobile?: boolean;
}

export default function TripFeedbackControl({ disabled = false, initial, mobile = false }: Props) {
  const [open, setOpen] = useState(false);
  const [rollup, setRollup] = useState(initial);
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [currentFeedbackId, setCurrentFeedbackId] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => setRollup(initial), [initial]);
  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const submit = async (payload: {
    feedback_id?: string;
    sentiment?: "up" | "down";
    rating?: number;
    comment?: string;
  }) => {
    setSaving(true);
    setError("");
    try {
      const next = await submitTripFeedback({ ...payload, client: mobile ? "mobile" : "web" });
      setRollup(next);
      setCurrentFeedbackId(next.feedback_id ?? null);
      setComment("");
      setRating(0);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save feedback.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div ref={rootRef} className={`relative flex items-center ${mobile ? "gap-0" : "gap-1"}`}>
      {rollup.count > 0 && !mobile && (
        <span className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-700">
          <Check size={11} aria-hidden /> Sent {rollup.count > 1 ? `· ${rollup.count}` : ""}
        </span>
      )}
      {(["up", "down"] as const).map((sentiment) => {
        const Icon = sentiment === "up" ? ThumbsUp : ThumbsDown;
        return (
          <button
            key={sentiment}
            type="button"
            disabled={disabled || saving}
            onClick={() => { setCurrentFeedbackId(null); void submit({ sentiment }); setOpen(true); }}
            className="inline-flex h-8 w-8 items-center justify-center rounded-md text-slate-500 transition hover:bg-slate-100 hover:text-slate-700 disabled:opacity-40"
            aria-label={sentiment === "up" ? "This trip works" : "This trip misses"}
          >
            <Icon size={14} aria-hidden />
          </button>
        );
      })}
      {!mobile && (
        <button
          type="button"
          disabled={disabled}
          onClick={() => setOpen((current) => !current)}
          className="inline-flex h-8 items-center gap-1 rounded-md px-1.5 text-xs font-semibold text-slate-500 transition hover:bg-slate-100 hover:text-slate-700 disabled:opacity-40"
          aria-expanded={open}
        >
          <Star size={13} aria-hidden /> Rate
        </button>
      )}
      {open && (
        <section className={`absolute z-[90] border border-slate-200 bg-white p-3 shadow-pop ${mobile ? "fixed inset-x-3 bottom-16 rounded-lg" : "right-0 top-full mt-1 w-80 rounded-lg"}`} aria-label="Trip feedback">
          <div className="flex items-start justify-between gap-3">
            <div><h3 className="text-sm font-semibold text-ink">How does this trip read?</h3><p className="mt-0.5 text-xs text-slate-500">One tap is enough. Stars and a note are optional.</p></div>
            <button type="button" onClick={() => setOpen(false)} className="grid h-7 w-7 place-items-center rounded-md text-slate-400 hover:bg-slate-100" aria-label="Close feedback"><X size={14} /></button>
          </div>
          <div className="mt-3 flex gap-1" role="group" aria-label="Star rating">
            {[1, 2, 3, 4, 5].map((value) => <button key={value} type="button" onClick={() => setRating(value)} className={`grid h-7 w-7 place-items-center rounded-md ${value <= rating ? "text-amber-500" : "text-slate-300 hover:text-amber-400"}`} aria-label={`${value} stars`}><Star size={17} fill={value <= rating ? "currentColor" : "none"} /></button>)}
          </div>
          <textarea value={comment} onChange={(event) => setComment(event.target.value)} maxLength={1000} placeholder="Optional: what would you change?" className="mt-3 min-h-20 w-full resize-none rounded-md border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand" />
          {error && <p className="mt-1 text-xs text-rose-600" role="alert">{error}</p>}
          <button type="button" disabled={saving || (!rating && !comment.trim())} onClick={() => void submit({ feedback_id: currentFeedbackId ?? undefined, rating: rating || undefined, comment: comment.trim() || undefined })} className="mt-2 inline-flex h-8 items-center gap-1.5 rounded-md bg-brand px-3 text-xs font-semibold text-white disabled:opacity-40"><Send size={13} /> Add feedback</button>
        </section>
      )}
    </div>
  );
}