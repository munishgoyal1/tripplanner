import { execFileSync } from "node:child_process";
import { copyFile, mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

export interface LabSelection {
  labId: string;
  labTitle: string;
  selection: string;
  selectionLabel: string;
  comment: string;
  disposition?: "ready" | "implemented-review" | "parked" | "completed" | "discarded";
  stateChangedAt?: string;
  updatedAt: string;
}

export type LabSelections = Record<string, LabSelection>;

const localDataRoot = process.env.LOCALAPPDATA || resolve(process.env.USERPROFILE || ".", ".tripplanner");
export const feedbackPath = resolve(localDataRoot, "Tripplanner", "ux-labs", "selections.json");
export const backupPath = resolve(localDataRoot, "Tripplanner", "ux-labs", "selections.previous.json");

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

export async function readSelections(): Promise<LabSelections> {
  const stored = await readJson(feedbackPath);
  if (stored) return stored;

  const legacy = await readJson(canonicalLegacyPath());
  if (!legacy) return {};
  await writeSelections(legacy);
  return legacy;
}

export async function writeSelections(selections: LabSelections): Promise<void> {
  await mkdir(dirname(feedbackPath), { recursive: true });
  const temporaryPath = `${feedbackPath}.${process.pid}.tmp`;
  await writeFile(temporaryPath, `${JSON.stringify(selections, null, 2)}\n`, "utf8");
  try {
    await copyFile(feedbackPath, backupPath);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
  }
  await rename(temporaryPath, feedbackPath);
}