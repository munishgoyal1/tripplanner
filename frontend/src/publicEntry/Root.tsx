import { useEffect, useState } from "react";
import { isAnonymousUser } from "../auth/authSession";
import AccountSettingsController from "../components/AccountSettingsController";
import PublicEntry from "./PublicEntry";
import {
  isPublicEntryPath,
  markPublicEntrySkipped,
  shouldShowPublicEntry,
} from "./publicEntryState";
import App from "../App";

/** `/welcome` always opens the public entry; normal return visits open the workspace. */
export default function Root() {
  const [showEntry, setShowEntry] = useState(
    () => isPublicEntryPath() || shouldShowPublicEntry(isAnonymousUser())
  );
  const [initialRequest, setInitialRequest] = useState<string | null>(null);

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
