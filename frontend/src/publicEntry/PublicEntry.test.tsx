import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PublicEntry from "./PublicEntry";
import { writeDisplayPreferences } from "../lib/displayPreferences";
import {
  demoArtifactForLocale,
  demoDecisionsForLocale,
  demoTripForLocale,
} from "./demoRun";
import { hasSkippedPublicEntry, markPublicEntrySkipped, shouldShowPublicEntry } from "./publicEntryState";
import { Masthead } from "./stagePieces";

// The run animates one receipt at a time; the tests jump to the finished plan instead of
// waiting out the timers.
function renderFinished(props: { onPlan?: (request: string) => void; onSkip?: () => void } = {}) {
  const result = render(
    <PublicEntry onPlan={props.onPlan ?? (() => {})} onSkip={props.onSkip ?? (() => {})} />
  );
  fireEvent.click(screen.getByRole("button", { name: /show the finished plan/i }));
  return result;
}

describe("publicEntryState", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("shows the entry only to anonymous visitors who have not skipped", () => {
    expect(shouldShowPublicEntry(true)).toBe(true);
    expect(shouldShowPublicEntry(false)).toBe(false);
    markPublicEntrySkipped();
    expect(hasSkippedPublicEntry()).toBe(true);
    expect(shouldShowPublicEntry(true)).toBe(false);
  });
});

describe("PublicEntry", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("starts the captured run from reset when reduced motion is preferred", () => {
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      value: vi.fn().mockReturnValue({ matches: true }),
    });

    render(<PublicEntry onPlan={() => {}} onSkip={() => {}} />);

    expect(screen.getByText(/replaying a real run/i)).toBeInTheDocument();
    expect(screen.queryByText(/plan complete/i)).not.toBeInTheDocument();
  });

  it("chooses representative trips for major locale regions", () => {
    const samples = [
      ["IN", "INR", "Mumbai to Jaipur"],
      ["CN", "CNY", "Beijing to Xi'an"],
      ["AU", "AUD", "Sydney to Cairns"],
      ["JP", "JPY", "Tokyo to Kyoto"],
      ["CA", "CAD", "Calgary to Banff"],
    ] as const;
    for (const [region, currency, title] of samples) {
      const trip = demoTripForLocale(region, currency);
      expect(trip.title).toBe(title);
      const content = JSON.stringify(trip);
      expect(content).not.toMatch(/Lisbon|Porto|Portugal|Principe Real|G\.A Palace/i);
      if (currency === "INR") expect(content).not.toMatch(/€/);
    }
  });

  it("lets a changed display country override the previous currency", () => {
    expect(demoArtifactForLocale("FR", "INR").trip.title).toBe("Lisbon to Porto");
  });

  it("switches the visible welcome artifact immediately when display country changes", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("unavailable", { status: 503 }));
    writeDisplayPreferences({ region: "IN", currency: "INR", language: "en" });
    render(<PublicEntry onPlan={() => {}} onSkip={() => {}} />);
    expect(screen.getByText(/agent · Mumbai to Jaipur/i)).toBeInTheDocument();

    writeDisplayPreferences({ region: "FR", currency: "INR", language: "en" });

    await waitFor(() => expect(screen.getByText(/agent · Lisbon to Porto/i)).toBeInTheDocument());
    expect(screen.queryByText(/agent · Mumbai to Jaipur/i)).not.toBeInTheDocument();
  });

  it("selects ten independent standalone artifacts", () => {
    const mappings = [
      ["IN", "INR"], ["US", "USD"], ["CA", "CAD"], ["GB", "GBP"], ["EU", "EUR"],
      ["JP", "JPY"], ["CN", "CNY"], ["AU", "AUD"], ["AE", "AED"], ["BR", "BRL"],
    ] as const;
    const artifacts = mappings.map(([region, currency]) => demoArtifactForLocale(region, currency));

    expect(new Set(artifacts.map((artifact) => artifact.artifact_version))).toHaveLength(10);
    expect(new Set(artifacts.map((artifact) => artifact.trip.id))).toHaveLength(10);
    for (const artifact of artifacts) {
      const { trip } = artifact;
      const dayNumbers = trip.days.map((day) => day.day);
      const hotelMarkers = new Set(trip.hotels.map((hotel) => hotel.marker));
      const entities = new Set(artifact.market.entities);
      expect(trip.days.length).toBeGreaterThanOrEqual(4);
      expect(trip.days.length).toBeLessThanOrEqual(6);
      expect(trip.receipts.length).toBeGreaterThanOrEqual(6);
      expect(dayNumbers).toEqual([...new Set(dayNumbers)].sort((left, right) => left - right));
      expect(new Set(trip.receipts.flatMap((receipt) => receipt.day ?? []))).toEqual(
        new Set(dayNumbers),
      );
      expect(trip.days.every((day) => day.stops.length >= 2)).toBe(true);
      expect(trip.days.every((day) => hotelMarkers.has(day.hotel))).toBe(true);
      expect(trip.days.flatMap((day) => day.stops)
        .filter((stop) => stop.kind === "hotel")
        .every((stop) => Boolean(stop.marker) && hotelMarkers.has(stop.marker!))).toBe(true);
      expect(artifact.market.cities.every((city) => entities.has(city))).toBe(true);
      expect(trip.hotels.every((hotel) => entities.has(hotel.name))).toBe(true);
      expect(trip.days.flatMap((day) => day.stops)
        .filter((stop) => ["hotel", "attraction", "meal"].includes(stop.kind))
        .every((stop) => entities.has(stop.name))).toBe(true);
      expect(trip.hotels.length).toBeGreaterThanOrEqual(1);
      expect(trip.compares.length).toBeGreaterThanOrEqual(1);
      expect(trip.lines.length).toBeGreaterThanOrEqual(2);
      expect(artifact.decisions.length).toBeGreaterThanOrEqual(1);
    }
  });

  it("uses a self-contained Rajasthan run for India", () => {
    const content = JSON.stringify({
      trip: demoTripForLocale("IN", "INR"),
      decisions: demoDecisionsForLocale("IN", "INR"),
    });
    expect(content).toMatch(/Amber Fort/);
    expect(content).toMatch(/Mumbai → Jaipur/);
    expect(content).not.toMatch(/London|\bLHR\b|\bLGW\b/);
    expect(content).not.toMatch(/Lisbon|Porto|Portugal|Portuguese|Principe Real|G\.A Palace|Bairro Alto|Alfama|Bel[eé]m|Tapabento|Time Out Market|Ribeira|Livraria Lello|Bolh[aã]o|Port wine|Past[eé]is|Zenith|Cervejaria|Lisboa|LHR-LIS|\bLIS\b|\bOPO\b/i);
  });

  it("renders bundled data immediately and replaces only a complete remote artifact", async () => {
    const remote = structuredClone(demoArtifactForLocale("US", "USD"));
    remote.artifact_version = "remote-us-v2";
    remote.trip.title = "Remote Pacific run";
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("/public/demo-run")) {
        return new Response(JSON.stringify(remote), { status: 200 });
      }
      return new Response("{}", { status: 500 });
    });

    render(<PublicEntry onPlan={() => {}} onSkip={() => {}} />);
    expect(screen.getByText(/agent · San Francisco to Yosemite/i)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(/agent · Remote Pacific run/i)).toBeInTheDocument());
  });

  it("keeps the bundled artifact when the regional API fails", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("unavailable", { status: 503 }));

    render(<PublicEntry onPlan={() => {}} onSkip={() => {}} />);

    expect(screen.getByText(/agent · San Francisco to Yosemite/i)).toBeInTheDocument();
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(screen.queryByText(/Remote Pacific run/i)).not.toBeInTheDocument();
  });

  it("plays the captured run and lands on the trip total", () => {
    renderFinished();
    const expectedTrip = demoTripForLocale("US", "USD");
    expect(screen.getByText(/plan complete/i)).toBeInTheDocument();
    expect(screen.getAllByText(expectedTrip.total).length).toBeGreaterThan(0);
    const lastDay = expectedTrip.days[expectedTrip.days.length - 1];
    expect(screen.getAllByText(new RegExp(`Day ${lastDay.day} ·`))).not.toHaveLength(0);
  });

  it("shows complete representative beta pricing", () => {
    renderFinished();
    const expectedTrip = demoTripForLocale("US", "USD");

    expect(screen.getAllByText(expectedTrip.total).length).toBeGreaterThan(0);
    expect(screen.queryByText(/€/)).not.toBeInTheDocument();
    expect(screen.getAllByText("AI Tripplanner", { exact: false }).length).toBeGreaterThan(0);
    expect(screen.queryByText(/no live rate|no fare source/i)).not.toBeInTheDocument();
  });

  it("re-settles the plan when a decision is overruled, and restores it on undo", () => {
    const decision = demoDecisionsForLocale("US", "USD")[0];
    const expectedTrip = demoTripForLocale("US", "USD");
    renderFinished();
    fireEvent.click(screen.getByRole("button", { name: decision.overrule }));
    expect(screen.getByText(decision.outcome.headline)).toBeInTheDocument();
    expect(screen.getByText(decision.outcome.warning)).toBeInTheDocument();
    expect(screen.getByText(/re-settled around your change/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /put it back/i }));
    expect(screen.queryByText(decision.outcome.headline)).not.toBeInTheDocument();
    expect(screen.queryByText(/re-settled around your change/i)).not.toBeInTheDocument();
    expect(screen.getAllByText(expectedTrip.total).length).toBeGreaterThan(0);
  });

  it("hands a typed request to the workspace", () => {
    const onPlan = vi.fn();
    renderFinished({ onPlan });
    fireEvent.change(screen.getByLabelText(/where do you want to go/i), {
      target: { value: "  Kyoto in April  " },
    });
    fireEvent.click(screen.getByRole("button", { name: /plan mine/i }));
    expect(onPlan).toHaveBeenCalledWith("Kyoto in April");
  });

  it("does not hand over an empty request", () => {
    const onPlan = vi.fn();
    renderFinished({ onPlan });
    fireEvent.click(screen.getByRole("button", { name: /plan mine/i }));
    expect(onPlan).not.toHaveBeenCalled();
  });

  it("offers a way straight to the app", () => {
    const onSkip = vi.fn();
    renderFinished({ onSkip });
    fireEvent.click(screen.getByRole("button", { name: /skip to the app/i }));
    expect(onSkip).toHaveBeenCalled();
  });

  it("shows the signed-in display name in the masthead", () => {
    const onSkip = vi.fn();
    const onOpenAccount = vi.fn();
    render(<Masthead tone="dark" onSkip={onSkip} onOpenAccount={onOpenAccount} accountLabel="Munish" signedIn />);

    expect(screen.getByText("Munish")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Munish profile" }));
    expect(onSkip).not.toHaveBeenCalled();
    expect(onOpenAccount).toHaveBeenCalledOnce();
  });
});
