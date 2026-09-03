import { EyeOff, Maximize2, Minimize2 } from "lucide-react";
import type { ReactNode } from "react";

interface Props {
  label: "Itinerary" | "Map" | "Assistant";
  maximized: boolean;
  onHide: () => void;
  onToggleMaximize: () => void;
  headerTargetRef?: (node: HTMLDivElement | null) => void;
  children: ReactNode;
}

export default function CanvasPaneFrame({
  label,
  maximized,
  onHide,
  onToggleMaximize,
  headerTargetRef,
  children,
}: Props) {
  return (
    <article className="flex h-full min-h-0 flex-col overflow-hidden rounded-md border border-border bg-paper shadow-card">
      <header className="flex h-10 shrink-0 items-center gap-2 border-b border-border bg-paper px-3">
        <h2 className="display text-base text-ink">{label}</h2>
        {headerTargetRef && <div ref={headerTargetRef} className="min-w-0 flex-1" />}
        <div role="group" aria-label={`${label} pane controls`} className="ml-auto flex shrink-0 items-center rounded-full bg-sand p-0.5 ring-1 ring-inset ring-border">
          <button
            type="button"
            onClick={onHide}
            className="grid h-7 w-7 place-items-center rounded-full text-muted transition hover:bg-paper hover:text-ink hover:shadow-sm"
            aria-label={`Hide ${label}`}
            title={`Hide ${label}`}
          >
            <EyeOff size={14} aria-hidden />
          </button>
          <button
            type="button"
            onClick={onToggleMaximize}
            className="grid h-7 w-7 place-items-center rounded-full text-muted transition hover:bg-paper hover:text-ink hover:shadow-sm"
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