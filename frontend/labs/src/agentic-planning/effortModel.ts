/**
 * The trip critic: what a day costs, and what it costs by the end of the week.
 *
 * Kept deliberately apart from `planEngine.ts`. The invariants there are boolean,
 * provable, and they block. Everything here is continuous, arguable, and it may
 * only rank and warn. Merging the two produces one of two failures: a taste
 * penalty that starts refusing legal plans, or a real violation averaged away by
 * a good score somewhere else.
 *
 *   The invariant may block but never speaks in numbers.
 *   The score may speak but never blocks.
 *
 * Two further rules hold throughout:
 *
 * - **Effort, not distance.** Five kilometres of jeep on a broken track costs
 *   more than thirty on a highway, and the arithmetic below says so out loud.
 * - **No composite ever reaches the user.** `describe*` returns measured
 *   quantities and comparisons. The scalar exists only to sort candidates and to
 *   be inspected in the plan console.
 */

import { distanceKm, fmtMin, sortStops, toMin, travelMin } from "./planEngine";
import type { Stop } from "./fixture";

/* --------------------------------- units ----------------------------------- */

/**
 * Everything is denominated in effort-minutes: one minute of unhurried
 * sightseeing costs 1. It makes five unlike things comparable and keeps the
 * debugging read intuitive — "this day costs like nine hours of easy walking".
 */
export type Currency = "physical" | "transit" | "logistical" | "circadian" | "exposure";

export const CURRENCIES: Currency[] = ["physical", "transit", "logistical", "circadian", "exposure"];

export type Effort = Record<Currency, number>;

export const zeroEffort = (): Effort => ({
  physical: 0,
  transit: 0,
  logistical: 0,
  circadian: 0,
  exposure: 0,
});

export const addEffort = (a: Effort, b: Effort): Effort => ({
  physical: a.physical + b.physical,
  transit: a.transit + b.transit,
  logistical: a.logistical + b.logistical,
  circadian: a.circadian + b.circadian,
  exposure: a.exposure + b.exposure,
});

export const totalEffort = (effort: Effort) =>
  CURRENCIES.reduce((sum, currency) => sum + effort[currency], 0);

export const CURRENCY_LABEL: Record<Currency, string> = {
  physical: "on your feet",
  transit: "in transit",
  logistical: "packing up and moving on",
  circadian: "against the clock",
  exposure: "out in the weather",
};

/* ------------------------------- coefficients ------------------------------- */

/**
 * Every tunable number in the model lives in this block, so retuning is one
 * edit rather than an archaeology exercise. None of these are measured truths;
 * they are defensible priors, which is exactly why they may never block.
 */

/** How tiring a minute of travel is, by mode and surface. */
export const MODE_FACTOR = {
  train: 0.7,
  car_highway: 1.0,
  car_city: 1.2,
  car_winding: 1.55,
  car_rough: 2.1,
  bus: 1.35,
  flight: 1.3,
  walk: 2.4,
  boat: 1.25,
} as const;

export type Mode = keyof typeof MODE_FACTOR;

export const MODE_LABEL: Record<Mode, string> = {
  train: "train",
  car_highway: "highway driving",
  car_city: "city driving",
  car_winding: "winding road",
  car_rough: "rough track",
  bus: "bus",
  flight: "flying",
  walk: "walking",
  boat: "boat",
};

const WALK_MIN_PER_KM = 13;
const ASCENT_COST_PER_M = 0.35;
const STEP_COST = 0.22;
const STANDING_FACTOR = 0.6;
const CROWD_SURCHARGE = 0.25;

const TRANSITION_COST = 12;
const CHECK_COST = 25;
const AIRPORT_COST = 45;

const EARLY_HOUR = 7 * 60;
const LATE_HOUR = 22 * 60;
const EARLY_FACTOR = 1.4;
const LATE_FACTOR = 1.2;

/** The share of a day's debt in each currency that one night clears. */
export const RECOVERY: Record<Currency, number> = {
  physical: 0.55,
  transit: 0.8,
  logistical: 0.95,
  circadian: 0.35,
  exposure: 0.7,
};

const BASE_CAPACITY_MIN = 480;

/* ---------------------------------- facts ----------------------------------- */

/**
 * What we know about a stop beyond its own clock. Tiered by where it comes from,
 * because provenance decides how loudly a fact may speak:
 *
 * - `measured`   — arithmetic over the trip itself. Always available, offline.
 * - `structured` — OSM surface and smoothness tags, elevation, place details.
 *                  Authoritative, cached hard, barely changes.
 * - `inferred`   — read out of review text by a model. May lower a ranking or
 *                  add a caveat; may never block and is never phrased as certain.
 */
export type FactSource = "measured" | "structured" | "inferred";

export interface StopFacts {
  walkKm?: number;
  ascentM?: number;
  steps?: number;
  standingMin?: number;
  crowded?: boolean;
  outdoor?: boolean;
  mode?: Mode;
  /** When the place is actually worth seeing, where that is a property of the place. */
  bestTime?: "morning" | "afternoon" | "sunset" | "evening" | "any";
  /** A headline sight: the reason someone took the trip. */
  headline?: boolean;
  /** What reviewers consistently say the visit takes. The one review signal worth trusting. */
  reviewedMinutes?: number;
  source?: FactSource;
  note?: string;
}

export type FactBook = Record<string, StopFacts>;

/** Heat, cold or altitude during outdoor hours, as a multiplier on outdoor minutes. */
export interface Conditions {
  /** 1.0 is benign. 1.3 is a 38°C afternoon or 3,500 m of altitude. */
  outdoorFactor: number;
  note: string;
}

export const BENIGN: Conditions = { outdoorFactor: 1, note: "" };

/* ---------------------------------- party ----------------------------------- */

export interface Party {
  adults: number;
  /** Ages, so a five-year-old and a fifteen-year-old are not the same constraint. */
  childAges: number[];
  seniors: number;
  pace: "packed" | "steady" | "slow";
}

export const SOLO_STEADY: Party = { adults: 1, childAges: [], seniors: 0, pace: "steady" };

/**
 * A party moves at the pace of its most limited member, so capacity is the
 * minimum across it and never the average. This single choice carries more of
 * the real-world signal than any amount of personal taste.
 */
export function capacityFor(party: Party): { minutes: number; limitedBy: string } {
  const paceFactor = party.pace === "packed" ? 1.25 : party.pace === "slow" ? 0.8 : 1;
  let factor = 1;
  let limitedBy = "an adult travelling at your usual pace";

  for (const age of party.childAges) {
    const childFactor = age <= 4 ? 0.6 : age <= 8 ? 0.72 : age <= 12 ? 0.85 : 1;
    if (childFactor < factor) {
      factor = childFactor;
      limitedBy = `the ${age}-year-old`;
    }
  }
  if (party.seniors > 0 && 0.8 < factor) {
    factor = 0.8;
    limitedBy = "the oldest traveller";
  }
  return { minutes: Math.round(BASE_CAPACITY_MIN * factor * paceFactor), limitedBy };
}

/* ------------------------------- stop effort -------------------------------- */

const absStart = (stop: Stop) => (stop.day - 1) * 1440 + toMin(stop.start);
const absEnd = (stop: Stop) => absStart(stop) + stop.durationMin;

export interface EffortLine {
  currency: Currency;
  amount: number;
  /** A measured quantity, phrased for a human. Never a score. */
  evidence: string;
  source: FactSource;
}

export interface StopEffort {
  stopId: string;
  title: string;
  effort: Effort;
  lines: EffortLine[];
}

function modeOf(stop: Stop, facts: StopFacts): Mode {
  if (facts.mode) return facts.mode;
  if (stop.kind === "flight") return "flight";
  return "car_city";
}

export function stopEffort(
  stop: Stop,
  facts: StopFacts = {},
  conditions: Conditions = BENIGN,
): StopEffort {
  const effort = zeroEffort();
  const lines: EffortLine[] = [];
  const add = (currency: Currency, amount: number, evidence: string, source: FactSource) => {
    if (amount <= 0.5) return;
    effort[currency] += amount;
    lines.push({ currency, amount, evidence, source });
  };

  if (stop.kind === "flight" || stop.kind === "transfer") {
    const mode = modeOf(stop, facts);
    const factor = MODE_FACTOR[mode];
    add(
      "transit",
      stop.durationMin * factor,
      `${stop.durationMin} min of ${MODE_LABEL[mode]}`,
      facts.mode ? (facts.source ?? "structured") : "measured",
    );
    if (stop.kind === "flight") {
      add("logistical", AIRPORT_COST, "an airport either end", "measured");
    }
  } else if (stop.kind === "stay") {
    add("logistical", CHECK_COST, "bags, desk and keys", "measured");
  } else {
    // Time on your feet at a sight is the baseline against which everything else
    // is denominated, so it costs its own minutes and no more.
    add("physical", stop.durationMin * 0.6, `${stop.durationMin} min at the sight`, "measured");
  }

  if (facts.walkKm) {
    add(
      "physical",
      facts.walkKm * WALK_MIN_PER_KM * MODE_FACTOR.walk,
      `${facts.walkKm.toFixed(1)} km on foot`,
      facts.source ?? "structured",
    );
  }
  if (facts.ascentM) {
    add(
      "physical",
      facts.ascentM * ASCENT_COST_PER_M,
      `${facts.ascentM} m of climbing`,
      facts.source ?? "structured",
    );
  }
  if (facts.steps) {
    add("physical", facts.steps * STEP_COST, `${facts.steps} steps`, facts.source ?? "structured");
  }
  if (facts.standingMin) {
    add(
      "physical",
      facts.standingMin * STANDING_FACTOR,
      `${facts.standingMin} min standing`,
      facts.source ?? "inferred",
    );
  }
  if (facts.crowded) {
    add(
      "physical",
      stop.durationMin * CROWD_SURCHARGE,
      "crowded at this hour",
      facts.source ?? "inferred",
    );
  }
  if (facts.outdoor && conditions.outdoorFactor > 1) {
    add(
      "exposure",
      stop.durationMin * (conditions.outdoorFactor - 1),
      conditions.note || "outdoors in demanding weather",
      "structured",
    );
  }

  const localStart = toMin(stop.start);
  const localEnd = localStart + stop.durationMin;
  if (localStart < EARLY_HOUR) {
    add(
      "circadian",
      (EARLY_HOUR - localStart) * EARLY_FACTOR,
      `a ${stop.start} start`,
      "measured",
    );
  }
  if (localEnd > LATE_HOUR) {
    add("circadian", (localEnd - LATE_HOUR) * LATE_FACTOR, `running to ${fmtMin(localEnd)}`, "measured");
  }

  return { stopId: stop.id, title: stop.title, effort, lines };
}

/* -------------------------------- day effort -------------------------------- */

export interface DayEffort {
  day: number;
  effort: Effort;
  total: number;
  lines: EffortLine[];
  walkKm: number;
  transitMin: number;
  firstStart: string;
  lastEnd: string;
  stops: StopEffort[];
}

export function dayEffort(
  stops: Stop[],
  day: number,
  facts: FactBook = {},
  conditions: Conditions = BENIGN,
): DayEffort {
  const ordered = sortStops(stops.filter((stop) => stop.day === day));
  let effort = zeroEffort();
  const lines: EffortLine[] = [];
  const perStop: StopEffort[] = [];
  let walkKm = 0;
  let transitMin = 0;

  for (const stop of ordered) {
    const stopFacts = facts[stop.id] ?? {};
    const measured = stopEffort(stop, stopFacts, conditions);
    effort = addEffort(effort, measured.effort);
    lines.push(...measured.lines);
    perStop.push(measured);
    walkKm += stopFacts.walkKm ?? 0;
    if (stop.kind === "flight" || stop.kind === "transfer") transitMin += stop.durationMin;
  }

  // The hops between stops are real travel that no stop record owns.
  const located = ordered.filter((stop) => stop.kind !== "flight" && stop.kind !== "transfer");
  for (let i = 0; i < located.length - 1; i += 1) {
    const minutes = travelMin(located[i], located[i + 1]);
    effort.transit += minutes * MODE_FACTOR.car_city;
    effort.logistical += TRANSITION_COST;
    transitMin += minutes;
  }
  if (located.length > 1) {
    lines.push({
      currency: "transit",
      amount: transitMin * MODE_FACTOR.car_city,
      evidence: `${located.length - 1} hops between stops`,
      source: "measured",
    });
  }

  return {
    day,
    effort,
    total: totalEffort(effort),
    lines,
    walkKm,
    transitMin,
    firstStart: ordered.length ? ordered[0].start : "—",
    lastEnd: ordered.length ? fmtMin(toMin(ordered[ordered.length - 1].start) + ordered[ordered.length - 1].durationMin) : "—",
    stops: perStop,
  };
}

/* ------------------------------ the reserve --------------------------------- */

/**
 * Fatigue is a stock, not a flow.
 *
 * Three consecutive heavy days are worse than one brutal day with a light one
 * either side, and per-day scoring rates the first arrangement better. The debt
 * carried out of a day is composed of whatever made that day heavy, and each
 * part fades at its own rate overnight: legs slowly, an early alarm barely at
 * all, yesterday's four transfers almost completely.
 */
export interface ReserveDay {
  day: number;
  spend: number;
  carriedIn: Effort;
  carriedOut: Effort;
  /** What the day actually feels like: its own cost plus what it inherited. */
  load: number;
  capacity: number;
  overCapacity: boolean;
  /** The currency carrying the most inherited debt into this day. */
  dominantDebt: Currency | null;
}

export function reserveCurve(
  stops: Stop[],
  party: Party = SOLO_STEADY,
  facts: FactBook = {},
  conditions: Conditions = BENIGN,
): ReserveDay[] {
  const capacity = capacityFor(party).minutes;
  const days = [...new Set(stops.map((stop) => stop.day))].sort((a, b) => a - b);
  let carried = zeroEffort();
  const out: ReserveDay[] = [];

  for (const day of days) {
    const spend = dayEffort(stops, day, facts, conditions);
    const carriedIn = carried;
    const load = spend.total + totalEffort(carriedIn);
    const strain = Math.max(0, load - capacity);

    const carriedOut = zeroEffort();
    const spendTotal = spend.total || 1;
    for (const currency of CURRENCIES) {
      const share = (spend.effort[currency] + carriedIn[currency]) / (spendTotal + totalEffort(carriedIn) || 1);
      carriedOut[currency] = strain * share * (1 - RECOVERY[currency]);
    }

    let dominantDebt: Currency | null = null;
    for (const currency of CURRENCIES) {
      if (carriedIn[currency] > 1 && (!dominantDebt || carriedIn[currency] > carriedIn[dominantDebt])) {
        dominantDebt = currency;
      }
    }

    out.push({
      day,
      spend: spend.total,
      carriedIn,
      carriedOut,
      load,
      capacity,
      overCapacity: load > capacity,
      dominantDebt,
    });
    carried = carriedOut;
  }
  return out;
}

/* ------------------------------ the one warning ----------------------------- */

/**
 * The reserve informs every ranking, always and invisibly. It is allowed to
 * speak at most once per trip, at the single worst point, and only when the debt
 * is large and sustained. A per-day drumbeat would turn every long trip into a
 * scolding, which is the friction this layer exists to avoid.
 */
export interface PacingVerdict {
  day: number;
  statement: string;
  remedyDay: number;
  remedy: string;
}

export function pacingVerdict(
  stops: Stop[],
  party: Party = SOLO_STEADY,
  facts: FactBook = {},
  conditions: Conditions = BENIGN,
): PacingVerdict | null {
  const curve = reserveCurve(stops, party, facts, conditions);
  const capacity = capacityFor(party).minutes;
  const limitedBy = capacityFor(party).limitedBy;

  for (let i = 2; i < curve.length; i += 1) {
    const today = curve[i];
    const sustained = curve[i - 1].overCapacity && curve[i - 2].overCapacity;
    if (!sustained || totalEffort(today.carriedIn) < capacity * 0.25) continue;

    const cause = today.dominantDebt ?? "physical";
    const heaviest = curve[i - 2].load >= curve[i - 1].load ? curve[i - 2] : curve[i - 1];
    return {
      day: today.day,
      statement:
        `Days ${curve[i - 2].day} and ${curve[i - 1].day} are both fuller than your usual day, so day ${today.day} ` +
        `starts tired rather than fresh — mostly from being ${CURRENCY_LABEL[cause]}, and day ${today.day} is where ` +
        `it catches up with ${limitedBy}.`,
      remedyDay: heaviest.day,
      remedy:
        `The fix is on day ${heaviest.day}, not day ${today.day}: moving one thing off the heavier day earlier ` +
        `leaves day ${today.day} intact.`,
    };
  }
  return null;
}

/* --------------------------- coherence, not fatigue -------------------------- */

/**
 * A day can be light and still look wrong to a human. These are the cheap,
 * high-signal checks, and like everything else here they annotate rather than
 * refuse.
 */
export interface CoherenceFlag {
  code: string;
  day: number;
  title: string;
  detail: string;
  source: FactSource;
}

const inWindow = (min: number, from: number, to: number) => min >= from && min <= to;

/** The shortest round trip through a day's stops, for comparison with the planned order. */
function optimalRouteKm(stops: Stop[]) {
  if (stops.length < 3) return routeKm(stops);
  const remaining = stops.slice(1);
  let current = stops[0];
  let total = 0;
  while (remaining.length) {
    let bestIndex = 0;
    let best = Infinity;
    remaining.forEach((candidate, index) => {
      const d = distanceKm(current, candidate);
      if (d < best) {
        best = d;
        bestIndex = index;
      }
    });
    total += best;
    current = remaining[bestIndex];
    remaining.splice(bestIndex, 1);
  }
  return total;
}

function routeKm(stops: Stop[]) {
  let total = 0;
  for (let i = 0; i < stops.length - 1; i += 1) total += distanceKm(stops[i], stops[i + 1]);
  return total;
}

export function coherenceFlags(stops: Stop[], facts: FactBook = {}): CoherenceFlag[] {
  const out: CoherenceFlag[] = [];
  const days = [...new Set(stops.map((stop) => stop.day))].sort((a, b) => a - b);

  for (const day of days) {
    const ordered = sortStops(stops.filter((stop) => stop.day === day));
    if (!ordered.length) continue;

    for (const stop of ordered) {
      const best = facts[stop.id]?.bestTime;
      if (!best || best === "any") continue;
      const start = toMin(stop.start);
      const fits =
        best === "morning" ? inWindow(start, 6 * 60, 11 * 60)
        : best === "afternoon" ? inWindow(start, 12 * 60, 16 * 60)
        : best === "sunset" ? inWindow(start + stop.durationMin, 16 * 60 + 30, 19 * 60 + 30)
        : inWindow(start, 18 * 60, 23 * 60);
      if (!fits) {
        out.push({
          code: "C1",
          day,
          title: `${stop.title} is scheduled away from its hour`,
          detail: `It is at its best ${best === "sunset" ? "around sunset" : `in the ${best}`}; this visit is ${stop.start}–${fmtMin(start + stop.durationMin)}.`,
          source: facts[stop.id]?.source ?? "inferred",
        });
      }
    }

    const hasMidday = ordered.some(
      (stop) => stop.kind === "meal" && inWindow(toMin(stop.start), 11 * 60 + 30, 15 * 60),
    );
    const spansMidday =
      toMin(ordered[0].start) < 12 * 60 + 30 &&
      toMin(ordered[ordered.length - 1].start) + ordered[ordered.length - 1].durationMin > 14 * 60;
    let middayGap = 0;
    for (let i = 0; i < ordered.length - 1; i += 1) {
      const gapFrom = absEnd(ordered[i]);
      const gapTo = absStart(ordered[i + 1]);
      const localFrom = gapFrom - (day - 1) * 1440;
      if (localFrom > 11 * 60 && localFrom < 15 * 60) middayGap = Math.max(middayGap, gapTo - gapFrom);
    }
    if (spansMidday && !hasMidday && middayGap < 45) {
      out.push({
        code: "C2",
        day,
        title: `Day ${day} runs through lunch with nowhere to stop`,
        detail: `The day is continuous from ${ordered[0].start} with no meal and no gap longer than ${middayGap} minutes between 11:00 and 15:00.`,
        source: "measured",
      });
    }

    const located = ordered.filter((stop) => stop.kind !== "flight" && stop.kind !== "transfer");
    if (located.length >= 3) {
      const planned = routeKm(located);
      const shortest = optimalRouteKm(located);
      if (planned > shortest * 1.6 && planned - shortest > 8) {
        out.push({
          code: "C3",
          day,
          title: `Day ${day} crosses the city and comes back`,
          detail: `The planned order covers ${planned.toFixed(0)} km where the same stops in a better order cover ${shortest.toFixed(0)} km.`,
          source: "measured",
        });
      }
    }

    const next = days[days.indexOf(day) + 1];
    if (next !== undefined) {
      const nextStops = sortStops(stops.filter((stop) => stop.day === next));
      const endsLate = toMin(ordered[ordered.length - 1].start) + ordered[ordered.length - 1].durationMin > 22 * 60;
      const startsEarly = nextStops.length > 0 && toMin(nextStops[0].start) < 8 * 60;
      if (endsLate && startsEarly) {
        out.push({
          code: "C4",
          day: next,
          title: `A late night runs straight into an early start`,
          detail: `Day ${day} ends at ${fmtMin(toMin(ordered[ordered.length - 1].start) + ordered[ordered.length - 1].durationMin)} and day ${next} begins at ${nextStops[0].start}.`,
          source: "measured",
        });
      }
    }
  }

  // The one review-derived signal worth putting in front of the owner. Asking a
  // model how tiring a place is returns "moderate walking" for everything;
  // asking how long people actually stay returns a number we can check against
  // the plan, and being an hour short is a real defect a human would catch.
  for (const stop of stops) {
    const reviewed = facts[stop.id]?.reviewedMinutes;
    if (!reviewed || reviewed <= stop.durationMin * 1.4) continue;
    out.push({
      code: "C6",
      day: stop.day,
      title: `${stop.title} has less time than people usually take`,
      detail: `The visit is booked for ${stop.durationMin} minutes; reviews consistently describe ${reviewed} or more.`,
      source: "inferred",
    });
  }

  const headliners = stops.filter((stop) => facts[stop.id]?.headline);
  const lastDay = days[days.length - 1];
  for (const stop of headliners) {
    if (stop.day === lastDay) {
      out.push({
        code: "C5",
        day: lastDay,
        title: `${stop.title} is on the day you fly home`,
        detail: "The thing worth the trip is sharing a day with a check-out and a departure.",
        source: "inferred",
      });
    }
  }
  for (const day of days) {
    const onDay = headliners.filter((stop) => stop.day === day);
    if (onDay.length > 1) {
      out.push({
        code: "C5",
        day,
        title: `Two headline sights compete on day ${day}`,
        detail: `${onDay.map((stop) => stop.title).join(" and ")} are both on this day; neither gets an unhurried visit.`,
        source: "inferred",
      });
    }
  }

  return out;
}

/* ------------------------------- comparison --------------------------------- */

export interface EffortDelta {
  currency: Currency;
  delta: number;
  sentence: string;
}

/** Ranking is comparative by construction: a lone absolute score means nothing. */
export function compareEffort(left: Effort, right: Effort): EffortDelta[] {
  return CURRENCIES.map((currency) => {
    const delta = right[currency] - left[currency];
    const minutes = Math.abs(Math.round(delta));
    return {
      currency,
      delta,
      sentence:
        minutes < 10
          ? `about the same ${CURRENCY_LABEL[currency]}`
          : `${minutes} min ${delta > 0 ? "more" : "less"} ${CURRENCY_LABEL[currency]}`,
    };
  }).sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));
}

export interface TravelOption {
  id: string;
  label: string;
  mode: Mode;
  minutes: number;
  departs: string;
  price: number;
  /** A berth, so the hours between 23:00 and 07:00 are hours you were going to lose anyway. */
  sleeper?: boolean;
  /** Set when the option removes a hotel night, as an overnight leg does. */
  savesHotelNight?: boolean;
}

export interface RankedOption extends TravelOption {
  effort: Effort;
  total: number;
  /** Minutes of the leg spent asleep in a berth rather than enduring it. */
  sleptMin: number;
  reasons: string[];
}

const SLEEP_FROM = 23 * 60;
const SLEEP_TO = 31 * 60;
const SLEEPING_DISCOUNT = 0.3;

/** Minutes of a leg that fall inside the night, for a berth that can be slept in. */
function sleepingMinutes(departs: string, minutes: number) {
  const from = toMin(departs);
  const to = from + minutes;
  return Math.max(0, Math.min(to, SLEEP_TO) - Math.max(from, SLEEP_FROM));
}

/**
 * Why the overnight train can beat the dawn flight: a mode the traveller finds
 * restful, no 04:30 alarm, and a hotel night that never has to be paid for.
 * Stated preference tilts the comfort factor; it never invents a constraint.
 */
export function rankTravelOptions(
  options: TravelOption[],
  prefs: { prefersRail?: boolean; dislikesEarlyStarts?: boolean } = {},
): RankedOption[] {
  return options
    .map((option) => {
      const effort = zeroEffort();
      const reasons: string[] = [];
      const comfort = MODE_FACTOR[option.mode] * (prefs.prefersRail && option.mode === "train" ? 0.85 : 1);
      const sleptMin = option.sleeper ? sleepingMinutes(option.departs, option.minutes) : 0;
      const awakeMin = option.minutes - sleptMin;
      effort.transit = (awakeMin + sleptMin * SLEEPING_DISCOUNT) * comfort;
      reasons.push(`${Math.floor(option.minutes / 60)}h ${option.minutes % 60}m by ${MODE_LABEL[option.mode]}`);
      if (sleptMin >= 120) reasons.push(`${Math.floor(sleptMin / 60)}h of it in a berth overnight`);

      const departs = toMin(option.departs);
      if (departs < EARLY_HOUR) {
        const penalty = (EARLY_HOUR - departs) * EARLY_FACTOR * (prefs.dislikesEarlyStarts ? 1.5 : 1);
        effort.circadian = penalty;
        reasons.push(`a ${option.departs} departure, so the alarm is earlier still`);
      }
      effort.logistical = option.mode === "flight" ? AIRPORT_COST : TRANSITION_COST;
      if (option.mode === "flight") reasons.push("an airport at either end");
      if (option.savesHotelNight) reasons.push("travels overnight, so it saves a hotel night");

      return { ...option, effort, total: totalEffort(effort), sleptMin, reasons };
    })
    .sort((a, b) => a.total - b.total);
}

/* -------------------------------- phrasing ---------------------------------- */

/**
 * The only functions the product may call to talk about effort. They return
 * measured quantities and comparisons — "11 km on foot, roughly double any other
 * day" — because a quantity is checkable and a composite is an opinion wearing a
 * fact's clothes.
 */
export function describeDay(curve: ReserveDay[], day: number, effort: DayEffort): string {
  const row = curve.find((entry) => entry.day === day);
  const parts: string[] = [];
  if (effort.walkKm >= 1) parts.push(`${effort.walkKm.toFixed(1)} km on foot`);
  if (effort.transitMin >= 45) parts.push(`${Math.round(effort.transitMin / 60)}h in transit`);
  if (toMin(effort.firstStart) < EARLY_HOUR) parts.push(`a ${effort.firstStart} start`);
  if (!parts.length) return `Day ${day} is an easy one.`;
  const heaviest = curve.reduce((a, b) => (b.load > a.load ? b : a));
  const tail = row && row.day === heaviest.day ? " — the fullest day of the trip" : "";
  return `Day ${day}: ${parts.join(", ")}${tail}.`;
}

export function describeChoice(ranked: RankedOption[]): string {
  if (ranked.length < 2) return "";
  const [best, next] = ranked;
  const deltas = compareEffort(best.effort, next.effort).filter((entry) => Math.abs(entry.delta) >= 10);
  const priceGap = next.price - best.price;
  const money =
    Math.abs(priceGap) < 200
      ? ""
      : ` It costs ₹${Math.abs(priceGap).toLocaleString("en-IN")} ${priceGap > 0 ? "less" : "more"}.`;
  const cost = deltas.length ? deltas.slice(0, 2).map((entry) => entry.sentence).join(" and ") : "much the same effort";
  // Say the awkward part first. A recommendation that hides the longer journey
  // is the kind of confident nudge that costs trust the one time it is wrong.
  const clockGap = Math.round((best.minutes - next.minutes) / 60);
  const clock =
    Math.abs(clockGap) < 1
      ? ""
      : `It takes ${Math.abs(clockGap)} hours ${clockGap > 0 ? "longer" : "less"} end to end. `;
  const night = best.savesHotelNight ? " It also saves a hotel night." : "";
  return `${clock}${best.label} over ${next.label}: ${cost}.${money}${night}`;
}

/** True when the change is worth mentioning at all. Silence is the default. */
export function worthMentioning(before: Effort, after: Effort, capacity: number) {
  return totalEffort(after) - totalEffort(before) > capacity * 0.15;
}
