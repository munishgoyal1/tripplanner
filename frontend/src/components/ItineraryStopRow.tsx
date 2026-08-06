import { CalendarCheck2, Check, ChevronDown, Loader2, MapPin, Route, Trash2 } from "lucide-react";
import { useState } from "react";
import type { ItineraryStop } from "../types";
import { isIntercityTravel } from "./map/routeDerivations";

const KIND_ICON: Record<string, string> = {
  hotel: "\u{1F3E8}",
  origin: "\u{1F4CD}",
  attraction: "\u{1F3AF}",
  meal: "\u{1F37D}\uFE0F",
  transport: "\u{1F695}",
  flight: "\u2708\uFE0F",
  airport: "\u{1F6EB}",
  station: "\u{1F686}",
  bus_station: "\u{1F68F}",
  other: "\u{1F4CD}",
};

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
  onToggleBooked: (next: boolean) => void;
  onFocus: () => void;
  onMap: () => void;
  onRemove?: () => void | Promise<void>;
}

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
  onToggleBooked,
  onFocus,
  onMap,
  onRemove,
}: ItineraryStopRowProps) {
  const focusable = canFocus(stop);
  const routeFocusable = isIntercityTravel(stop.kind, stop.name);
  const removable = !!onRemove && ["attraction", "activity", "meal", "restaurant"].includes(stop.kind);
  const [removing, setRemoving] = useState(false);
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
      {stop.travel_from_previous && (
        <div className="flex items-start gap-2 py-1.5 pl-3">
          <span className="mt-2 h-px w-4 flex-shrink-0 bg-slate-200" aria-hidden />
          <div
            aria-label={`Travel from previous stop: ${stop.travel_from_previous.distance_display}, ${stop.travel_from_previous.duration_display}`}
            className="flex flex-wrap items-center gap-x-1.5 text-[10px] font-medium text-accent"
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
        </div>
      )}
      <article
        className={`rounded-2xl p-3 shadow-card ring-1 transition ${
          jumpActive
            ? "bg-amber-50 ring-2 ring-amber-300"
            : active
              ? "bg-brand/5 ring-brand/30"
              : focusable
                ? "cursor-pointer bg-white ring-slate-200/80 hover:ring-slate-300"
                : "bg-white ring-slate-200/80"
        }`}
      >
        <div className="flex items-start gap-2.5">
          {mapLabel ? (
            <span
              aria-label={mapLabel.startsWith("H")
                ? "Hotel map marker"
                : `Map stop ${mapLabel}`}
              aria-current={active ? "location" : undefined}
              className={`mt-0.5 grid h-7 w-7 flex-shrink-0 place-items-center rounded-full border text-[11px] font-semibold tabular-nums transition ${active ? "scale-110 text-white shadow-sm" : "bg-white"}`}
              style={{
                borderColor: stop.color,
                color: active ? "white" : stop.color,
                backgroundColor: active ? stop.color : "white",
              }}
            >
              {mapLabel}
            </span>
          ) : (
            <span
              aria-hidden
              className="mt-0.5 grid h-7 w-7 flex-shrink-0 place-items-center rounded-full border border-slate-200 bg-white text-[11px]"
            >
              {KIND_ICON[stop.kind] || KIND_ICON.other}
            </span>
          )}
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-baseline gap-x-1.5">
              {stop.time && (
                <span className="text-sm font-semibold tabular-nums text-ink">
                  {stop.time}{stop.time_estimated ? " est." : ""}
                </span>
              )}
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
                title={routeFocusable
                  ? "Show complete route"
                  : stop.kind === "airport"
                    ? "Show airport details"
                    : focusable ? "Show photos & reviews" : undefined}
              >
                {circuitReturn ? `Return to ${stop.name}` : stop.name}
              </button>
            </div>
            <p className="mt-0.5 flex flex-wrap items-center gap-x-1.5 text-[11px] text-slate-500">
              <span className="font-bold uppercase text-slate-400">{timingLabel}</span>
              <span aria-hidden>·</span>
              <span className="font-bold uppercase text-slate-400">{circuitReturn ? "Hotel return" : stop.kind}</span>
              {durationText && (
                <>
                  <span aria-hidden>·</span>
                  <span>{durationText}</span>
                </>
              )}
              {departureText && (
                <>
                  <span aria-hidden>·</span>
                  <span className="font-medium tabular-nums text-slate-600">{departureText}</span>
                </>
              )}
            </p>
          </div>
          {!circuitReturn && !["airport", "station", "bus_station", "origin"].includes(stop.kind) && <button
            type="button"
            aria-pressed={stop.booked}
            aria-label={`${stop.name}: ${stop.booked ? "Mark as needing booking" : "Mark confirmed"}`}
            onClick={(event) => {
              event.stopPropagation();
              onToggleBooked(!stop.booked);
            }}
            className={`inline-flex h-6 flex-shrink-0 items-center gap-1 rounded-full px-2 text-[10px] font-semibold ring-1 transition ${
              stop.booked
                ? "bg-emerald-50 text-emerald-700 ring-emerald-200 hover:bg-emerald-100"
                : "bg-amber-50 text-amber-800 ring-amber-200 hover:text-brand hover:ring-brand/30"
            }`}
          >
            {stop.booked ? <Check size={11} aria-hidden /> : <CalendarCheck2 size={11} aria-hidden />}
            {stop.booked ? "Confirmed" : "Needs booking"}
          </button>}
          <div className="flex flex-shrink-0 items-center gap-0.5 transition sm:opacity-0 sm:focus-within:opacity-100 sm:group-hover:opacity-100">
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                onMap();
              }}
              aria-label={`Show ${stop.name} on the map`}
              className="grid h-6 w-6 place-items-center rounded-full text-slate-400 transition hover:bg-slate-100 hover:text-brand"
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
                className="grid h-6 w-6 place-items-center rounded-full text-slate-400 transition hover:bg-slate-100 hover:text-rose-600"
                title="Remove from itinerary"
              >
                {removing ? <Loader2 size={12} className="animate-spin" aria-hidden /> : <Trash2 size={13} aria-hidden />}
              </button>
            )}
          </div>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-1 pl-[2.375rem]">
          {!circuitReturn && stop.cost_display && <span className="chip">{stop.cost_display}</span>}
          {!circuitReturn && stop.opening_hours && <span className="chip">{stop.opening_hours}</span>}
          {!circuitReturn && typeof stop.rating === "number" && (
            <span className="chip" aria-label={`${stop.name} rating ${stop.rating.toFixed(1)} out of 5`}>
              ★ {stop.rating.toFixed(1)}
              {typeof stop.review_count === "number" && stop.review_count > 0
                ? ` · ${reviewCountLabel(stop.review_count)} reviews`
                : ""}
            </span>
          )}
          {!circuitReturn && typeof stop.popularity_score === "number" && stop.kind === "attraction" && (
            <span
              className="chip"
              title="Estimated from Google rating and review volume; not an itinerary inclusion percentage."
            >
              Must-visit score {stop.popularity_score}/100
            </span>
          )}
        </div>
        {concernTexts.length > 0 && (
          <div className="mt-2 space-y-0.5 pl-[2.375rem]">
            {concernTexts.map((text) => <p key={text} className="text-xs font-medium text-rose-700">{text}</p>)}
          </div>
        )}
        {hasNotes && (
          <div className="pl-[2.375rem]">
            <button
              type="button"
              aria-expanded={notesOpen}
              onClick={(event) => {
                event.stopPropagation();
                setNotesOpen((open) => !open);
              }}
              className="mt-1.5 inline-flex items-center gap-1 text-[11px] font-semibold text-slate-500 transition hover:text-ink"
            >
              {notesOpen ? "Hide notes" : "Notes & tips"}
              <ChevronDown size={12} className={`transition ${notesOpen ? "rotate-180" : ""}`} aria-hidden />
            </button>
            {notesOpen && (
              <div className="mt-1 space-y-0.5 border-l-2 border-slate-100 pl-2.5">
                {noteTexts.map((text) => <p key={text} className="text-xs text-slate-500">{text}</p>)}
                {!circuitReturn && insightTexts.map((text) => <p key={text} className="text-xs text-slate-600">{text}</p>)}
              </div>
            )}
          </div>
        )}
      </article>
    </li>
  );
}