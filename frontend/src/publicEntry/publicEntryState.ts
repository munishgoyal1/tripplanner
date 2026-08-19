export const PUBLIC_ENTRY_PATH = "/welcome";
export const PLANNER_PATH = "/planner";

export function isPublicEntryPath(pathname = window.location.pathname) {
  return pathname.replace(/\/+$/, "") === PUBLIC_ENTRY_PATH;
}

export function isPlannerPath(pathname = window.location.pathname) {
  return pathname.replace(/\/+$/, "") === PLANNER_PATH;
}
