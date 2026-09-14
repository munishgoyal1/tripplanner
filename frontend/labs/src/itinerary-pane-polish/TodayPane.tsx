/// <reference types="vite/client" />
// The production pane pulls in the API client, which reads import.meta.env.
import ItineraryPanel from "../../../src/components/ItineraryPanel";
import type { Itinerary, TripVerification } from "../../../src/types";
import type { PlannerState } from "./state";

/**
 * The production pane, unmodified, fed the Lab fixture. Its few API calls are
 * answered in-page so the comparison is the real component rather than a
 * re-drawing of it that could quietly flatter the options.
 */

interface LabApi {
  verification: () => TripVerification;
  setBooked: (day: number, name: string, booked: boolean) => Itinerary;
}

let api: LabApi | null = null;
let installed = false;

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
}

function installLabFetch() {
  if (installed || typeof window === "undefined") return;
  installed = true;
  const original = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    if (!url.includes("/api/") || !api) return original(input, init);
    const body = init?.body ? JSON.parse(String(init.body)) as Record<string, unknown> : {};
    await new Promise((resolve) => window.setTimeout(resolve, 250));
    if (url.includes("/auth/guest/session")) return json({ token: "ux-lab" });
    if (url.includes("/trip/verification/refresh")) {
      return json({ ok: true, stale: false, message: "", checked_at: new Date().toISOString(), checked: 14, total: 14, comparison_available: true, changes: [], failed: [], verification: api.verification() });
    }
    if (url.includes("/trip/verification")) return json(api.verification());
    if (url.includes("/trip/stop/booked")) return json({ itinerary: api.setBooked(Number(body.day), String(body.name), Boolean(body.booked)) });
    if (url.includes("/trip/prices/recheck")) return json({ ok: true, stale: false, message: "Prices rechecked.", rechecked: 2, results: [{ kind: "hotel", provider: "Booking.com", status: "live", delta: 1200, observed_at: new Date().toISOString() }, { kind: "flight", provider: "IndiGo", status: "live", delta: 0, observed_at: new Date().toISOString() }] });
    if (url.includes("/trip/repair")) {
      return json({ ok: true, stale: false, changed: true, message: "", moves: [{ name: "Bagore ki Haveli", from_day: 4, to_day: 3, time: "18:45" }], blocked: [], before: { contradictions: 1, travel_min: 0 }, after: { contradictions: 0, travel_min: 0 } });
    }
    return json({});
  };
}

export function TodayPane({ state }: { state: PlannerState }) {
  installLabFetch();
  api = { verification: () => state.verification, setBooked: state.setBooked };
  const circuitActive = state.circuitDay != null || state.allDays;
  return (
    <ItineraryPanel
      key={state.scenario}
      filters={state.filters}
      overview={state.overview}
      tripId="ux-lab-rajasthan"
      seed={state.itinerary}
      circuitFocusDay={state.circuitDay ?? undefined}
      circuitFocusToken={circuitActive ? 1 : 0}
      focusName={state.focus?.name ?? null}
      focusDay={state.focus?.day}
      focusStop={state.focus?.index}
      onStopFocus={(_kind, name, day, stop) => state.focusAt(day, stop, name, `${name} focused: photos and reviews load in Details, pin highlighted on the map.`)}
      onStopMap={(_kind, name, day, stop) => state.focusAt(day, stop, name, `Map jumps to ${name}.`)}
      onDayMap={state.showDay}
      onAllDaysMap={state.showAllDays}
      onStopRemove={(_kind, name, day, stop) => state.removeAt(day, stop, name)}
      onAdjustDays={state.adjustDays}
    />
  );
}
