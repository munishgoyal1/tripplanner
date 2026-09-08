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
    <section className="flex h-screen flex-col">
      <button
        type="button"
        onClick={onOpenWelcome}
        className="fixed right-3 top-3 z-30 inline-flex h-8 items-center gap-1.5 rounded-md bg-white/90 px-2.5 text-xs font-semibold text-slate-600 shadow-sm ring-1 ring-slate-200 backdrop-blur hover:bg-white"
        aria-label="Open home page"
      >
        <span aria-hidden>⌂</span> Home
      </button>
      {hasTrip && (
        <div className="fixed left-3 top-3 z-30 rounded-md bg-white/90 shadow-sm ring-1 ring-slate-200 backdrop-blur">
          <TripFeedbackControl initial={feedback} mobile />
        </div>
      )}
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