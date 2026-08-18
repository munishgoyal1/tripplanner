import { execFileSync } from "node:child_process";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { buildHandoffHistory } from "./feedback-plugin";
import {
  commitSelectionStore,
  mergeSelections,
  migrateLegacyHandoffs,
  type LabSelection,
} from "./lab-selection-store";

const temporaryRepositories: string[] = [];

async function createRepository() {
  const root = await mkdtemp(resolve(tmpdir(), "tripplanner-lab-store-"));
  temporaryRepositories.push(root);
  const storePath = resolve(root, "docs/ux-experiments/LAB_SELECTIONS.json");
  await mkdir(dirname(storePath), { recursive: true });
  await writeFile(storePath, "{}\n", "utf8");
  await writeFile(resolve(root, "unrelated.txt"), "initial\n", "utf8");
  execFileSync("git", ["init", "-q"], { cwd: root });
  execFileSync("git", ["config", "user.name", "Lab Test"], { cwd: root });
  execFileSync("git", ["config", "user.email", "lab-test@example.com"], { cwd: root });
  execFileSync("git", ["config", "commit.gpgsign", "false"], { cwd: root });
  execFileSync("git", ["add", "."], { cwd: root });
  execFileSync("git", ["commit", "-q", "-m", "Initial"], { cwd: root });
  return { root, storePath };
}

afterEach(async () => {
  await Promise.all(temporaryRepositories.splice(0).map((path) => rm(path, { recursive: true, force: true })));
});

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

describe("commitSelectionStore", () => {
  it("commits only the Lab store and leaves unrelated changes untouched", async () => {
    const { root, storePath } = await createRepository();
    await writeFile(storePath, "{\"trip-feedback\": {}}\n", "utf8");
    await writeFile(resolve(root, "unrelated.txt"), "owner work\n", "utf8");

    expect(commitSelectionStore("trip-feedback", storePath, false)).toBe(true);
    expect(execFileSync("git", ["log", "-1", "--pretty=%s"], { cwd: root, encoding: "utf8" }).trim())
      .toBe("Record trip-feedback Lab handoff");
    expect(await readFile(storePath, "utf8")).toBe("{\"trip-feedback\": {}}\n");
    expect(execFileSync("git", ["status", "--porcelain"], { cwd: root, encoding: "utf8" }).trim())
      .toBe("M unrelated.txt");
  });

  it("does not create a commit when the Lab store is unchanged", async () => {
    const { root, storePath } = await createRepository();
    const previousHead = execFileSync("git", ["rev-parse", "HEAD"], { cwd: root, encoding: "utf8" }).trim();

    expect(commitSelectionStore("trip-feedback", storePath, false)).toBe(false);
    expect(execFileSync("git", ["rev-parse", "HEAD"], { cwd: root, encoding: "utf8" }).trim())
      .toBe(previousHead);
  });

  it("reports a push failure after preserving the local Lab commit", async () => {
    const { root, storePath } = await createRepository();
    await writeFile(storePath, "{\"trip-feedback\": {}}\n", "utf8");

    expect(() => commitSelectionStore("trip-feedback", storePath)).toThrow();
    expect(execFileSync("git", ["log", "-1", "--pretty=%s"], { cwd: root, encoding: "utf8" }).trim())
      .toBe("Record trip-feedback Lab handoff");
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

describe("mergeSelections", () => {
  it("loads tracked history when a machine has no local store", () => {
    expect(mergeSelections({ "live-plan": baseSelection }, null)).toEqual({
      "live-plan": baseSelection,
    });
  });

  it("preserves a newer machine-local handoff for the next tracked write", () => {
    const newer = { ...baseSelection, comment: "New Windows handoff", updatedAt: "2026-08-09T01:00:00.000Z" };
    const older = { ...baseSelection, comment: "Tracked handoff", updatedAt: "2026-08-08T01:00:00.000Z" };

    expect(mergeSelections({ "live-plan": older }, { "live-plan": newer })["live-plan"]).toMatchObject(newer);
  });

  it("retains richer older machine-local history while using the newer tracked state", () => {
    const local = {
      ...baseSelection,
      updatedAt: "2026-08-08T01:00:00.000Z",
      handoffs: [{
        version: 7,
        selection: "a",
        selectionLabel: "A · First",
        comment: "Exact devbox note",
        disposition: "ready" as const,
        recordedAt: "2026-08-08T01:00:00.000Z",
      }],
    };
    const canonical = {
      ...baseSelection,
      disposition: "completed" as const,
      updatedAt: "2026-08-09T01:00:00.000Z",
      handoffs: [{
        version: 1,
        selection: "a",
        selectionLabel: "A · First",
        comment: "Completed on the new machine",
        disposition: "completed" as const,
        recordedAt: "2026-08-09T01:00:00.000Z",
      }],
    };

    const merged = mergeSelections({ "live-plan": canonical }, { "live-plan": local })["live-plan"];
    expect(merged.disposition).toBe("completed");
    expect(merged.handoffs?.map(({ version, comment }) => ({ version, comment }))).toEqual([
      { version: 1, comment: "Exact devbox note" },
      { version: 2, comment: "Completed on the new machine" },
    ]);
  });

  it("deduplicates equivalent timestamp precision from different writers", () => {
    const tracked = {
      ...baseSelection,
      handoffs: [{
        version: 1,
        selection: "a",
        selectionLabel: "A · Implemented",
        comment: "Same handoff",
        disposition: "implemented-review" as const,
        recordedAt: "2026-08-09T11:43:12.43017Z",
      }],
      implementations: [{
        version: 1,
        handoffVersion: 1,
        selection: "a",
        selectionLabel: "A · Implemented",
        comment: "Same handoff",
        summary: "Same implementation",
        recordedAt: "2026-08-09T11:43:12.43017Z",
      }],
    };
    const local = {
      ...tracked,
      handoffs: tracked.handoffs.map((record) => ({
        ...record,
        recordedAt: "2026-08-09T11:43:12.4301700Z",
      })),
      implementations: tracked.implementations.map((record) => ({
        ...record,
        recordedAt: "2026-08-09T11:43:12.4301700Z",
      })),
    };

    const merged = mergeSelections({ "live-plan": tracked }, { "live-plan": local })["live-plan"];

    expect(merged.handoffs).toEqual(tracked.handoffs);
    expect(merged.implementations).toEqual(tracked.implementations);
  });

  it("remaps implementation links when an imported handoff changes version", () => {
    const local = {
      ...baseSelection,
      updatedAt: "2026-08-07T01:00:00.000Z",
      handoffs: [{
        version: 1,
        selection: "a",
        selectionLabel: "A · Earlier",
        comment: "Earlier devbox note",
        disposition: "ready" as const,
        recordedAt: "2026-08-07T01:00:00.000Z",
      }],
    };
    const canonical = {
      ...baseSelection,
      updatedAt: "2026-08-09T01:00:00.000Z",
      handoffs: [{
        version: 1,
        selection: "a",
        selectionLabel: "A · Implemented",
        comment: "Tracked implementation handoff",
        disposition: "implemented-review" as const,
        recordedAt: "2026-08-08T01:00:00.000Z",
      }],
      implementations: [{
        version: 1,
        handoffVersion: 1,
        selection: "a",
        selectionLabel: "A · Implemented",
        comment: "Tracked implementation handoff",
        summary: "Implemented",
        recordedAt: "2026-08-08T02:00:00.000Z",
      }],
    };

    const merged = mergeSelections({ "live-plan": canonical }, { "live-plan": local })["live-plan"];
    expect(merged.implementations?.[0].handoffVersion).toBe(2);
  });
});
