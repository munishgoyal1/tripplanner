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
            ? "h-full rounded-md border border-border"
            : "absolute inset-y-2 right-2 z-40 w-[min(27rem,calc(100vw-2rem))] rounded-md border border-border shadow-pop"
        }`}
      >
        <section className={`h-full min-h-0 flex-col ${open ? "flex" : "hidden"}`}>
          <header className="flex h-9 shrink-0 items-center gap-2 border-b border-border px-2.5" title={focused ? "Selected stop" : "Trip context"}>
            <Icon size={14} className="shrink-0 text-muted" aria-hidden />
            <h2 className="shrink-0 text-[13px] font-semibold tracking-[-0.01em] text-ink">{focused ? "Place details" : "Destination guide"}</h2>
            {focused && <span className="min-w-0 truncate text-[12px] text-muted">{focusName}</span>}
            <div role="group" aria-label="Details pane controls" className="ml-auto flex shrink-0 items-center gap-0.5">
              <button
                type="button"
                onClick={onHide}
                className="grid h-7 w-7 place-items-center rounded text-muted transition hover:bg-sand hover:text-ink"
                aria-label="Hide Details"
                title="Hide Details"
              >
                <EyeOff size={14} aria-hidden />
              </button>
              <button
                type="button"
                onClick={onToggleMaximize}
                className="grid h-7 w-7 place-items-center rounded text-muted transition hover:bg-sand hover:text-ink"
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
