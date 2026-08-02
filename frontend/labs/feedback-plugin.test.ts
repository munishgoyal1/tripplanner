import { describe, expect, it } from "vitest";
import { buildImplementationHistory } from "./feedback-plugin";
import type { LabSelection } from "./lab-selection-store";

const baseSelection: LabSelection = {
  labId: "multi-city-itinerary",
  labTitle: "Transition-day itinerary design",
  selection: "a",
  selectionLabel: "A · Implemented",
  comment: "First exact note",
  disposition: "completed",
  updatedAt: "2026-08-01T00:00:00.000Z",
};

describe("buildImplementationHistory", () => {
  it("appends the next implementation version after a reopened Lab", () => {
    const previous = {
      ...baseSelection,
      disposition: "ready" as const,
      implementation: {
        selection: "a",
        selectionLabel: "A · Implemented",
        comment: "First exact note",
        recordedAt: "2026-08-01T00:00:00.000Z",
      },
    };
    const history = buildImplementationHistory(previous, {
      ...previous,
      selection: "b",
      selectionLabel: "B · Alternative",
      comment: "Second exact note",
      disposition: "implemented-review",
    }, "2026-08-02T00:00:00.000Z");

    expect(history.map(({ version, selection, comment }) => ({ version, selection, comment }))).toEqual([
      { version: 1, selection: "a", comment: "First exact note" },
      { version: 2, selection: "b", comment: "Second exact note" },
    ]);
  });

  it("updates the current review version instead of creating a duplicate", () => {
    const previous = {
      ...baseSelection,
      disposition: "implemented-review" as const,
      implementations: [{
        version: 1,
        selection: "a",
        selectionLabel: "A · Implemented",
        comment: "Draft note",
        recordedAt: "2026-08-01T00:00:00.000Z",
      }],
    };
    const history = buildImplementationHistory(previous, {
      ...previous,
      comment: "Corrected exact note",
    }, "2026-08-02T00:00:00.000Z");

    expect(history).toHaveLength(1);
    expect(history[0]).toMatchObject({ version: 1, comment: "Corrected exact note" });
  });
});
