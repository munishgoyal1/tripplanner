const SKIP_KEY = "tripplanner_public_entry_skipped";
export const PUBLIC_ENTRY_PATH = "/welcome";
export const PLANNER_PATH = "/planner";

function readFlag() {
  try {
    return window.localStorage.getItem(SKIP_KEY) === "1";
  } catch {
    return false;
  }
}

/** True once the visitor has asked for the workspace, so the entry never blocks a return visit. */
export function hasSkippedPublicEntry() {
  return readFlag();
}

export function markPublicEntrySkipped() {
  try {
    window.localStorage.setItem(SKIP_KEY, "1");
  } catch {
    // A visitor with storage blocked sees the entry again next time; that is better than failing.
  }
}

export function shouldShowPublicEntry(anonymous: boolean) {
  return anonymous && !readFlag();
}

export function isPublicEntryPath(pathname = window.location.pathname) {
  return pathname.replace(/\/+$/, "") === PUBLIC_ENTRY_PATH;
}

export function isPlannerPath(pathname = window.location.pathname) {
  return pathname.replace(/\/+$/, "") === PLANNER_PATH;
}
