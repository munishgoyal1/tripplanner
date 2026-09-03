import type { ReactNode } from "react";
import AccessibleSheet from "./AccessibleSheet";
import TripFeedbackControl from "./TripFeedbackControl";

interface Props {
  chat: ReactNode;
  hasTrip: boolean;
  tripOpen: boolean;
  onOpenTrip: () => void;
  onCloseTrip: () => void;
  tripDetails: ReactNode;
  onOpenWelcome: () => void;
  feedback: { count: number; last_rating?: number | null; last_sentiment?: "up" | "down" | null };
}

export default function MobileWorkspaceShell({
  chat,
  hasTrip,
  tripOpen,
  onOpenTrip,
  onCloseTrip,
  tripDetails,
  onOpenWelcome,
  feedback,
}: Props) {
  return (
    <section className="flex h-screen flex-col bg-sand">
      <header className="relative z-30 flex h-11 shrink-0 items-center justify-between border-b border-border bg-paper/95 px-3 backdrop-blur">
        <div className="rounded-full bg-sand ring-1 ring-border">
          {hasTrip && <TripFeedbackControl initial={feedback} mobile />}
        </div>
        <button
          type="button"
          onClick={onOpenWelcome}
          className="inline-flex h-8 items-center gap-1.5 rounded-full bg-paper px-2.5 text-xs font-semibold text-ink ring-1 ring-border hover:bg-clay-soft"
          aria-label="Open home page"
        >
          <span aria-hidden>⌂</span> Home
        </button>
      </header>
      <div className="min-h-0 flex-1">{chat}</div>

      {hasTrip && !tripOpen && (
        <button
          type="button"
          onClick={onOpenTrip}
          aria-label="Open trip details"
          className="fixed bottom-4 right-4 z-30 inline-flex items-center gap-2 rounded-full bg-brand px-4 py-2.5 text-sm font-medium text-white shadow-pop ring-1 ring-black/10 transition active:scale-95"
        >
          <span>Trip details</span>
        </button>
      )}

      <AccessibleSheet
        open={tripOpen}
        label="Trip details"
        closeLabel="Close trip details"
        onClose={onCloseTrip}
      >
        {tripDetails}
      </AccessibleSheet>
    </section>
  );
}