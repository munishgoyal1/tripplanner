import { useEffect, useState } from "react";
import { X } from "lucide-react";
import {
  disableAnalytics,
  enableAnalytics,
  fetchAnalyticsConfig,
  getAnalyticsPreference,
  setAnalyticsPreference,
  type AnalyticsPreference,
} from "../analytics";

export default function AnalyticsConsent() {
  const [measurementId, setMeasurementId] = useState("");
  const [preference, setPreference] = useState<AnalyticsPreference | null>(
    getAnalyticsPreference,
  );
  const [settingsOpen, setSettingsOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchAnalyticsConfig()
      .then((config) => {
        if (cancelled || !config.enabled) return;
        setMeasurementId(config.measurement_id);
        if (getAnalyticsPreference() === "granted") {
          enableAnalytics(config.measurement_id);
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const openSettings = () => setSettingsOpen(true);
    window.addEventListener("tripplanner:analytics-settings", openSettings);
    return () => window.removeEventListener("tripplanner:analytics-settings", openSettings);
  }, []);

  const firstRunPrompt = Boolean(measurementId) && preference === null;
  if (!settingsOpen && !firstRunPrompt) return null;

  const choose = (next: AnalyticsPreference) => {
    setAnalyticsPreference(next);
    setPreference(next);
    setSettingsOpen(false);
    if (next === "granted" && measurementId) enableAnalytics(measurementId);
    else disableAnalytics();
  };

  return (
    <aside
      aria-label="Analytics preferences"
      className="fixed inset-x-3 bottom-3 z-[120] mx-auto flex max-w-3xl flex-col gap-3 rounded-lg border border-slate-200 bg-white p-4 shadow-pop sm:flex-row sm:items-center"
    >
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-ink">Analytics preferences</p>
        <p className="mt-1 text-sm leading-5 text-slate-600">
          Allow anonymous usage analytics to help improve customer flow. Trip details,
          messages, account identity, and shared-link tokens are never sent.
        </p>
        {!measurementId && <p className="mt-1 text-xs text-slate-400">Analytics collection is not configured in this environment. Your preference will still be saved.</p>}
      </div>
      <div className="flex shrink-0 gap-2">
        <button type="button" className="btn-ghost" aria-pressed={preference === "denied"} onClick={() => choose("denied")}>
          No thanks
        </button>
        <button type="button" className="btn-primary" aria-pressed={preference === "granted"} onClick={() => choose("granted")}>
          Allow analytics
        </button>
        {settingsOpen && <button type="button" onClick={() => setSettingsOpen(false)} className="grid h-9 w-9 place-items-center rounded-md text-slate-400 hover:bg-slate-100 hover:text-ink" aria-label="Close analytics preferences"><X size={15} aria-hidden /></button>}
      </div>
    </aside>
  );
}