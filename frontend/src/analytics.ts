export type AnalyticsEvent =
  | "planning_started"
  | "planning_completed"
  | "planning_failed"
  | "trip_created"
  | "new_trip_started"
  | "login"
  | "place_added"
  | "place_removed"
  | "trip_shared"
  | "itinerary_exported"
  | "calendar_exported"
  | "shared_trip_imported";

export type AnalyticsPreference = "granted" | "denied";
type EventParameters = Record<string, string | number | boolean>;

const CONSENT_KEY = "tripplanner_analytics_consent";
let measurementId = "";
let ready = false;

function analyticsWindow(): Window & {
  dataLayer?: unknown[];
  gtag?: (...args: unknown[]) => void;
} {
  return window;
}

export function getAnalyticsPreference(): AnalyticsPreference | null {
  const value = localStorage.getItem(CONSENT_KEY);
  return value === "granted" || value === "denied" ? value : null;
}

export function setAnalyticsPreference(preference: AnalyticsPreference): void {
  localStorage.setItem(CONSENT_KEY, preference);
}

export async function fetchAnalyticsConfig(): Promise<{
  enabled: boolean;
  measurement_id: string;
}> {
  const response = await fetch("/api/analytics/config", { credentials: "same-origin" });
  if (!response.ok) return { enabled: false, measurement_id: "" };
  return response.json();
}

export function enableAnalytics(id: string): void {
  if (ready || !/^G-[A-Z0-9]+$/.test(id)) return;
  measurementId = id;
  const target = analyticsWindow();
  target.dataLayer = target.dataLayer || [];
  target.gtag = function () {
    target.dataLayer!.push(arguments);
  };
  target.gtag("consent", "default", {
    analytics_storage: "denied",
    ad_storage: "denied",
    ad_user_data: "denied",
    ad_personalization: "denied",
  });

  const script = document.createElement("script");
  script.async = true;
  script.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(id)}`;
  document.head.appendChild(script);

  target.gtag("js", new Date());
  target.gtag("consent", "update", { analytics_storage: "granted" });
  target.gtag("config", id, {
    send_page_view: false,
    allow_google_signals: false,
    allow_ad_personalization_signals: false,
  });
  ready = true;
  target.gtag("event", "page_view", {
    page_location: `${window.location.origin}${window.location.pathname}`,
    page_title: document.title,
  });
}

export function disableAnalytics(): void {
  const target = analyticsWindow();
  target.gtag?.("consent", "update", { analytics_storage: "denied" });
  ready = false;
  measurementId = "";
}

export function trackEvent(name: AnalyticsEvent, parameters: EventParameters = {}): void {
  if (!ready || !measurementId) return;
  analyticsWindow().gtag?.("event", name, parameters);
}