import { Clock3, ExternalLink, MapPin, Minus, Plus, Route, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { fetchItinerary, setStopBooked } from "../api";
import type { Itinerary, ItineraryDay, ItineraryStop, TripOverview } from "../types";
import { itineraryStopMatchesFilters, type ItineraryFilter } from "../lib/itineraryFilters";
import { formatDistance, formatTemperature, useDisplayPreferences } from "../lib/displayPreferences";
import ItineraryFilterControls from "./ItineraryFilterControls";
import ItineraryStopRow from "./ItineraryStopRow";
import TripSnapshot from "./TripSnapshot";
import TripVerificationCard from "./TripVerificationCard";
import WeatherIcon from "./WeatherIcon";
import { hotelIdentityGroups, hotelIdentityMatches } from "./map/placeIdentity";

const ITINERARY_LOAD_DEADLINE_MS = 30_000;

interface Props {
  filters?: readonly ItineraryFilter[];
  onFilterToggle?: (filter: ItineraryFilter) => void;
  headerTarget?: HTMLElement | null;
  overview?: TripOverview | null;
  /** Bump to refetch the itinerary after the trip changes. */
  reloadToken?: number;
  /** Stable identity of the active trip; a change clears the outgoing itinerary. */
  tripId?: string | null;
  /** Itinerary handed over by a trip switch; consumed once, then refetches. */
  seed?: Itinerary | null;
  /** A workspace fetch that will deliver `seed` is in flight. */
  seedPending?: boolean;
  /** Click a stop to focus it (loads its photos + highlights its map pin). */
  onStopFocus?: (kind: string, name: string, day: number, stop: number, routeCircuitId?: string) => void;
  /** Jump to the map focused on a stop (and optionally details). */
  onStopMap?: (kind: string, name: string, day: number, stop: number, routeCircuitId?: string) => void;
  /** Show the complete route circuit for one itinerary day. */
  onDayMap?: (day: number) => void;
  /** Show all itinerary day circuits on the map. */
  onAllDaysMap?: () => void;
  /** Aggregate map selection shared with the day and All days controls. */
  circuitFocusDay?: number;
  circuitFocusToken?: number;
  /** The currently focused stop name (so we can highlight the active row). */
  focusName?: string | null;
  /** Exact focused occurrence for places repeated across days or within a circuit. */
  focusDay?: number;
  focusStop?: number;
  /** Bumped on every focus click so re-picking the same place scrolls again. */
  focusToken?: number;
  /** Programmatic jump target after add-to-trip actions. */
  jumpTo?: { day: number; name?: string; token: number } | { summary: true; token: number } | null;
  /** Remove a stop from the itinerary / trip. */
  onStopRemove?: (kind: string, name: string, day: number, stop: number) => void | Promise<void>;
  /** Refresh authoritative workspace state after this panel persists trip metadata. */
  onTripChanged?: () => void | Promise<void>;
  /** Ask the planner to add or remove one day while preserving trip coherence. */
  onAdjustDays?: (direction: "add" | "reduce", replanWholeTrip: boolean) => void;
  /** Reports the itinerary this pane currently shows, including booking toggles. */
  onItineraryChange?: (itinerary: Itinerary | null) => void;
}

type RowDensity = "comfortable" | "compact";

function TripLengthControls({
  days,
  onAdjust,
}: {
  days: number;
  onAdjust?: (direction: "add" | "reduce", replanWholeTrip: boolean) => void;
}) {
  const [pending, setPending] = useState<"add" | "reduce" | null>(null);
  const [replanWholeTrip, setReplanWholeTrip] = useState(false);

  const open = (direction: "add" | "reduce") => {
    setReplanWholeTrip(false);
    setPending(direction);
  };

  if (!onAdjust) return null;
  return (
    <div className="relative ml-auto flex shrink-0 items-center gap-1">
      <button type="button" onClick={() => open("add")} className="inline-flex h-7 items-center gap-1 rounded px-2 text-[12px] font-semibold text-brand hover:bg-brand/10">
        <Plus size={13} aria-hidden /> Add a day
      </button>
      <button type="button" disabled={days <= 1} onClick={() => open("reduce")} className="inline-flex h-7 items-center gap-1 rounded px-2 text-[12px] font-semibold text-muted hover:bg-sand hover:text-ink disabled:opacity-40">
        <Minus size={13} aria-hidden /> Reduce a day
      </button>
      {pending && (
        <section className="absolute right-0 top-full z-40 mt-1 w-72 rounded-md border border-border bg-paper p-3 text-left shadow-pop" aria-label={pending === "add" ? "Add a day" : "Reduce a day"}>
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold text-ink">{pending === "add" ? "Add one more day" : "Remove one day"}</h3>
              <p className="mt-1 text-[11px] leading-relaxed text-muted">
                {pending === "add"
                  ? "Dates, hotel nights and departure plans will update automatically with minimal changes."
                  : "Dates, hotel nights and the remaining stops will be adjusted coherently with minimal changes."}
              </p>
            </div>
            <button type="button" onClick={() => setPending(null)} className="grid h-6 w-6 shrink-0 place-items-center rounded-md text-muted hover:bg-sand" aria-label="Close day adjustment">
              <X size={13} aria-hidden />
            </button>
          </div>
          <label className="mt-3 flex cursor-pointer items-start gap-2 rounded-lg bg-sand/60 p-2 text-[11px] text-ink">
            <input type="checkbox" checked={replanWholeTrip} onChange={(event) => setReplanWholeTrip(event.target.checked)} className="mt-0.5" />
            <span><strong className="block font-semibold">Replan the whole itinerary</strong><span className="text-muted">Unchecked keeps existing days stable and makes only the changes needed.</span></span>
          </label>
          <button
            type="button"
            onClick={() => {
              onAdjust(pending, replanWholeTrip);
              setPending(null);
            }}
            className="mt-3 inline-flex h-8 w-full items-center justify-center rounded-md bg-ink px-3 text-xs font-semibold text-white hover:bg-ink/90"
          >
            {pending === "add" ? "Add day and update trip" : "Reduce day and update trip"}
          </button>
        </section>
      )}
    </div>
  );
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

function DayCard({
  day,
  filters,
  active,
  circuitActive,
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
  compact,
}: {
  day: ItineraryDay;
  filters: readonly ItineraryFilter[];
  active: boolean;
  circuitActive: boolean;
  onToggleBooked: (day: number, name: string, next: boolean) => void;
  onFocus: (kind: string, name: string, day: number, stop: number, routeCircuitId?: string) => void;
  onMap: (kind: string, name: string, day: number, stop: number, routeCircuitId?: string) => void;
  onDayMap: (day: number) => void;
  focusName?: string | null;
  focusDay?: number;
  focusStop?: number;
  jumpTo?: { day: number; name?: string } | null;
  jumpToken: number;
  onRemove?: (kind: string, name: string, day: number, stop: number) => void;
  compact: boolean;
}) {
  const { region } = useDisplayPreferences();
  let visitOrder = 0;
  const hotelNames = hotelIdentityGroups(
    day.stops.filter((stop) => stop.kind === "hotel").map((stop) => stop.name),
  );
  const hotelLabels = new Map(
    hotelNames.map((name, index) => [name, hotelNames.length > 1 ? `H${index + 1}` : "H"]),
  );
  const mapLabels = day.stops.map((stop) => {
    if (stop.kind === "hotel") {
      const hotelName = hotelNames.find((name) => hotelIdentityMatches(name, stop.name));
      return hotelName ? hotelLabels.get(hotelName) : undefined;
    }
    if (stop.kind === "airport") return "A";
    if (stop.kind === "origin") return "O";
    if (!["attraction", "meal", "restaurant"].includes(stop.kind)) return undefined;
    visitOrder += 1;
    return String(visitOrder);
  });
  const plannedStops = day.stops.filter((stop) => !["hotel", "airport", "origin"].includes(stop.kind));
  const confirmedStops = plannedStops.filter((stop) => stop.booked).length;
  const remainingStops = plannedStops.length - confirmedStops;
  const firstStop = day.stops[0];
  const lastStop = day.stops[day.stops.length - 1];
  const hasHotelEndpoints = day.stops.length > 1 && firstStop?.kind === "hotel" && lastStop?.kind === "hotel";
  const circuitHotelIndex = lastStop?.kind === "hotel"
    ? day.stops.findIndex((stop, index) => (
      index < day.stops.length - 1
      && stop.kind === "hotel"
      && hotelIdentityMatches(stop.name, lastStop.name)
    ))
    : -1;
  const combinesHotelCircuit = circuitHotelIndex >= 0;
  const changesHotel = hasHotelEndpoints && !hotelIdentityMatches(firstStop.name, lastStop.name);
  const destinationHotelIndex = changesHotel
    ? combinesHotelCircuit ? circuitHotelIndex : day.stops.length - 1
    : -1;
  const visibleStops = day.stops
    .map((stop, index) => ({ stop, index }))
    .filter(({ stop, index }) => itineraryStopMatchesFilters(stop, filters, day.stops, index));
  const renderStop = ({ stop, index: i }: { stop: ItineraryStop; index: number }) => {
    const circuitReturn = combinesHotelCircuit && i === day.stops.length - 1;
    const representedStopIndexes = [i + 1];
    const baseRowId = `it-stop-${day.day}-${stop.name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
    const rowId = circuitReturn ? `${baseRowId}-return` : baseRowId;
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
        circuitReturn={circuitReturn}
        representedStopIndexes={representedStopIndexes}
        mapLabel={circuitReturn ? undefined : mapLabels[i]}
        active={
          active
          && focusName?.toLowerCase() === stop.name.toLowerCase()
          && (focusDay == null || focusDay === day.day)
          && (focusStop == null || representedStopIndexes.includes(focusStop))
        }
        jumpActive={jumpActive}
        rowId={rowId}
        compact={compact}
        onToggleBooked={(next) => onToggleBooked(day.day, stop.name, next)}
        onFocus={() => stop.route_circuit_id
          ? onFocus(stop.kind, stop.name, day.day, i + 1, stop.route_circuit_id)
          : onFocus(stop.kind, stop.name, day.day, i + 1)}
        onMap={() => stop.route_circuit_id
          ? onMap(stop.kind, stop.name, day.day, i + 1, stop.route_circuit_id)
          : onMap(stop.kind, stop.name, day.day, i + 1)}
        onRemove={onRemove ? () => onRemove(stop.kind, stop.name, day.day, i + 1) : undefined}
      />
    );
  };
  const bookedPct = plannedStops.length ? Math.round((confirmedStops / plannedStops.length) * 100) : 0;
  const stopList = day.stops.length > 0 && (
    <ul
      aria-label={changesHotel && destinationHotelIndex > 0
        ? `Transition day timeline from ${firstStop.name} to ${day.stops[destinationHotelIndex].name}`
        : undefined}
      className="divide-y divide-border/70 border-t border-border pb-1"
    >
      {visibleStops.map(renderStop)}
    </ul>
  );
  return (
    <section id={`it-day-${day.day}`} data-audit-day={day.day} className="bg-paper">
      {/* A sticky, day-tinted band marks every day change, even mid-scroll. */}
      <div
        className="sticky top-0 z-10 flex items-center gap-3 border-b border-border px-3 py-2.5"
        style={{
          borderTop: `3px solid ${day.color}`,
          background: circuitActive
            ? `color-mix(in oklch, ${day.color} 16%, oklch(var(--paper)))`
            : `color-mix(in oklch, ${day.color} 6%, oklch(var(--paper)))`,
        }}
      >
        <button
          type="button"
          onClick={() => onDayMap(day.day)}
          aria-current={circuitActive ? "true" : undefined}
          className="group/day flex min-w-0 flex-1 items-center gap-2.5 text-left"
          title={`Show complete Day ${day.day} circuit on map`}
        >
          <span
            className="grid h-8 w-8 flex-shrink-0 place-items-center rounded-md text-[13px] font-bold text-white transition group-hover/day:shadow-sm"
            style={{ backgroundColor: day.color }}
            aria-hidden
          >
            {day.day}
          </span>
          <span className="min-w-0">
            <h3 className="text-[16.5px] font-semibold leading-tight tracking-[-0.015em] text-ink">{day.title}</h3>
            {day.date && <p className="text-[12px] text-muted">{dayDateLabel(day.date)}</p>}
          </span>
        </button>
        <div className="flex flex-shrink-0 flex-col items-end gap-1">
          {day.weather && (
            <div
              className="inline-flex items-center gap-1.5 text-[12px] font-medium text-muted"
              aria-label={`${day.weather.summary}, high ${day.weather.high_c ?? "unknown"} degrees Celsius, low ${day.weather.low_c ?? "unknown"} degrees Celsius`}
              title={day.weather.precip_probability_pct != null ? `${day.weather.precip_probability_pct}% chance of precipitation` : day.weather.summary}
            >
              <span className="text-accent"><WeatherIcon condition={day.weather.condition} size={15} /></span>
              {day.weather.high_c != null && day.weather.low_c != null && (
                <span className="tabular-nums text-ink">{formatTemperature(day.weather.high_c, region)} / {formatTemperature(day.weather.low_c, region)}</span>
              )}
              {day.weather.precip_probability_pct != null && day.weather.precip_probability_pct >= 30 && (
                <span className="text-sky-700">{Math.round(day.weather.precip_probability_pct)}% rain</span>
              )}
            </div>
          )}
          {plannedStops.length > 0 && (
            <span
              className="flex items-center gap-1.5 text-[11px] tabular-nums text-muted"
              title={`${confirmedStops} of ${plannedStops.length} planned stops confirmed`}
              aria-hidden
            >
              <span className="h-1 w-12 overflow-hidden rounded-full bg-border">
                <span className="block h-full rounded-full bg-emerald-600" style={{ width: `${bookedPct}%` }} />
              </span>
              {confirmedStops}/{plannedStops.length}
            </span>
          )}
        </div>
      </div>

      <div className="px-3 pb-2.5 pt-2.5">
        {day.summary && <p className="text-[13px] leading-relaxed text-ink/80">{day.summary}</p>}
        <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[12px] text-muted">
          {day.weather && <span>{day.weather.summary}</span>}
          {day.schedule?.duration_display && (
            <span className="inline-flex items-center gap-1 tabular-nums">
              <Clock3 size={12} aria-hidden />
              <strong className="font-medium text-ink">Schedule duration:</strong> {day.schedule.duration_display}
              {day.schedule.start && day.schedule.end
                ? ` · ${day.schedule.start}–${day.schedule.end}${day.schedule.estimated ? " est." : ""}`
                : day.schedule.estimated ? " est." : ""}
            </span>
          )}
          {day.route && (
            <span className="inline-flex items-center gap-1 tabular-nums">
              <MapPin size={12} aria-hidden />
              <strong className="font-medium text-ink">Day&apos;s travel:</strong>
              {day.route.duration_display} · {formatDistance(day.route.distance_km, region)} · {day.route.mode}
            </span>
          )}
          <span className="inline-flex flex-wrap items-center gap-x-1.5">
            <strong className="font-medium text-ink">{plannedStops.length} planned {plannedStops.length === 1 ? "stop" : "stops"}</strong>
            <span aria-hidden>·</span>
            <span className={remainingStops > 0 ? "text-amber-700" : "text-emerald-700"}>
              {confirmedStops} confirmed · {remainingStops} to book
            </span>
          </span>
        </div>
        {day.reachability && (
          <p className="mt-1.5 text-[12px] leading-relaxed text-muted">
            <strong className="font-semibold text-ink">Travel rhythm:</strong> {day.reachability}
          </p>
        )}
        <div className="mt-1.5 flex items-center gap-1">
          <button
            type="button"
            onClick={() => onDayMap(day.day)}
            className={`inline-flex h-7 items-center gap-1.5 rounded px-1.5 text-[12px] font-semibold transition ${
              circuitActive ? "bg-ink text-white" : "text-muted hover:bg-sand hover:text-ink"
            }`}
          >
            <Route size={12} aria-hidden /> Day on map
          </button>
          {day.google_maps_url && (
            <a
              href={day.google_maps_url}
              target="_blank"
              rel="noreferrer"
              onClick={(event) => event.stopPropagation()}
              className="inline-flex h-7 items-center gap-1.5 rounded px-1.5 text-[12px] font-semibold text-muted transition hover:bg-sand hover:text-ink"
              title={`Open Day ${day.day} route in Google Maps`}
            >
              <Route size={12} aria-hidden /> Open route <ExternalLink size={11} aria-hidden />
            </a>
          )}
        </div>
      </div>

      {stopList}
    </section>
  );
}

export default function ItineraryPanel({
  filters = [],
  onFilterToggle,
  headerTarget,
  overview,
  reloadToken = 0,
  tripId = null,
  seed = null,
  seedPending = false,
  onStopFocus,
  onStopMap,
  onDayMap,
  onAllDaysMap,
  circuitFocusDay,
  circuitFocusToken = 0,
  focusName,
  focusDay,
  focusStop,
  focusToken = 0,
  jumpTo,
  onStopRemove,
  onTripChanged,
  onAdjustDays,
  onItineraryChange,
}: Props) {
  const [it, setIt] = useState<Itinerary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retryToken, setRetryToken] = useState(0);
  const [flashTarget, setFlashTarget] = useState<{ day: number; name: string; token: number } | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const previousTripIdRef = useRef(tripId);
  const consumedSeedRef = useRef<Itinerary | null>(null);
  const seededRequestRef = useRef<{ reloadToken: typeof reloadToken; retryToken: number; tripId: typeof tripId } | null>(null);
  const [density, setDensity] = useState<RowDensity>("comfortable");
  const allDaysActive = circuitFocusDay == null && circuitFocusToken > 0;
  const readiness = it?.has_itinerary
    ? <span className="shrink-0 text-[11px] font-medium tabular-nums text-muted" title="Planned stops confirmed">{it.stats.booked}/{it.stats.stops} ready</span>
    : null;
  const filterControls = onFilterToggle
    ? <ItineraryFilterControls filters={filters} onToggle={onFilterToggle} target={headerTarget} trailing={readiness} />
    : null;

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    if (previousTripIdRef.current !== tripId) {
      previousTripIdRef.current = tripId;
      setIt(null);
    }
    // Commit seed consumption with the state update. Render-time ref mutations
    // survive discarded StrictMode renders while their state updates do not.
    if (seed && seed !== consumedSeedRef.current) {
      consumedSeedRef.current = seed;
      seededRequestRef.current = { reloadToken, retryToken, tripId };
      setIt(seed);
      setError(null);
      setLoading(false);
      return;
    }
    const seededRequest = seededRequestRef.current;
    if (seed && seededRequest?.reloadToken === reloadToken
      && seededRequest.retryToken === retryToken && seededRequest.tripId === tripId) {
      return;
    }
    // A workspace payload carrying this itinerary is on its way. Racing it with
    // /trip/itinerary made the server assemble the same trip twice per page
    // load, and the two builds then contended for the same place lookups.
    if (seedPending) {
      setLoading(true);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    const deadline = window.setTimeout(() => {
      if (cancelled) return;
      cancelled = true;
      controller.abort();
      setError("The itinerary took too long to load.");
      setLoading(false);
    }, ITINERARY_LOAD_DEADLINE_MS);
    fetchItinerary(controller.signal)
      .then((data) => {
        if (!cancelled) setIt(data);
      })
      .catch(() => {
        if (!cancelled) setError("Could not refresh the itinerary.");
      })
      .finally(() => {
        window.clearTimeout(deadline);
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
      window.clearTimeout(deadline);
      controller.abort();
    };
  }, [reloadToken, retryToken, tripId, seed, seedPending]);

  useEffect(() => {
    onItineraryChange?.(it);
  }, [it, onItineraryChange]);

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
      scrollRef.current?.scrollTo({ top: 0, behavior: "auto" });
      setFlashTarget(null);
      return;
    }
    const targetId = jumpTo.name
      ? `it-stop-${jumpTo.day}-${jumpTo.name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`
      : `it-day-${jumpTo.day}`;
    let cancelled = false;
    let attempts = 0;
    let flashTimer: number | undefined;
    let retryTimer: number | undefined;

    const tryScroll = () => {
      if (cancelled) return;
      const el = document.getElementById(targetId);
      if (el) {
        el.scrollIntoView({
          behavior: jumpTo.name ? "smooth" : "auto",
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
        retryTimer = window.setTimeout(tryScroll, 90);
      }
    };

    tryScroll();
    return () => {
      cancelled = true;
      if (retryTimer) window.clearTimeout(retryTimer);
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
  }, [focusName, focusDay, focusStop, focusToken, it]);

  if (loading && !it) {
    return (
      <div ref={scrollRef} className="h-full overflow-y-auto bg-sidebar">
        {filterControls}
        {overview && <TripSnapshot overview={overview} active={allDaysActive} onAllDaysMap={onAllDaysMap} onTripChanged={onTripChanged} />}
        <div className="grid min-h-40 place-items-center p-6 text-sm text-muted">
          Loading itinerary…
        </div>
      </div>
    );
  }

  if (error && !it) {
    return (
      <div ref={scrollRef} className="h-full overflow-y-auto bg-sidebar">
        {filterControls}
        {overview && <TripSnapshot overview={overview} active={allDaysActive} onAllDaysMap={onAllDaysMap} onTripChanged={onTripChanged} />}
        <div className="grid min-h-48 place-items-center p-6 text-center">
          <div className="max-w-xs text-sm text-rose-600">
            <p>{error}</p>
            <button type="button" onClick={() => setRetryToken((token) => token + 1)} className="mt-2 font-semibold underline">
              Retry
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (!it || !it.has_itinerary) {
    return (
      <div ref={scrollRef} className="h-full overflow-y-auto bg-sidebar">
        {filterControls}
        {overview && <TripSnapshot overview={overview} active={allDaysActive} onAllDaysMap={onAllDaysMap} onTripChanged={onTripChanged} />}
        <div className="grid min-h-48 place-items-center p-6 text-center">
          <div className="max-w-xs text-sm text-muted">
            No day-by-day plan yet. Once the assistant builds your itinerary, each
            day's stops will appear here — check them off as you book.
          </div>
        </div>
      </div>
    );
  }

  const { stats } = it;
  const visibleDays = filters.length === 0
    ? it.days
    : it.days.filter((day) => day.stops.some((stop, index) => (
      itineraryStopMatchesFilters(stop, filters, day.stops, index)
    )));
  return (
    <div
      ref={scrollRef}
      data-testid="audit-itinerary"
      className="itinerary-rows h-full overflow-y-auto bg-background"
    >
      {filterControls}
      {overview && (
        <TripSnapshot
          overview={overview}
          booked={stats.booked}
          stops={stats.stops}
          active={allDaysActive}
          onAllDaysMap={onAllDaysMap}
          onTripChanged={onTripChanged}
        />
      )}
      {error && (
        <div role="status" className="border-b border-rose-100 bg-rose-50 px-3.5 py-2 text-xs text-rose-700">
          {error}{" "}
          <button type="button" onClick={() => setRetryToken((token) => token + 1)} className="font-semibold underline">
            Retry
          </button>
        </div>
      )}
      <div className="border-b border-border bg-paper px-3.5 py-2 empty:hidden">
        <TripVerificationCard revision={retryToken} onTripChanged={onTripChanged} />
      </div>
      <header className="flex items-center gap-2 border-b border-border bg-paper px-3.5 py-1">
        <h2 className="shrink-0 whitespace-nowrap text-[12px] font-semibold text-ink">Day by day</h2>
        {!overview && (
          <span className="chip hidden 2xl:inline-flex">
            {loading ? "Refreshing… · " : ""}{stats.days} {stats.days === 1 ? "day" : "days"} · {stats.booked}/{stats.stops} booked
          </span>
        )}
        <div role="group" aria-label="Row density" className="flex shrink-0 items-center gap-0.5 rounded bg-sand p-0.5">
          {(["comfortable", "compact"] as const).map((value) => (
            <button
              key={value}
              type="button"
              aria-pressed={density === value}
              onClick={() => setDensity(value)}
              className={`h-6 rounded px-1.5 text-[11px] font-semibold capitalize transition ${
                density === value ? "bg-paper text-ink shadow-sm" : "text-muted hover:text-ink"
              }`}
            >
              {value}
            </button>
          ))}
        </div>
        <TripLengthControls days={stats.days} onAdjust={onAdjustDays} />
      </header>
      <div className="space-y-2 pb-4 pt-2">
        {visibleDays.length === 0 && (
          <div className="py-8 text-center text-sm text-muted">No itinerary items match these filters.</div>
        )}
        {visibleDays.map((day) => (
          <DayCard
            key={day.day}
            day={day}
            filters={filters}
            active
            circuitActive={circuitFocusToken > 0 && circuitFocusDay === day.day}
            focusName={focusName}
            focusDay={focusDay}
            focusStop={focusStop}
            jumpTo={jumpTo && "day" in jumpTo ? { day: jumpTo.day, name: jumpTo.name } : null}
            jumpToken={flashTarget?.token || 0}
            onToggleBooked={handleToggleBooked}
            onFocus={(kind, name, focusDay, stop, circuitId) => circuitId
              ? onStopFocus?.(kind, name, focusDay, stop, circuitId)
              : onStopFocus?.(kind, name, focusDay, stop)}
            onMap={(kind, name, mapDay, stop, circuitId) => circuitId
              ? onStopMap?.(kind, name, mapDay, stop, circuitId)
              : onStopMap?.(kind, name, mapDay, stop)}
            onDayMap={(mapDay) => onDayMap?.(mapDay)}
            onRemove={onStopRemove}
            compact={density === "compact"}
          />
        ))}
      </div>
    </div>
  );
}
