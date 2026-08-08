import { useState } from "react";
import { isAnonymousUser } from "../auth/authSession";
import PublicEntry from "./PublicEntry";
import { markPublicEntrySkipped, shouldShowPublicEntry } from "./publicEntryState";
import App from "../App";

/** Anonymous first visits land on the public entry; everyone else opens the workspace. */
export default function Root() {
  const [showEntry, setShowEntry] = useState(() => shouldShowPublicEntry(isAnonymousUser()));
  const [initialRequest, setInitialRequest] = useState<string | null>(null);

  if (showEntry) {
    return (
      <PublicEntry
        onPlan={(request) => {
          markPublicEntrySkipped();
          setInitialRequest(request);
          setShowEntry(false);
        }}
        onSkip={() => {
          markPublicEntrySkipped();
          setShowEntry(false);
        }}
      />
    );
  }

  return <App initialRequest={initialRequest} />;
}
