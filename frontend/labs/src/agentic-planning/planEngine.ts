/**
 * A deterministic plan engine that sits between an intent and the trip.
 *
 * The model reads intent and writes prose. It never edits the trip directly.
 * Placement, validation, blast radius and repair are computed here, so the same
 * guarantees hold whether the intent arrived from chat, the map, the itinerary
 * or the details pane.
 */

import { HOME, baseTrip, patalpani, shreemaya } from "./fixture";
import type { Candidate, Stop } from "./fixture";

const DAY_START = "08:30";
const DAY_END = "21:30";
const PRE_FLIGHT_BUFFER_MIN = 120;
const TURNAROUND_MIN = 10;
const ROAD_SPEED_KMH = 42;

export const toMin = (hhmm: string) => {
  const [h, m] = hhmm.split(":").map(Number);
  return h * 60 + m;
};

export const fmtMin = (min: number) => {
  const wrapped = ((min % 1440) + 1440) % 1440;
  return `${String(Math.floor(wrapped / 60)).padStart(2, "0")}:${String(wrapped % 60).padStart(2, "0")}`;
};

const absStart = (stop: Stop) => (stop.day - 1) * 1440 + toMin(stop.start);
const absEnd = (stop: Stop) => absStart(stop) + stop.durationMin;
const absOf = (day: number, hhmm: string) => (day - 1) * 1440 + toMin(hhmm);

export function distanceKm(a: { lat: number; lng: number }, b: { lat: number; lng: number }) {
  const R = 6371;
  const dLat = ((b.lat - a.lat) * Math.PI) / 180;
  const dLng = ((b.lng - a.lng) * Math.PI) / 180;
  const lat1 = (a.lat * Math.PI) / 180;
  const lat2 = (b.lat * Math.PI) / 180;
  const h = Math.sin(dLat / 2) ** 2 + Math.sin(dLng / 2) ** 2 * Math.cos(lat1) * Math.cos(lat2);
  return 2 * R * Math.asin(Math.sqrt(h));
}

export const travelMin = (a: { lat: number; lng: number }, b: { lat: number; lng: number }) =>
  Math.max(TURNAROUND_MIN, Math.round((distanceKm(a, b) / ROAD_SPEED_KMH) * 60) + TURNAROUND_MIN);

/** Closing time in minutes, unwrapped so a place that shuts after midnight stays open. */
const closingMin = (openFrom: string, openTo: string) => {
  const opens = toMin(openFrom);
  const closes = toMin(openTo);
  return closes <= opens ? closes + 1440 : closes;
};

export const sortStops = (stops: Stop[]) => [...stops].sort((a, b) => absStart(a) - absStart(b));

/* ------------------------------- presence ---------------------------------- */

interface Segment { city: string; from: number; to: number }

export function presenceSegments(stops: Stop[]): Segment[] {
  const flights = sortStops(stops.filter((stop) => stop.kind === "flight"));
  const segments: Segment[] = [];
  let city = HOME;
  let cursor = -Infinity;
  for (const flight of flights) {
    segments.push({ city, from: cursor, to: absStart(flight) });
    segments.push({ city: "in the air", from: absStart(flight), to: absEnd(flight) });
    city = flight.toCity ?? city;
    cursor = absEnd(flight);
  }
  segments.push({ city, from: cursor, to: Infinity });
  return segments;
}

export function cityAt(stops: Stop[], at: number) {
  const segment = presenceSegments(stops).find((entry) => at >= entry.from && at < entry.to);
  return segment?.city ?? HOME;
}

/** The only interval in which destination plans may exist. */
export function envelope(stops: Stop[]) {
  const flights = sortStops(stops.filter((stop) => stop.kind === "flight"));
  const arrival = flights.find((flight) => flight.role === "arrival");
  const departure = [...flights].reverse().find((flight) => flight.role === "departure");
  return {
    from: arrival ? absEnd(arrival) : -Infinity,
    to: departure ? absStart(departure) : Infinity,
    arrival,
    departure,
  };
}

/* ------------------------------- invariants -------------------------------- */

export interface Violation {
  code: string;
  rule: string;
  message: string;
  stopId?: string;
  severity: "hard" | "soft";
}

export const invariants = [
  { code: "I1", rule: "Trip envelope", text: "Nothing in the destination may be scheduled before you land or after you take off." },
  { code: "I2", rule: "Presence", text: "A stop's city must be the city you are actually in at that moment." },
  { code: "I3", rule: "Opening hours", text: "A visit must start and end while the place is open." },
  { code: "I4", rule: "Temporal feasibility", text: "Visit plus travel must fit before the next stop starts." },
  { code: "I5", rule: "Departure buffer", text: "At least two hours must stay free before a flight." },
  { code: "I6", rule: "Stay coverage", text: "Every night away from home has an active stay." },
  { code: "I7", rule: "Return coverage", text: "An outbound leg keeps its matching return leg." },
  { code: "I8", rule: "Blast radius", text: "An operation may only change the entities it declared." },
];

export function validate(stops: Stop[]): Violation[] {
  const out: Violation[] = [];
  const env = envelope(stops);
  const ordered = sortStops(stops);

  if (!env.arrival) {
    out.push({ code: "I1", rule: "Trip envelope", message: "The trip has no arrival leg.", severity: "hard" });
  }
  if (!env.departure) {
    out.push({
      code: "I7",
      rule: "Return coverage",
      message: `The outbound leg to ${baseTrip[0].toCity} has no matching return to ${HOME}.`,
      severity: "hard",
    });
  }

  for (const stop of ordered) {
    if (stop.kind === "flight") continue;
    const start = absStart(stop);
    const end = absEnd(stop);

    if (env.arrival && start < env.from) {
      out.push({
        code: "I1", rule: "Trip envelope", stopId: stop.id, severity: "hard",
        message: `${stop.title} starts at ${stop.start} on day ${stop.day}, before you land at ${fmtMin(env.from)}.`,
      });
    }
    if (env.departure && end > env.to) {
      out.push({
        code: "I1", rule: "Trip envelope", stopId: stop.id, severity: "hard",
        message: `${stop.title} runs to ${fmtMin(toMin(stop.start) + stop.durationMin)} on day ${stop.day}, after your ${fmtMin(env.to)} departure.`,
      });
    }
    const where = cityAt(stops, start);
    if (where !== stop.city) {
      out.push({
        code: "I2", rule: "Presence", stopId: stop.id, severity: "hard",
        message: `${stop.title} is in ${stop.city}, but at ${stop.start} on day ${stop.day} you are ${where === "in the air" ? "in the air" : `in ${where}`}.`,
      });
    }
    if (stop.openFrom && stop.openTo) {
      const opens = toMin(stop.openFrom);
      const closes = closingMin(stop.openFrom, stop.openTo);
      const localStart = toMin(stop.start);
      if (localStart < opens || localStart + stop.durationMin > closes) {
        out.push({
          code: "I3", rule: "Opening hours", stopId: stop.id, severity: "hard",
          message: `${stop.title} is open ${stop.openFrom}–${stop.openTo}; the visit runs ${stop.start}–${fmtMin(localStart + stop.durationMin)}.`,
        });
      }
    }
  }

  for (let i = 0; i < ordered.length - 1; i += 1) {
    const current = ordered[i];
    const next = ordered[i + 1];
    if (current.day !== next.day) continue;
    // A flight is not reached by road from the previous stop; it is protected by its buffer.
    const needed =
      next.kind === "flight"
        ? absEnd(current) + PRE_FLIGHT_BUFFER_MIN
        : absEnd(current) + travelMin(current, next);
    if (needed > absStart(next)) {
      const gap = needed - absStart(next);
      out.push({
        code: next.kind === "flight" ? "I5" : "I4",
        rule: next.kind === "flight" ? "Departure buffer" : "Temporal feasibility",
        stopId: next.id, severity: "hard",
        message:
          next.kind === "flight"
            ? `${current.title} leaves only ${absStart(next) - absEnd(current)} minutes before ${next.title}; ${PRE_FLIGHT_BUFFER_MIN} are required.`
            : `${current.title} cannot reach ${next.title} in time; short by ${gap} minutes.`,
      });
    }
  }

  const checkIn = stops.find((stop) => stop.role === "check-in");
  const checkOut = stops.find((stop) => stop.role === "check-out");
  if (!checkIn || !checkOut) {
    out.push({ code: "I6", rule: "Stay coverage", severity: "hard", message: "One or more nights away from home have no stay." });
  }

  return out;
}

/* ----------------------------- day scoring (today) -------------------------- */

export interface DayScore {
  day: number;
  count: number;
  routeKm: number;
  durationMin: number;
  score: number;
  chosen: boolean;
}

/**
 * Reproduces the production heuristic in `_place_selected_stop`: geography and
 * load only. It has no notion of the envelope, presence, or anchors, which is
 * exactly why the lightest day of a trip is often the departure day.
 */
export function dayScores(stops: Stop[]): DayScore[] {
  const dayNumbers = [...new Set(stops.map((stop) => stop.day))].sort((a, b) => a - b);
  const rows = dayNumbers.map((day) => {
    const dayStops = sortStops(stops.filter((stop) => stop.day === day));
    // Flights and drives have no place record, so production's route maths skips them.
    const located = dayStops.filter((stop) => stop.kind !== "flight" && stop.kind !== "transfer");
    let routeKm = 0;
    for (let i = 0; i < located.length - 1; i += 1) routeKm += distanceKm(located[i], located[i + 1]);
    const durationMin = dayStops.reduce((total, stop) => total + stop.durationMin, 0);
    const score = routeKm * 2.5 + dayStops.length * 18 + durationMin * 0.35;
    return { day, count: dayStops.length, routeKm, durationMin, score, chosen: false };
  });
  const best = rows.reduce((a, b) => (b.score < a.score ? b : a));
  return rows.map((row) => ({ ...row, chosen: row.day === best.day }));
}

/* ------------------------------- placement --------------------------------- */

export interface Placement {
  day: number;
  time: string;
  score: number;
  reasons: string[];
  adjustment?: string;
}

export interface Rejection { day: number; window: string; code: string; message: string }

interface Window { day: number; from: number; to: number; prev?: Stop; next?: Stop }

function windowsForDay(stops: Stop[], day: number): Window[] {
  const env = envelope(stops);
  const dayStops = sortStops(stops.filter((stop) => stop.day === day));
  let from = absOf(day, DAY_START);
  let to = absOf(day, DAY_END);
  if (env.arrival && env.arrival.day === day) from = Math.max(from, env.from);
  if (env.departure && env.departure.day === day) to = Math.min(to, env.to - PRE_FLIGHT_BUFFER_MIN);
  if (to <= from) return [];

  const blocks = dayStops
    .filter((stop) => stop.kind !== "flight")
    .map((stop) => ({ stop, from: absStart(stop) - TURNAROUND_MIN, to: absEnd(stop) + TURNAROUND_MIN }));

  const windows: Window[] = [];
  let cursor = from;
  for (const block of blocks) {
    if (block.from > cursor) {
      windows.push({
        day,
        from: cursor,
        to: Math.min(block.from, to),
        prev: blocks.find((entry) => entry.to <= cursor)?.stop,
        next: block.stop,
      });
    }
    cursor = Math.max(cursor, block.to);
  }
  if (cursor < to) {
    windows.push({ day, from: cursor, to, prev: [...blocks].reverse().find((entry) => entry.to <= cursor)?.stop });
  }
  return windows.filter((window) => window.to > window.from);
}

function evaluateWindow(stops: Stop[], window: Window, place: Candidate) {
  const inbound = window.prev ? travelMin(window.prev, place) : TURNAROUND_MIN;
  const outbound = window.next ? travelMin(place, window.next) : TURNAROUND_MIN;
  const needed = inbound + place.durationMin + outbound;
  const available = window.to - window.from;
  const label = `${fmtMin(window.from)}–${fmtMin(window.to)}`;

  if (available < needed) {
    return {
      ok: false as const,
      rejection: {
        day: window.day, window: label, code: "I4",
        message: `Needs ${needed} minutes with travel, the gap is ${available}.`,
      },
    };
  }

  const rawStart = window.from + inbound;
  const start = Math.ceil(rawStart / 5) * 5;
  const local = start - (window.day - 1) * 1440;
  if (local < toMin(place.openFrom) || local + place.durationMin > closingMin(place.openFrom, place.openTo)) {
    return {
      ok: false as const,
      rejection: {
        day: window.day, window: label, code: "I3",
        message: `Arriving ${fmtMin(local)} does not fit ${place.openFrom}–${place.openTo}.`,
      },
    };
  }

  const detourKm =
    (window.prev ? distanceKm(window.prev, place) : 0) +
    (window.next ? distanceKm(place, window.next) : 0) -
    (window.prev && window.next ? distanceKm(window.prev, window.next) : 0);
  const dayLoad = stops.filter((stop) => stop.day === window.day).reduce((total, stop) => total + stop.durationMin, 0);
  const slack = available - needed;
  const env = envelope(stops);
  const arrivalDay = env.arrival?.day === window.day;

  let score = Math.max(0, detourKm) * 1.4 + dayLoad * 0.08 - Math.min(slack, 180) * 0.15;
  if (arrivalDay) score += 25;

  const reasons = [
    `${Math.round(Math.max(0, detourKm))} km of extra driving against the day's existing route`,
    `${Math.round(inbound)} min in, ${Math.round(outbound)} min out, ${slack} min of slack left`,
    `Day ${window.day} currently holds ${Math.round(dayLoad / 60)}h of plans`,
    `Open ${place.openFrom}–${place.openTo}; this visit is ${fmtMin(local)}–${fmtMin(local + place.durationMin)}`,
  ];
  if (arrivalDay) reasons.push("Penalised for being the arrival day, when delays are most likely");

  return { ok: true as const, placement: { day: window.day, time: fmtMin(local), score, reasons } };
}

export interface Proposal {
  intent: string;
  operation: string;
  channelHint: string;
  blastRadius: string[];
  chosen: Placement | null;
  alternatives: Placement[];
  rejected: Rejection[];
  collateral: Change[];
  violations: Violation[];
  consent: string[];
  status: "ready" | "needs-consent" | "blocked";
  narration: string;
  apply: (stops: Stop[]) => Stop[];
  naive: { stops: Stop[]; note: string; violations: Violation[] };
}

export interface Change {
  verb: "added" | "removed" | "moved" | "changed";
  id: string;
  title: string;
  detail: string;
}

export function diffStops(before: Stop[], after: Stop[]): Change[] {
  const changes: Change[] = [];
  const beforeById = new Map(before.map((stop) => [stop.id, stop]));
  const afterById = new Map(after.map((stop) => [stop.id, stop]));
  for (const stop of before) {
    const next = afterById.get(stop.id);
    if (!next) {
      changes.push({ verb: "removed", id: stop.id, title: stop.title, detail: `was day ${stop.day} at ${stop.start}` });
      continue;
    }
    if (next.day !== stop.day || next.start !== stop.start) {
      changes.push({
        verb: "moved", id: stop.id, title: stop.title,
        detail: `day ${stop.day} ${stop.start} → day ${next.day} ${next.start}`,
      });
    } else if (next.title !== stop.title || next.ref !== stop.ref) {
      changes.push({ verb: "changed", id: stop.id, title: next.title, detail: `was ${stop.title}` });
    }
  }
  for (const stop of after) {
    if (!beforeById.has(stop.id)) {
      changes.push({ verb: "added", id: stop.id, title: stop.title, detail: `day ${stop.day} at ${stop.start}` });
    }
  }
  return changes;
}

const stopFromCandidate = (place: Candidate, day: number, time: string): Stop => ({
  id: place.id,
  kind: "attraction",
  title: place.title,
  city: place.city,
  day,
  start: time,
  durationMin: place.durationMin,
  lat: place.lat,
  lng: place.lng,
  openFrom: place.openFrom,
  openTo: place.openTo,
  note: place.note,
});

/** What the trip agent does today: cheapest day by load, appended at the end. */
export function naiveAddPlace(stops: Stop[], place: Candidate) {
  const target = dayScores(stops).find((row) => row.chosen)!.day;
  const dayStops = sortStops(stops.filter((stop) => stop.day === target));
  const last = dayStops[dayStops.length - 1];
  const time = fmtMin(Math.min(toMin(last.start) + 120, 22 * 60));
  return {
    stops: [...stops, stopFromCandidate(place, target, time)],
    note:
      `Production picks day ${target} because it scores lowest on route length, stop count and duration. ` +
      `The place has no cached coordinates, so the insert index falls back to the end of the day, and the ` +
      `time is inferred as the previous stop plus two hours — the previous stop being the departure flight.`,
  };
}

export function proposeAddPlace(stops: Stop[], place: Candidate): Proposal {
  const days = [...new Set(stops.map((stop) => stop.day))].sort((a, b) => a - b);
  const placements: Placement[] = [];
  const rejected: Rejection[] = [];

  for (const day of days) {
    for (const window of windowsForDay(stops, day)) {
      const verdict = evaluateWindow(stops, window, place);
      if (verdict.ok) placements.push(verdict.placement);
      else rejected.push(verdict.rejection);
    }
  }

  const naive = naiveAddPlace(stops, place);
  const naiveViolations = validate(naive.stops).filter((violation) => violation.stopId === place.id);
  const naiveStop = naive.stops.find((stop) => stop.id === place.id)!;
  for (const violation of naiveViolations) {
    rejected.push({
      day: naiveStop.day,
      window: `${naiveStop.start} (today's answer)`,
      code: violation.code,
      message: violation.message,
    });
  }

  // When nothing fits cleanly, look for a single movable stop that would open a window.
  if (placements.length < 2) {
    outer: for (const day of days) {
      const movable = stops.filter(
        (stop) => stop.day === day && !stop.locked && !stop.booked && stop.kind !== "flight" && stop.kind !== "transfer",
      );
      for (const candidateStop of movable) {
        const without = stops.filter((stop) => stop.id !== candidateStop.id);
        for (const window of windowsForDay(without, day)) {
          const verdict = evaluateWindow(without, window, place);
          if (verdict.ok) {
            placements.push({
              ...verdict.placement,
              score: verdict.placement.score + 20,
              adjustment: `Requires moving ${candidateStop.title} off day ${day}`,
            });
            break outer;
          }
        }
      }
    }
  }

  placements.sort((a, b) => a.score - b.score);
  const chosen = placements[0] ?? null;

  return {
    intent: `Add ${place.title} on the best day`,
    operation: "placeStop",
    channelHint: "Same result from chat, the map's Add to trip, or an itinerary drop.",
    blastRadius: [place.id],
    chosen,
    alternatives: placements.slice(1, 3),
    rejected,
    collateral: [],
    violations: [],
    consent: chosen?.adjustment ? [chosen.adjustment] : [],
    status: chosen ? (chosen.adjustment ? "needs-consent" : "ready") : "blocked",
    narration: chosen
      ? `Day ${chosen.day} at ${chosen.time} is the only slot that keeps ${place.title} inside its opening hours, ` +
        `inside the trip envelope, and reachable from the stops on either side. ${rejected.length} other slots were ruled out.`
      : `No slot in this trip can hold ${place.title} without breaking a hard rule. Nothing was changed.`,
    apply: (current) => (chosen ? sortStops([...current, stopFromCandidate(place, chosen.day, chosen.time)]) : current),
    naive: { stops: naive.stops, note: naive.note, violations: naiveViolations },
  };
}

/* -------------------------- stay replacement -------------------------------- */

/** What was observed: the stay is swapped and the return leg quietly disappears. */
export function naiveSwapHotel(stops: Stop[]) {
  return stops
    .filter((stop) => stop.id !== "flight-back")
    .map((stop) =>
      stop.role === "check-in" || stop.role === "check-out"
        ? {
            ...stop,
            title: stop.role === "check-in" ? `Check in · ${shreemaya.title}` : `Check out · ${shreemaya.title}`,
            lat: shreemaya.lat,
            lng: shreemaya.lng,
            ref: shreemaya.ref,
            note: stop.role === "check-in" ? shreemaya.note : undefined,
          }
        : stop,
    );
}

export function proposeSwapHotel(stops: Stop[]): Proposal {
  const blastRadius = ["stay-in", "stay-out"];
  const naive = naiveSwapHotel(stops);
  const collateral = diffStops(stops, naive).filter((change) => !blastRadius.includes(change.id));
  const naiveViolations = validate(naive);

  const safe = (current: Stop[]) =>
    sortStops(
      current.map((stop) =>
        stop.role === "check-in"
          ? {
              ...stop,
              title: `Check in · ${shreemaya.title}`,
              start: shreemaya.checkIn,
              lat: shreemaya.lat,
              lng: shreemaya.lng,
              ref: shreemaya.ref,
              note: shreemaya.note,
            }
          : stop.role === "check-out"
            ? { ...stop, title: `Check out · ${shreemaya.title}`, lat: shreemaya.lat, lng: shreemaya.lng, ref: shreemaya.ref }
            : stop,
      ),
    );

  return {
    intent: "Change the Indore hotel to a 3-star",
    operation: "replaceStay",
    channelHint: "Same result from chat or from Details on the stay card.",
    blastRadius,
    chosen: null,
    alternatives: [],
    rejected: [],
    collateral,
    violations: naiveViolations,
    consent: [
      "Check-in moves 09:30 → 13:00, because Shreemaya releases rooms at 13:00. Bags can be left from 09:30.",
      "Booking 4471-9922 at Sayaji is confirmed and must be cancelled before the new stay is held.",
      "Four nights fall from ₹9,400 to ₹3,900, so the trip total drops by ₹22,000.",
    ],
    status: "needs-consent",
    narration:
      `Replacing the stay is allowed to touch two entities: check-in and check-out. The naive rewrite also deletes ` +
      `${collateral.length} entity outside that radius, so it is refused rather than applied. Here is the safe version, ` +
      `with the three consequences that need your word.`,
    apply: safe,
    naive: { stops: naive, note: "Rewrote the stay block and dropped everything else attached to that day container.", violations: naiveViolations },
  };
}

export const scenarios = [
  {
    id: "add-place",
    label: "Add Patalpani Waterfall on the best day",
    detail: "The reported case: a new attraction landed after the departure flight, back home in Bengaluru.",
    build: (stops: Stop[]) => proposeAddPlace(stops, patalpani),
  },
  {
    id: "swap-hotel",
    label: "Change the Indore hotel to a 3-star",
    detail: "The reported case: the hotel changed and the Bengaluru return flight vanished without a word.",
    build: (stops: Stop[]) => proposeSwapHotel(stops),
  },
];

export const startingTrip = sortStops(baseTrip);
