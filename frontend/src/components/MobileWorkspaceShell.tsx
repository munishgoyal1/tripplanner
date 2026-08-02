import type { ReactNode } from "react";

interface Props {
  chat: ReactNode;
  hasTrip: boolean;
  tripOpen: boolean;
  onOpenTrip: () => void;
  onCloseTrip: () => void;
  tripDetails: ReactNode;
}

export default function MobileWorkspaceShell({
  chat,
  hasTrip,
  tripOpen,
  onOpenTrip,
  onCloseTrip,
  tripDetails,
}: Props) {
  return (
    <section className="flex h-screen flex-col">
      {chat}

      {hasTrip && !tripOpen && (
        <button
          type="button"
          onClick={onOpenTrip}
          aria-label="Open trip details"
          className="fixed bottom-4 right-4 z-30 inline-flex items-center gap-2 rounded-full bg-ink px-4 py-2.5 text-sm font-medium text-white shadow-pop ring-1 ring-black/10 transition active:scale-95"
        >
          <span>Trip details</span>
        </button>
      )}

      <div
        onClick={onCloseTrip}
        aria-hidden={!tripOpen}
        className={`fixed inset-0 z-40 bg-black/40 backdrop-blur-sm transition-opacity ${
          tripOpen ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
      />
      <section
        role="dialog"
        aria-modal="true"
        aria-label="Trip details"
        className={`fixed inset-x-0 bottom-0 z-50 flex h-[88vh] flex-col rounded-t-3xl bg-surface shadow-pop transition-transform duration-300 ${
          tripOpen ? "translate-y-0" : "translate-y-full"
        }`}
      >
        <div className="flex items-center justify-between px-4 pt-2 pb-1">
          <button
            type="button"
            onClick={onCloseTrip}
            aria-label="Close trip details"
            className="-ml-2 grid h-10 w-10 place-items-center rounded-full text-slate-500 transition hover:bg-slate-100 hover:text-ink"
          >
            <span className="text-xl leading-none">x</span>
          </button>
          <div
            onClick={onCloseTrip}
            className="mx-auto -ml-10 h-1.5 w-12 cursor-pointer rounded-full bg-slate-300"
            aria-hidden
          />
          <span className="w-10" aria-hidden />
        </div>
        <div className="min-h-0 flex-1">{tripDetails}</div>
      </section>
    </section>
  );
}