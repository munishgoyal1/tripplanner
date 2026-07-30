import { useEffect, useState } from "react";
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
    const openSettings = () => setPreference(null);
    window.addEventListener("tripplanner:analytics-settings", openSettings);
    return () => window.removeEventListener("tripplanner:analytics-settings", openSettings);
  }, []);

  if (!measurementId || preference !== null) return null;

  const choose = (next: AnalyticsPreference) => {
    setAnalyticsPreference(next);
    setPreference(next);
    if (next === "granted") enableAnalytics(measurementId);
    else disableAnalytics();
  };

  return (
    <aside
      aria-label="Analytics preferences"
      className="fixed inset-x-3 bottom-3 z-[120] mx-auto flex max-w-3xl flex-col gap-3 rounded-lg border border-slate-200 bg-white p-4 shadow-pop sm:flex-row sm:items-center"
    >
      <p className="min-w-0 flex-1 text-sm leading-5 text-slate-600">
        Allow anonymous usage analytics to help improve customer flow. Trip details,
        messages, account identity, and shared-link tokens are never sent.
      </p>
      <div className="flex shrink-0 gap-2">
        <button type="button" className="btn-ghost" onClick={() => choose("denied")}>
          No thanks
        </button>
        <button type="button" className="btn-primary" onClick={() => choose("granted")}>
          Allow analytics
        </button>
      </div>
    </aside>
  );
}