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
  recordId: string | null;
};

export function debugToolsEnabled(): boolean {
  return import.meta.env.VITE_DEBUG_TOOLS === "1";
}

export function readInspectRequest(search: string): InspectRequest | null {
  const params = new URLSearchParams(search);
  const userId = (params.get("inspect") || "").trim();
  if (!userId) return null;
  return {
    userId,
    tripId: (params.get("trip") || "").trim() || null,
    recordId: (params.get("record") || "").trim() || null,
  };
}

/** Adopt the inspected identity. Returns null when nothing was asked for. */
export function beginInspection(search: string): InspectRequest | null {
  if (!debugToolsEnabled()) return null;
  const request = readInspectRequest(search);
  if (!request) return null;

  // The restore key doubles as the "currently inspecting" flag, so it has to be
  // written even when there is nothing to come back to. A Google session lives
  // in a cookie and is only mirrored into localStorage after the first render,
  // long after this runs, so the previous identity is often simply absent.
  if (localStorage.getItem(RESTORE_KEY) === null) {
    localStorage.setItem(RESTORE_KEY, localStorage.getItem(USER_KEY) ?? "");
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
  // An empty sentinel means there was no identity before; leaving the inspected
  // one behind would silently make it the owner's own.
  if (previous) localStorage.setItem(USER_KEY, previous);
  else localStorage.removeItem(USER_KEY);
  localStorage.removeItem(RESTORE_KEY);
  localStorage.removeItem(GUEST_KEY);
}

/** Take an editable copy of the inspected trip, owned by whoever is signed in. */
export async function forkInspectedTrip(): Promise<string> {
  const { apiFetch, BASE } = await import("../auth/authSession");
  const view = await (await apiFetch(`${BASE}/trip/view`)).json();
  const response = await apiFetch(`${BASE}/trip/fork`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      trip_id: view?.trip_id ?? "",
      owner_id: localStorage.getItem(RESTORE_KEY) || "",
    }),
  });
  if (!response.ok) throw new Error(await response.text());
  const forked = await response.json();
  // Leave inspection first, so the copy opens as the owner's own trip.
  endInspection();
  return forked.trip_id as string;
}
