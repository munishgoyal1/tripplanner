import { AlertTriangle, CheckCircle2, Loader2, XCircle } from "lucide-react";
import type { ReactNode } from "react";
import { dismissNotice, useNotice, type Notice, type NoticeTone } from "../lib/notices";

const TONE_TEXT: Record<NoticeTone, string> = {
  progress: "text-brand",
  success: "text-emerald-700",
  error: "text-rose-700",
  decision: "text-amber-800",
};

function ToneIcon({ tone }: { tone: NoticeTone }) {
  if (tone === "progress") return <Loader2 size={13} className="animate-spin" aria-hidden />;
  if (tone === "error") return <XCircle size={13} aria-hidden />;
  if (tone === "decision") return <AlertTriangle size={13} aria-hidden />;
  return <CheckCircle2 size={13} aria-hidden />;
}

function NoticeLine({ notice, actions }: { notice: Notice; actions?: ReactNode }) {
  return (
    <div className="flex items-start gap-1.5">
      <span className={`mt-0.5 shrink-0 ${TONE_TEXT[notice.tone]}`}>
        <ToneIcon tone={notice.tone} />
      </span>
      <p
        className={`line-clamp-2 min-w-0 flex-1 whitespace-normal text-xs font-medium leading-tight ${TONE_TEXT[notice.tone]}`}
        title={notice.message}
      >
        {notice.message}
      </p>
      {actions}
      {notice.tone === "error" && (
        <button
          type="button"
          onClick={() => dismissNotice(notice.id)}
          className="shrink-0 rounded px-1 text-xs font-semibold leading-none text-rose-700 hover:bg-rose-50"
          aria-label="Dismiss notification"
        >
          ✕
        </button>
      )}
    </div>
  );
}

/** The workspace's single status line: what is happening, or what just did. */
export default function StatusBar({ actions }: { actions?: ReactNode }) {
  const notice = useNotice();
  return (
    <div
      className="min-w-0 flex-1"
      role="status"
      aria-live={notice?.tone === "error" ? "assertive" : "polite"}
    >
      {notice ? <NoticeLine notice={notice} actions={actions} /> : null}
    </div>
  );
}

/** Mobile has no toolbar row, so the same channel floats over the workspace. */
export function FloatingStatusBar() {
  const notice = useNotice();
  if (!notice) return null;
  return (
    <div className="pointer-events-none fixed inset-x-0 top-0 z-[70] flex justify-center px-3 pt-2">
      <div
        className="pointer-events-auto w-full max-w-sm rounded-lg border border-slate-200 bg-white/95 px-3 py-2 shadow-lg backdrop-blur"
        role="status"
        aria-live={notice.tone === "error" ? "assertive" : "polite"}
      >
        <NoticeLine notice={notice} />
      </div>
    </div>
  );
}
