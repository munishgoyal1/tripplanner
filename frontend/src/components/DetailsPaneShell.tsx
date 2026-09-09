import { Compass, EyeOff, MapPin, Maximize2, Minimize2 } from "lucide-react";
import type { ReactNode, Ref } from "react";

interface Props {
  open: boolean;
  canvasMaximized: boolean;
  wideLayout: boolean;
  maximized: boolean;
  focused: boolean;
  focusName: string | null;
  inspectorRef: Ref<HTMLElement>;
  onHide: () => void;
  onToggleMaximize: () => void;
  children: ReactNode;
}

export default function DetailsPaneShell({
  open,
  canvasMaximized,
  wideLayout,
  maximized,
  focused,
  focusName,
  inspectorRef,
  onHide,
  onToggleMaximize,
  children,
}: Props) {
  const Icon = focused ? MapPin : Compass;
  return (
    <div className={!open || canvasMaximized ? "hidden" : "contents"}>
      <aside
        ref={inspectorRef}
        data-testid="context-inspector"
        className={`flex min-h-0 flex-col overflow-hidden bg-paper ${
          wideLayout || maximized
            ? "h-full rounded-lg border border-border shadow-card"
            : "absolute inset-y-2 right-2 z-40 w-[min(27rem,calc(100vw-2rem))] rounded-md border border-border shadow-pop"
        }`}
      >
        <section className={`h-full min-h-0 flex-col ${open ? "flex" : "hidden"}`}>
          <header className="flex h-11 shrink-0 items-center gap-2.5 border-b border-border bg-sidebar/70 px-3">
            <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-paper text-brand shadow-sm ring-1 ring-border" aria-hidden>
              <Icon size={14} />
            </span>
            <span className="flex min-w-0 flex-col leading-none">
              <span className="text-[9px] font-bold uppercase tracking-[0.09em] text-muted">{focused ? "Selected stop" : "Trip context"}</span>
              <span className="mt-1 flex min-w-0 items-baseline gap-2">
                <h2 className="shrink-0 text-sm font-semibold text-ink">{focused ? "Place details" : "Destination guide"}</h2>
                {focused && <span className="min-w-0 truncate text-[11px] text-muted">{focusName}</span>}
              </span>
            </span>
            <div role="group" aria-label="Details pane controls" className="ml-auto flex shrink-0 items-center rounded-full bg-sand p-0.5 ring-1 ring-inset ring-border">
              <button
                type="button"
                onClick={onHide}
                className="grid h-7 w-7 place-items-center rounded-full text-muted hover:bg-paper hover:text-ink hover:shadow-sm"
                aria-label="Hide Details"
                title="Hide Details"
              >
                <EyeOff size={14} aria-hidden />
              </button>
              <button
                type="button"
                onClick={onToggleMaximize}
                className="grid h-7 w-7 place-items-center rounded-full text-muted hover:bg-paper hover:text-ink hover:shadow-sm"
                aria-label={maximized ? "Restore Details" : "Maximize Details"}
                title={maximized ? "Restore" : "Maximize"}
              >
                {maximized ? <Minimize2 size={14} aria-hidden /> : <Maximize2 size={14} aria-hidden />}
              </button>
            </div>
          </header>
          <div className="min-h-0 flex-1">{children}</div>
        </section>
      </aside>
    </div>
  );
}
