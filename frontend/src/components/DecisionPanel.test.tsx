import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { writeDisplayPreferences } from "../lib/displayPreferences";
import type { Decision, TripView } from "../types";
import DecisionPanel from "./DecisionPanel";

const overrideDecision = vi.fn();
const restoreDecision = vi.fn();

vi.mock("../api", () => ({
  overrideDecision: (...args: unknown[]) => overrideDecision(...args),
  restoreDecision: (...args: unknown[]) => restoreDecision(...args),
}));

const view = { has_trip: true } as unknown as TripView;

function decision(overrides: Partial<Decision> = {}): Decision {
  return {
    id: "dec_transport_lisbon_porto",
    kind: "transport_mode",
    subject: "Lisbon to Porto",
    scope: { day: 2, from_place: "Lisbon", to_place: "Porto" },
    rule: { code: "door_to_door_time", text: "Fastest door to door." },
    state: "agent",
    priced: "full",
    chosen_option_id: "opt_train",
    agent_option_id: "opt_train",
    override: null,
    effect: { total_cost: 1000, delta: 0, currency: "EUR" },
    options: [
      {
        id: "opt_train",
        mode: "train",
        label: "Train",
        price: { amount: 120, currency: "EUR", basis: "per_party" },
        priced: true,
        unpriced_reason: null,
        duration_min: 165,
        door_to_door_min: 285,
      },
      {
        id: "opt_air",
        mode: "flight",
        label: "Flight",
        price: null,
        priced: false,
        unpriced_reason: "no_source",
        duration_min: 60,
        door_to_door_min: 270,
        rejected_because: "Barely faster once you add the airport.",
      },
    ],
    ...overrides,
  };
}

function renderPanel(decisions: Decision[]) {
  const onApplied = vi.fn<(view: TripView, message: string, warnings: string[]) => void>();
  const onStale = vi.fn<(view: TripView | undefined, message: string) => void>();
  const onError = vi.fn<(message: string) => void>();
  render(
    <DecisionPanel
      decisions={decisions}
      updatedAt="2026-05-01T10:00:00"
      baseline={null}
      onApplied={onApplied}
      onStale={onStale}
      onError={onError}
    />,
  );
  return { onApplied, onStale, onError };
}

describe("DecisionPanel", () => {
  beforeEach(() => {
    writeDisplayPreferences({ region: "FR", language: "en", currency: "EUR" });
    overrideDecision.mockReset();
    restoreDecision.mockReset();
  });

  it("shows the rule and why each rejected option lost", () => {
    renderPanel([decision()]);

    expect(screen.getByText("Fastest door to door.")).toBeTruthy();
    expect(screen.getByText("Barely faster once you add the airport.")).toBeTruthy();
  });

  it("never invents a price for an option no source covered", () => {
    renderPanel([decision()]);

    expect(screen.getByText("€120")).toBeTruthy();
    expect(screen.getByText("We have no fare source for this")).toBeTruthy();
  });

  it("shows sourced stay facts without transport language", () => {
    renderPanel([
      decision({
        id: "dec_lodging_lisbon",
        kind: "lodging",
        subject: "Stay in Lisbon",
        rule: {
          code: "verified_stay_total",
          text: "Lowest verified stay total; provider rating and refundability break ties",
        },
        chosen_option_id: "opt_memmo",
        agent_option_id: "opt_memmo",
        options: [
          {
            id: "opt_memmo",
            mode: null,
            label: "Memmo Alfama",
            detail: "River view king",
            price: { amount: 640, currency: "EUR", basis: "per_party" },
            priced: true,
            unpriced_reason: null,
            lodging: {
              room_name: "River view king",
              board_name: "Breakfast",
              rating: 4.7,
              refundable: true,
            },
          },
        ],
      }),
    ]);

    expect(screen.getByText(/4.7 provider rating/)).toBeTruthy();
    expect(screen.getByText(/Refundable/)).toBeTruthy();
    expect(screen.queryByText(/door to door/)).toBeNull();
  });

  it("applies an overrule through the state owner with the trip revision", async () => {
    overrideDecision.mockResolvedValue({
      ok: true,
      message: "Switched to Flight. €166 more.",
      view,
      warnings: [],
    });
    const { onApplied } = renderPanel([decision()]);

    fireEvent.click(screen.getByRole("button", { name: "Take this" }));

    await waitFor(() => expect(onApplied).toHaveBeenCalled());
    expect(overrideDecision).toHaveBeenCalledWith(
      "dec_transport_lisbon_porto",
      "opt_air",
      "2026-05-01T10:00:00",
    );
    expect(onApplied.mock.calls[0][0]).toBe(view);
  });

  it("offers the original back once the traveller has overruled it", async () => {
    restoreDecision.mockResolvedValue({ ok: true, message: "Restored Train.", view, warnings: [] });
    const overruled = decision({
      state: "overruled",
      chosen_option_id: "opt_air",
      override: {
        option_id: "opt_air",
        at: "2026-05-02T09:00:00",
        previous_option_id: "opt_train",
        effect: { total_cost: 1166, delta: 166, currency: "EUR" },
        warnings: [],
      },
    });
    const { onApplied } = renderPanel([overruled]);

    expect(screen.getByText("You chose this.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Use the original/ }));

    await waitFor(() => expect(onApplied).toHaveBeenCalled());
    expect(restoreDecision).toHaveBeenCalledWith(
      "dec_transport_lisbon_porto",
      "2026-05-01T10:00:00",
    );
  });

  it("surfaces the casualty of an overrule instead of hiding it", () => {
    renderPanel([
      decision({
        state: "overruled",
        chosen_option_id: "opt_air",
        override: {
          option_id: "opt_air",
          at: "2026-05-02T09:00:00",
          previous_option_id: "opt_train",
          effect: { total_cost: 1166, delta: 166, currency: "EUR" },
          warnings: ["Livraria Lello now starts after it closes."],
        },
      }),
    ]);

    expect(screen.getByText("Livraria Lello now starts after it closes.")).toBeTruthy();
  });

  it("hands a stale write back to the caller rather than reporting an error", async () => {
    overrideDecision.mockResolvedValue({
      ok: false,
      stale: true,
      message: "This trip changed somewhere else. Reloaded it for you.",
      view,
    });
    const { onStale, onError } = renderPanel([decision()]);

    fireEvent.click(screen.getByRole("button", { name: "Take this" }));

    await waitFor(() => expect(onStale).toHaveBeenCalled());
    expect(onError).not.toHaveBeenCalled();
  });

  it("renders nothing for a trip planned before comparisons were recorded", () => {
    const { container } = render(
      <DecisionPanel
        decisions={[]}
        updatedAt={null}
        baseline={null}
        onApplied={vi.fn()}
        onStale={vi.fn()}
        onError={vi.fn()}
      />,
    );

    expect(container.innerHTML).toBe("");
  });

  it("says when each price was last checked and flags one that has aged out", () => {
    render(
      <DecisionPanel
        decisions={[]}
        updatedAt={null}
        baseline={null}
        provenance={[
          {
            kind: "flights",
            provider: "Duffel",
            checked_at: "2026-05-04T09:00:00",
            expires_at: "2026-05-04T09:30:00",
            current: true,
            text: "Flights priced from Duffel on 04 May 09:00.",
          },
          {
            kind: "lodging",
            provider: "LiteAPI",
            checked_at: "2026-05-01T09:00:00",
            expires_at: "2026-05-01T21:00:00",
            current: false,
            text: "Stays last priced from LiteAPI on 01 May 09:00 — may have changed.",
          },
        ]}
        onApplied={vi.fn()}
        onStale={vi.fn()}
        onError={vi.fn()}
      />,
    );

    expect(screen.getByText("Flights priced from Duffel on 04 May 09:00.")).toBeTruthy();
    const stale = screen.getByText(
      "Stays last priced from LiteAPI on 01 May 09:00 — may have changed.",
    );
    expect(stale.className).toContain("text-amber-700");
  });
});
