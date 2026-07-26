import { Clock3, ExternalLink, Loader2, MapPin, Route, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { fetchItinerary, setStopBooked } from "../api";
import type { Itinerary, ItineraryDay, ItineraryStop, TripOverview } from "../types";
import TripSnapshot from "./TripSnapshot";

interface Props {
  overview?: TripOverview | null;
  /** Bump to refetch the itinerary after the trip changes. */
  reloadToken?: number;
  /** Click a stop to focus it (loads its photos + highlights its map pin). */
  onStopFocus?: (kind: string, name: string, day: number, stop: number) => void;
  /** Jump to the map focused on a stop (and optionally details). */
  onStopMap?: (kind: string, name: string, day: number, stop: number) => void;
  /** Show the complete route circuit for one itinerary day. */
  onDayMap?: (day: number) => void;
  /** The currently focused stop name (so we can highlight the active row). */
  focusName?: string | null;
  /** Exact focused occurrence for places repeated across days or within a circuit. */
  focusDay?: number;
  focusStop?: number;
  /** Programmatic jump target after add-to-trip actions. */
  jumpTo?: { day: number; name?: string; token: number } | null;
  /** Remove a stop from the itinerary / trip. */
  onStopRemove?: (kind: string, name: string, day: number, stop: number) => void | Promise<void>;
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
  return ["hotel", "attraction", "meal", "restaurant"].includes(kind);
}

function StopRow({
  stop,
  day,
  stopIndex,
  mapLabel,
  active,
  jumpActive,
  rowId,
  onToggleBooked,
  onFocus,
  onMap,
  onRemove,
}: {
  stop: ItineraryStop;
  day: number;
  stopIndex: number;
  mapLabel?: string;
  active: boolean;
  jumpActive: boolean;
  rowId: string;
  onToggleBooked: (next: boolean) => void;
  onFocus: () => void;
  onMap: () => void;
  onRemove?: () => void | Promise<void>;
}) {
  const focusable = canFocus(stop.kind);
  const removable = !!onRemove && focusable;
  const [removing, setRemoving] = useState(false);
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
      data-stop-day={day}
      data-stop-index={stopIndex}
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
        aria-label={`${stop.name}: ${stop.booked ? "Mark not booked" : "Mark booked"}`}
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
        {stop.travel_from_previous && (
          <div
            aria-label={`Travel from previous stop: ${stop.travel_from_previous.distance_display}, ${stop.travel_from_previous.duration_display}`}
            className="mb-1 flex items-center gap-1 text-[10px] font-medium text-slate-400"
            title={`${stop.travel_from_previous.mode} estimate`}
          >
            <Route size={11} aria-hidden />
            <span>{stop.travel_from_previous.distance_display}</span>
            <span aria-hidden>·</span>
            <span>{stop.travel_from_previous.duration_display}</span>
          </div>
        )}
        <div className="flex items-center gap-2">
          {mapLabel && (
            <span
              aria-label={mapLabel === "H" ? "Hotel map marker" : `Map stop ${mapLabel}`}
              aria-current={active ? "location" : undefined}
              className={`grid h-5 w-5 flex-shrink-0 place-items-center rounded-full border text-[10px] font-semibold tabular-nums transition ${active ? "scale-110 text-white shadow-sm" : "bg-white"}`}
              style={{
                borderColor: stop.color,
                color: active ? "white" : stop.color,
                backgroundColor: active ? stop.color : "white",
              }}
            >
              {mapLabel}
            </span>
          )}
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
            disabled={removing}
            onClick={async (e) => {
              e.stopPropagation();
              setRemoving(true);
              try {
                await onRemove?.();
              } finally {
                setRemoving(false);
              }
            }}
            aria-label={stop.kind === "hotel" ? `Remove ${stop.name} stay` : `Remove ${stop.name} from itinerary`}
            className={`grid h-7 w-7 place-items-center rounded-full transition ring-1 ${
              stop.kind === "hotel"
                ? "bg-rose-50 text-rose-700 ring-rose-100 hover:bg-rose-100"
                : "bg-slate-50 text-slate-600 ring-slate-200 hover:bg-slate-100"
            }`}
            title={stop.kind === "hotel" ? "Remove stay from itinerary" : "Remove from itinerary"}
          >
            {removing ? <Loader2 size={13} className="animate-spin" aria-hidden /> : <Trash2 size={13} aria-hidden />}
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
          <MapPin size={15} aria-hidden />
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
  onDayMap,
  focusName,
  focusDay,
  focusStop,
  jumpTo,
  jumpToken,
  onRemove,
}: {
  day: ItineraryDay;
  active: boolean;
  onToggleBooked: (day: number, name: string, next: boolean) => void;
  onFocus: (kind: string, name: string, day: number, stop: number) => void;
  onMap: (kind: string, name: string, day: number, stop: number) => void;
  onDayMap: (day: number) => void;
  focusName?: string | null;
  focusDay?: number;
  focusStop?: number;
  jumpTo?: { day: number; name?: string } | null;
  jumpToken: number;
  onRemove?: (kind: string, name: string, day: number, stop: number) => void;
}) {
  let visitOrder = 0;
  const mapLabels = day.stops.map((stop) => {
    if (stop.kind === "hotel") return "H";
    if (!["attraction", "meal", "restaurant"].includes(stop.kind)) return undefined;
    visitOrder += 1;
    return String(visitOrder);
  });
  const plannedMinutes = day.stops.reduce((total, stop) => total + (stop.duration_min || 0), 0);
  const plannedDuration = plannedMinutes > 0
    ? plannedMinutes >= 60
      ? `${Math.floor(plannedMinutes / 60)}h${plannedMinutes % 60 ? ` ${plannedMinutes % 60}m` : ""}`
      : `${plannedMinutes}m`
    : null;
  return (
    <section id={`it-day-${day.day}`} className="card p-4">
      <div
        onClick={() => onDayMap(day.day)}
        className="group/day flex cursor-pointer items-center gap-3"
        title={`Show complete Day ${day.day} circuit on map`}
      >
        <span
          className="grid h-9 w-9 flex-shrink-0 place-items-center rounded-full text-sm font-bold text-white transition hover:scale-105 hover:shadow-sm disabled:cursor-default disabled:hover:scale-100"
          style={{ backgroundColor: day.color }}
          aria-hidden
        >
          {day.day}
        </span>
        <div className="min-w-0">
          <h3 className="display truncate text-base font-semibold text-ink">
            {day.title}
          </h3>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-xs text-slate-500">
            {day.date && <span>{day.date}</span>}
            <span>{day.stops.length} {day.stops.length === 1 ? "stop" : "stops"}</span>
            {plannedDuration && (
              <span className="inline-flex items-center gap-1">
                <Clock3 size={12} aria-hidden /> {plannedDuration} planned
              </span>
            )}
            {day.route && (
              <span className="inline-flex items-center gap-1">
                <MapPin size={12} aria-hidden /> {day.route.distance_display} · {day.route.duration_display} · {day.route.mode}
              </span>
            )}
            {day.google_maps_url && (
              <a
                href={day.google_maps_url}
                target="_blank"
                rel="noreferrer"
                onClick={(event) => event.stopPropagation()}
                className="inline-flex items-center gap-1 font-medium text-brand hover:text-brand/80"
                title={`Open Day ${day.day} route in Google Maps`}
              >
                <ExternalLink size={12} aria-hidden /> Open route
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
                !!jumpTo.name &&
                jumpTo.name.toLowerCase() === stop.name.toLowerCase();
              return (
            <StopRow
              key={`${stop.name}-${i}`}
              stop={stop}
              day={day.day}
              stopIndex={i + 1}
              mapLabel={mapLabels[i]}
              active={
                active
                && focusName?.toLowerCase() === stop.name.toLowerCase()
                && (focusDay == null || focusDay === day.day)
                && (focusStop == null || focusStop === i + 1)
              }
              jumpActive={jumpActive}
              rowId={rowId}
              onToggleBooked={(next) => onToggleBooked(day.day, stop.name, next)}
              onFocus={() => onFocus(stop.kind, stop.name, day.day, i + 1)}
              onMap={() => onMap(stop.kind, stop.name, day.day, i + 1)}
              onRemove={onRemove ? () => onRemove(stop.kind, stop.name, day.day, i + 1) : undefined}
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
  overview,
  reloadToken = 0,
  onStopFocus,
  onStopMap,
  onDayMap,
  focusName,
  focusDay,
  focusStop,
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
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fetchItinerary(controller.signal)
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
      controller.abort();
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
    const targetId = jumpTo.name
      ? `it-stop-${jumpTo.day}-${jumpTo.name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`
      : `it-day-${jumpTo.day}`;
    let cancelled = false;
    let attempts = 0;
    let flashTimer: number | undefined;

    const tryScroll = () => {
      if (cancelled) return;
      const el = document.getElementById(targetId);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        if (jumpTo.name) {
          setFlashTarget({ day: jumpTo.day, name: jumpTo.name, token: jumpTo.token });
          flashTimer = window.setTimeout(() => {
            setFlashTarget((prev) => (prev && prev.token === jumpTo.token ? null : prev));
          }, 2200);
        }
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
    const row = rows.find((el) =>
      (el.dataset.stopName || "").toLowerCase() === target
      && (focusDay == null || Number(el.dataset.stopDay) === focusDay)
      && (focusStop == null || Number(el.dataset.stopIndex) === focusStop)
    );
    if (!row) return;
    row.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [focusName, focusDay, focusStop, it]);

  if (loading && !it) {
    return (
      <div className="h-full overflow-y-auto bg-white">
        {overview && <TripSnapshot overview={overview} />}
        <div className="grid min-h-40 place-items-center p-6 text-sm text-slate-400">
          Loading itinerary…
        </div>
      </div>
    );
  }

  if (!it || !it.has_itinerary) {
    return (
      <div className="h-full overflow-y-auto bg-white">
        {overview && <TripSnapshot overview={overview} />}
        <div className="grid min-h-48 place-items-center p-6 text-center">
          <div className="max-w-xs text-sm text-slate-500">
            No day-by-day plan yet. Once the assistant builds your itinerary, each
            day's stops will appear here — check them off as you book.
          </div>
        </div>
      </div>
    );
  }

  const { stats } = it;
  return (
    <div className="h-full overflow-y-auto bg-white">
      {overview && <TripSnapshot overview={overview} booked={stats.booked} stops={stats.stops} />}
      <div className="px-4 py-4">
        {error && (
          <div role="status" className="mb-3 rounded-xl bg-rose-50 px-3 py-2 text-xs text-rose-700 ring-1 ring-rose-100">
            {error}{" "}
            <button type="button" onClick={() => setRetryToken((token) => token + 1)} className="font-semibold underline">
              Retry
            </button>
          </div>
        )}
        <header className="mb-3 flex items-center justify-between gap-3">
          <h2 className="text-xs font-semibold uppercase text-slate-500">Day by day</h2>
          {!overview && (
            <span className="chip">
              {loading ? "Refreshing… · " : ""}{stats.days} {stats.days === 1 ? "day" : "days"} · {stats.booked}/{stats.stops} booked
            </span>
          )}
        </header>
        <div className="space-y-3 pb-6">
        {it.days.map((day) => (
          <DayCard
            key={day.day}
            day={day}
            active
            focusName={focusName}
            focusDay={focusDay}
            focusStop={focusStop}
            jumpTo={jumpTo ? { day: jumpTo.day, name: jumpTo.name } : null}
            jumpToken={flashTarget?.token || 0}
            onToggleBooked={handleToggleBooked}
            onFocus={(kind, name, focusDay, stop) => onStopFocus?.(kind, name, focusDay, stop)}
            onMap={(kind, name, mapDay, stop) => onStopMap?.(kind, name, mapDay, stop)}
            onDayMap={(mapDay) => onDayMap?.(mapDay)}
            onRemove={onStopRemove}
          />
        ))}
        </div>
      </div>
    </div>
  );
}
