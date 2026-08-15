// Opens an audited trip in the real product UI, under the identity that owns
// it, so a finding from the audit report can actually be looked at.
//
// Corpus trips are stored under synthetic `corpus-<slug>` identities, which the
// local API honours because `resolve_user_id` trusts a claimed id when not
// hosted. Reaching them previously meant hand-editing localStorage.
//
// Inert unless VITE_DEBUG_TOOLS is set at build time. Callers must check
// `debugToolsEnabled()` before importing anything else here.

const USER_KEY = "tripplanner_user_id";
const GUEST_KEY = "tripplanner_guest_session";
const RESTORE_KEY = "tripplanner_inspect_restore";

export type InspectRequest = {
  userId: string;
  tripId: string | null;
};

export function debugToolsEnabled(): boolean {
  return import.meta.env.VITE_DEBUG_TOOLS === "1";
}

export function readInspectRequest(search: string): InspectRequest | null {
  const params = new URLSearchParams(search);
  const userId = (params.get("inspect") || "").trim();
  if (!userId) return null;
  return { userId, tripId: (params.get("trip") || "").trim() || null };
}

/** Adopt the inspected identity. Returns null when nothing was asked for. */
export function beginInspection(search: string): InspectRequest | null {
  if (!debugToolsEnabled()) return null;
  const request = readInspectRequest(search);
  if (!request) return null;

  // Remember the owner's own identity once, so hopping between several
  // inspected trips still returns to the workspace they started from.
  const current = localStorage.getItem(USER_KEY);
  if (current && current !== request.userId && localStorage.getItem(RESTORE_KEY) === null) {
    localStorage.setItem(RESTORE_KEY, current);
  }
  localStorage.setItem(USER_KEY, request.userId);
  localStorage.removeItem(GUEST_KEY);
  return request;
}

export function inspectedUserId(): string | null {
  if (!debugToolsEnabled()) return null;
  return localStorage.getItem(RESTORE_KEY) === null ? null : localStorage.getItem(USER_KEY);
}

export function endInspection(): void {
  const previous = localStorage.getItem(RESTORE_KEY);
  if (previous === null) return;
  localStorage.setItem(USER_KEY, previous);
  localStorage.removeItem(RESTORE_KEY);
  localStorage.removeItem(GUEST_KEY);
}
