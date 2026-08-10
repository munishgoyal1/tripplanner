import type { AccountDestination } from "./AccountSettingsHub";

export const ACCOUNT_SETTINGS_EVENT = "tripplanner:open-account";

export function openAccountSettings(destination: AccountDestination = "menu") {
  window.dispatchEvent(new CustomEvent(ACCOUNT_SETTINGS_EVENT, { detail: { destination } }));
}
