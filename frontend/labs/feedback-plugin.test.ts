import { describe, expect, it } from "vitest";
import { buildHandoffHistory } from "./feedback-plugin";
import { migrateLegacyHandoffs, type LabSelection } from "./lab-selection-store";

const baseSelection: LabSelection = {
  labId: "multi-city-itinerary",
  labTitle: "Transition-day itinerary design",
  selection: "a",
  selectionLabel: "A · Implemented",
  comment: "First exact note",
  disposition: "completed",
  updatedAt: "2026-08-01T00:00:00.000Z",
};

describe("buildHandoffHistory", () => {
  it("migrates a legacy saved choice into version one before appending", () => {
    const history = buildHandoffHistory(baseSelection, {
      ...baseSelection,
      selection: "b",
      selectionLabel: "B · Alternative",
      comment: "Second exact note",
      disposition: "ready",
    }, "2026-08-02T00:00:00.000Z");

    expect(history.map(({ version, selection, comment }) => ({ version, selection, comment }))).toEqual([
      { version: 1, selection: "a", comment: "First exact note" },
      { version: 2, selection: "b", comment: "Second exact note" },
    ]);
  });

  it("records another immutable version when the same handoff is saved again", () => {
    const previous = {
      ...baseSelection,
      handoffs: [{
        version: 1,
        selection: "a",
        selectionLabel: "A · Implemented",
        comment: "First exact note",
        disposition: "ready" as const,
        recordedAt: "2026-08-01T00:00:00.000Z",
      }],
    };
    const history = buildHandoffHistory(previous, previous, "2026-08-02T00:00:00.000Z");

    expect(history).toHaveLength(2);
    expect(history[1]).toMatchObject({ version: 2, selection: "a", comment: "First exact note" });
  });

  it("uses the maximum imported handoff version", () => {
    const previous = {
      ...baseSelection,
      handoffs: [{
        version: 8,
        selection: "a",
        selectionLabel: "A · Implemented",
        comment: "Imported exact note",
        disposition: "ready" as const,
        recordedAt: "2026-08-01T00:00:00.000Z",
      }],
    };

    expect(buildHandoffHistory(previous, previous, "2026-08-02T00:00:00.000Z").at(-1)?.version).toBe(9);
  });
});

describe("migrateLegacyHandoffs", () => {
  it("turns an existing Lab 20 choice into auditable version one", () => {
    const selections = {
      "travel-documents": {
        ...baseSelection,
        labId: "travel-documents",
        selection: "vault",
        selectionLabel: "B · Account vault, trip shows gaps",
        comment: "",
        disposition: "ready" as const,
      },
    };

    expect(migrateLegacyHandoffs(selections)).toBe(true);
    expect(selections["travel-documents"].handoffs).toEqual([{
      version: 1,
      selection: "vault",
      selectionLabel: "B · Account vault, trip shows gaps",
      comment: "",
      disposition: "ready",
      recordedAt: "2026-08-01T00:00:00.000Z",
    }]);
  });

  it("links legacy implementation evidence to migrated handoff version one", () => {
    const selections = {
      "travel-documents": {
        ...baseSelection,
        implementation: {
          selection: "a",
          selectionLabel: "A · Implemented",
          comment: "First exact note",
          recordedAt: "2026-08-01T00:00:00.000Z",
        },
        implementations: [{
          version: 1,
          selection: "a",
          selectionLabel: "A · Implemented",
          comment: "First exact note",
          recordedAt: "2026-08-01T00:00:00.000Z",
        }],
      },
    };

    expect(migrateLegacyHandoffs(selections)).toBe(true);
    expect(selections["travel-documents"].implementation.handoffVersion).toBe(1);
    expect(selections["travel-documents"].implementations[0].handoffVersion).toBe(1);
  });
});
