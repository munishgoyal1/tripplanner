import { useCallback, useEffect, useState } from "react";
import { fetchItinerary, setStopBooked } from "../api";
import type { Itinerary, ItineraryDay, ItineraryStop } from "../types";

interface Props {
  /** Bump to refetch the itinerary after the trip changes. */
  reloadToken?: number;
  /** Click a stop to focus it (loads its photos + highlights its map pin). */
  onStopFocus?: (kind: string, name: string) => void;
  /** Jump to the map focused on a stop (and optionally details). */
  onStopMap?: (kind: string, name: string) => void;
  /** The currently focused stop name (so we can highlight the active row). */
  focusName?: string | null;
}

const KIND_ICON: Record<string, string> = {
  hotel: "\u{1F3E8}",
  attraction: "\u{1F3AF}",
  meal: "\u{1F37D}\uFE0F",
  transport: "\u{1F695}",
  flight: "\u2708\uFE0F",
  other: "\u{1F4CD}",
};

// A place stop can load photos; meals/transport/flights are informational.
function canFocus(kind: string): boolean {
  return kind === "hotel" || kind === "attraction";
}

function StopRow({
  stop,
  active,
  onToggleBooked,
  onFocus,
  onMap,
}: {
  stop: ItineraryStop;
  active: boolean;
  onToggleBooked: (next: boolean) => void;
  onFocus: () => void;
  onMap: () => void;
}) {
  const focusable = canFocus(stop.kind);
  return (
    <li
      className={`group flex items-start gap-3 rounded-2xl px-3 py-2.5 transition ${
        active ? "bg-brand/5 ring-1 ring-brand/20" : "hover:bg-slate-50"
      }`}
    >
      <button
        type="button"
        role="checkbox"
        aria-checked={stop.booked}
        aria-label={stop.booked ? "Mark not booked" : "Mark booked"}
        onClick={() => onToggleBooked(!stop.booked)}
        className={`mt-0.5 grid h-5 w-5 flex-shrink-0 place-items-center rounded-md border transition ${
          stop.booked
            ? "border-emerald-500 bg-emerald-500 text-white"
            : "border-slate-300 bg-white text-transparent hover:border-emerald-400"
        }`}
      >
        <span className="text-[11px] leading-none">{"\u2713"}</span>
      </button>

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          {stop.time && (
            <span className="font-mono text-[11px] tabular-nums text-slate-400">
              {stop.time}
            </span>
          )}
          <button
            type="button"
            disabled={!focusable}
            onClick={onFocus}
            className={`truncate text-left text-sm font-semibold ${
              focusable
                ? "text-ink hover:text-brand"
                : "cursor-default text-ink"
            } ${stop.booked ? "line-through decoration-emerald-500/50" : ""}`}
            title={focusable ? "Show photos & reviews" : undefined}
          >
            <span className="mr-1" aria-hidden>
              {KIND_ICON[stop.kind] || KIND_ICON.other}
            </span>
            {stop.name}
          </button>
        </div>
        {(stop.note || stop.duration_min || stop.selected) && (
          <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
            {stop.selected && (
              <span className="pill bg-emerald-50 text-emerald-700 ring-1 ring-emerald-100">
                In trip
              </span>
            )}
            {stop.duration_min ? (
              <span className="chip">{Math.round(stop.duration_min)} min</span>
            ) : null}
            {stop.note && <span className="text-xs text-slate-500">{stop.note}</span>}
          </div>
        )}
      </div>

      <button
        type="button"
        onClick={onMap}
        aria-label={`Show ${stop.name} on the map`}
        className="mt-0.5 grid h-7 w-7 flex-shrink-0 place-items-center rounded-full text-slate-400 opacity-0 transition hover:bg-white hover:text-brand group-hover:opacity-100"
        title="Show on map"
      >
        <span aria-hidden>{"\u{1F4CD}"}</span>
      </button>
    </li>
  );
}

function DayCard({
  day,
  active,
  onToggleBooked,
  onFocus,
  onMap,
  focusName,
}: {
  day: ItineraryDay;
  active: boolean;
  onToggleBooked: (day: number, name: string, next: boolean) => void;
  onFocus: (kind: string, name: string) => void;
  onMap: (kind: string, name: string) => void;
  focusName?: string | null;
}) {
  return (
    <section className="card p-4">
      <div className="flex items-center gap-3">
        <span
          className="grid h-9 w-9 flex-shrink-0 place-items-center rounded-full text-sm font-bold text-white"
          style={{ backgroundColor: day.color }}
        >
          {day.day}
        </span>
        <div className="min-w-0">
          <h3 className="display truncate text-base font-semibold text-ink">
            {day.title}
          </h3>
          {day.date && <p className="text-xs text-slate-400">{day.date}</p>}
        </div>
      </div>

      {day.summary && (
        <p className="mt-2.5 text-sm leading-relaxed text-slate-600">{day.summary}</p>
      )}

      {day.stops.length > 0 && (
        <ul className="mt-3 space-y-1">
          {day.stops.map((stop, i) => (
            <StopRow
              key={`${stop.name}-${i}`}
              stop={stop}
              active={active && focusName?.toLowerCase() === stop.name.toLowerCase()}
              onToggleBooked={(next) => onToggleBooked(day.day, stop.name, next)}
              onFocus={() => onFocus(stop.kind, stop.name)}
              onMap={() => onMap(stop.kind, stop.name)}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

export default function ItineraryPanel({
  reloadToken = 0,
  onStopFocus,
  onStopMap,
  focusName,
}: Props) {
  const [it, setIt] = useState<Itinerary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchItinerary()
      .then((data) => {
        if (!cancelled) setIt(data);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

  const handleToggleBooked = useCallback(
    async (day: number, name: string, next: boolean) => {
      // Optimistic update so the checkbox feels instant.
      setIt((prev) =>
        prev
          ? {
              ...prev,
              days: prev.days.map((d) =>
                d.day === day
                  ? {
                      ...d,
                      stops: d.stops.map((s) =>
                        s.name === name ? { ...s, booked: next } : s
                      ),
                    }
                  : d
              ),
            }
          : prev
      );
      const fresh = await setStopBooked(day, name, next);
      setIt(fresh);
    },
    []
  );

  if (loading && !it) {
    return (
      <div className="grid h-full place-items-center p-6 text-sm text-slate-400">
        Loading itinerary…
      </div>
    );
  }

  if (!it || !it.has_itinerary) {
    return (
      <div className="grid h-full place-items-center p-6 text-center">
        <div className="max-w-xs text-sm text-slate-500">
          No day-by-day plan yet. Once the assistant builds your itinerary, each
          day's stops will appear here — check them off as you book.
        </div>
      </div>
    );
  }

  const { stats } = it;
  return (
    <div className="h-full overflow-y-auto px-4 py-4">
      <header className="mb-3 flex items-center justify-between">
        <h2 className="display text-lg font-semibold text-ink">
          {it.destination ? `${it.destination} itinerary` : "Itinerary"}
        </h2>
        <span className="chip">
          {stats.days} {stats.days === 1 ? "day" : "days"} · {stats.booked}/{stats.stops}{" "}
          booked
        </span>
      </header>
      <div className="space-y-3 pb-6">
        {it.days.map((day) => (
          <DayCard
            key={day.day}
            day={day}
            active
            focusName={focusName}
            onToggleBooked={handleToggleBooked}
            onFocus={(kind, name) => onStopFocus?.(kind, name)}
            onMap={(kind, name) => onStopMap?.(kind, name)}
          />
        ))}
      </div>
    </div>
  );
}
