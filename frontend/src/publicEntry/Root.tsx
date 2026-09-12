import { lazy, Suspense, useEffect, useState } from "react";
import AccountSettingsController from "../components/AccountSettingsController";
import {
  isPlannerPath,
  isPublicEntryPath,
} from "./publicEntryState";
import { trackPageView } from "../analytics";

const PublicEntry = lazy(() => import("./PublicEntry"));
const App = lazy(() => import("../App"));
const OpsDashboard = lazy(() => import("../ops/OpsDashboard"));

/** `/` owns the public entry, `/planner` owns the workspace, and `/welcome` redirects home. */
function Routes() {
  if (window.location.pathname === "/operations") {
    return <OpsDashboard />;
  }

  const [showEntry, setShowEntry] = useState(() => !isPlannerPath());
  const [initialRequest, setInitialRequest] = useState<string | null>(null);

  useEffect(() => {
    if (isPublicEntryPath()) window.history.replaceState({}, "", "/");
  }, []);

  useEffect(() => {
    const handlePopState = () => {
      if (isPublicEntryPath()) window.history.replaceState({}, "", "/");
      const showPublicEntry = !isPlannerPath();
      setShowEntry(showPublicEntry);
      if (showPublicEntry) setInitialRequest(null);
      trackPageView();
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  const openWorkspace = (request: string | null = null) => {
    window.history.pushState({}, "", "/planner");
    setInitialRequest(request);
    setShowEntry(false);
    trackPageView();
  };

  useEffect(() => {
    const openWelcome = () => {
      window.history.pushState({}, "", "/");
      setInitialRequest(null);
      setShowEntry(true);
      trackPageView();
    };
    window.addEventListener("tripplanner:open-welcome", openWelcome);
    return () => window.removeEventListener("tripplanner:open-welcome", openWelcome);
  }, []);

  return (
    <>
      {showEntry ? (
      <div className="product-theme-aegean min-h-full">
        <PublicEntry
          onPlan={(request) => openWorkspace(request)}
          onSkip={() => openWorkspace()}
        />
      </div>
      ) : <App initialRequest={initialRequest} />}
      <AccountSettingsController />
    </>
  );
}

export default function Root() {
  return (
    <Suspense fallback={<main className="app-startup" role="status"><strong>AI Tripplanner</strong>Opening your planner…</main>}>
      <Routes />
    </Suspense>
  );
}
