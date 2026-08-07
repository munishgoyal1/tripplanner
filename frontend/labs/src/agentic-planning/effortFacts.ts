/**
 * What the engine knows about this trip's stops beyond their own clock.
 *
 * In production these fields fill from three tiers, and the tier decides how
 * loudly the fact may speak:
 *
 *   Tier 0 · measured    minutes, distances, opening hours, party. Free, offline,
 *                        always available, and on its own enough for a verdict.
 *   Tier 1 · structured  OSM `surface`, `smoothness`, `highway=track`, step
 *                        counts, elevation, place details. Cached hard; a road's
 *                        surface changes once a decade.
 *   Tier 2 · inferred    read out of review text, only for places already in the
 *                        plan and only when tiers 0 and 1 left the answer
 *                        ambiguous. Cached with a checked-on date.
 *
 * The guard degrades to less insightful, never to wrong and never to blocked.
 */

import type { Conditions, FactBook, TravelOption } from "./effortModel";

export const indoreFacts: FactBook = {
  rajwada: {
    walkKm: 0.9,
    steps: 60,
    crowded: true,
    headline: true,
    source: "structured",
    note: "Four floors, stairs only, busy from late morning.",
  },
  sarafa: {
    standingMin: 90,
    crowded: true,
    outdoor: true,
    bestTime: "evening",
    source: "structured",
    note: "A street market: nowhere to sit, and it does not open until 19:00.",
  },
  lalbagh: { walkKm: 1.4, outdoor: true, source: "structured" },
  kanch: { walkKm: 0.3, source: "structured" },
  annapurna: { walkKm: 0.5, crowded: true, source: "structured" },
  "mandu-out": {
    mode: "car_winding",
    source: "structured",
    note: "The last 30 km climb the ghat in switchbacks; the map's flat kilometres lie about this leg.",
  },
  "mandu-back": { mode: "car_winding", source: "structured" },
  jahaz: {
    walkKm: 2.2,
    ascentM: 40,
    outdoor: true,
    headline: true,
    source: "structured",
  },
  roopmati: {
    walkKm: 1.8,
    ascentM: 90,
    steps: 120,
    outdoor: true,
    bestTime: "sunset",
    source: "structured",
    note: "The pavilion sits above the escarpment; the view it is famous for is the one at dusk.",
  },
  khajrana: { standingMin: 40, crowded: true, source: "structured" },
  museum: {
    walkKm: 0.8,
    reviewedMinutes: 150,
    source: "inferred",
    note: "Reviewers describe two to three hours across the sculpture galleries.",
  },
};

/** A hot, dry November afternoon in Malwa: real, and only relevant outdoors. */
export const novemberMalwa: Conditions = {
  outdoorFactor: 1.15,
  note: "outdoors through the middle of a 33°C day",
};

/**
 * The owner's own example, made checkable: an overnight berth against a dawn
 * flight. The flight wins on wall-clock time and loses on everything else.
 */
export const legOptions: TravelOption[] = [
  {
    id: "flight-dawn",
    label: "The 06:00 flight",
    mode: "flight",
    minutes: 95,
    departs: "06:00",
    price: 6400,
  },
  {
    id: "train-overnight",
    label: "The overnight train",
    mode: "train",
    minutes: 610,
    departs: "21:30",
    price: 2300,
    sleeper: true,
    savesHotelNight: true,
  },
  {
    id: "bus-day",
    label: "The daytime bus",
    mode: "bus",
    minutes: 540,
    departs: "08:00",
    price: 1450,
  },
];

/**
 * The comparison that makes the point in one line: distance is not the currency.
 * Five kilometres of broken track beats thirty of highway, and the arithmetic
 * agrees before anyone is asked to trust a model about it.
 */
export const surfaceExample = [
  { label: "30 km of smooth highway", mode: "car_highway" as const, km: 30, speedKmh: 60 },
  { label: "5 km of jeep track on a trek approach", mode: "car_rough" as const, km: 5, speedKmh: 14 },
];
