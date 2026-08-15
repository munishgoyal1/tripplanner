import React from "react";
import ReactDOM from "react-dom/client";
import AnalyticsConsent from "./components/AnalyticsConsent";
import Root from "./publicEntry/Root";
import "./index.css";

// Every debug import sits inside this constant check, so an unset flag makes the
// whole branch statically dead and none of it reaches a production bundle.
async function inspectionBanner(): Promise<React.ReactNode> {
  if (import.meta.env.VITE_DEBUG_TOOLS !== "1") return null;

  const { beginInspection } = await import("./debug/inspectSession");
  const request = beginInspection(window.location.search);
  if (request?.tripId) {
    // Make the named trip active before the first render, so the workspace opens
    // on the flagged trip rather than whichever one was last used.
    const { switchTrip } = await import("./api");
    await switchTrip(request.tripId).catch(() => null);
  }
  const { default: InspectBanner } = await import("./debug/InspectBanner");
  return <InspectBanner />;
}

async function start(): Promise<void> {
  const banner = await inspectionBanner();
  ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
      <Root />
      <AnalyticsConsent />
      {banner}
    </React.StrictMode>
  );
}

void start();
