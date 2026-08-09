import { useState } from "react";
import { isAnonymousUser } from "../auth/authSession";
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

  const openWorkspace = (request: string | null = null) => {
    markPublicEntrySkipped();
    if (isPublicEntryPath()) {
      window.history.replaceState({}, "", "/");
    }
    setInitialRequest(request);
    setShowEntry(false);
  };

  if (showEntry) {
    return (
      <div className="product-theme-aegean min-h-full">
        <PublicEntry
          onPlan={(request) => openWorkspace(request)}
          onSkip={() => openWorkspace()}
        />
      </div>
    );
  }

  return <App initialRequest={initialRequest} />;
}
