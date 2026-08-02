import { EyeOff, Maximize2, Minimize2 } from "lucide-react";
import type { ReactNode } from "react";

interface Props {
  label: "Itinerary" | "Map";
  maximized: boolean;
  hideDisabled: boolean;
  onHide: () => void;
  onToggleMaximize: () => void;
  headerTargetRef?: (node: HTMLDivElement | null) => void;
  children: ReactNode;
}

export default function CanvasPaneFrame({
  label,
  maximized,
  hideDisabled,
  onHide,
  onToggleMaximize,
  headerTargetRef,
  children,
}: Props) {
  return (
    <article className="flex h-full min-h-0 flex-col overflow-hidden rounded-2xl border border-slate-200/70 bg-white shadow-card">
      <header className="flex h-10 shrink-0 items-center gap-2 border-b border-slate-100 px-3">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</h2>
        {headerTargetRef && <div ref={headerTargetRef} className="min-w-0 flex-1" />}
        <div role="group" aria-label={`${label} pane controls`} className="ml-auto flex shrink-0 items-center rounded-md bg-slate-50 p-0.5 ring-1 ring-inset ring-slate-200/80">
          <button
            type="button"
            onClick={onHide}
            className="grid h-7 w-7 place-items-center rounded-[5px] text-slate-500 transition hover:bg-white hover:text-ink hover:shadow-sm disabled:opacity-30"
            aria-label={`Hide ${label}`}
            title={`Hide ${label}`}
            disabled={hideDisabled}
          >
            <EyeOff size={14} aria-hidden />
          </button>
          <button
            type="button"
            onClick={onToggleMaximize}
            className="grid h-7 w-7 place-items-center rounded-[5px] text-slate-500 transition hover:bg-white hover:text-ink hover:shadow-sm"
            aria-label={maximized ? `Restore ${label}` : `Maximize ${label}`}
            title={maximized ? "Restore" : "Maximize"}
          >
            {maximized ? <Minimize2 size={14} aria-hidden /> : <Maximize2 size={14} aria-hidden />}
          </button>
        </div>
      </header>
      <div className="min-h-0 flex-1">{children}</div>
    </article>
  );
}