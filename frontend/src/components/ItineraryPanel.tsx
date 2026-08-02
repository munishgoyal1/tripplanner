import { ExternalLink, MapPin, Route } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { fetchItinerary, setStopBooked } from "../api";
import type { Itinerary, ItineraryDay, ItineraryStop, TripOverview } from "../types";
import ItineraryStopRow from "./ItineraryStopRow";
import TripSnapshot from "./TripSnapshot";
import WeatherIcon from "./WeatherIcon";

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

function normalizedPlaceName(name: string): string {
  return name.trim().replace(/\s+/g, " ").toLowerCase();
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
  const hotelNames = [...new Set(
    day.stops
      .filter((stop) => stop.kind === "hotel")
      .map((stop) => normalizedPlaceName(stop.name)),
  )];
  const hotelLabels = new Map(
    hotelNames.map((name, index) => [name, hotelNames.length > 1 ? `H${index + 1}` : "H"]),
  );
  const mapLabels = day.stops.map((stop) => {
    if (stop.kind === "hotel") return hotelLabels.get(normalizedPlaceName(stop.name));
    if (stop.kind === "airport") return "A";
    if (!["attraction", "meal", "restaurant"].includes(stop.kind)) return undefined;
    visitOrder += 1;
    return String(visitOrder);
  });
  const plannedStops = day.stops.filter((stop) => !["hotel", "airport"].includes(stop.kind));
  const confirmedStops = plannedStops.filter((stop) => stop.booked).length;
  const remainingStops = plannedStops.length - confirmedStops;
  const firstStop = day.stops[0];
  const lastStop = day.stops[day.stops.length - 1];
  const hasHotelEndpoints = day.stops.length > 1 && firstStop?.kind === "hotel" && lastStop?.kind === "hotel";
  const circuitHotelIndex = lastStop?.kind === "hotel"
    ? day.stops.findIndex((stop, index) => (
      index < day.stops.length - 1
      && stop.kind === "hotel"
      && normalizedPlaceName(stop.name) === normalizedPlaceName(lastStop.name)
    ))
    : -1;
  const combinesHotelCircuit = circuitHotelIndex >= 0;
  const changesHotel = hasHotelEndpoints && normalizedPlaceName(firstStop.name) !== normalizedPlaceName(lastStop.name);
  const destinationHotelIndex = changesHotel
    ? combinesHotelCircuit ? circuitHotelIndex : day.stops.length - 1
    : -1;
  const visibleStops = day.stops
    .map((stop, index) => ({ stop, index }))
    .filter(({ index }) => !combinesHotelCircuit || index < day.stops.length - 1);
  const renderStop = ({ stop, index: i }: { stop: ItineraryStop; index: number }) => {
    const returnStop = combinesHotelCircuit && i === circuitHotelIndex ? lastStop : undefined;
    const representedStopIndexes = returnStop ? [i + 1, day.stops.length] : [i + 1];
    const rowId = `it-stop-${day.day}-${stop.name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
    const jumpActive =
      jumpToken > 0
      && !!jumpTo
      && jumpTo.day === day.day
      && !!jumpTo.name
      && jumpTo.name.toLowerCase() === stop.name.toLowerCase();
    return (
      <ItineraryStopRow
        key={`${stop.name}-${i}`}
        stop={stop}
        day={day.day}
        stopIndex={i + 1}
        isFirst={i === 0}
        isLast={i === day.stops.length - 1}
        hotelTimingLabel={changesHotel && i === 0 ? "Check out" : changesHotel && i === destinationHotelIndex ? "Check in" : undefined}
        returnStop={returnStop}
        representedStopIndexes={representedStopIndexes}
        mapLabel={mapLabels[i]}
        active={
          active
          && focusName?.toLowerCase() === stop.name.toLowerCase()
          && (focusDay == null || focusDay === day.day)
          && (focusStop == null || representedStopIndexes.includes(focusStop))
        }
        jumpActive={jumpActive}
        rowId={rowId}
        onToggleBooked={(next) => onToggleBooked(day.day, stop.name, next)}
        onFocus={() => onFocus(stop.kind, stop.name, day.day, i + 1)}
        onMap={() => onMap(stop.kind, stop.name, day.day, i + 1)}
        onRemove={onRemove ? () => onRemove(stop.kind, stop.name, day.day, i + 1) : undefined}
      />
    );
  };
  return (
    <section id={`it-day-${day.day}`} className="overflow-hidden rounded-md bg-white shadow-card ring-1 ring-slate-200">
      <div
        onClick={() => onDayMap(day.day)}
        className="group/day grid cursor-pointer gap-2 px-3 py-2.5 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start"
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
              {day.weather && (
                <div
                  className="mt-1 inline-flex items-center gap-1.5 text-xs font-medium text-slate-600"
                  aria-label={`${day.weather.summary}, high ${day.weather.high_c ?? "unknown"} degrees Celsius, low ${day.weather.low_c ?? "unknown"} degrees Celsius`}
                  title={day.weather.precip_probability_pct != null ? `${day.weather.precip_probability_pct}% chance of precipitation` : day.weather.summary}
                >
                  <span className="text-accent"><WeatherIcon condition={day.weather.condition} size={16} /></span>
                  <span>{day.weather.summary}</span>
                  {day.weather.high_c != null && day.weather.low_c != null && (
                    <span className="tabular-nums text-slate-500">{Math.round(day.weather.high_c)}° / {Math.round(day.weather.low_c)}°C</span>
                  )}
                  {day.weather.precip_probability_pct != null && day.weather.precip_probability_pct >= 30 && (
                    <span className="text-sky-700">{Math.round(day.weather.precip_probability_pct)}% rain</span>
                  )}
                </div>
              )}
            </div>
          </div>
          {day.summary && <p className="mt-2 text-xs leading-relaxed text-slate-600">{day.summary}</p>}
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-slate-100 pt-1.5 text-[11px] text-slate-500">
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
        changesHotel && destinationHotelIndex > 0 ? (
          <div className="border-t border-slate-200 bg-surface px-3 py-3 sm:px-4" aria-label={`Stay handoff from ${firstStop.name} to ${day.stops[destinationHotelIndex].name}`}>
            <div className="mb-2 flex items-center justify-between gap-3">
              <p className="text-[10px] font-bold uppercase text-brand">Stay handoff</p>
              <p className="text-[10px] text-slate-500">Leaving → arriving</p>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              <ul className="overflow-hidden rounded-md bg-white ring-1 ring-slate-200">
                {renderStop(visibleStops[0])}
              </ul>
              <ul className="overflow-hidden rounded-md bg-white ring-1 ring-slate-200">
                {renderStop(visibleStops.find(({ index }) => index === destinationHotelIndex)!)}
              </ul>
            </div>
            {destinationHotelIndex > 1 && (
              <section className="mt-3 overflow-hidden rounded-md bg-teal-50/70 ring-1 ring-teal-100" aria-label="Journey between stays">
                <p className="px-3 pt-2 text-[10px] font-bold uppercase text-teal-800">Journey</p>
                <ul className="divide-y divide-teal-100 px-2 pb-1">
                  {visibleStops.filter(({ index }) => index > 0 && index < destinationHotelIndex).map(renderStop)}
                </ul>
              </section>
            )}
            {visibleStops.some(({ index }) => index > destinationHotelIndex) && (
              <section className="mt-3" aria-label="Plans after check-in">
                <p className="mb-1 px-1 text-[10px] font-bold uppercase text-slate-500">After check-in</p>
                <ul className="divide-y divide-slate-100">
                  {visibleStops.filter(({ index }) => index > destinationHotelIndex).map(renderStop)}
                </ul>
              </section>
            )}
          </div>
        ) : (
          <ul className="divide-y divide-slate-100 border-t border-slate-200 bg-surface px-3 sm:px-4">
            {visibleStops.map(renderStop)}
          </ul>
        )
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
      && (focusStop == null || (el.dataset.stopIndexes || el.dataset.stopIndex || "").split(",").includes(String(focusStop)))
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
