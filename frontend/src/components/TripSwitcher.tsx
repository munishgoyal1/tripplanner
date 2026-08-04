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
  const [deleteMode, setDeleteMode] = useState(false);
  const [selectedTripIds, setSelectedTripIds] = useState<Set<string>>(() => new Set());
  const [deleting, setDeleting] = useState(false);
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
      if (ref.current && !ref.current.contains(event.target as Node)) {
        setOpen(false);
        setDeleteMode(false);
        setSelectedTripIds(new Set());
      }
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
    setDeleteMode(false);
    setSelectedTripIds(new Set());
    try {
      const view = await switchTrip(tripId);
      if (view) onSwitched(tripId, view);
    } catch {
      setError("Could not switch trips.");
    }
  };

  const toggleSelected = (tripId: string) => {
    setSelectedTripIds((current) => {
      const next = new Set(current);
      if (next.has(tripId)) next.delete(tripId);
      else next.add(tripId);
      return next;
    });
  };

  const toggleAll = () => {
    setSelectedTripIds((current) => (
      current.size === trips.length
        ? new Set()
        : new Set(trips.map((trip) => trip.trip_id))
    ));
  };

  const onRemoveSelected = async () => {
    const selectedTrips = trips.filter((trip) => selectedTripIds.has(trip.trip_id));
    if (selectedTrips.length === 0) return;
    const deletingAll = selectedTrips.length === trips.length;
    const message = selectedTrips.length === 1
      ? `Delete ${selectedTrips[0].destination || "this trip"} and its chat history? This cannot be undone.`
      : deletingAll
        ? `Delete all ${selectedTrips.length} saved trips and their chat history? This cannot be undone.`
        : `Delete ${selectedTrips.length} saved trips and their chat history? This cannot be undone.`;
    if (!window.confirm(message)) return;

    let remaining = trips;
    let deletedCount = 0;
    setDeleting(true);
    setError(null);
    try {
      for (const trip of selectedTrips) {
        remaining = await deleteTrip(trip.trip_id);
        deletedCount += 1;
        setTrips(remaining);
      }
      setOpen(false);
      setDeleteMode(false);
      setSelectedTripIds(new Set());
      onSwitched();
    } catch {
      setSelectedTripIds(new Set(
        selectedTrips
          .slice(deletedCount)
          .map((trip) => trip.trip_id),
      ));
      setError(
        deletedCount > 0
          ? `Deleted ${deletedCount} ${deletedCount === 1 ? "trip" : "trips"}, but could not delete the rest.`
          : "Could not delete the selected trips.",
      );
      if (deletedCount > 0) onSwitched();
    } finally {
      setDeleting(false);
    }
  };

  const active = trips.find((trip) => trip.is_active);
  const label = active ? active.destination || "Untitled" : "My trips";
  const selectedCount = selectedTripIds.size;
  const deleteLabel = selectedCount === 1
    ? "Delete 1 trip"
    : selectedCount === trips.length
      ? `Delete all ${selectedCount} trips`
      : selectedCount > 1
        ? `Delete ${selectedCount} trips`
        : "Delete selected";

  return (
    <div ref={ref} className="relative z-[70] shrink-0">
      <button
        type="button"
        onClick={() => {
          if (open) {
            setDeleteMode(false);
            setSelectedTripIds(new Set());
          }
          setOpen((current) => !current);
        }}
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
        <div data-testid="saved-trips-menu" className="absolute left-0 top-full z-[80] mt-1.5 w-80 overflow-hidden rounded-lg bg-white shadow-pop ring-1 ring-slate-100">
          <div className="flex h-10 items-center justify-between border-b border-slate-100 px-3">
            {deleteMode ? (
              <>
                <button type="button" onClick={toggleAll} disabled={deleting} className="text-xs font-semibold text-brand disabled:opacity-50">
                  {selectedCount === trips.length ? "Clear all" : "Select all"}
                </button>
                <span className="text-xs text-slate-400">{selectedCount} selected</span>
              </>
            ) : (
              <>
                <span className="text-xs font-semibold text-slate-500">Saved trips</span>
                <button
                  type="button"
                  onClick={() => {
                    setDeleteMode(true);
                    setSelectedTripIds(new Set());
                    setError(null);
                  }}
                  className="inline-flex h-7 items-center gap-1.5 rounded-md px-2 text-xs font-semibold text-slate-500 hover:bg-rose-50 hover:text-rose-600"
                >
                  <Trash2 size={13} aria-hidden />
                  Delete trips
                </button>
              </>
            )}
          </div>
          <div className="max-h-72 overflow-y-auto p-1.5">
            {trips.map((trip) => {
              const dates =
                trip.departure_date && trip.return_date
                  ? `${trip.departure_date} \u2192 ${trip.return_date}`
                  : trip.departure_date || "dates TBD";
              const badge = STATUS_BADGE[trip.status] || STATUS_BADGE.draft;
              const details = (
                <div className="min-w-0 flex-1">
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
                </div>
              );
              return (
                <div
                  key={trip.trip_id}
                  className={`flex w-full items-start gap-2 rounded-md px-2.5 py-2 text-left transition hover:bg-slate-50 ${
                    trip.is_active ? "bg-brand/5 ring-1 ring-brand/20" : ""
                  }`}
                >
                  {deleteMode ? (
                    <label className="flex min-w-0 flex-1 cursor-pointer items-start gap-2">
                      <input
                        type="checkbox"
                        checked={selectedTripIds.has(trip.trip_id)}
                        onChange={() => toggleSelected(trip.trip_id)}
                        disabled={deleting}
                        aria-label={`Select ${trip.destination || "untitled trip"} for deletion`}
                        className="mt-1 h-4 w-4 shrink-0 accent-brand"
                      />
                      {details}
                    </label>
                  ) : (
                    <button type="button" onClick={() => onPick(trip.trip_id)} className="min-w-0 flex-1 text-left">
                      {details}
                    </button>
                  )}
                </div>
              );
            })}
          </div>
          {deleteMode && (
            <div className="flex items-center justify-end gap-2 border-t border-slate-100 px-3 py-2">
              <button
                type="button"
                onClick={() => {
                  setDeleteMode(false);
                  setSelectedTripIds(new Set());
                }}
                disabled={deleting}
                className="h-8 rounded-md px-3 text-xs font-semibold text-slate-500 hover:bg-slate-100 disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void onRemoveSelected()}
                disabled={selectedCount === 0 || deleting}
                className="h-8 rounded-md bg-rose-600 px-3 text-xs font-semibold text-white hover:bg-rose-700 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {deleting ? "Deleting..." : deleteLabel}
              </button>
            </div>
          )}
        </div>
      )}
      {error && <p role="status" className="absolute left-0 top-full z-30 mt-1 text-xs text-rose-600">{error}</p>}
    </div>
  );
}
