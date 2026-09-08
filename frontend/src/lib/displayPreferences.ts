import { useEffect, useState } from "react";

export type DisplayCurrency = string;
export interface DisplayPreferences {
  region: string;
  language: string;
  currency: DisplayCurrency;
}
export interface DisplayOption {
  code: string;
  label: string;
}

const STORAGE_KEY = "tripplanner_display_preferences";
const SOURCE_KEY = "tripplanner_display_preferences_source";
const DEFAULTS: DisplayPreferences = { region: "", language: "en", currency: "USD" };
const RATES_FROM_USD: Record<string, number> = {
  USD: 1,
  EUR: 0.92,
  GBP: 0.78,
  INR: 83,
  JPY: 147,
  CAD: 1.36,
  AUD: 1.52,
  CHF: 0.88,
  CNY: 7.2,
  AED: 3.67,
  BRL: 5,
};
const DISPLAY_LANGUAGE_CODES = [
  "en", "ar", "de", "es", "fr", "hi", "id", "it", "ja",
  "ko", "nl", "pl", "pt", "ru", "sv", "th", "tr", "vi", "zh",
];
// Values saved before the fixed selector, plus the shorthand travellers type.
const LEGACY_REGION_ALIASES: Record<string, string> = {
  USA: "US",
  "UNITED STATES OF AMERICA": "US",
  UK: "GB",
  UAE: "AE",
  EUROPE: "EU",
};
const MILES_REGIONS = new Set(["US", "GB", "LR", "MM"]);
const FAHRENHEIT_REGIONS = new Set(["US"]);
const REGION_CURRENCIES: Record<string, string> = {
  AE: "AED", AU: "AUD", BR: "BRL", CA: "CAD", CH: "CHF",
  CN: "CNY", GB: "GBP", IN: "INR", JP: "JPY", US: "USD",
};
const EURO_REGIONS = new Set([
  "AT", "BE", "CY", "DE", "EE", "ES", "EU", "FI", "FR", "GR", "HR",
  "IE", "IT", "LT", "LU", "LV", "MT", "NL", "PT", "SI", "SK",
]);

function displayNames(type: "region" | "language"): Intl.DisplayNames | null {
  try {
    return new Intl.DisplayNames(["en"], { type });
  } catch {
    return null;
  }
}

let regionOptions: DisplayOption[] | null = null;

export function supportedDisplayRegions(): DisplayOption[] {
  if (regionOptions) return regionOptions;
  const names = displayNames("region");
  const letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
  const options: DisplayOption[] = [];
  for (const first of letters) {
    for (const second of letters) {
      const code = `${first}${second}`;
      // Intl echoes the code back for unassigned regions, leaving only real ones.
      const label = names?.of(code);
      if (label && label !== code) options.push({ code, label });
    }
  }
  regionOptions = options.sort((left, right) => left.label.localeCompare(right.label));
  return regionOptions;
}

export function normalizeDisplayRegion(value: string): string {
  const raw = (value || "").trim();
  if (!raw) return "";
  const upper = raw.toUpperCase();
  if (LEGACY_REGION_ALIASES[upper]) return LEGACY_REGION_ALIASES[upper];
  if (/^[A-Z]{2}$/.test(upper)) {
    return supportedDisplayRegions().some((option) => option.code === upper) ? upper : "";
  }
  return supportedDisplayRegions().find((option) => option.label.toUpperCase() === upper)?.code || "";
}

export function displayRegionLabel(region: string): string {
  const code = normalizeDisplayRegion(region);
  return supportedDisplayRegions().find((option) => option.code === code)?.label || region;
}

export function supportedDisplayLanguages(): DisplayOption[] {
  const names = displayNames("language");
  return DISPLAY_LANGUAGE_CODES
    .map((code) => ({ code, label: names?.of(code) || code }))
    .sort((left, right) => left.label.localeCompare(right.label));
}

export function normalizeDisplayLanguage(value: string): string {
  const code = (value || "").trim().toLowerCase().split("-")[0];
  return DISPLAY_LANGUAGE_CODES.includes(code) ? code : "en";
}

export function displayLanguageLabel(language: string): string {
  const code = normalizeDisplayLanguage(language);
  return supportedDisplayLanguages().find((option) => option.code === code)?.label || code;
}

/** Language and country combined into the locale used for dates and numbers. */
export function displayLocale(preferences: DisplayPreferences = readDisplayPreferences()): string {
  const language = normalizeDisplayLanguage(preferences.language);
  const region = normalizeDisplayRegion(preferences.region);
  if (!region) return language;
  try {
    return Intl.getCanonicalLocales(`${language}-${region}`)[0] || language;
  } catch {
    return language;
  }
}

function normalizeCurrency(currency: string): string {
  const value = currency.toUpperCase();
  if (value === "€" || value === "EUR") return "EUR";
  if (value === "£" || value === "GBP") return "GBP";
  if (value === "₹" || value === "INR") return "INR";
  return /^[A-Z]{3}$/.test(value) ? value : "USD";
}

export function supportedDisplayCurrencies(): string[] {
  return Object.keys(RATES_FROM_USD);
}

export function displayCurrencyLabel(currency: string): string {
  try {
    const name = new Intl.DisplayNames(["en"], { type: "currency" }).of(currency);
    return name ? `${currency} - ${name}` : currency;
  } catch {
    return currency;
  }
}

function isDisplayPreferences(value: unknown): value is DisplayPreferences {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<DisplayPreferences>;
  return /^[a-z]{2}$/.test(candidate.language || "") && /^[A-Z]{3}$/.test(candidate.currency || "");
}

export function readDisplayPreferences(): DisplayPreferences {
  try {
    const value = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
    return isDisplayPreferences(value) ? value : DEFAULTS;
  } catch {
    return DEFAULTS;
  }
}

export function writeDisplayPreferences(next: DisplayPreferences, source: "detected" | "profile" = "profile"): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  localStorage.setItem(SOURCE_KEY, source);
  window.dispatchEvent(new Event("tripplanner:display-preferences-changed"));
}

export function detectInitialDisplayPreferences(): DisplayPreferences {
  const locale = typeof navigator === "undefined" ? "en-US" : navigator.language || "en-US";
  const region = normalizeDisplayRegion(locale.split("-")[1] || "");
  const language = normalizeDisplayLanguage(locale.split("-")[0]);
  return { region, language, currency: currencyForRegion(region) };
}

export function currencyForRegion(region: string): DisplayCurrency {
  const code = normalizeDisplayRegion(region);
  return REGION_CURRENCIES[code] || (EURO_REGIONS.has(code) ? "EUR" : "USD");
}

export function ensureInitialDisplayPreferences(): DisplayPreferences {
  const existing = readDisplayPreferences();
  if (localStorage.getItem(STORAGE_KEY) && localStorage.getItem(SOURCE_KEY)) return existing;
  const detected = detectInitialDisplayPreferences();
  writeDisplayPreferences(detected, "detected");
  return detected;
}

export function useDisplayPreferences(): DisplayPreferences {
  const [preferences, setPreferences] = useState(readDisplayPreferences);
  useEffect(() => {
    const refresh = () => setPreferences(readDisplayPreferences());
    window.addEventListener("tripplanner:display-preferences-changed", refresh);
    return () => window.removeEventListener("tripplanner:display-preferences-changed", refresh);
  }, []);
  return preferences;
}

export function formatDate(value: string, locale = displayLocale()): string {
  if (!value) return "";
  return new Date(`${value}T12:00:00`).toLocaleDateString(locale, { day: "numeric", month: "short", year: "numeric" });
}

export function formatDisplayAmount(
  amount: number,
  sourceCurrency: string,
  targetCurrency: DisplayCurrency,
  locale = displayLocale(),
): string {
  const normalizedSource = normalizeCurrency(sourceCurrency);
  const sourceRate = RATES_FROM_USD[normalizedSource];
  const targetRate = RATES_FROM_USD[targetCurrency];
  if (!sourceRate || !targetRate) return new Intl.NumberFormat(locale, { style: "currency", currency: normalizedSource, maximumFractionDigits: 0 }).format(amount);
  const converted = amount / sourceRate * targetRate;
  return new Intl.NumberFormat(locale, { style: "currency", currency: targetCurrency, maximumFractionDigits: 0 }).format(converted);
}

export function formatSourceAmount(amount: number, sourceCurrency: string, targetCurrency: DisplayCurrency): string {
  return formatDisplayAmount(amount, sourceCurrency, targetCurrency);
}

export function formatCostDisplay(value: string, targetCurrency: DisplayCurrency): string {
  const match = value.trim().match(/^([€£$₹]|[A-Z]{3})\s*(.*)$/);
  if (!match) return value;
  const sourceCurrency = normalizeCurrency(match[1]);
  if (!RATES_FROM_USD[sourceCurrency] || !RATES_FROM_USD[targetCurrency]) return value;
  return match[2].replace(/\d[\d,]*(?:\.\d+)?/g, (number) => (
    formatDisplayAmount(Number(number.replace(/,/g, "")), sourceCurrency, targetCurrency)
  ));
}

export function formatDistance(distanceKm: number, region: string): string {
  const usesMiles = MILES_REGIONS.has(normalizeDisplayRegion(region));
  const value = usesMiles ? distanceKm * 0.621371 : distanceKm;
  return `${new Intl.NumberFormat("en", { maximumFractionDigits: 1 }).format(value)} ${usesMiles ? "mi" : "km"}`;
}

export function formatTemperature(celsius: number, region: string): string {
  const usesFahrenheit = FAHRENHEIT_REGIONS.has(normalizeDisplayRegion(region));
  const value = usesFahrenheit ? celsius * 9 / 5 + 32 : celsius;
  return `${Math.round(value)}°${usesFahrenheit ? "F" : "C"}`;
}