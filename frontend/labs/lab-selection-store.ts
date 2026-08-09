import { execFileSync } from "node:child_process";
import { copyFile, mkdir, open, readFile, rename, unlink, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

export interface ImplementationRecord {
  version: number;
  handoffVersion?: number;
  selection: string;
  selectionLabel: string;
  comment: string;
  summary?: string;
  recordedAt: string;
}

export interface HandoffRecord {
  version: number;
  selection: string;
  selectionLabel: string;
  comment: string;
  disposition: "ready" | "implemented-review" | "parked" | "completed" | "discarded";
  summary?: string;
  recordedAt: string;
}

export interface LabSelection {
  labId: string;
  labTitle: string;
  selection: string;
  selectionLabel: string;
  comment: string;
  disposition?: "ready" | "implemented-review" | "parked" | "completed" | "discarded";
  handoffs?: HandoffRecord[];
  implementationSummary?: string;
  implementation?: Omit<ImplementationRecord, "version">;
  implementations?: ImplementationRecord[];
  stateChangedAt?: string;
  updatedAt: string;
}

export type LabSelections = Record<string, LabSelection>;

const localDataRoot = process.env.LOCALAPPDATA
  || resolve(process.env.USERPROFILE || process.env.HOME || ".", ".tripplanner");
export const feedbackPath = resolve(localDataRoot, "Tripplanner", "ux-labs", "selections.json");
export const backupPath = resolve(localDataRoot, "Tripplanner", "ux-labs", "selections.previous.json");
export const canonicalPath = resolve(__dirname, "../../docs/ux-experiments/LAB_SELECTIONS.json");
const lockPath = `${feedbackPath}.lock`;

export async function withSelectionStoreLock<T>(operation: () => Promise<T>): Promise<T> {
  await mkdir(dirname(feedbackPath), { recursive: true });
  const deadline = Date.now() + 10_000;
  while (true) {
    try {
      const lock = await open(lockPath, "wx");
      try {
        await lock.writeFile(JSON.stringify({ pid: process.pid, acquiredAt: new Date().toISOString() }));
        return await operation();
      } finally {
        await lock.close();
        await unlink(lockPath).catch(() => undefined);
      }
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
      const snapshot = await readFile(lockPath, "utf8").catch(() => "");
      try {
        const owner = JSON.parse(snapshot) as { pid?: number; acquiredAt?: string };
        const age = owner.acquiredAt ? Date.now() - Date.parse(owner.acquiredAt) : 0;
        let ownerAlive = true;
        if (owner.pid && age > 1_000) {
          try {
            process.kill(owner.pid, 0);
          } catch {
            ownerAlive = false;
          }
        }
        if (!ownerAlive && snapshot === await readFile(lockPath, "utf8").catch(() => "")) {
          await unlink(lockPath).catch(() => undefined);
          continue;
        }
      } catch {
        // An empty or malformed lock may still belong to a writer acquiring it now.
      }
      if (Date.now() >= deadline) throw new Error(`Timed out waiting for Lab selection lock: ${lockPath}`);
      await new Promise((resolveDelay) => setTimeout(resolveDelay, 50));
    }
  }
}

function canonicalLegacyPath(): string {
  try {
    const commonGitDir = execFileSync(
      "git",
      ["rev-parse", "--path-format=absolute", "--git-common-dir"],
      { cwd: __dirname, encoding: "utf8", windowsHide: true },
    ).trim();
    return resolve(dirname(commonGitDir), "docs", "ux-experiments", "LAB_SELECTIONS.local.json");
  } catch {
    return resolve(__dirname, "../../docs/ux-experiments/LAB_SELECTIONS.local.json");
  }
}

async function readJson(path: string): Promise<LabSelections | null> {
  try {
    return JSON.parse(await readFile(path, "utf8")) as LabSelections;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw error;
  }
}

export function migrateLegacyHandoffs(selections: LabSelections): boolean {
  let migrated = false;
  for (const selection of Object.values(selections)) {
    if (!selection.handoffs?.length && selection.selection) {
      selection.handoffs = [{
        version: 1,
        selection: selection.selection,
        selectionLabel: selection.selectionLabel,
        comment: selection.comment,
        disposition: selection.disposition || "ready",
        recordedAt: selection.updatedAt,
      }];
      migrated = true;
    }
    if (selection.handoffs?.length) {
      if (selection.implementation && !selection.implementation.handoffVersion) {
        selection.implementation.handoffVersion = selection.handoffs[0].version;
        migrated = true;
      }
      for (const implementation of selection.implementations || []) {
        if (!implementation.handoffVersion) {
          implementation.handoffVersion = selection.handoffs[0].version;
          migrated = true;
        }
      }
      if (selection.implementation && !selection.implementations?.length) {
        selection.implementations = [{ ...selection.implementation, version: 1 }];
        migrated = true;
      }
    }
  }
  return migrated;
}

function handoffIdentity(record: HandoffRecord): string {
  return JSON.stringify([record.recordedAt, record.selection, record.disposition, record.comment]);
}

function implementationIdentity(record: ImplementationRecord): string {
  return JSON.stringify([record.recordedAt, record.selection, record.summary]);
}

export function mergeSelections(
  canonical: LabSelections | null,
  local: LabSelections | null,
): LabSelections {
  const merged = { ...(canonical || {}) };
  for (const [labId, selection] of Object.entries(local || {})) {
    const existing = merged[labId];
    if (!existing) {
      merged[labId] = selection;
      continue;
    }
    const latest = selection.updatedAt > existing.updatedAt ? selection : existing;
    const handoffs = [...(existing.handoffs || []), ...(selection.handoffs || [])]
      .filter((record, index, records) => records.findIndex((candidate) =>
        handoffIdentity(candidate) === handoffIdentity(record)
      ) === index)
      .sort((first, second) => first.recordedAt.localeCompare(second.recordedAt))
      .map((record, index) => ({ ...record, version: index + 1 }));
    const implementationSources = [
      ...(existing.implementations || []).map((record) => ({ record, handoffs: existing.handoffs || [] })),
      ...(selection.implementations || []).map((record) => ({ record, handoffs: selection.handoffs || [] })),
    ];
    const implementations = implementationSources
      .filter((source, index, sources) => sources.findIndex((candidate) =>
        implementationIdentity(candidate.record) === implementationIdentity(source.record)
      ) === index)
      .sort((first, second) => first.record.recordedAt.localeCompare(second.record.recordedAt))
      .map(({ record, handoffs: sourceHandoffs }, index) => {
        const linkedHandoff = sourceHandoffs.find((handoff) => handoff.version === record.handoffVersion);
        const mergedHandoff = linkedHandoff
          ? handoffs.find((handoff) => handoffIdentity(handoff) === handoffIdentity(linkedHandoff))
          : undefined;
        return {
          ...record,
          version: index + 1,
          handoffVersion: mergedHandoff?.version ?? record.handoffVersion,
        };
      });
    const latestLinkedHandoff = latest.handoffs?.find((handoff) =>
      handoff.version === latest.implementation?.handoffVersion
    );
    const mergedLatestHandoff = latestLinkedHandoff
      ? handoffs.find((handoff) => handoffIdentity(handoff) === handoffIdentity(latestLinkedHandoff))
      : undefined;
    merged[labId] = {
      ...latest,
      handoffs: handoffs.length ? handoffs : latest.handoffs,
      implementations: implementations.length ? implementations : latest.implementations,
      implementation: latest.implementation ? {
        ...latest.implementation,
        handoffVersion: mergedLatestHandoff?.version ?? latest.implementation.handoffVersion,
      } : undefined,
    };
  }
  return merged;
}

export async function readSelections(): Promise<LabSelections> {
  const canonical = await readJson(canonicalPath);
  const stored = await readJson(feedbackPath) || await readJson(canonicalLegacyPath());
  const canonicalSnapshot = JSON.stringify(canonical || {});
  const storedSnapshot = JSON.stringify(stored || {});
  const selections = mergeSelections(canonical, stored);
  const migrated = migrateLegacyHandoffs(selections);
  const mergedSnapshot = JSON.stringify(selections);
  if (migrated || canonicalSnapshot !== mergedSnapshot || storedSnapshot !== mergedSnapshot) {
    await writeSelections(selections);
  }
  return selections;
}

export async function writeSelections(selections: LabSelections): Promise<void> {
  await mkdir(dirname(canonicalPath), { recursive: true });
  await mkdir(dirname(feedbackPath), { recursive: true });
  const contents = `${JSON.stringify(selections, null, 2)}\n`;
  const canonicalTemporaryPath = `${canonicalPath}.${process.pid}.tmp`;
  const localTemporaryPath = `${feedbackPath}.${process.pid}.tmp`;
  await writeFile(canonicalTemporaryPath, contents, "utf8");
  await writeFile(localTemporaryPath, contents, "utf8");
  try {
    await copyFile(feedbackPath, backupPath);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
  }
  await rename(canonicalTemporaryPath, canonicalPath);
  await rename(localTemporaryPath, feedbackPath);
}