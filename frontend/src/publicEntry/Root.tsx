import { useEffect, useState } from "react";
import { fetchSavedTrips } from "../api";
import { isAnonymousUser } from "../auth/authSession";
import AccountSettingsController from "../components/AccountSettingsController";
import PublicEntry from "./PublicEntry";
import {
  isPlannerPath,
  isPublicEntryPath,
  markPublicEntrySkipped,
  shouldShowPublicEntry,
} from "./publicEntryState";
import App from "../App";
import OpsDashboard from "../ops/OpsDashboard";

/** `/welcome` always opens the public entry; `/planner` and normal return visits open the
 * workspace, except for a guest who has no saved trip yet. */
export default function Root() {
  if (window.location.pathname === "/operations") {
    return <OpsDashboard />;
  }

  const plannerPath = isPlannerPath();
  const [showEntry, setShowEntry] = useState(
    () => isPublicEntryPath() || (!plannerPath && shouldShowPublicEntry(isAnonymousUser()))
  );
  // A guest reaching /planner only falls back to the landing page once we know they have no trip.
  const [tripCheckPending, setTripCheckPending] = useState(() => plannerPath && isAnonymousUser());
  const [initialRequest, setInitialRequest] = useState<string | null>(null);

  useEffect(() => {
    if (!tripCheckPending) return;
    let cancelled = false;
    fetchSavedTrips()
      .then((trips) => {
        if (!cancelled) setShowEntry(trips.length === 0);
      })
      .catch(() => {
        if (!cancelled) setShowEntry(false);
      })
      .finally(() => {
        if (!cancelled) setTripCheckPending(false);
      });
    return () => {
      cancelled = true;
    };
  }, [tripCheckPending]);

  useEffect(() => {
    const handlePopState = () => {
      const showWelcome = isPublicEntryPath();
      setShowEntry(showWelcome);
      if (showWelcome) setInitialRequest(null);
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  const openWorkspace = (request: string | null = null) => {
    markPublicEntrySkipped();
    if (isPublicEntryPath()) {
      window.history.pushState({}, "", "/");
    }
    setInitialRequest(request);
    setShowEntry(false);
  };

  useEffect(() => {
    const openWelcome = () => {
      window.history.pushState({}, "", "/welcome");
      setInitialRequest(null);
      setShowEntry(true);
    };
    window.addEventListener("tripplanner:open-welcome", openWelcome);
    return () => window.removeEventListener("tripplanner:open-welcome", openWelcome);
  }, []);

  if (tripCheckPending) return null;

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
