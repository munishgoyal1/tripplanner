import { EyeOff, ListChecks, MapPin, Maximize2, Minimize2 } from "lucide-react";
import type { ReactNode } from "react";

interface Props {
  label: "Itinerary" | "Map" | "Assistant";
  maximized: boolean;
  onHide: () => void;
  onToggleMaximize: () => void;
  headerTargetRef?: (node: HTMLDivElement | null) => void;
  children: ReactNode;
}

/** Flat one-line pane header: identity, pane-owned controls, then Hide and Maximize. */
export default function CanvasPaneFrame({
  label,
  maximized,
  onHide,
  onToggleMaximize,
  headerTargetRef,
  children,
}: Props) {
  const Icon = label === "Map" ? MapPin : ListChecks;
  const context = label === "Map" ? "Explore and route" : "Read and refine";
  return (
    <article className="flex h-full min-h-0 flex-col overflow-hidden rounded-md border border-border bg-paper">
      <header className="flex h-9 shrink-0 items-center gap-2 border-b border-border px-2.5" title={context}>
        <Icon size={14} className="shrink-0 text-muted" aria-hidden />
        <h2 className="shrink-0 text-[13px] font-semibold tracking-[-0.01em] text-ink">{label}</h2>
        {headerTargetRef && <div ref={headerTargetRef} className="flex min-w-0 flex-1 items-center justify-between gap-2 pl-1" />}
        <div role="group" aria-label={`${label} pane controls`} className="ml-auto flex shrink-0 items-center gap-0.5">
          <button
            type="button"
            onClick={onHide}
            className="grid h-7 w-7 place-items-center rounded text-muted transition hover:bg-sand hover:text-ink"
            aria-label={`Hide ${label}`}
            title={`Hide ${label}`}
          >
            <EyeOff size={14} aria-hidden />
          </button>
          <button
            type="button"
            onClick={onToggleMaximize}
            className="grid h-7 w-7 place-items-center rounded text-muted transition hover:bg-sand hover:text-ink"
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
