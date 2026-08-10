import type { AccountDestination } from "./AccountSettingsHub";

export const ACCOUNT_SETTINGS_EVENT = "tripplanner:open-account";

const ACCOUNT_DESTINATIONS = new Set<AccountDestination>([
  "menu",
  "profile",
  "travel",
  "documents",
  "analytics",
  "privacy",
]);

export function normalizeAccountDestination(destination: unknown): AccountDestination {
  return typeof destination === "string" && ACCOUNT_DESTINATIONS.has(destination as AccountDestination)
    ? destination as AccountDestination
    : "menu";
}

export function openAccountSettings(): void;
export function openAccountSettings(destination: AccountDestination): void;
export function openAccountSettings(destination: unknown = "menu") {
  const requested = normalizeAccountDestination(destination);
  window.dispatchEvent(new CustomEvent(ACCOUNT_SETTINGS_EVENT, { detail: { destination: requested } }));
}
