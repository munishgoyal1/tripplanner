import { useEffect, useState } from "react";

export type DisplayCurrency = string;
export interface DisplayPreferences {
  region: string;
  language: "en";
  currency: DisplayCurrency;
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
  return candidate.language === "en" && /^[A-Z]{3}$/.test(candidate.currency || "");
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
  const region = locale.split("-")[1]?.toUpperCase() || "";
  const currency: DisplayCurrency = region === "IN" ? "INR" : region === "GB" ? "GBP" : ["DE", "ES", "FR", "IT", "NL"].includes(region) ? "EUR" : "USD";
  return { region, language: "en", currency };
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

export function formatDate(value: string, locale = "en-US"): string {
  if (!value) return "";
  return new Date(`${value}T12:00:00`).toLocaleDateString(locale, { day: "numeric", month: "short", year: "numeric" });
}

export function formatDisplayAmount(amount: number, sourceCurrency: string, targetCurrency: DisplayCurrency): string {
  const normalizedSource = normalizeCurrency(sourceCurrency);
  const sourceRate = RATES_FROM_USD[normalizedSource];
  const targetRate = RATES_FROM_USD[targetCurrency];
  if (!sourceRate || !targetRate) return new Intl.NumberFormat("en", { style: "currency", currency: normalizedSource, maximumFractionDigits: 0 }).format(amount);
  const converted = amount / sourceRate * targetRate;
  return new Intl.NumberFormat("en", { style: "currency", currency: targetCurrency, maximumFractionDigits: 0 }).format(converted);
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
  const usesMiles = /united states|united kingdom|uk/i.test(region);
  const value = usesMiles ? distanceKm * 0.621371 : distanceKm;
  return `${new Intl.NumberFormat("en", { maximumFractionDigits: 1 }).format(value)} ${usesMiles ? "mi" : "km"}`;
}

export function formatTemperature(celsius: number, region: string): string {
  const usesFahrenheit = /united states/i.test(region);
  const value = usesFahrenheit ? celsius * 9 / 5 + 32 : celsius;
  return `${Math.round(value)}°${usesFahrenheit ? "F" : "C"}`;
}