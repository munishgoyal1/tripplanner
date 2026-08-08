// The public entry replays one real planning run that was captured in advance, rather than
// starting an agent for every stranger who loads the page. That keeps the first impression
// free of rate limits, spend and the chance of failing in front of someone who has not yet
// decided to trust the product. The visitor's own trip is planned live, in the workspace.
//
// Everything below is derived from that capture: the receipts are the tool calls the run
// actually made, the days are the itinerary it saved, the comparison is the decision it
// recorded, and each overrule outcome is what the real re-settle produced when the losing
// option was forced in. Nothing here is written by hand to sound convincing.

import capture from "./capturedRun.json";
import type {
  CapturedDecision,
  CapturedHotel,
  CapturedOption,
  CapturedRun,
  CapturedStop,
} from "./capturedRun";

const run = capture as unknown as CapturedRun;

export type StageMode = "flight" | "train" | "road" | "tram" | "metro" | "bus" | "walk" | "ferry";

export type StopKind = "flight" | "hotel" | "attraction" | "meal" | "transport";

export interface StageStop {
  time: string;
  name: string;
  detail?: string;
  kind: StopKind;
  marker?: string;
  cost?: string;
}

export interface StageLeg {
  mode: StageMode;
  label: string;
  duration: string;
  cost?: string;
}

export interface StageDay {
  day: number;
  weekday: string;
  date: string;
  city: string;
  title: string;
  color: string;
  hotel: string;
  legs: StageLeg[];
  stops: StageStop[];
}

export interface StageHotel {
  marker: string;
  name: string;
  city: string;
  area: string;
  nights: string;
  price: string;
  source: string;
  checked: string;
  why: string;
}

export interface ModeOption {
  mode: StageMode;
  label: string;
  door: string;
  cost: string;
  verdict: string;
  picked?: boolean;
}

export interface ModeCompare {
  id: string;
  subject: string;
  chosen: string;
  options: ModeOption[];
  why: string;
}

export interface StageReceipt {
  at: string;
  kind: "read" | "search" | "price" | "hotel" | "place" | "compare" | "check";
  text: string;
  /** Set on the receipt that completes a day, so day cards can only finish when the run does. */
  day?: number;
}

export interface PriceLine {
  label: string;
  detail: string;
  price: string;
  source: string;
  checked: string;
}

export interface StageTrip {
  id: string;
  title: string;
  summary: string;
  dateRange: string;
  travellers: string;
  receipts: StageReceipt[];
  days: StageDay[];
  hotels: StageHotel[];
  compares: ModeCompare[];
  lines: PriceLine[];
  total: string;
  totalLabel: string;
  totalNote: string;
  sources: string;
}
export interface StageDecision {
  id: string;
  /** Receipt timestamp this decision belongs to, so it reads as part of the run. */
  at: string;
  /** Index of the receipt it follows. A clock string is not unique; a position is. */
  after: number;
  subject: string;
  verdict: string;
  reason: string;
  rule: string;
  options: ModeOption[];
  overrule: string;
  /** One line short enough to sit inside the receipt console. */
  inline: string;
  outcome: {
    headline: string;
    changes: string[];
    total: string;
    delta: string;
    warning: string;
  };
}

const SYMBOL = run.trip.currency || "€";
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function parseDate(iso: string): Date {
  return new Date(`${iso.slice(0, 10)}T00:00:00`);
}

function shortDate(iso: string): string {
  const date = parseDate(iso);
  return `${date.getDate()} ${MONTHS[date.getMonth()]}`;
}

function money(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${SYMBOL}${Math.round(value).toLocaleString("en-GB")}`;
}

function minutes(total: number): string {
  const hours = Math.floor(total / 60);
  const rest = Math.round(total % 60);
  return hours ? `${hours}h ${String(rest).padStart(2, "0")}` : `${rest} min`;
}

function checkedAt(iso: string): string {
  const at = new Date(iso);
  const hh = String(at.getHours()).padStart(2, "0");
  const mm = String(at.getMinutes()).padStart(2, "0");
  return `${at.getDate()} ${MONTHS[at.getMonth()]} ${hh}:${mm}`;
}

// The engine names a tool's field of work; the console colours a smaller set of shapes. The
// two vocabularies meet here rather than in the components.
const RECEIPT_KINDS: Record<string, StageReceipt["kind"]> = {
  places: "place",
  lodging: "hotel",
  flights: "price",
  transport: "compare",
  routing: "check",
  weather: "check",
  entry: "check",
  events: "search",
  web: "search",
};

const MODES: Record<string, StageMode> = {
  flight: "flight",
  train: "train",
  road: "road",
  bus: "bus",
  ferry: "ferry",
  walk: "walk",
};

const STOP_KINDS: Record<string, StopKind> = {
  flight: "flight",
  hotel: "hotel",
  meal: "meal",
  restaurant: "meal",
  attraction: "attraction",
  transport: "transport",
  airport: "transport",
  origin: "transport",
};

function tidyPlace(name: string): string {
  return name
    .replace(/\s*\([A-Z0-9]{2,7}\)\s*/g, " ")
    .replace(/\bAirport Airport\b/g, "Airport")
    .replace(/\s+/g, " ")
    .trim();
}

// "Flight: London Airport to Lisbon (BA0117) Airport" and "Duffel Airways Flight LHR-LIS" are
// both how a plan stores a leg. A visitor should read the journey, not the record of it.
function tidyName(name: string): string {
  const leg = name.match(/^(?:Flight|Train|Drive|Bus|Ferry):\s*(.+?)\s+to\s+(.+)$/i);
  if (leg) return `${tidyPlace(leg[1])} → ${tidyPlace(leg[2])}`;
  const coded = name.match(/\b([A-Z]{3})\s*[-–→]\s*([A-Z]{3})\b/);
  if (coded) return `${coded[1]} → ${coded[2]}`;
  return tidyPlace(name);
}

const hotelNames = (run.plan.selected_hotels ?? []).map((hotel) => hotel.name);

function hotelMarker(name: string): string {
  const index = hotelNames.indexOf(name);
  return index >= 0 ? `H${index + 1}` : "";
}

function toStop(stop: CapturedStop): StageStop {
  const kind = STOP_KINDS[stop.kind] ?? "attraction";
  return {
    time: stop.time,
    name: tidyName(stop.name),
    kind,
    marker: kind === "hotel" ? hotelMarker(stop.name) : undefined,
    // A hotel carries its real price in the strip below, so repeating an estimate band on
    // every check-in and return line would only argue with it.
    cost: kind === "hotel" ? undefined : stop.cost_display || undefined,
  };
}

function legMode(stop: CapturedStop): StageMode | null {
  if (stop.kind === "flight") return "flight";
  if (/train/i.test(stop.name)) return "train";
  if (/drive|car/i.test(stop.name)) return "road";
  if (/bus|coach/i.test(stop.name)) return "bus";
  if (/ferry/i.test(stop.name)) return "ferry";
  return null;
}

function toLeg(stop: CapturedStop): StageLeg | null {
  const mode = legMode(stop);
  if (!mode) return null;
  return {
    mode,
    label: tidyName(stop.name),
    duration: stop.duration_min ? minutes(stop.duration_min) : "—",
    cost: stop.distance_km ? `${Math.round(stop.distance_km)} km` : undefined,
  };
}

const days: StageDay[] = run.days.map((day) => {
  const date = parseDate(day.date);
  // Where the day ends, not where it started: on a transfer day that is the new city.
  const hotelStops = day.stops.filter((stop) => stop.kind === "hotel");
  const hotelStop = hotelStops[hotelStops.length - 1];
  const hotel = (run.plan.selected_hotels ?? []).find((entry) => entry.name === hotelStop?.name);
  return {
    day: day.day,
    weekday: WEEKDAYS[date.getDay()],
    date: shortDate(day.date),
    city: hotel?.city ?? run.trip.destination,
    title: day.title,
    color: day.color,
    hotel: hotelMarker(hotelStop?.name ?? ""),
    legs: day.stops.map(toLeg).filter((leg): leg is StageLeg => leg !== null),
    // Airports and kerbside pickups are how a plan is built, not what a visitor came to see.
    stops: day.stops
      .filter((stop) => stop.kind !== "airport" && stop.kind !== "origin")
      .map(toStop),
  };
});

// The run does not record which receipt settled which day, so the reveal is paced across the
// tail of the stream. It controls when a day card appears, never what the card claims.
const dayMarks = new Map<number, number>();
run.days.forEach((day, index) => {
  const slot = Math.max(run.receipts.length - run.days.length + index, index);
  dayMarks.set(slot, day.day);
});

const receipts: StageReceipt[] = run.receipts.map((receipt, index) => ({
  at: receipt.at,
  kind: RECEIPT_KINDS[receipt.kind] ?? "search",
  text: receipt.detail ? `${receipt.text} · ${receipt.detail}` : receipt.text,
  day: dayMarks.get(index),
}));

function hotelPrice(hotel: CapturedHotel, nights: number): number | null {
  if (hotel.price_total != null) return hotel.price_total;
  if (hotel.total_price != null) return hotel.total_price;
  if (hotel.price_per_night != null) return hotel.price_per_night * nights;
  return null;
}

// A plan does not always save check-in dates, but the itinerary always knows where each day
// ends. Counting the days a hotel is the base — less the last one, which you leave in the
// morning — gives the same answer without inventing a date.
const nightsByMarker = new Map<string, number>();
days.forEach((day) => {
  if (day.hotel) nightsByMarker.set(day.hotel, (nightsByMarker.get(day.hotel) ?? 0) + 1);
});
const lastBase = days[days.length - 1]?.hotel;
if (lastBase) nightsByMarker.set(lastBase, (nightsByMarker.get(lastBase) ?? 1) - 1);

const hotels: StageHotel[] = (run.plan.selected_hotels ?? []).map((hotel, index) => {
  const marker = `H${index + 1}`;
  const nights =
    hotel.checkin && hotel.checkout
      ? Math.round(
          (parseDate(hotel.checkout).getTime() - parseDate(hotel.checkin).getTime()) / 86_400_000,
        )
      : (nightsByMarker.get(marker) ?? 0);
  const price = hotelPrice(hotel, nights);
  return {
    marker,
    name: hotel.name,
    city: hotel.city,
    area: (hotel.address ?? "").split(",")[0] ?? "",
    nights: `${nights} night${nights === 1 ? "" : "s"}`,
    price: price === null ? "no live rate" : money(price),
    source: "Google Places",
    checked: checkedAt(run.captured_at),
    why: hotel.rating
      ? `${hotel.rating}★ from ${(hotel.review_count ?? 0).toLocaleString("en-GB")} reviews.`
      : "Chosen on where it sits against the days around it.",
  };
});

function toOption(decision: CapturedDecision, option: CapturedOption): ModeOption {
  return {
    mode: MODES[option.mode] ?? "road",
    label: option.label,
    door: `${minutes(option.door_to_door_min)} door to door`,
    cost: option.priced ? money(option.price) : "no fare source",
    verdict: option.rejected_because ?? option.detail,
    picked: option.id === decision.chosen_option_id,
  };
}

const compares: ModeCompare[] = run.decisions.map((decision) => {
  const chosen = decision.options.find((option) => option.id === decision.chosen_option_id);
  return {
    id: decision.id,
    subject: decision.subject,
    chosen: chosen?.label ?? "",
    options: decision.options.map((option) => toOption(decision, option)),
    why: decision.rule_text,
  };
});

// A flight record can hold the way back on the same row, so the label follows what the record
// actually contains rather than assuming a shape.
const bookings = run.plan.selected_flights ?? [];
const flightCheck = run.provenance.find((row) => row.kind === "flights");
const flightTotal = bookings.reduce((sum, booking) => sum + (booking.total_price ?? 0), 0);

function flightRoute(booking: (typeof bookings)[number]): string {
  const out = `${tidyPlace(booking.from ?? "")} → ${tidyPlace(booking.to ?? "")}`;
  return booking.return_departure ? `${out}, ${tidyPlace(booking.to ?? "")} → ${tidyPlace(booking.from ?? "")}` : out;
}

const returning = bookings.some((booking) => booking.return_departure) || bookings.length === 2;

const lines: PriceLine[] = [
  ...(bookings.length
    ? [
        {
          label: `${bookings[0].airline ?? "Flights"} · ${returning ? "return" : "one way"}`,
          detail: bookings.map(flightRoute).join(", "),
          price: flightTotal ? money(flightTotal) : "no live fare",
          source: flightCheck?.provider ?? "Duffel",
          checked: flightCheck ? checkedAt(flightCheck.checked_at) : "",
        },
      ]
    : []),
  ...hotels.map((hotel) => ({
    label: hotel.name,
    detail: `${hotel.city} · ${hotel.nights}`,
    price: hotel.price,
    source: hotel.source,
    checked: hotel.checked,
  })),
];

function dateRange(from: string, to: string): string {
  const start = parseDate(from);
  const end = parseDate(to);
  const tail = `${shortDate(to)} ${end.getFullYear()}`;
  return start.getMonth() === end.getMonth()
    ? `${start.getDate()}–${tail}`
    : `${shortDate(from)} – ${tail}`;
}

const providers = new Set(run.provenance.map((row) => row.provider));

// If the saved total is only the fares, saying "trip total" would be the one dishonest number
// on a page about not inventing numbers.
const faresOnly = Math.abs(run.trip.total_cost - flightTotal) < 1 && hotels.length > 0;

export const demoTrip: StageTrip = {
  id: run.trip.id,
  title: `${run.stats.days} days in ${run.trip.destination}`,
  summary: `${hotels.length} hotels · ${run.stats.days} days · ${run.stats.stops} stops`,
  dateRange: dateRange(run.trip.departure_date, run.trip.return_date),
  travellers: run.trip.travellers,
  receipts,
  days,
  hotels,
  compares,
  lines,
  total: run.overview.total_cost_display ?? money(run.trip.total_cost),
  totalLabel: faresOnly ? "Priced so far" : "Trip total",
  totalNote: faresOnly
    ? "what a provider actually quoted, stays and daily spend excluded"
    : "with the per-day food and entry estimates",
  sources: providers.size
    ? `${providers.size} priced source${providers.size === 1 ? "" : "s"}`
    : "no live fare on this hop",
};

// The engine labels an option; a person says it. "I would rather take the fly" is neither.
function askFor(mode: string, label: string): string {
  if (mode === "flight") return "I would rather fly";
  if (mode === "road") return "I would rather drive";
  if (mode === "walk") return "I would rather walk";
  return `I would rather take the ${label.toLowerCase()}`;
}

// One card per way the planner could have been overruled. The outcome is not a description of
// what would happen — it is what did happen when the real plan was re-settled on that option.
export const demoDecisions: StageDecision[] = run.overrules.map((overrule) => {
  const decision = run.decisions.find((entry) => entry.id === overrule.decision_id);
  const after = run.receipts.findIndex((entry) => entry.decision_id === overrule.decision_id);
  const chosen = decision?.options.find((option) => option.id === decision.chosen_option_id);
  const rejected = decision?.options.find((option) => option.id === overrule.option_id);
  const day = decision?.scope.day;
  const moved = overrule.changes.length;
  return {
    id: `${overrule.decision_id}-${overrule.option_id}`,
    at: run.receipts[Math.max(after, 0)]?.at ?? "0:00",
    after: after >= 0 ? after : run.receipts.length - 1,
    subject: day ? `${decision?.subject ?? ""}, on day ${day}` : (decision?.subject ?? ""),
    verdict: `${chosen?.label ?? ""}, not ${overrule.label}`,
    reason: rejected?.rejected_because ?? decision?.rule_text ?? "",
    rule: decision?.rule_text ?? "",
    options: compares.find((compare) => compare.id === overrule.decision_id)?.options ?? [],
    overrule: askFor(rejected?.mode ?? "", overrule.label),
    inline: rejected?.rejected_because ?? "",
    outcome: {
      headline: `${overrule.message} ${moved} thing${moved === 1 ? "" : "s"} moved in the plan.`,
      changes: overrule.changes,
      total: money(overrule.total_cost),
      delta: overrule.delta === 0 ? "total unchanged" : money(overrule.delta),
      warning: overrule.warnings[0] ?? "",
    },
  };
});

export const faq = [
  {
    q: "Is this run live?",
    a: "No, and it does not pretend to be. This is one real run, captured and replayed, so the page cannot fail in front of you and planning it costs you nothing. The trip you type is planned live in the workspace.",
  },
  {
    q: "Are these the prices I would pay?",
    a: "Not yet. The flight and room prices here come from provider sandboxes, so treat them as sample figures. What is real is where each one came from and when it was fetched — the same plumbing carries live rates once the accounts are live.",
  },
  {
    q: "Do I have to watch it?",
    a: "No. Skip to the finished plan at any point, or go straight to the planner and start your own trip.",
  },
  {
    q: "Why does it compare trains and cars at all?",
    a: "Because a trip is decided by how you move between places, not by the places. The planner measures the flight, the train, the coach and the car for each hop, door to door, then keeps whichever wins.",
  },
  {
    q: "Can it book any of it?",
    a: "Not yet, and not silently. It hands you the exact provider page with dates, travellers and fare already chosen. We never hold a card.",
  },
];

export const trustPoints = [
  "No account needed to plan. Your trip is saved in this browser until you sign in.",
  "We never take a payment and never hold your card. Booking finishes on the provider's own site.",
  "Every price carries its source and the minute it was fetched, and anything nobody quoted says so instead of guessing.",
  "Transport is compared across flight, rail, road and coach on every hop, and the losing options stay visible.",
];
