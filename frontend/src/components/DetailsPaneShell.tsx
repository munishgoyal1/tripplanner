import { EyeOff, Maximize2, Minimize2 } from "lucide-react";
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
  return (
    <div className={!open || canvasMaximized ? "hidden" : "contents"}>
      <aside
        ref={inspectorRef}
        data-testid="context-inspector"
        className={`flex min-h-0 flex-col overflow-hidden bg-surface ${
          wideLayout || maximized
            ? "h-full rounded-2xl border border-slate-200/70 shadow-card"
            : "absolute inset-y-2 right-2 z-40 w-[min(27rem,calc(100vw-2rem))] rounded-2xl border border-slate-200 shadow-pop"
        }`}
      >
        <section className={`h-full min-h-0 flex-col ${open ? "flex" : "hidden"}`}>
          <header className="flex h-10 shrink-0 items-center gap-2 border-b border-slate-100 bg-white px-3">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              {focused ? "Place details" : "Destination guide"}
            </h2>
            {focused && <span className="min-w-0 truncate text-xs font-medium text-ink">{focusName}</span>}
            <div role="group" aria-label="Details pane controls" className="ml-auto flex shrink-0 items-center rounded-md bg-slate-50 p-0.5 ring-1 ring-inset ring-slate-200/80">
              <button
                type="button"
                onClick={onHide}
                className="grid h-7 w-7 place-items-center rounded-[5px] text-slate-500 hover:bg-white hover:text-ink hover:shadow-sm"
                aria-label="Hide Details"
                title="Hide Details"
              >
                <EyeOff size={14} aria-hidden />
              </button>
              <button
                type="button"
                onClick={onToggleMaximize}
                className="grid h-7 w-7 place-items-center rounded-[5px] text-slate-500 hover:bg-white hover:text-ink hover:shadow-sm"
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