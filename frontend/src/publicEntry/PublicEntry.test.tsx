import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PublicEntry from "./PublicEntry";
import { demoTrip } from "./demoRun";
import { hasSkippedPublicEntry, markPublicEntrySkipped, shouldShowPublicEntry } from "./publicEntryState";

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

  it("plays the captured run and lands on the best total", () => {
    renderFinished();
    expect(screen.getByText(/plan complete/i)).toBeInTheDocument();
    expect(screen.getAllByText(demoTrip.best).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Day 5 ·/)).not.toHaveLength(0);
  });

  it("re-settles the total when a decision is overruled, and restores it on undo", () => {
    renderFinished();
    fireEvent.click(screen.getByRole("button", { name: /i would rather fly it/i }));
    expect(screen.getAllByText("€3,858").length).toBeGreaterThan(0);
    expect(screen.getAllByText("+€94").length).toBeGreaterThan(0);
    expect(screen.getByText(/re-settled around your change/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /put it back/i }));
    expect(screen.queryByText("€3,858")).not.toBeInTheDocument();
    expect(screen.queryByText(/re-settled around your change/i)).not.toBeInTheDocument();
    expect(screen.getAllByText(demoTrip.best).length).toBeGreaterThan(0);
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
});
