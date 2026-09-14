import type { ItineraryDay, ItineraryStop, RouteMetrics } from "../../../src/types";
import { itineraryStopMatchesFilters, type ItineraryFilter } from "../../../src/lib/itineraryFilters";
import { isIntercityTravel } from "../../../src/components/map/routeDerivations";
import { hotelIdentityGroups, hotelIdentityMatches } from "../../../src/components/map/placeIdentity";

/**
 * The facts production derives for one day and one stop row, computed once so
 * every option renders the same statements. The derivations mirror
 * `ItineraryPanel.DayCard` and `ItineraryStopRow` line for line: an option may
 * change how a fact looks or where it sits, never what it says.
 */

export interface TravelFacts {
  mode: string;
  distance: string;
  duration: string;
  detail?: string;
  /** "Est. arrive 10:40", when production shows an arrival line. */
  arrival?: string;
  /** "50 min free before 11:30". */
  buffer?: string;
  /** "schedule is 10 min too tight". */
  conflict?: string;
  aria: string;
  title: string;
}

export interface RowFacts {
  stop: ItineraryStop;
  /** 1-based position within the day, as production reports it. */
  index: number;
  key: string;
  rowId: string;
  name: string;
  kindLabel: string;
  timingLabel: string;
  circuitReturn: boolean;
  mapLabel?: string;
  kindGlyph: string;
  time?: string;
  durationText: string | null;
  departureText: string | null;
  notes: string[];
  insights: string[];
  concerns: string[];
  hasNotes: boolean;
  focusable: boolean;
  routeFocusable: boolean;
  removable: boolean;
  bookable: boolean;
  focusTitle?: string;
  travel?: TravelFacts;
  cost?: string;
  hours?: string;
  rating?: { value: string; reviews?: string; aria: string };
  mustVisit?: { score: number; title: string };
}

export interface DayFacts {
  day: ItineraryDay;
  dateLabel: string;
  dateShort: string;
  planned: number;
  confirmed: number;
  remaining: number;
  rows: RowFacts[];
  scheduleText?: string;
  transition?: { from: string; to: string };
}

export const KIND_GLYPH: Record<string, string> = {
  hotel: "\u{1F3E8}",
  origin: "\u{1F4CD}",
  attraction: "\u{1F3AF}",
  meal: "\u{1F37D}️",
  transport: "\u{1F695}",
  flight: "✈️",
  airport: "\u{1F6EB}",
  station: "\u{1F686}",
  bus_station: "\u{1F68F}",
  other: "\u{1F4CD}",
};

export const MUST_VISIT_TITLE = "Estimated from Google rating and review volume; not an itinerary inclusion percentage.";

function canFocus(stop: ItineraryStop): boolean {
  return ["hotel", "attraction", "meal", "restaurant", "airport", "station", "bus_station", "origin"].includes(stop.kind)
    || isIntercityTravel(stop.kind, stop.name);
}

export function reviewCountLabel(count: number): string {
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

function travelFacts(stop: ItineraryStop, leg: RouteMetrics): TravelFacts {
  return {
    mode: leg.mode,
    distance: leg.distance_display,
    duration: leg.duration_display,
    detail: leg.detail,
    arrival: stop.expected_arrival_time ? `Est. arrive ${stop.expected_arrival_time}` : undefined,
    buffer: stop.expected_arrival_time && stop.buffer_before_display && stop.time
      ? `${stop.buffer_before_display} free before ${stop.time}`
      : undefined,
    conflict: stop.expected_arrival_time && !(stop.buffer_before_display && stop.time) && stop.timing_conflict_display
      ? `schedule is ${stop.timing_conflict_display} too tight`
      : undefined,
    aria: `Travel from previous stop: ${leg.distance_display}, ${leg.duration_display}`,
    title: `${leg.mode} estimate`,
  };
}

export function dayDateLabel(date: string): string {
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

export function dayDateShort(date: string): string {
  if (!date) return "";
  const parsed = new Date(`${date}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return date;
  return new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" }).format(parsed);
}

export function deriveDay(day: ItineraryDay, filters: readonly ItineraryFilter[], formatCost: (value: string) => string): DayFacts {
  let visitOrder = 0;
  const hotelNames = hotelIdentityGroups(day.stops.filter((entry) => entry.kind === "hotel").map((entry) => entry.name));
  const hotelLabels = new Map(hotelNames.map((name, index) => [name, hotelNames.length > 1 ? `H${index + 1}` : "H"]));
  const mapLabels = day.stops.map((entry) => {
    if (entry.kind === "hotel") {
      const hotelName = hotelNames.find((name) => hotelIdentityMatches(name, entry.name));
      return hotelName ? hotelLabels.get(hotelName) : undefined;
    }
    if (entry.kind === "airport") return "A";
    if (entry.kind === "origin") return "O";
    if (!["attraction", "meal", "restaurant"].includes(entry.kind)) return undefined;
    visitOrder += 1;
    return String(visitOrder);
  });
  const plannedStops = day.stops.filter((entry) => !["hotel", "airport", "origin"].includes(entry.kind));
  const confirmed = plannedStops.filter((entry) => entry.booked).length;
  const firstStop = day.stops[0];
  const lastStop = day.stops[day.stops.length - 1];
  const hasHotelEndpoints = day.stops.length > 1 && firstStop?.kind === "hotel" && lastStop?.kind === "hotel";
  const circuitHotelIndex = lastStop?.kind === "hotel"
    ? day.stops.findIndex((entry, index) => index < day.stops.length - 1 && entry.kind === "hotel" && hotelIdentityMatches(entry.name, lastStop.name))
    : -1;
  const combinesHotelCircuit = circuitHotelIndex >= 0;
  const changesHotel = hasHotelEndpoints && !hotelIdentityMatches(firstStop.name, lastStop.name);
  const destinationHotelIndex = changesHotel ? (combinesHotelCircuit ? circuitHotelIndex : day.stops.length - 1) : -1;

  const rows = day.stops.flatMap((entry, i): RowFacts[] => {
    if (!itineraryStopMatchesFilters(entry, filters, day.stops, i)) return [];
    const isFirst = i === 0;
    const isLast = i === day.stops.length - 1;
    const circuitReturn = combinesHotelCircuit && isLast;
    const hotelTimingLabel = changesHotel && isFirst ? "Check out" : changesHotel && i === destinationHotelIndex ? "Check in" : undefined;
    const baseRowId = `lab-it-stop-${day.day}-${entry.name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
    const insightTexts = uniqueDetailTexts(entry.insight);
    const insightKeys = new Set(insightTexts.map((text) => text.toLowerCase()));
    const circuitTimingNotes = new Set(["start from your stay", "return to your stay"]);
    const noteTexts = uniqueDetailTexts(entry.note).filter((text) => !insightKeys.has(text.toLowerCase()) && !circuitTimingNotes.has(text.toLowerCase()));
    const driveOrigin = entry.kind === "transport" ? roadOrigin(entry.name) : null;
    const timingLabel = circuitReturn ? "Return" : hotelTimingLabel || (terminalTimingLabel(entry)
      ?? (entry.kind === "hotel" && isFirst && isLast ? "Stay"
        : entry.kind === "hotel" && isFirst ? "Depart"
          : entry.kind === "hotel" && isLast ? "Return"
            : entry.kind === "flight" ? "Depart"
              : entry.kind === "transport" ? (driveOrigin ? `Depart from ${driveOrigin}` : "Travel")
                : "Arrive"));
    const durationText = entry.operational_time_display
      ? entry.operational_time_display
      : entry.kind !== "hotel" && entry.duration_min
        ? `${durationLabel(entry.duration_min)} ${entry.kind === "flight" ? "flight" : entry.kind === "transport" ? "transfer" : "visit"}${entry.duration_estimated ? " est." : ""}`
        : null;
    const departureText = entry.departure_time
      ? `${entry.kind === "flight" ? "Arrive" : entry.kind === "transport" ? "Ends" : "Leave"} ${entry.departure_time}`
      : null;
    const focusable = canFocus(entry);
    const routeFocusable = isIntercityTravel(entry.kind, entry.name);
    return [{
      stop: entry,
      index: i + 1,
      key: `${entry.name}-${i}`,
      rowId: circuitReturn ? `${baseRowId}-return` : baseRowId,
      name: circuitReturn ? `Return to ${entry.name}` : entry.name,
      kindLabel: circuitReturn ? "Hotel return" : entry.kind,
      timingLabel,
      circuitReturn,
      mapLabel: circuitReturn ? undefined : mapLabels[i],
      kindGlyph: KIND_GLYPH[entry.kind] || KIND_GLYPH.other,
      time: entry.time ? `${entry.time}${entry.time_estimated ? " est." : ""}` : undefined,
      durationText,
      departureText,
      notes: noteTexts,
      insights: circuitReturn ? [] : insightTexts,
      concerns: uniqueDetailTexts(entry.concern),
      hasNotes: noteTexts.length > 0 || (!circuitReturn && insightTexts.length > 0),
      focusable,
      routeFocusable,
      removable: ["attraction", "activity", "meal", "restaurant"].includes(entry.kind) && !circuitReturn,
      bookable: !circuitReturn && !["airport", "station", "bus_station", "origin"].includes(entry.kind),
      focusTitle: routeFocusable ? "Show complete route" : entry.kind === "airport" ? "Show airport details" : focusable ? "Show photos & reviews" : undefined,
      travel: entry.travel_from_previous ? travelFacts(entry, entry.travel_from_previous) : undefined,
      cost: !circuitReturn && entry.cost_display ? formatCost(entry.cost_display) : undefined,
      hours: !circuitReturn ? entry.opening_hours : undefined,
      rating: !circuitReturn && typeof entry.rating === "number"
        ? {
          value: entry.rating.toFixed(1),
          reviews: typeof entry.review_count === "number" && entry.review_count > 0 ? `${reviewCountLabel(entry.review_count)} reviews` : undefined,
          aria: `${entry.name} rating ${entry.rating.toFixed(1)} out of 5`,
        }
        : undefined,
      mustVisit: !circuitReturn && typeof entry.popularity_score === "number" && entry.kind === "attraction"
        ? { score: entry.popularity_score, title: MUST_VISIT_TITLE }
        : undefined,
    }];
  });

  return {
    day,
    dateLabel: dayDateLabel(day.date),
    dateShort: dayDateShort(day.date),
    planned: plannedStops.length,
    confirmed,
    remaining: plannedStops.length - confirmed,
    rows,
    scheduleText: day.schedule?.duration_display
      ? `${day.schedule.duration_display}${day.schedule.start && day.schedule.end
        ? ` · ${day.schedule.start}–${day.schedule.end}${day.schedule.estimated ? " est." : ""}`
        : day.schedule.estimated ? " est." : ""}`
      : undefined,
    transition: changesHotel && destinationHotelIndex > 0 ? { from: firstStop.name, to: day.stops[destinationHotelIndex].name } : undefined,
  };
}
