import React from "react";
import ReactDOM from "react-dom/client";
import AnalyticsConsent from "./components/AnalyticsConsent";
import Root from "./publicEntry/Root";
import "./index.css";

// Every debug reference sits behind this constant, so an unset flag makes the
// branch statically dead and none of it reaches a production bundle.
const debugTools = import.meta.env.VITE_DEBUG_TOOLS === "1";
const InspectBanner = debugTools ? React.lazy(() => import("./debug/InspectBanner")) : null;

// Adopts the inspected identity, then re-enters without the query so the whole
// app loads under it. Deliberately not awaited before render: an earlier version
// blocked rendering on this and any failure here left a blank page.
async function runInspection(): Promise<void> {
  if (!debugTools) return;
  try {
    const { beginInspection } = await import("./debug/inspectSession");
    const request = beginInspection(window.location.search);
    if (!request) return;
    if (request.tripId) {
      const { switchTrip } = await import("./api");
      await switchTrip(request.tripId);
    }
    // The banner reads the flag from storage, so the query is no longer needed
    // and dropping it stops a refresh from re-running this.
    window.location.replace(window.location.pathname);
  } catch {
    // Inspection is a developer affordance; it must never keep the app down.
  }
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Root />
    <AnalyticsConsent />
    {InspectBanner && (
      <React.Suspense fallback={null}>
        <InspectBanner />
      </React.Suspense>
    )}
  </React.StrictMode>
);

void runInspection();
