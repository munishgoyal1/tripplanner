import { CalendarCheck2, Check, ExternalLink, Loader2, MapPin, Route, Trash2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
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
  jumpTo?: { day: number; name?: string; token: number } | { summary: true; token: number } | null;
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

function dayDateLabel(date: string): string {
  if (!date) return "";
  const parsed = new Date(`${date}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return date;
  return new Intl.DateTimeFormat("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(parsed).replace(",", " ·");
}

function reviewCountLabel(count: number): string {
  return new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(count);
}

function StopRow({
  stop,
  day,
  stopIndex,
  isFirst,
  isLast,
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
  isFirst: boolean;
  isLast: boolean;
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
  const removable = !!onRemove && focusable && stop.kind !== "hotel";
  const [removing, setRemoving] = useState(false);
  const noteText = (stop.note || "").trim();
  const insightText = (stop.insight || "").trim();
  const showNote = !!noteText && noteText.toLowerCase() !== insightText.toLowerCase();
  const showInsight = !!insightText;
  const timingLabel = stop.kind === "hotel" && isFirst
    ? "Depart"
    : stop.kind === "hotel" && isLast
      ? "Return"
      : "Arrive";
  const handleRowClick = () => {
    if (focusable) {
      onFocus();
    }
  };
  return (
    <li
      id={rowId}
      data-stop-name={stop.name.toLowerCase()}
      data-stop-day={day}
      data-stop-index={stopIndex}
      onClick={handleRowClick}
      className={`group grid grid-cols-[3.75rem_minmax(0,1fr)] gap-2 px-1 py-2 transition ${
        jumpActive
          ? "bg-amber-50 ring-2 ring-amber-300"
          : active
            ? "bg-brand/5 ring-1 ring-brand/20"
            : focusable
              ? "cursor-pointer hover:bg-slate-50"
              : "hover:bg-slate-50"
                  }`}
    >
      <div className="pt-0.5 text-left">
        <p className="text-[10px] font-bold uppercase text-slate-400">{timingLabel}</p>
        {stop.time && (
          <p className="text-xs font-bold tabular-nums text-ink">
            {stop.time}{stop.time_estimated ? " est." : ""}
          </p>
        )}
        {stop.kind !== "hotel" && stop.duration_min ? (
          <p className="mt-0.5 text-[10px] text-slate-500">{Math.round(stop.duration_min)} min visit</p>
        ) : null}
        {stop.departure_time && (
          <p className="mt-0.5 text-[10px] font-medium tabular-nums text-slate-600">Leave {stop.departure_time}</p>
        )}
      </div>

      <div className="min-w-0">
        {stop.travel_from_previous && (
          <div
            aria-label={`Travel from previous stop: ${stop.travel_from_previous.distance_display}, ${stop.travel_from_previous.duration_display}`}
            className="mb-1 flex flex-wrap items-center gap-x-1.5 text-[10px] font-medium text-accent"
            title={`${stop.travel_from_previous.mode} estimate`}
          >
            <Route size={11} aria-hidden />
            <span className="font-semibold capitalize">{stop.travel_from_previous.mode}</span>
            <span>{stop.travel_from_previous.distance_display}</span>
            <span aria-hidden>·</span>
            <span>{stop.travel_from_previous.duration_display}</span>
            {stop.travel_from_previous.detail && (
              <span className="basis-full font-normal text-slate-600">{stop.travel_from_previous.detail}</span>
            )}
            {stop.expected_arrival_time && (
              <span className="basis-full font-normal text-slate-500">
                Est. arrive {stop.expected_arrival_time}
                {stop.buffer_before_display && stop.time
                  ? ` · ${stop.buffer_before_display} free before ${stop.time}`
                  : stop.timing_conflict_display
                    ? ` · schedule is ${stop.timing_conflict_display} too tight`
                    : ""}
              </span>
            )}
          </div>
        )}
        <div className="flex items-start gap-1.5">
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
          <div className="min-w-0 flex-1">
            <p className="text-[10px] font-bold uppercase text-slate-400">{stop.kind}</p>
            <button
              type="button"
              disabled={!focusable}
              onClick={(event) => {
                event.stopPropagation();
                onFocus();
              }}
              className={`block max-w-full truncate text-left text-sm font-semibold ${
                focusable ? "text-ink hover:text-brand" : "cursor-default text-ink"
              }`}
              title={focusable ? "Show photos & reviews" : undefined}
            >
              <span className="mr-1" aria-hidden>{KIND_ICON[stop.kind] || KIND_ICON.other}</span>
              {stop.name}
            </button>
          </div>
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-1">
          <button
            type="button"
            aria-pressed={stop.booked}
            aria-label={`${stop.name}: ${stop.booked ? "Mark as needing booking" : "Mark confirmed"}`}
            onClick={(event) => {
              event.stopPropagation();
              onToggleBooked(!stop.booked);
            }}
            className={`inline-flex h-6 items-center gap-1 rounded-full px-2 text-[10px] font-semibold ring-1 transition ${
              stop.booked
                ? "bg-emerald-50 text-emerald-700 ring-emerald-200 hover:bg-emerald-100"
                : "bg-white text-slate-600 ring-slate-200 hover:text-brand hover:ring-brand/30"
            }`}
          >
            {stop.booked ? <Check size={11} aria-hidden /> : <CalendarCheck2 size={11} aria-hidden />}
            {stop.booked ? "Confirmed" : "Needs booking"}
          </button>
          {stop.cost_display && <span className="chip">{stop.cost_display}</span>}
          {stop.opening_hours && <span className="chip">{stop.opening_hours}</span>}
          {typeof stop.rating === "number" && (
            <span className="chip" aria-label={`${stop.name} rating ${stop.rating.toFixed(1)} out of 5`}>
              ★ {stop.rating.toFixed(1)}
              {typeof stop.review_count === "number" && stop.review_count > 0
                ? ` · ${reviewCountLabel(stop.review_count)} reviews`
                : ""}
            </span>
          )}
          {typeof stop.popularity_score === "number" && stop.kind !== "hotel" && (
            <span
              className="chip"
              title="Estimated from Google rating and review volume; not an itinerary inclusion percentage."
            >
              Must-visit score {stop.popularity_score}/100
            </span>
          )}
          {removable && (
            <button
              type="button"
              disabled={removing}
              onClick={async (event) => {
                event.stopPropagation();
                setRemoving(true);
                try {
                  await onRemove?.();
                } finally {
                  setRemoving(false);
                }
              }}
              aria-label={`Remove ${stop.name} from itinerary`}
              className="grid h-6 w-6 place-items-center rounded-full bg-slate-50 text-slate-600 ring-1 ring-slate-200 transition hover:bg-slate-100"
              title="Remove from itinerary"
            >
              {removing ? <Loader2 size={12} className="animate-spin" aria-hidden /> : <Trash2 size={12} aria-hidden />}
            </button>
          )}
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onMap();
            }}
            aria-label={`Show ${stop.name} on the map`}
            className="grid h-6 w-6 place-items-center rounded-full text-slate-400 transition hover:bg-white hover:text-brand"
            title="Show on map"
          >
            <MapPin size={13} aria-hidden />
          </button>
        </div>
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
  const plannedStops = day.stops.filter((stop) => stop.kind !== "hotel");
  const confirmedStops = plannedStops.filter((stop) => stop.booked).length;
  const remainingStops = plannedStops.length - confirmedStops;
  return (
    <section id={`it-day-${day.day}`} className="overflow-hidden rounded-md bg-white shadow-card ring-1 ring-slate-200">
      <div
        onClick={() => onDayMap(day.day)}
        className="group/day grid cursor-pointer gap-2 p-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start"
        title={`Show complete Day ${day.day} circuit on map`}
      >
        <div className="min-w-0">
          <div className="flex items-start gap-3">
            <span
              className="grid h-9 w-9 flex-shrink-0 place-items-center rounded-full text-sm font-bold text-white transition group-hover/day:scale-105 group-hover/day:shadow-sm"
              style={{ backgroundColor: day.color }}
              aria-hidden
            >
              {day.day}
            </span>
            <div className="min-w-0">
              {day.date && <p className="text-[11px] font-bold uppercase text-brand">{dayDateLabel(day.date)}</p>}
              <h3 className="display truncate text-lg font-semibold text-ink">{day.title}</h3>
            </div>
          </div>
          {day.summary && <p className="mt-2 text-xs leading-relaxed text-slate-600">{day.summary}</p>}
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-slate-100 pt-2 text-[11px] text-slate-500">
            <strong className="text-ink">{plannedStops.length} planned {plannedStops.length === 1 ? "stop" : "stops"}</strong>
            {day.schedule?.duration_display && (
              <span className="basis-full">
                <strong className="font-semibold text-ink">Schedule duration:</strong> {day.schedule.duration_display}
                {day.schedule.start && day.schedule.end
                  ? ` · ${day.schedule.start}–${day.schedule.end}${day.schedule.estimated ? " est." : ""}`
                  : day.schedule.estimated ? " est." : ""}
              </span>
            )}
            {day.route && (
              <span className="inline-flex basis-full items-center gap-1">
                <MapPin size={12} aria-hidden />
                <strong className="font-semibold text-ink">Day&apos;s travel:</strong>
                {day.route.duration_display} · {day.route.distance_display} · {day.route.mode}
              </span>
            )}
            <span className={remainingStops > 0 ? "text-amber-700" : "text-emerald-700"}>
              {confirmedStops} confirmed · {remainingStops} to book
            </span>
            {day.reachability && (
              <p className="basis-full text-slate-500">
                <strong className="font-semibold text-accent">Travel rhythm:</strong> {day.reachability}
              </p>
            )}
          </div>
        </div>
        {day.google_maps_url && (
          <a
            href={day.google_maps_url}
            target="_blank"
            rel="noreferrer"
            onClick={(event) => event.stopPropagation()}
            className="inline-flex h-8 items-center justify-center gap-1.5 rounded-full bg-brand px-3 text-xs font-semibold text-white shadow-sm"
            title={`Open Day ${day.day} route in Google Maps`}
          >
            <Route size={13} aria-hidden /> Open route <ExternalLink size={11} aria-hidden />
          </a>
        )}
      </div>

      {day.stops.length > 0 && (
        <ul className="divide-y divide-slate-100 border-t border-slate-200 bg-surface px-3 sm:px-4">
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
              isFirst={i === 0}
              isLast={i === day.stops.length - 1}
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
  const scrollRef = useRef<HTMLDivElement>(null);

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
    if ("summary" in jumpTo) {
      scrollRef.current?.scrollTo({ top: 0, behavior: "smooth" });
      setFlashTarget(null);
      return;
    }
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
        el.scrollIntoView({
          behavior: "smooth",
          block: jumpTo.name ? "center" : "start",
        });
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
  }, [jumpTo, it]);

  useEffect(() => {
    if (!focusName || !it?.has_itinerary) return;
    setFlashTarget(null);
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
      <div ref={scrollRef} className="h-full overflow-y-auto bg-white">
        {overview && <TripSnapshot overview={overview} />}
        <div className="grid min-h-40 place-items-center p-6 text-sm text-slate-400">
          Loading itinerary…
        </div>
      </div>
    );
  }

  if (!it || !it.has_itinerary) {
    return (
      <div ref={scrollRef} className="h-full overflow-y-auto bg-white">
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
    <div ref={scrollRef} className="h-full overflow-y-auto bg-white">
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
            jumpTo={jumpTo && "day" in jumpTo ? { day: jumpTo.day, name: jumpTo.name } : null}
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
