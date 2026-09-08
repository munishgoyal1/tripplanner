import { X } from "lucide-react";
import type { ReactNode } from "react";

interface Props {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
}

export default function AssistantModalShell({ open, onClose, children }: Props) {
  return (
    <div
      data-testid="assistant-modal-layer"
      className={`fixed bottom-4 right-4 z-[60] h-[68%] min-h-[31rem] w-[min(30rem,calc(100vw-2rem))] ${open ? "flex" : "hidden"}`}
    >
      <aside
        data-testid="assistant-modal"
        role="dialog"
        aria-label="Trip Assistant"
        className="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-md border border-slate-200 bg-white shadow-[0_24px_70px_rgba(15,23,42,.28)]"
      >
        <div className="relative min-h-0 flex-1">{children}</div>
        <button
          type="button"
          onClick={onClose}
          className="absolute right-3 top-3 z-30 grid h-8 w-8 place-items-center rounded-md bg-white text-slate-500 shadow-sm ring-1 ring-slate-200 hover:bg-slate-50 hover:text-ink"
          aria-label="Close Assistant"
          title="Close Assistant"
        >
          <X size={15} aria-hidden />
        </button>
      </aside>
    </div>
  );
}