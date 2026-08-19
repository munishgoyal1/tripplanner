import { useEffect, useState } from "react";
import AccountSettingsController from "../components/AccountSettingsController";
import PublicEntry from "./PublicEntry";
import {
  isPlannerPath,
  isPublicEntryPath,
} from "./publicEntryState";
import App from "../App";
import OpsDashboard from "../ops/OpsDashboard";

/** `/` owns the public entry, `/planner` owns the workspace, and `/welcome` redirects home. */
export default function Root() {
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
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  const openWorkspace = (request: string | null = null) => {
    window.history.pushState({}, "", "/planner");
    setInitialRequest(request);
    setShowEntry(false);
  };

  useEffect(() => {
    const openWelcome = () => {
      window.history.pushState({}, "", "/");
      setInitialRequest(null);
      setShowEntry(true);
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
