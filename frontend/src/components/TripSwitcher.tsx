import { ChevronDown, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { deleteTrip, fetchSavedTrips, switchTrip } from "../api";
import type { SavedTrip, TripView } from "../types";

const STATUS_BADGE: Record<string, string> = {
  draft: "bg-slate-100 text-slate-600",
  finalized: "bg-emerald-50 text-emerald-700",
  booked: "bg-brand/10 text-brand",
};

export default function TripSwitcher({
  version,
  onSwitched,
}: {
  version: number;
  onSwitched: (tripId?: string, view?: TripView | null) => void;
}) {
  const [trips, setTrips] = useState<SavedTrip[]>([]);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryToken, setRetryToken] = useState(0);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let alive = true;
    setError(null);
    fetchSavedTrips()
      .then((savedTrips) => alive && setTrips(savedTrips))
      .catch(() => alive && setError("Could not load saved trips."));
    return () => {
      alive = false;
    };
  }, [version, retryToken]);

  useEffect(() => {
    if (!open) return;
    const onDocumentClick = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDocumentClick);
    return () => document.removeEventListener("mousedown", onDocumentClick);
  }, [open]);

  if (trips.length === 0) {
    return error ? (
      <span role="status" className="text-xs text-rose-600">
        {error}{" "}
        <button type="button" onClick={() => setRetryToken((token) => token + 1)} className="font-semibold underline">
          Retry
        </button>
      </span>
    ) : null;
  }

  const onPick = async (tripId: string) => {
    setOpen(false);
    try {
      const view = await switchTrip(tripId);
      if (view) onSwitched(tripId, view);
    } catch {
      setError("Could not switch trips.");
    }
  };

  const onRemove = async (tripId: string) => {
    const trip = trips.find((candidate) => candidate.trip_id === tripId);
    const name = trip?.destination || "this trip";
    if (!window.confirm(`Delete ${name} and its chat history? This cannot be undone.`)) return;
    try {
      const remaining = await deleteTrip(tripId);
      setTrips(remaining);
      onSwitched();
    } catch {
      setError("Could not delete the trip.");
    }
  };

  const active = trips.find((trip) => trip.is_active);
  const label = active ? active.destination || "Untitled" : "My trips";

  return (
    <div ref={ref} className="relative z-[70] shrink-0">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        className="pill bg-white text-ink ring-1 ring-slate-200 transition hover:bg-slate-50"
        title="Switch between your saved trips"
        aria-expanded={open}
      >
        <span aria-hidden>{"\u{1F9F3}"}</span>
        <span className="max-w-[9rem] truncate">{label}</span>
        <span className="text-slate-400">({trips.length})</span>
        <ChevronDown size={14} aria-hidden />
      </button>
      {open && (
        <div data-testid="saved-trips-menu" className="absolute left-0 top-full z-[80] mt-1.5 max-h-80 w-72 overflow-y-auto rounded-2xl bg-white p-1.5 shadow-pop ring-1 ring-slate-100">
          {trips.map((trip) => {
            const dates =
              trip.departure_date && trip.return_date
                ? `${trip.departure_date} \u2192 ${trip.return_date}`
                : trip.departure_date || "dates TBD";
            const badge = STATUS_BADGE[trip.status] || STATUS_BADGE.draft;
            return (
              <div
                key={trip.trip_id}
                className={`flex w-full items-start gap-2 rounded-xl px-2.5 py-2 text-left transition hover:bg-slate-50 ${
                  trip.is_active ? "bg-brand/5 ring-1 ring-brand/20" : ""
                }`}
              >
                <button type="button" onClick={() => onPick(trip.trip_id)} className="min-w-0 flex-1 text-left">
                  <div className="flex items-center gap-1.5">
                    <span className="truncate text-sm font-medium text-ink">
                      {trip.destination || "Untitled trip"}
                    </span>
                    <span className={`chip ${badge}`}>{trip.status}</span>
                  </div>
                  <div className="truncate text-xs text-muted">{dates}</div>
                  <div className="mt-0.5 text-[11px] text-slate-400">
                    {trip.counts.flights}{"\u2708 \u00b7 "}{trip.counts.hotels}{"\u{1F3E8} \u00b7 "}{trip.counts.activities}{"\u{1F3AF}"}
                  </div>
                </button>
                <button
                  type="button"
                  onClick={() => onRemove(trip.trip_id)}
                  aria-label={`Delete ${trip.destination || "untitled trip"}`}
                  className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full text-slate-300 transition hover:bg-rose-50 hover:text-rose-500"
                  title="Delete this saved trip"
                >
                  <Trash2 size={14} aria-hidden />
                </button>
              </div>
            );
          })}
        </div>
      )}
      {error && <p role="status" className="absolute left-0 top-full z-30 mt-1 text-xs text-rose-600">{error}</p>}
    </div>
  );
}
