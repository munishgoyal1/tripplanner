import { useEffect, useState } from "react";
import { BarChart3, ChevronLeft } from "lucide-react";
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

  if (!measurementId || preference !== null) return null;

  const choose = (next: AnalyticsPreference) => {
    setAnalyticsPreference(next);
    setPreference(next);
    if (next === "granted") enableAnalytics(measurementId);
    else disableAnalytics();
  };

  return (
    <aside aria-label="Analytics consent" className="fixed inset-x-3 bottom-3 z-[120] mx-auto flex max-w-3xl flex-col gap-3 rounded-lg border border-slate-200 bg-white p-4 shadow-pop sm:flex-row sm:items-center">
      <div className="min-w-0 flex-1"><p className="text-sm font-semibold text-ink">Help improve Tripplanner</p><p className="mt-1 text-sm leading-5 text-slate-600">Allow anonymous usage analytics. Trip details, messages, account identity, and shared-link tokens are never sent.</p></div>
      <div className="flex shrink-0 gap-2"><button type="button" className="btn-ghost" onClick={() => choose("denied")}>No thanks</button><button type="button" className="btn-primary" onClick={() => choose("granted")}>Allow analytics</button></div>
    </aside>
  );
}

export function AnalyticsPreferences({ onBack }: { onBack: () => void }) {
  const [measurementId, setMeasurementId] = useState("");
  const [preference, setPreference] = useState<AnalyticsPreference | null>(
    getAnalyticsPreference,
  );

  useEffect(() => {
    let cancelled = false;
    fetchAnalyticsConfig()
      .then((config) => {
        if (!cancelled && config.enabled) setMeasurementId(config.measurement_id);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  const choose = (next: AnalyticsPreference) => {
    setAnalyticsPreference(next);
    setPreference(next);
    if (next === "granted" && measurementId) enableAnalytics(measurementId);
    else disableAnalytics();
  };

  return (
    <section aria-label="Analytics preferences" className="p-4">
      <button type="button" onClick={onBack} className="inline-flex items-center gap-1 text-xs font-semibold text-slate-500 hover:text-ink"><ChevronLeft size={14} aria-hidden /> Back to settings</button>
      <div className="mt-4 flex items-start gap-3">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-teal-50 text-teal-700"><BarChart3 size={17} aria-hidden /></span>
        <div><p className="text-[10px] font-bold uppercase text-brand">Product improvement</p><h3 className="mt-0.5 text-sm font-semibold text-ink">Analytics preferences</h3><p className="mt-1 text-xs leading-relaxed text-slate-500">Choose whether anonymous usage analytics can help improve customer flow.</p></div>
      </div>
      <div className="mt-4 rounded-md bg-slate-50 p-3 ring-1 ring-slate-200">
        <p className="text-xs leading-5 text-slate-600">
          Allow anonymous usage analytics to help improve customer flow. Trip details,
          messages, account identity, and shared-link tokens are never sent.
        </p>
        {!measurementId && <p className="mt-1 text-xs text-slate-400">Analytics collection is not configured in this environment. Your preference will still be saved.</p>}
      </div>
      <div className="mt-4 grid grid-cols-2 gap-2">
        <button type="button" className={`h-9 rounded-md text-xs font-semibold ring-1 ${preference === "denied" ? "bg-slate-100 text-ink ring-slate-300" : "text-slate-500 ring-slate-200 hover:bg-slate-50"}`} aria-pressed={preference === "denied"} onClick={() => choose("denied")}>
          No thanks
        </button>
        <button type="button" className={`h-9 rounded-md text-xs font-semibold ring-1 ${preference === "granted" ? "bg-brand text-white ring-brand" : "text-brand ring-brand/30 hover:bg-brand/5"}`} aria-pressed={preference === "granted"} onClick={() => choose("granted")}>
          Allow analytics
        </button>
      </div>
      <p className="mt-3 text-[11px] text-slate-400">Current choice: {preference === "granted" ? "Allowed" : preference === "denied" ? "Not allowed" : "Not chosen"}</p>
    </section>
  );
}
