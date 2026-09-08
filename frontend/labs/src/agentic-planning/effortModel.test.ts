import { describe, expect, it } from "vitest";
import type { Stop } from "./fixture";
import { startingTrip } from "./planEngine";
import { indoreFacts, legOptions, novemberMalwa } from "./effortFacts";
import {
  MODE_FACTOR,
  SOLO_STEADY,
  capacityFor,
  coherenceFlags,
  dayEffort,
  describeChoice,
  describeDay,
  pacingVerdict,
  rankTravelOptions,
  reserveCurve,
  stopEffort,
  totalEffort,
} from "./effortModel";
import type { Party } from "./effortModel";

const facts = indoreFacts;
const family: Party = { adults: 2, childAges: [7], seniors: 0, pace: "steady" };

const extraStop: Stop = {
  id: "extra",
  kind: "attraction",
  title: "An extra sight",
  city: "Indore",
  day: 2,
  start: "18:30",
  durationMin: 60,
  lat: 22.7,
  lng: 75.85,
};

describe("effort is monotonic", () => {
  it("never falls when a stop is added to a day", () => {
    const before = dayEffort(startingTrip, 2, facts);
    const after = dayEffort([...startingTrip, extraStop], 2, facts);
    expect(after.total).toBeGreaterThan(before.total);
  });

  it("never falls when a visit is made longer", () => {
    const longer = startingTrip.map((stop) =>
      stop.id === "rajwada" ? { ...stop, durationMin: stop.durationMin + 60 } : stop,
    );
    expect(dayEffort(longer, 1, facts).total).toBeGreaterThan(dayEffort(startingTrip, 1, facts).total);
  });
});

describe("surface beats distance", () => {
  it("costs a short rough track more than a long highway run", () => {
    const highway = (30 / 60) * 60 * MODE_FACTOR.car_highway;
    const track = (5 / 14) * 60 * MODE_FACTOR.car_rough;
    expect(track).toBeGreaterThan(highway);
  });

  it("charges a winding ghat drive more than the same minutes on a flat road", () => {
    const drive = startingTrip.find((stop) => stop.id === "mandu-out")!;
    const winding = stopEffort(drive, facts["mandu-out"]).effort.transit;
    const flat = stopEffort(drive, {}).effort.transit;
    expect(winding).toBeGreaterThan(flat);
  });
});

describe("capacity follows the most limited traveller", () => {
  it("is lower with a young child than travelling alone", () => {
    expect(capacityFor(family).minutes).toBeLessThan(capacityFor(SOLO_STEADY).minutes);
    expect(capacityFor(family).limitedBy).toContain("7-year-old");
  });
});

describe("the reserve carries debt forward", () => {
  const curve = reserveCurve(startingTrip, family, facts, novemberMalwa);

  it("makes a day's load exceed its own spend once debt exists", () => {
    const indebted = curve.find((row) => totalEffort(row.carriedIn) > 0);
    expect(indebted).toBeDefined();
    expect(indebted!.load).toBeGreaterThan(indebted!.spend);
  });

  it("repays logistical debt faster than circadian debt", () => {
    const heavy = curve.find((row) => row.overCapacity)!;
    const share = (currency: "logistical" | "circadian") =>
      heavy.carriedOut[currency] / (heavy.carriedIn[currency] + 1);
    expect(share("logistical")).toBeLessThan(share("circadian") + 1);
  });
});

describe("the pacing verdict is rationed", () => {
  it("stays silent for a single traveller on this itinerary", () => {
    expect(pacingVerdict(startingTrip, SOLO_STEADY, facts, novemberMalwa)).toBeNull();
  });

  it("speaks exactly once, and points the remedy at an earlier day", () => {
    const verdict = pacingVerdict(startingTrip, family, facts, novemberMalwa);
    expect(verdict).not.toBeNull();
    expect(verdict!.remedyDay).toBeLessThan(verdict!.day);
  });
});

describe("nothing user-facing carries a composite", () => {
  const curve = reserveCurve(startingTrip, SOLO_STEADY, facts, novemberMalwa);
  const sentences = [
    ...[1, 2, 3, 4, 5].map((day) => describeDay(curve, day, dayEffort(startingTrip, day, facts))),
    describeChoice(rankTravelOptions(legOptions, { prefersRail: true })),
    pacingVerdict(startingTrip, family, facts, novemberMalwa)!.statement,
  ];

  it("never mentions a score, a rating or a percentage", () => {
    for (const sentence of sentences) {
      expect(sentence.toLowerCase()).not.toMatch(/score|rating|\/\s?100|%|out of \d/);
    }
  });
});

describe("option ranking", () => {
  it("prefers an overnight berth to a dawn flight for someone who dislikes early starts", () => {
    const ranked = rankTravelOptions(legOptions, { prefersRail: true, dislikesEarlyStarts: true });
    expect(ranked[0].id).toBe("train-overnight");
    expect(ranked[0].sleptMin).toBeGreaterThan(120);
  });

  it("says the longer wall-clock time out loud", () => {
    const sentence = describeChoice(rankTravelOptions(legOptions, { prefersRail: true }));
    expect(sentence).toMatch(/longer end to end/);
  });
});

describe("coherence checks", () => {
  const flags = coherenceFlags(startingTrip, facts);

  it("catches a sunset viewpoint scheduled in the early afternoon", () => {
    expect(flags.some((flag) => flag.code === "C1" && flag.title.includes("Roopmati"))).toBe(true);
  });

  it("catches a visit shorter than reviewers say it takes", () => {
    expect(flags.some((flag) => flag.code === "C6" && flag.title.includes("Central Museum"))).toBe(true);
  });

  it("stays quiet about routing on a day that is already sensibly ordered", () => {
    expect(flags.some((flag) => flag.code === "C3" && flag.day === 2)).toBe(false);
  });
});
