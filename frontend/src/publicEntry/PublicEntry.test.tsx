import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PublicEntry from "./PublicEntry";
import { demoDecisions, demoDecisionsForLocale, demoTripForLocale } from "./demoRun";
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
      ["IN", "INR", "Rajasthan heritage circuit"],
      ["CN", "CNY", "China's imperial cities"],
      ["AU", "AUD", "Australia's east coast"],
      ["JP", "JPY", "Japan by rail"],
      ["CA", "CAD", "Canadian Rockies"],
    ] as const;
    for (const [region, currency, title] of samples) {
      const trip = demoTripForLocale(region, currency);
      expect(trip.title).toBe(title);
      const content = JSON.stringify(trip);
      expect(content).not.toMatch(/Lisbon|Porto|Portugal|Principe Real|G\.A Palace/i);
      if (currency === "INR") expect(content).not.toMatch(/€/);
    }
  });

  it("uses a self-contained Rajasthan run for India", () => {
    const content = JSON.stringify({
      trip: demoTripForLocale("IN", "INR"),
      decisions: demoDecisionsForLocale("IN", "INR"),
    });
    expect(content).toMatch(/Amber Fort/);
    expect(content).toMatch(/Mehrangarh Fort/);
    expect(content).toMatch(/Lake Pichola/);
    expect(content).not.toMatch(/Lisbon|Porto|Portugal|Portuguese|Principe Real|G\.A Palace|Bairro Alto|Alfama|Bel[eé]m|Tapabento|Time Out Market|Ribeira|Livraria Lello|Bolh[aã]o|Port wine|Past[eé]is|Zenith|Cervejaria|Lisboa|LHR-LIS|\bLIS\b|\bOPO\b/i);
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
    const decision = demoDecisions[0];
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
    render(<Masthead tone="dark" onSkip={() => {}} accountLabel="Munish" signedIn />);

    expect(screen.getByText("Munish")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Munish profile" })).toBeInTheDocument();
  });
});
