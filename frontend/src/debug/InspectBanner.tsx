// Says whose trip is on screen while inspecting, because every pane otherwise
// looks exactly like the owner's own workspace and there is no way back.

import { endInspection, inspectedUserId } from "./inspectSession";

export default function InspectBanner() {
  const userId = inspectedUserId();
  if (!userId) return null;

  const leave = () => {
    endInspection();
    window.location.href = window.location.pathname;
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
      </span>
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
