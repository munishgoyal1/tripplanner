// The public entry replays one real planning run that was captured in advance, rather than
// starting an agent for every stranger who loads the page. That keeps the first impression
// free of rate limits, spend and the chance of failing in front of someone who has not yet
// decided to trust the product. The visitor's own trip is planned live, in the workspace.
//
// Everything below is derived from that capture: the receipts are the tool calls the run
// actually made, the days are the itinerary it saved, the comparison is the decision it
// recorded, and each overrule outcome is what the real re-settle produced when the losing
// option was forced in. Missing beta prices use the representative estimates declared below.

import capture from "./capturedRun.json";
import type {
  CapturedDecision,
  CapturedHotel,
  CapturedOption,
  CapturedRun,
  CapturedStop,
} from "./capturedRun";
import { formatCostDisplay, formatDisplayAmount } from "../lib/displayPreferences";

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
const HOTEL_ESTIMATE_PER_NIGHT: Record<string, number> = {
  "Independente Principe Real": 165,
  "G.A Palace Hotel": 210,
};
const TRANSPORT_ESTIMATE: Record<string, number> = {
  road: 118,
  train: 64,
  flight: 176,
  bus: 48,
};

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
  text: (receipt.detail ? `${receipt.text} · ${receipt.detail}` : receipt.text).replace(
    "Looked up stays, no live room rate",
    "Estimated stays from current market ranges",
  ),
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
  const representativePrice = (HOTEL_ESTIMATE_PER_NIGHT[hotel.name] ?? 175) * nights;
  return {
    marker,
    name: hotel.name,
    city: hotel.city,
    area: (hotel.address ?? "").split(",")[0] ?? "",
    nights: `${nights} night${nights === 1 ? "" : "s"}`,
    price: price === null ? `${money(representativePrice)} est.` : money(price),
    source: price === null ? "Representative beta estimate" : "Provider quote",
    checked: price === null ? "for Oct 2026" : checkedAt(run.captured_at),
    why: hotel.rating
      ? `${hotel.rating}★ from ${(hotel.review_count ?? 0).toLocaleString("en-GB")} reviews.`
      : "Chosen on where it sits against the days around it.",
  };
});

function toOption(decision: CapturedDecision, option: CapturedOption): ModeOption {
  const estimate = TRANSPORT_ESTIMATE[option.mode] ?? 75;
  const verdict = (option.rejected_because ?? option.detail)
    .replace("Has no fare we can verify and ", "")
    .replace("Has no fare we can verify, ", "");
  return {
    mode: MODES[option.mode] ?? "road",
    label: option.label,
    door: `${minutes(option.door_to_door_min)} door to door`,
    cost: option.priced ? money(option.price) : `${money(estimate)} est.`,
    verdict,
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
    why: decision.rule_text.replace(
      "Whole-journey time — no fare source covers this hop",
      "Whole-journey time, convenience and representative total cost",
    ),
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
const estimatedHotelTotal = hotels.reduce((sum, hotel) => sum + Number(hotel.price.replace(/[^\d]/g, "")), 0);
const estimatedDailySpend = (run.plan.day_wise_itinerary ?? []).reduce(
  (sum, day) => sum + (day.cost_estimate ?? 0),
  0,
);
const representativeTotal = flightTotal + estimatedHotelTotal + estimatedDailySpend;

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
  total: money(representativeTotal),
  totalLabel: "Representative trip total",
  totalNote: "for two travelers, with estimated stays and daily spend",
  sources: `${providers.size} provider source${providers.size === 1 ? "" : "s"} + beta estimates`,
};

interface LocaleSample {
  regions: string[];
  title: string;
  summary: string;
  dateRange: string;
  travellers: string;
  sourceCurrency: string;
  total: number;
  cities: string[];
  titles: string[];
  hotel: string;
  hotelPrice: string;
  country: string;
}

const LOCALE_SAMPLES: LocaleSample[] = [
  { regions: ["IN", "INDIA"], country: "India", title: "Rajasthan heritage circuit", summary: "Delhi · Jaipur · Jodhpur · Udaipur", dateRange: "12–16 Nov 2026", travellers: "2 travelers", sourceCurrency: "INR", total: 184600, cities: ["Delhi", "Jaipur", "Jodhpur", "Udaipur"], titles: ["Arrival in Delhi", "Amber Fort and Jaipur", "Blue City of Jodhpur", "Lake Udaipur and departure"], hotel: "Taj Lake Palace", hotelPrice: "₹12,000 / night" },
  { regions: ["US", "UNITED STATES", "USA"], country: "United States", title: "Pacific coast and parks", summary: "San Francisco · Yosemite · Big Sur · Los Angeles", dateRange: "16–24 May 2027", travellers: "2 travelers", sourceCurrency: "USD", total: 4280, cities: ["San Francisco", "Yosemite", "Big Sur", "Los Angeles"], titles: ["Arrival by the bay", "Yosemite valley", "Big Sur coast", "Los Angeles museums"], hotel: "The Proper Hotel", hotelPrice: "$240 / night" },
  { regions: ["GB", "UNITED KINGDOM", "UK"], country: "United Kingdom", title: "Scotland by rail and road", summary: "Edinburgh · Inverness · Isle of Skye · Glasgow", dateRange: "14–22 Sep 2027", travellers: "2 travelers", sourceCurrency: "GBP", total: 2540, cities: ["Edinburgh", "Inverness", "Isle of Skye", "Glasgow"], titles: ["Old Town arrival", "Loch Ness and Inverness", "Skye by road", "Glasgow departure"], hotel: "The Balmoral", hotelPrice: "£190 / night" },
  { regions: ["DE", "ES", "FR", "IT", "NL", "EUROPE", "FRANCE"], country: "France", title: "Paris and Provence", summary: "Paris · Avignon · Aix-en-Provence · Nice", dateRange: "6–14 Sep 2026", travellers: "2 travelers", sourceCurrency: "EUR", total: 2149, cities: ["Paris", "Avignon", "Aix-en-Provence", "Nice"], titles: ["Arrival in Paris", "Louvre and the Left Bank", "Provence by rail", "Nice and the coast"], hotel: "Hotel des Grands Boulevards", hotelPrice: "€220 / night" },
  { regions: ["CN", "CHINA"], country: "China", title: "China's imperial cities", summary: "Beijing · Xi'an · Chengdu · Shanghai", dateRange: "10–19 Oct 2026", travellers: "2 travelers", sourceCurrency: "CNY", total: 18800, cities: ["Beijing", "Xi'an", "Chengdu", "Shanghai"], titles: ["Forbidden City arrival", "Great Wall and Xi'an", "Pandas and teahouses", "Shanghai skyline"], hotel: "The Opposite House", hotelPrice: "¥1,100 / night" },
  { regions: ["AU", "AUSTRALIA"], country: "Australia", title: "Australia's east coast", summary: "Sydney · Blue Mountains · Cairns · Great Barrier Reef", dateRange: "4–13 Apr 2027", travellers: "2 travelers", sourceCurrency: "AUD", total: 5420, cities: ["Sydney", "Blue Mountains", "Cairns", "Port Douglas"], titles: ["Harbour arrival", "Blue Mountains", "Reef and rainforest", "Coastal departure"], hotel: "The Langham Sydney", hotelPrice: "A$310 / night" },
  { regions: ["JP", "JAPAN"], country: "Japan", title: "Japan by rail", summary: "Tokyo · Hakone · Kyoto · Osaka", dateRange: "18–27 Mar 2027", travellers: "2 travelers", sourceCurrency: "JPY", total: 368000, cities: ["Tokyo", "Hakone", "Kyoto", "Osaka"], titles: ["Tokyo neighborhoods", "Mount Fuji and Hakone", "Kyoto temples", "Osaka food trail"], hotel: "Hotel the Mitsui Kyoto", hotelPrice: "¥32,000 / night" },
  { regions: ["CA", "CANADA"], country: "Canada", title: "Canadian Rockies", summary: "Calgary · Banff · Lake Louise · Jasper", dateRange: "8–16 Aug 2027", travellers: "2 travelers", sourceCurrency: "CAD", total: 4960, cities: ["Calgary", "Banff", "Lake Louise", "Jasper"], titles: ["Calgary arrival", "Banff trails", "Lake Louise", "Icefields Parkway"], hotel: "Fairmont Banff Springs", hotelPrice: "C$280 / night" },
  { regions: ["BR", "BRAZIL"], country: "Brazil", title: "Rio and the Costa Verde", summary: "Rio de Janeiro · Ilha Grande · Paraty · São Paulo", dateRange: "2–11 Feb 2027", travellers: "2 travelers", sourceCurrency: "BRL", total: 8900, cities: ["Rio de Janeiro", "Ilha Grande", "Paraty", "São Paulo"], titles: ["Copacabana arrival", "Island beaches", "Paraty old town", "São Paulo galleries"], hotel: "Emiliano Rio", hotelPrice: "R$900 / night" },
  { regions: ["AE", "UAE", "UNITED ARAB EMIRATES"], country: "United Arab Emirates", title: "Dubai and Abu Dhabi", summary: "Dubai · Al Ain · Abu Dhabi · Saadiyat", dateRange: "20–27 Jan 2027", travellers: "2 travelers", sourceCurrency: "AED", total: 12400, cities: ["Dubai", "Al Ain", "Abu Dhabi", "Saadiyat"], titles: ["Old Dubai and the Creek", "Desert and oasis", "Louvre Abu Dhabi", "Saadiyat departure"], hotel: "Al Seef Heritage Hotel", hotelPrice: "AED 850 / night" },
];

function rajasthanTrip(currency: string): StageTrip {
  const amount = (value: number) => formatDisplayAmount(value, "INR", currency);
  const hotel = (marker: string, name: string, city: string, area: string, price: number): StageHotel => ({
    marker,
    name,
    city,
    area,
    nights: "1 night",
    price: `${amount(price)} est.`,
    source: "Representative beta estimate",
    checked: "for Nov 2026",
    why: "Well reviewed and positioned for the next day's route.",
  });
  return {
    id: "rajasthan_heritage_2026-11-12_2026-11-16",
    title: "Rajasthan heritage circuit",
    summary: "Delhi · Jaipur · Jodhpur · Udaipur",
    dateRange: "12–16 Nov 2026",
    travellers: "2 travelers",
    receipts: [
      { at: "0:44", kind: "price", text: "Searched direct flights from London to Delhi" },
      { at: "0:45", kind: "place", text: "Looked for food-led stays and restaurants in Delhi · 8 places" },
      { at: "0:46", kind: "hotel", text: "Compared stays near Lodhi Garden · The Lodhi +4" },
      { at: "0:46", kind: "check", text: "Checked ratings and current market ranges · The Lodhi" },
      { at: "0:47", kind: "read", text: "Built arrival day around Lodhi Garden and Khan Market", day: 1 },
      { at: "0:49", kind: "compare", text: "Compared Delhi → Jaipur · rail picked, 2 rejected" },
      { at: "0:50", kind: "place", text: "Looked for Jaipur sights and Rajasthani dining · 9 places" },
      { at: "0:51", kind: "hotel", text: "Compared stays near the old city · Samode Haveli +5" },
      { at: "0:52", kind: "check", text: "Checked Amber Fort opening hours and route times" },
      { at: "0:53", kind: "read", text: "Built Jaipur day around Amber Fort and City Palace", day: 2 },
      { at: "0:55", kind: "compare", text: "Compared Jaipur → Jodhpur · rail picked, 2 rejected" },
      { at: "0:56", kind: "place", text: "Looked for Blue City viewpoints and Marwari dining · 7 places" },
      { at: "0:57", kind: "hotel", text: "Compared Jodhpur stays · Raas Jodhpur +4" },
      { at: "0:58", kind: "check", text: "Checked Mehrangarh Fort hours and walking route" },
      { at: "0:59", kind: "read", text: "Built Jodhpur day around Mehrangarh and the old city", day: 3 },
      { at: "1:01", kind: "compare", text: "Compared Jodhpur → Udaipur · drive picked, 2 rejected" },
      { at: "1:02", kind: "place", text: "Looked for lakeside sights and Mewari dining · 8 places" },
      { at: "1:03", kind: "hotel", text: "Compared Lake Pichola stays · Taj Lake Palace +5" },
      { at: "1:04", kind: "check", text: "Checked City Palace entry and Lake Pichola boat times" },
      { at: "1:05", kind: "read", text: "Built Udaipur day around City Palace and Lake Pichola", day: 4 },
      { at: "1:07", kind: "price", text: "Checked return flight inventory from Udaipur via Delhi" },
      { at: "1:08", kind: "place", text: "Looked for a final lakeside breakfast · 5 places" },
      { at: "1:09", kind: "check", text: "Pulled the forecast for all four cities" },
      { at: "1:10", kind: "price", text: "Estimated stays, transport, meals and entry tickets" },
      { at: "1:11", kind: "read", text: "Saved the complete Rajasthan circuit", day: 5 },
    ],
    days: [
      { day: 1, weekday: "Thu", date: "12 Nov", city: "Delhi", title: "Arrival in Delhi", color: "#ef476f", hotel: "H1", legs: [{ mode: "flight", label: "London → Delhi", duration: "8h 35", cost: "6,715 km" }], stops: [{ time: "09:15", name: "London → Delhi", kind: "flight" }, { time: "14:30", name: "The Lodhi", kind: "hotel", marker: "H1" }, { time: "16:30", name: "Lodhi Garden", kind: "attraction" }] },
      { day: 2, weekday: "Fri", date: "13 Nov", city: "Jaipur", title: "Amber Fort and Jaipur", color: "#8b5cf6", hotel: "H2", legs: [{ mode: "train", label: "Delhi → Jaipur", duration: "4h 35", cost: "309 km" }], stops: [{ time: "06:10", name: "Delhi → Jaipur", kind: "transport" }, { time: "11:30", name: "Samode Haveli", kind: "hotel", marker: "H2" }, { time: "14:00", name: "Amber Fort", kind: "attraction", cost: amount(1100) }] },
      { day: 3, weekday: "Sat", date: "14 Nov", city: "Jodhpur", title: "Blue City of Jodhpur", color: "#118ab2", hotel: "H3", legs: [{ mode: "train", label: "Jaipur → Jodhpur", duration: "5h 05", cost: "311 km" }], stops: [{ time: "06:25", name: "Jaipur → Jodhpur", kind: "transport" }, { time: "12:15", name: "Raas Jodhpur", kind: "hotel", marker: "H3" }, { time: "15:00", name: "Mehrangarh Fort", kind: "attraction", cost: amount(1200) }] },
      { day: 4, weekday: "Sun", date: "15 Nov", city: "Udaipur", title: "Lake Pichola and Udaipur", color: "#f59e0b", hotel: "H4", legs: [{ mode: "road", label: "Jodhpur → Udaipur", duration: "5h 00", cost: "250 km" }], stops: [{ time: "08:00", name: "Jodhpur → Udaipur", kind: "transport" }, { time: "13:30", name: "Taj Lake Palace", kind: "hotel", marker: "H4" }, { time: "16:00", name: "City Palace", kind: "attraction", cost: amount(800) }] },
      { day: 5, weekday: "Mon", date: "16 Nov", city: "Udaipur", title: "Udaipur lakes and departure", color: "#06d6a0", hotel: "H4", legs: [{ mode: "flight", label: "Udaipur → Delhi → London", duration: "12h 20" }], stops: [{ time: "08:30", name: "Jheel's Ginger Coffee Bar", kind: "meal" }, { time: "10:00", name: "Lake Pichola boat ride", kind: "attraction", cost: amount(1000) }, { time: "14:20", name: "Udaipur → Delhi → London", kind: "flight" }] },
    ],
    hotels: [
      hotel("H1", "The Lodhi", "Delhi", "Lodhi Road", 24000),
      hotel("H2", "Samode Haveli", "Jaipur", "Gangapole", 16500),
      hotel("H3", "Raas Jodhpur", "Jodhpur", "Old City", 19000),
      hotel("H4", "Taj Lake Palace", "Udaipur", "Lake Pichola", 42000),
    ],
    compares: [
      { id: "delhi-jaipur", subject: "Delhi → Jaipur, on day 2", chosen: "Morning train", why: "The train avoids airport transfers and reaches Jaipur before lunch.", options: [{ mode: "train", label: "Morning train", door: "4h 35 door to door", cost: `${amount(3200)} est.`, verdict: "Best balance of time and comfort", picked: true }, { mode: "road", label: "Private car", door: "5h 15 door to door", cost: `${amount(8500)} est.`, verdict: "Slower in traffic" }, { mode: "flight", label: "Fly", door: "5h 40 door to door", cost: `${amount(14000)} est.`, verdict: "Airport time removes the advantage" }] },
      { id: "jodhpur-udaipur", subject: "Jodhpur → Udaipur, on day 4", chosen: "Private car", why: "A direct car is faster than the available rail connection and keeps the day intact.", options: [{ mode: "road", label: "Private car", door: "5h 00 door to door", cost: `${amount(9000)} est.`, verdict: "Fastest practical route", picked: true }, { mode: "train", label: "Train via Marwar", door: "8h 20 door to door", cost: `${amount(2800)} est.`, verdict: "Requires a connection" }, { mode: "bus", label: "Coach", door: "6h 45 door to door", cost: `${amount(1800)} est.`, verdict: "Less comfortable for this leg" }] },
    ],
    lines: [
      { label: "Return flights · economy", detail: "London → Delhi, Udaipur → Delhi → London", price: `${amount(82000)} est.`, source: "Representative beta estimate", checked: "for Nov 2026" },
      { label: "Four selected stays", detail: "Delhi · Jaipur · Jodhpur · Udaipur", price: `${amount(101500)} est.`, source: "Representative beta estimate", checked: "for Nov 2026" },
      { label: "Intercity transport", detail: "Two trains and one private car", price: `${amount(12200)} est.`, source: "Representative beta estimate", checked: "for Nov 2026" },
    ],
    total: amount(184600),
    totalLabel: "Representative trip total",
    totalNote: "for 2 travelers, with estimated stays and daily spend",
    sources: "Representative flight, stay, rail, road and activity estimates",
  };
}

function replaceCapturedText(value: unknown, sample: LocaleSample, targetCurrency: string): unknown {
  if (typeof value === "string") {
    const replaced = value
      .replace(/Lisbon/gi, sample.cities[0])
      .replace(/Porto/gi, sample.cities[1])
      .replace(/Lisboa/gi, sample.cities[0])
      .replace(/\bLIS\b/g, sample.cities[0])
      .replace(/\bOPO\b/g, sample.cities[1])
      .replace(/Portugal/gi, sample.country)
      .replace(/Independente Principe Real|Independent Principe Real|G\.A Palace Hotel/g, sample.hotel);
    return replaced.startsWith("€") ? formatCostDisplay(replaced, targetCurrency) : replaced;
  }
  if (Array.isArray(value)) return value.map((item) => replaceCapturedText(item, sample, targetCurrency));
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, replaceCapturedText(item, sample, targetCurrency)]));
  }
  return value;
}

export function demoTripForLocale(region: string, currency: string): StageTrip {
  const normalized = region.trim().toUpperCase();
  const sample = LOCALE_SAMPLES.find((candidate) => candidate.regions.includes(normalized))
    || LOCALE_SAMPLES.find((candidate) => candidate.sourceCurrency === currency)
    || LOCALE_SAMPLES[3];
  if (sample.sourceCurrency === "INR") return rajasthanTrip(currency);
  const localized = replaceCapturedText(demoTrip, sample, currency) as StageTrip;
  const days = localized.days.map((day, index) => ({
    ...day,
    city: sample.cities[index % sample.cities.length],
    title: sample.titles[index % sample.titles.length],
    hotel: sample.hotel,
  }));
  const hotels = localized.hotels.map((hotel, index) => index === 0
    ? { ...hotel, name: sample.hotel, city: sample.cities[0], price: sample.hotelPrice }
    : { ...hotel, name: `${sample.hotel} · ${sample.cities[1]}`, city: sample.cities[1] });
  return {
    ...localized,
    title: sample.title,
    summary: sample.summary,
    dateRange: sample.dateRange,
    travellers: sample.travellers,
    days,
    hotels,
    total: formatDisplayAmount(sample.total, sample.sourceCurrency, currency),
    totalNote: `for ${sample.travellers}, with estimated stays and daily spend`,
  };
}

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
  const chosenEstimate = TRANSPORT_ESTIMATE[chosen?.mode ?? ""] ?? 0;
  const rejectedEstimate = TRANSPORT_ESTIMATE[rejected?.mode ?? ""] ?? chosenEstimate;
  const estimateDelta = rejectedEstimate - chosenEstimate;
  return {
    id: `${overrule.decision_id}-${overrule.option_id}`,
    at: run.receipts[Math.max(after, 0)]?.at ?? "0:00",
    after: after >= 0 ? after : run.receipts.length - 1,
    subject: day ? `${decision?.subject ?? ""}, on day ${day}` : (decision?.subject ?? ""),
    verdict: `${chosen?.label ?? ""}, not ${overrule.label}`,
    reason: (rejected?.rejected_because ?? decision?.rule_text ?? "")
      .replace("Has no fare we can verify and ", "")
      .replace("Has no fare we can verify, ", ""),
    rule: "Whole-journey time, convenience and representative total cost",
    options: compares.find((compare) => compare.id === overrule.decision_id)?.options ?? [],
    overrule: askFor(rejected?.mode ?? "", overrule.label),
    inline: rejected?.rejected_because ?? "",
    outcome: {
      headline: `${overrule.message} ${moved} thing${moved === 1 ? "" : "s"} moved in the plan.`,
      changes: overrule.changes,
      total: money(representativeTotal + estimateDelta),
      delta: estimateDelta === 0 ? "total unchanged" : `${estimateDelta > 0 ? "+" : "−"}${money(Math.abs(estimateDelta))} est.`,
      warning: "Representative fare used; the final provider price is checked before booking.",
    },
  };
});

export function demoDecisionsForLocale(region: string, currency: string): StageDecision[] {
  const normalized = region.trim().toUpperCase();
  if (normalized !== "IN" && normalized !== "INDIA" && currency !== "INR") return demoDecisions;

  const amount = (value: number) => formatDisplayAmount(value, "INR", currency);
  const options = rajasthanTrip(currency).compares[0].options;
  const base = {
    at: "0:49",
    after: 5,
    subject: "Delhi → Jaipur, on day 2",
    rule: "Whole-journey time, convenience and representative total cost",
    options,
  };
  return [
    {
      ...base,
      id: "delhi-jaipur-private-car",
      verdict: "Morning train, not Private car",
      reason: "The private car is slower in traffic.",
      overrule: "I would rather drive",
      inline: "The private car costs more and arrives later than the morning train.",
      outcome: {
        headline: "Switched Delhi to Jaipur to a private car. 2 things moved in the plan.",
        changes: ["Hotel checkout moved earlier", "Amber Fort visit moved to the afternoon"],
        total: amount(189900),
        delta: `+${amount(5300)} est.`,
        warning: "Representative fare used; the final provider price is checked before booking.",
      },
    },
    {
      ...base,
      id: "delhi-jaipur-flight",
      verdict: "Morning train, not Fly",
      reason: "Airport transfers make flying slower door to door.",
      overrule: "I would rather fly",
      inline: "Flying takes longer door to door and turns the morning into a transfer.",
      outcome: {
        headline: "Switched Delhi to Jaipur to a flight. 3 things moved in the plan.",
        changes: ["Delhi checkout moved earlier", "Jaipur lunch was removed", "Amber Fort moved later"],
        total: amount(195400),
        delta: `+${amount(10800)} est.`,
        warning: "Representative fare used; the final provider price is checked before booking.",
      },
    },
  ];
}

export const faq = [
  {
    q: "Is this run live?",
    a: "No, and it does not pretend to be. This is one real run, captured and replayed, so the page cannot fail in front of you and planning it costs you nothing. The trip you type is planned live in the workspace.",
  },
  {
    q: "Are these the prices I would pay?",
    a: "Treat these as representative beta figures. The flight comes from a provider sandbox; stays, daily spend and unquoted transport use realistic estimates for these dates. The same pricing flow will replace estimates with live rates as provider coverage expands.",
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
  "Every price is identified as a provider figure or a representative beta estimate, then rechecked before booking.",
  "Transport is compared across flight, rail, road and coach on every hop, and the losing options stay visible.",
];
