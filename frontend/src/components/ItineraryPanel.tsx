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
  /** Programmatic jump target after add-to-trip actions. */
  jumpTo?: { day: number; name: string; token: number } | null;
  /** Remove a stop from the itinerary / trip. */
  onStopRemove?: (kind: string, name: string) => void;
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
  jumpActive,
  rowId,
  onToggleBooked,
  onFocus,
  onMap,
  onRemove,
}: {
  stop: ItineraryStop;
  active: boolean;
  jumpActive: boolean;
  rowId: string;
  onToggleBooked: (next: boolean) => void;
  onFocus: () => void;
  onMap: () => void;
  onRemove?: () => void;
}) {
  const focusable = canFocus(stop.kind);
  const removable = !!onRemove && focusable;
  const noteText = (stop.note || "").trim();
  const insightText = (stop.insight || "").trim();
  const showNote = !!noteText && noteText.toLowerCase() !== insightText.toLowerCase();
  const showInsight = !!insightText;
  const handleRowClick = () => {
    if (focusable) {
      onFocus();
    }
  };
  const hasConcern = !!stop.concern;
  return (
    <li
      id={rowId}
      data-stop-name={stop.name.toLowerCase()}
      onClick={handleRowClick}
      className={`group flex items-start gap-3 rounded-2xl px-3 py-2.5 transition ${
        jumpActive
          ? "bg-amber-50 ring-2 ring-amber-300"
          : active
            ? "bg-brand/5 ring-1 ring-brand/20"
            : focusable
              ? "cursor-pointer hover:bg-slate-50"
              : "hover:bg-slate-50"
                  } ${hasConcern ? "ring-1 ring-rose-200 bg-rose-50/60" : ""}`}
    >
      <button
        type="button"
        role="checkbox"
        aria-checked={stop.booked}
        aria-label={stop.booked ? "Mark not booked" : "Mark booked"}
        onClick={(e) => {
          e.stopPropagation();
          onToggleBooked(!stop.booked);
        }}
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
            onClick={(e) => {
              e.stopPropagation();
              onFocus();
            }}
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
        {(stop.duration_min || stop.selected || stop.cost_display || stop.opening_hours) && (
          <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
            {stop.selected && (
              <span className="pill bg-emerald-50 text-emerald-700 ring-1 ring-emerald-100">
                In trip
              </span>
            )}
            {stop.duration_min ? (
              <span className="chip">{Math.round(stop.duration_min)} min</span>
            ) : null}
            {stop.cost_display && <span className="chip">{stop.cost_display}</span>}
            {stop.opening_hours && <span className="chip">{stop.opening_hours}</span>}
          </div>
        )}
        {(stop.concern || showNote || showInsight) && (
          <div className="mt-1 space-y-0.5">
            {stop.concern && (
              <p className="text-xs font-medium text-rose-700">{stop.concern}</p>
            )}
            {showNote && <p className="text-xs text-slate-500">{noteText}</p>}
            {showInsight && <p className="text-xs text-slate-600">{insightText}</p>}
          </div>
        )}
      </div>

      <div className="mt-0.5 flex flex-shrink-0 flex-col items-end gap-1">
        {removable && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onRemove?.();
            }}
            className={`rounded-full px-3 py-1 text-[11px] font-medium transition ring-1 ${
              stop.kind === "hotel"
                ? "bg-rose-50 text-rose-700 ring-rose-100 hover:bg-rose-100"
                : "bg-slate-50 text-slate-600 ring-slate-200 hover:bg-slate-100"
            }`}
            title={stop.kind === "hotel" ? "Remove stay from itinerary" : "Remove from itinerary"}
          >
            {stop.kind === "hotel" ? "Remove stay" : "Remove"}
          </button>
        )}
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onMap();
          }}
          aria-label={`Show ${stop.name} on the map`}
          className="grid h-7 w-7 place-items-center rounded-full text-slate-400 transition hover:bg-white hover:text-brand"
          title="Show on map"
        >
          <span aria-hidden>{"\u{1F4CD}"}</span>
        </button>
      </div>
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
  jumpTo,
  jumpToken,
  onRemove,
}: {
  day: ItineraryDay;
  active: boolean;
  onToggleBooked: (day: number, name: string, next: boolean) => void;
  onFocus: (kind: string, name: string) => void;
  onMap: (kind: string, name: string) => void;
  focusName?: string | null;
  jumpTo?: { day: number; name: string } | null;
  jumpToken: number;
  onRemove?: (kind: string, name: string) => void;
}) {
  const firstPlace = day.stops.find((stop) => stop.kind === "hotel" || stop.kind === "attraction");
  return (
    <section className="card p-4">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => firstPlace && onMap(firstPlace.kind, firstPlace.name)}
          className="grid h-9 w-9 flex-shrink-0 place-items-center rounded-full text-sm font-bold text-white transition hover:scale-105 hover:shadow-sm disabled:cursor-default disabled:hover:scale-100"
          style={{ backgroundColor: day.color }}
          disabled={!firstPlace}
          title={firstPlace ? `Zoom map to Day ${day.day}` : "No mapped stops yet"}
        >
          {day.day}
        </button>
        <div className="min-w-0">
          <h3 className="display truncate text-base font-semibold text-ink">
            {day.title}
          </h3>
          <div className="flex flex-wrap items-center gap-2">
            {day.date && <p className="text-xs text-slate-400">{day.date}</p>}
            {day.route && (
              <p className="text-xs text-slate-500">
                · {day.route.distance_display} · {day.route.duration_display} · {day.route.mode}
              </p>
            )}
            {day.google_maps_url && (
              <a
                href={day.google_maps_url}
                target="_blank"
                rel="noreferrer"
                className="chip text-brand hover:bg-brand/5"
                title={`Open Day ${day.day} route in Google Maps`}
              >
                Open route ↗
              </a>
            )}
          </div>
          {day.reachability && (
            <p className="mt-1 text-xs text-slate-500">{day.reachability}</p>
          )}
        </div>
      </div>

      {day.summary && (
        <p className="mt-2.5 text-sm leading-relaxed text-slate-600">{day.summary}</p>
      )}

      {day.stops.length > 0 && (
        <ul className="mt-3 space-y-1">
          {day.stops.map((stop, i) => (
            (() => {
              const rowId = `it-stop-${day.day}-${stop.name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
              const jumpActive =
                jumpToken > 0 &&
                !!jumpTo &&
                jumpTo.day === day.day &&
                jumpTo.name.toLowerCase() === stop.name.toLowerCase();
              return (
            <StopRow
              key={`${stop.name}-${i}`}
              stop={stop}
              active={active && focusName?.toLowerCase() === stop.name.toLowerCase()}
              jumpActive={jumpActive}
              rowId={rowId}
              onToggleBooked={(next) => onToggleBooked(day.day, stop.name, next)}
              onFocus={() => onFocus(stop.kind, stop.name)}
              onMap={() => onMap(stop.kind, stop.name)}
              onRemove={onRemove ? () => onRemove(stop.kind, stop.name) : undefined}
            />
              );
            })()
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
  jumpTo,
  onStopRemove,
}: Props) {
  const [it, setIt] = useState<Itinerary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retryToken, setRetryToken] = useState(0);
  const [flashTarget, setFlashTarget] = useState<{ day: number; name: string; token: number } | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchItinerary()
      .then((data) => {
        if (!cancelled) setIt(data);
      })
      .catch(() => {
        if (!cancelled) setError("Could not refresh the itinerary.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [reloadToken, retryToken]);

  const handleToggleBooked = useCallback(
    async (day: number, name: string, next: boolean) => {
      const previous = it;
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
      try {
        const fresh = await setStopBooked(day, name, next);
        setIt(fresh);
        setError(null);
      } catch {
        setIt(previous);
        setError("Could not update the booking status.");
      }
    },
    [it]
  );

  useEffect(() => {
    if (!jumpTo || !it?.has_itinerary) return;
    const rowId = `it-stop-${jumpTo.day}-${jumpTo.name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
    let cancelled = false;
    let attempts = 0;
    let flashTimer: number | undefined;

    const tryScroll = () => {
      if (cancelled) return;
      const el = document.getElementById(rowId);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        setFlashTarget(jumpTo);
        flashTimer = window.setTimeout(() => {
          setFlashTarget((prev) => (prev && prev.token === jumpTo.token ? null : prev));
        }, 2200);
        return;
      }
      if (attempts++ < 8) {
        window.setTimeout(tryScroll, 90);
      }
    };

    const startTimer = window.setTimeout(tryScroll, 30);
    return () => {
      cancelled = true;
      window.clearTimeout(startTimer);
      if (flashTimer) window.clearTimeout(flashTimer);
    };
  }, [jumpTo?.token, jumpTo?.day, jumpTo?.name, it]);

  useEffect(() => {
    if (!focusName || !it?.has_itinerary) return;
    const target = focusName.trim().toLowerCase();
    if (!target) return;
    const rows = Array.from(document.querySelectorAll<HTMLElement>("[data-stop-name]"));
    const row = rows.find((el) => (el.dataset.stopName || "").toLowerCase() === target);
    if (!row) return;
    row.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [focusName, it]);

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
      {error && (
        <div role="status" className="mb-3 rounded-xl bg-rose-50 px-3 py-2 text-xs text-rose-700 ring-1 ring-rose-100">
          {error}{" "}
          <button type="button" onClick={() => setRetryToken((token) => token + 1)} className="font-semibold underline">
            Retry
          </button>
        </div>
      )}
      <header className="mb-3 flex items-center justify-between">
        <h2 className="display text-lg font-semibold text-ink">
          {it.destination ? `${it.destination} itinerary` : "Itinerary"}
        </h2>
        <span className="chip">
          {loading ? "Refreshing… · " : ""}{stats.days} {stats.days === 1 ? "day" : "days"} · {stats.booked}/{stats.stops} booked
        </span>
      </header>
      <div className="space-y-3 pb-6">
        {it.days.map((day) => (
          <DayCard
            key={day.day}
            day={day}
            active
            focusName={focusName}
            jumpTo={jumpTo ? { day: jumpTo.day, name: jumpTo.name } : null}
            jumpToken={flashTarget?.token || 0}
            onToggleBooked={handleToggleBooked}
            onFocus={(kind, name) => onStopFocus?.(kind, name)}
            onMap={(kind, name) => onStopMap?.(kind, name)}
            onRemove={onStopRemove}
          />
        ))}
      </div>
    </div>
  );
}
