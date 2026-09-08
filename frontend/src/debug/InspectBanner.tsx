// Says whose trip is on screen while inspecting, because every pane otherwise
// looks exactly like the owner's own workspace and there is no way back.

import { useState } from "react";
import { endInspection, forkInspectedTrip, inspectedUserId } from "./inspectSession";

export default function InspectBanner() {
  const userId = inspectedUserId();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (!userId) return null;

  const leave = () => {
    endInspection();
    window.location.href = window.location.pathname;
  };

  const copy = async () => {
    setBusy(true);
    setError("");
    try {
      await forkInspectedTrip();
      window.location.href = window.location.pathname;
    } catch {
      setError("Could not copy");
      setBusy(false);
    }
  };

  return (
    <div
      role="status"
      className="fixed bottom-3 left-1/2 z-[999] flex -translate-x-1/2 items-center gap-3
                 rounded-full border border-amber-400 bg-amber-50 px-4 py-1.5 text-sm
                 text-amber-900 shadow-lg"
    >
      <span>
        Inspecting <code className="font-mono">{userId}</code>
        <span className="ml-1 opacity-70">· read-only</span>
      </span>
      {error && <span className="text-red-700">{error}</span>}
      <button
        type="button"
        onClick={copy}
        disabled={busy}
        className="rounded-full border border-amber-500 px-3 py-0.5 text-xs font-medium
                   hover:bg-amber-100 disabled:opacity-50"
      >
        {busy ? "Copying…" : "Copy to my trips"}
      </button>
      <button
        type="button"
        onClick={leave}
        className="rounded-full bg-amber-900 px-3 py-0.5 text-xs font-medium text-amber-50
                   hover:bg-amber-800"
      >
        Leave
      </button>
    </div>
  );
}
