import {
  BedDouble, BusFront, CalendarCheck2, CarFront, Check, ChevronDown, Clock3, Flame, Footprints, Landmark, Loader2, MapPin,
  Plane, PlaneLanding, PlaneTakeoff, Route, Ship, Star, TrainFront, Trash2, UtensilsCrossed,
} from "lucide-react";
import { useState } from "react";
import type { ItineraryStop } from "../types";
import { isIntercityTravel } from "./map/routeDerivations";
import { formatCostDisplay, useDisplayPreferences } from "../lib/displayPreferences";
import { useUnmappedStop } from "../lib/unmappedStops";

/** Line icons for stops without a map marker (hotels are lettered, visits numbered). */
function kindIcon(stop: ItineraryStop) {
  if (stop.kind === "hotel") return BedDouble;
  if (stop.kind === "meal" || stop.kind === "restaurant") return UtensilsCrossed;
  if (stop.kind === "flight") return Plane;
  if (stop.kind === "airport") return stop.terminal_role === "departure" ? PlaneTakeoff : PlaneLanding;
  if (stop.kind === "station") return TrainFront;
  if (stop.kind === "bus_station") return BusFront;
  if (stop.kind === "transport") return CarFront;
  if (stop.kind === "attraction") return Landmark;
  return MapPin;
}

function modeIcon(mode: string) {
  const value = mode.toLowerCase();
  if (value.includes("walk")) return Footprints;
  if (value.includes("boat") || value.includes("ferry")) return Ship;
  if (value.includes("train") || value.includes("rail")) return TrainFront;
  if (value.includes("bus") || value.includes("coach")) return BusFront;
  if (value.includes("flight")) return Plane;
  if (value.includes("drive") || value.includes("car") || value.includes("taxi")) return CarFront;
  return Route;
}

function canFocus(stop: ItineraryStop): boolean {
  return ["hotel", "attraction", "meal", "restaurant", "airport", "station", "bus_station", "origin"].includes(stop.kind)
    || isIntercityTravel(stop.kind, stop.name);
}

function reviewCountLabel(count: number): string {
  return new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(count);
}

function durationLabel(minutes: number): string {
  if (minutes < 60) return `${Math.round(minutes)} min`;
  const rounded = Math.round(minutes);
  const hours = Math.floor(rounded / 60);
  const remaining = rounded % 60;
  return `${hours} ${hours === 1 ? "hr" : "hrs"}${remaining ? ` ${remaining} min` : ""}`;
}

function roadOrigin(name: string): string | null {
  if (!/(drive:|road transfer|private car)/i.test(name)) return null;
  const route = name.includes(":") ? name.split(":", 2)[1].trim() : name.trim();
  const endpoints = route.split(/\s+(?:to|->)\s+/i, 2);
  return endpoints.length === 2 ? endpoints[0].trim() || null : null;
}

function uniqueDetailTexts(...values: Array<string | undefined>): string[] {
  const seen = new Set<string>();
  return values.flatMap((value) => {
    const text = (value || "").trim();
    const key = text.toLowerCase();
    if (!text || seen.has(key)) return [];
    seen.add(key);
    return [text];
  });
}

function terminalTimingLabel(stop: ItineraryStop): string | null {
  if (!stop.terminal_role) return null;
  if (stop.terminal_role === "connection") return "Connection";
  if (stop.terminal_role === "departure") {
    if (stop.kind === "station") return "Station arrival";
    if (stop.kind === "bus_station") return "Bus stand arrival";
    return "Airport arrival";
  }
  if (stop.kind === "station") return "Train arrival";
  if (stop.kind === "bus_station") return "Bus arrival";
  return "Land";
}

export interface ItineraryStopRowProps {
  stop: ItineraryStop;
  day: number;
  stopIndex: number;
  isFirst: boolean;
  isLast: boolean;
  hotelTimingLabel?: "Check out" | "Check in";
  circuitReturn?: boolean;
  representedStopIndexes?: number[];
  mapLabel?: string;
  active: boolean;
  jumpActive: boolean;
  rowId: string;
  /** Tighter vertical rhythm; content and order are unchanged. */
  compact?: boolean;
  onToggleBooked: (next: boolean) => void;
  onFocus: () => void;
  onMap: () => void;
  onRemove?: () => void | Promise<void>;
}

const TAG = "inline-flex items-center gap-1 whitespace-nowrap rounded border border-border bg-paper px-1.5 py-px text-[11.5px] text-muted";

/**
 * One itinerary stop as a responsive grid (see `.it-stop` in index.css). A narrow
 * pane stacks name, details, tags and notes; a wide pane puts the tags, Notes &
 * tips and booking status on the stop's own line, so rows get shorter.
 */
export default function ItineraryStopRow({
  stop,
  day,
  stopIndex,
  isFirst,
  isLast,
  hotelTimingLabel,
  circuitReturn = false,
  representedStopIndexes,
  mapLabel,
  active,
  jumpActive,
  rowId,
  compact = false,
  onToggleBooked,
  onFocus,
  onMap,
  onRemove,
}: ItineraryStopRowProps) {
  const focusable = canFocus(stop);
  const unmapped = useUnmappedStop(stop.name);
  const routeFocusable = isIntercityTravel(stop.kind, stop.name);
  const removable = !!onRemove && ["attraction", "activity", "meal", "restaurant"].includes(stop.kind);
  const [removing, setRemoving] = useState(false);
  const { currency } = useDisplayPreferences();
  const [notesOpen, setNotesOpen] = useState(false);
  const circuitTimingNotes = new Set(["start from your stay", "return to your stay"]);
  const insightTexts = uniqueDetailTexts(stop.insight);
  const insightKeys = new Set(insightTexts.map((text) => text.toLowerCase()));
  const noteTexts = uniqueDetailTexts(stop.note).filter((text) =>
    !insightKeys.has(text.toLowerCase())
    && !circuitTimingNotes.has(text.toLowerCase())
  );
  const concernTexts = uniqueDetailTexts(stop.concern);
  const driveOrigin = stop.kind === "transport" ? roadOrigin(stop.name) : null;
  const timingLabel = circuitReturn ? "Return" : hotelTimingLabel || (terminalTimingLabel(stop)
    ?? (stop.kind === "hotel" && isFirst && isLast
        ? "Stay"
      : stop.kind === "hotel" && isFirst
        ? "Depart"
        : stop.kind === "hotel" && isLast
          ? "Return"
          : stop.kind === "flight"
            ? "Depart"
            : stop.kind === "transport"
              ? driveOrigin
              ? `Depart from ${driveOrigin}`
              : "Travel"
            : "Arrive"));
  const durationText = stop.operational_time_display
    ? stop.operational_time_display
    : stop.kind !== "hotel" && stop.duration_min
      ? `${durationLabel(stop.duration_min)} ${
        stop.kind === "flight" ? "flight" : stop.kind === "transport" ? "transfer" : "visit"
      }${stop.duration_estimated ? " est." : ""}`
      : null;
  const departureText = stop.departure_time
    ? `${stop.kind === "flight" ? "Arrive" : stop.kind === "transport" ? "Ends" : "Leave"} ${stop.departure_time}`
    : null;
  const hasNotes = noteTexts.length > 0 || (!circuitReturn && insightTexts.length > 0);
  const bookable = !circuitReturn && !["airport", "station", "bus_station", "origin"].includes(stop.kind);
  const travel = stop.travel_from_previous;
  const TravelIcon = travel ? modeIcon(travel.mode) : Route;
  const KindIcon = kindIcon(stop);
  const arrivalTone = stop.timing_conflict_display && !stop.buffer_before_display
    ? "font-medium text-rose-700"
    : stop.buffer_before_min != null && stop.buffer_before_min < 5
      ? "font-medium text-amber-700"
      : stop.buffer_before_display
        ? "text-emerald-700"
        : "text-muted";
  const hasTags = !circuitReturn && Boolean(
    stop.cost_display || stop.opening_hours || typeof stop.rating === "number"
    || (typeof stop.popularity_score === "number" && stop.kind === "attraction"),
  );
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
      data-stop-indexes={(representedStopIndexes || [stopIndex]).join(",")}
      onClick={handleRowClick}
      className="group"
    >
      {travel && (
        <div className="it-leg px-3">
          <span className="flex justify-center" aria-hidden><span className="w-px bg-border" /></span>
          <div
            aria-label={`Travel from previous stop: ${travel.distance_display}, ${travel.duration_display}`}
            className="it-leg-text min-w-0 py-1 text-[12px] leading-snug text-muted"
            title={`${travel.mode} estimate`}
          >
            <span className="min-w-0">
              <TravelIcon size={13} className="mr-1.5 inline -translate-y-px" aria-hidden />
              <span className="font-medium capitalize text-ink">{travel.mode}</span>
              <span aria-hidden> · </span>
              <span className="tabular-nums">{travel.distance_display}</span>
              <span aria-hidden> · </span>
              <span className="tabular-nums">{travel.duration_display}</span>
              {travel.detail && (
                <>
                  <span aria-hidden> — </span>
                  <span>{travel.detail}</span>
                </>
              )}
            </span>
            {stop.expected_arrival_time && (
              <span className={`it-leg-arrival tabular-nums ${arrivalTone}`}>
                Earliest arrival {stop.expected_arrival_time}
                {stop.buffer_before_display && stop.time
                  ? ` · ${stop.buffer_before_display} free before ${stop.time}`
                  : stop.timing_conflict_display
                    ? ` · ${stop.timing_conflict_display} after planned ${stop.time}; schedule needs revision`
                    : ""}
              </span>
            )}
          </div>
        </div>
      )}
      <article
        className={`it-stop px-3 transition ${compact ? "py-1.5" : "py-2.5"} ${
          jumpActive
            ? "bg-amber-50"
            : active
              ? "bg-sand ring-1 ring-inset ring-clay/15"
              : focusable
                ? "cursor-pointer hover:bg-sand/60"
                : ""
        }`}
        style={active ? { boxShadow: `inset 3px 0 0 ${stop.color}` } : undefined}
      >
        <div className="it-stop-time pt-px text-right text-[13px] font-semibold leading-tight tabular-nums text-ink">
          {stop.time && <span>{stop.time}{stop.time_estimated ? " est." : ""}</span>}
        </div>
        <div className="it-stop-main">
          <div className="it-stop-name flex items-start gap-2">
            {mapLabel ? (
              <span
                aria-label={mapLabel.startsWith("H")
                  ? "Hotel map marker"
                  : `Map stop ${mapLabel}`}
                aria-current={active ? "location" : undefined}
                className={`mt-px grid h-5 w-5 flex-shrink-0 place-items-center rounded-full border-[1.5px] text-[10px] font-semibold tabular-nums transition ${active ? "scale-110 text-white shadow-sm" : "bg-paper"}`}
                style={{
                  borderColor: stop.color,
                  color: active ? "white" : stop.color,
                  backgroundColor: active ? stop.color : "white",
                }}
              >
                {mapLabel}
              </span>
            ) : (
              <span aria-hidden className="mt-px grid h-5 w-5 flex-shrink-0 place-items-center rounded bg-sand text-muted ring-1 ring-border">
                <KindIcon size={11} />
              </span>
            )}
            <button
              type="button"
              disabled={!focusable}
              onClick={(event) => {
                event.stopPropagation();
                onFocus();
              }}
              className={`min-w-0 flex-1 text-left text-[14px] font-semibold leading-snug tracking-[-0.005em] ${
                focusable ? "text-ink hover:text-brand" : "cursor-default text-ink"
              }`}
              title={routeFocusable
                ? "Show complete route"
                : stop.kind === "airport"
                  ? "Show airport details"
                  : focusable ? "Show photos & reviews" : undefined}
            >
              {circuitReturn ? `Return to ${stop.name}` : stop.name}
            </button>
          </div>
          <p className="it-stop-detail mt-0.5 flex flex-wrap items-center gap-x-1.5 pl-7 text-[12px] text-muted">
            <span>{timingLabel}</span>
            <span aria-hidden>·</span>
            <span>{circuitReturn ? "Hotel return" : stop.kind}</span>
            {unmapped && (
              <>
                <span aria-hidden>·</span>
                <span
                  title={
                    unmapped.candidate
                      ? `The map found “${unmapped.candidate.name}” instead. Confirm it on the map to pin this stop.`
                      : "The map could not place this stop."
                  }
                  className={`font-semibold ${unmapped.tier === "anchor" ? "text-amber-600" : "text-amber-700"}`}
                >
                  Not on map
                </span>
              </>
            )}
            {durationText && (
              <>
                <span aria-hidden>·</span>
                <span>{durationText}</span>
              </>
            )}
            {departureText && (
              <>
                <span aria-hidden>·</span>
                <span className="tabular-nums">{departureText}</span>
              </>
            )}
          </p>
        </div>
        <div className="it-stop-tags flex flex-wrap items-center gap-1 pl-7 pt-1.5">
          {(hasTags || hasNotes) && (
            <>
              {!circuitReturn && typeof stop.rating === "number" && (
                <span className={TAG} aria-label={`${stop.name} rating ${stop.rating.toFixed(1)} out of 5`}>
                  <Star size={11} className="fill-amber-400 text-amber-400" aria-hidden />
                  <b className="font-semibold text-ink">{stop.rating.toFixed(1)}</b>
                  {typeof stop.review_count === "number" && stop.review_count > 0 && (
                    <span>· {reviewCountLabel(stop.review_count)} reviews</span>
                  )}
                </span>
              )}
              {!circuitReturn && typeof stop.popularity_score === "number" && stop.kind === "attraction" && (
                <span
                  className={`${TAG} text-brand`}
                  title="Estimated from Google rating and review volume; not an itinerary inclusion percentage."
                >
                  <Flame size={11} aria-hidden />
                  <span>Must-visit score {stop.popularity_score}/100</span>
                </span>
              )}
              {!circuitReturn && stop.cost_display && <span className={TAG}>{formatCostDisplay(stop.cost_display, currency)}</span>}
              {!circuitReturn && stop.opening_hours && (
                <span className={`${TAG} tabular-nums`}>
                  <Clock3 size={11} aria-hidden />
                  <span>{stop.opening_hours}</span>
                </span>
              )}
              {hasNotes && (
                <button
                  type="button"
                  aria-expanded={notesOpen}
                  onClick={(event) => {
                    event.stopPropagation();
                    setNotesOpen((open) => !open);
                  }}
                  className="inline-flex h-[22px] items-center gap-1 whitespace-nowrap rounded px-1.5 text-[11.5px] font-semibold text-muted transition hover:bg-sand hover:text-ink"
                >
                  {notesOpen ? "Hide notes" : "Notes & tips"}
                  <ChevronDown size={12} className={`transition ${notesOpen ? "rotate-180" : ""}`} aria-hidden />
                </button>
              )}
            </>
          )}
        </div>
        <div className="it-stop-status flex items-center gap-0.5">
          <div className="flex flex-shrink-0 items-center gap-0.5 transition sm:opacity-0 sm:focus-within:opacity-100 sm:group-hover:opacity-100">
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                onMap();
              }}
              aria-label={`Show ${stop.name} on the map`}
              className="grid h-6 w-6 place-items-center rounded text-muted transition hover:bg-sand hover:text-brand"
              title={routeFocusable ? "Show complete route" : "Show on map"}
            >
              <MapPin size={13} aria-hidden />
            </button>
            {!circuitReturn && removable && (
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
                className="grid h-6 w-6 place-items-center rounded text-muted transition hover:bg-sand hover:text-rose-600"
                title="Remove from itinerary"
              >
                {removing ? <Loader2 size={12} className="animate-spin" aria-hidden /> : <Trash2 size={13} aria-hidden />}
              </button>
            )}
          </div>
          {bookable && (
            <button
              type="button"
              aria-pressed={stop.booked}
              aria-label={`${stop.name}: ${stop.booked ? "Mark as needing booking" : "Mark confirmed"}`}
              onClick={(event) => {
                event.stopPropagation();
                onToggleBooked(!stop.booked);
              }}
              className={`inline-flex h-5 flex-shrink-0 items-center gap-1 rounded px-1.5 text-[10.5px] font-semibold ring-1 transition ${
                stop.booked
                  ? "bg-emerald-50/60 text-emerald-700 ring-emerald-200 hover:bg-emerald-50"
                  : "bg-amber-50 text-amber-800 ring-amber-200 hover:ring-brand/30"
              }`}
            >
              {stop.booked ? <Check size={11} aria-hidden /> : <CalendarCheck2 size={11} aria-hidden />}
              {stop.booked ? "Confirmed" : "To book"}
            </button>
          )}
        </div>
        <div className="it-stop-extra pl-7">
          {(concernTexts.length > 0 || notesOpen) && (
            <>
              {concernTexts.length > 0 && (
                <div className="mt-1.5 space-y-0.5">
                  {concernTexts.map((text) => <p key={text} className="text-[12px] font-medium text-rose-700">{text}</p>)}
                </div>
              )}
              {notesOpen && (
                <div className="mt-1.5 space-y-0.5 border-l-2 border-border pl-2.5">
                  {noteTexts.map((text) => <p key={text} className="text-[12.5px] leading-relaxed text-muted">{text}</p>)}
                  {!circuitReturn && insightTexts.map((text) => <p key={text} className="text-[12.5px] leading-relaxed text-muted">{text}</p>)}
                </div>
              )}
            </>
          )}
        </div>
      </article>
    </li>
  );
}
