import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

import {
  fetchAuthConfig,
  loginWithGoogle,
  logoutGoogle,
  runPrivacyAction,
  signIn,
  signOut,
  syncAuth,
  type AuthSession,
} from "../api";
import { trackEvent } from "../analytics";
import { getDisplayName, isAnonymousUser } from "../auth/authSession";
import AccountSettingsHub, { type AccountDestination } from "./AccountSettingsHub";
import { ACCOUNT_SETTINGS_EVENT } from "./accountSettings";

export default function AccountSettingsController() {
  const [open, setOpen] = useState(false);
  const [destination, setDestination] = useState<AccountDestination>("menu");
  const [auth, setAuth] = useState<AuthSession>({ authenticated: false });
  const [googleEnabled, setGoogleEnabled] = useState(false);
  const [nameInput, setNameInput] = useState(getDisplayName());
  const [privacyBusy, setPrivacyBusy] = useState(false);

  useEffect(() => {
    void fetchAuthConfig().then((config) => setGoogleEnabled(config.google));
    void syncAuth().then(setAuth);
  }, []);

  useEffect(() => {
    const showAccount = (event: Event) => {
      const requested = (event as CustomEvent<{ destination?: AccountDestination }>).detail?.destination;
      setDestination(requested ?? "menu");
      setOpen(true);
    };
    window.addEventListener(ACCOUNT_SETTINGS_EVENT, showAccount);
    return () => window.removeEventListener(ACCOUNT_SETTINGS_EVENT, showAccount);
  }, []);

  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [open]);

  const reloadAfter = (message: string) => {
    window.alert(message);
    window.location.reload();
  };

  const deleteTripHistory = async () => {
    if (!window.confirm("Delete all saved trips and related chat history for this account? This cannot be undone.")) return;
    setPrivacyBusy(true);
    try {
      const response = await runPrivacyAction("delete_trip_history");
      if (!response.ok) window.alert(response.message || "Could not delete trip history.");
      else reloadAfter("Trip history deleted.");
    } finally {
      setPrivacyBusy(false);
    }
  };

  const clearAllData = async () => {
    const confirmation = window.prompt("Type DELETE to clear all your app data for this account.");
    if ((confirmation || "").trim().toUpperCase() !== "DELETE") return;
    setPrivacyBusy(true);
    try {
      const response = await runPrivacyAction("clear_all_data", confirmation || "");
      if (!response.ok) window.alert(response.message || "Could not clear data.");
      else reloadAfter("All app data cleared for this account.");
    } finally {
      setPrivacyBusy(false);
    }
  };

  const deleteAccount = async () => {
    const confirmation = window.prompt("Type DELETE to delete this app account data. This clears all app data and signs you out.");
    if ((confirmation || "").trim().toUpperCase() !== "DELETE") return;
    setPrivacyBusy(true);
    try {
      const response = await runPrivacyAction("delete_account", confirmation || "");
      if (!response.ok) {
        window.alert(response.message || "Could not delete account data.");
        return;
      }
      if (auth.authenticated) await logoutGoogle();
      else signOut();
      reloadAfter("Account data deleted.");
    } finally {
      setPrivacyBusy(false);
    }
  };

  if (!open) return null;

  return createPortal(
    <AccountSettingsHub
      key={destination}
      auth={auth}
      googleEnabled={googleEnabled}
      localIdentityActive={!isAnonymousUser()}
      nameInput={nameInput}
      privacyBusy={privacyBusy}
      initialDestination={destination}
      onNameInputChange={setNameInput}
      onClose={() => setOpen(false)}
      onGoogleSignIn={() => {
        trackEvent("login", { method: "google_start" });
        loginWithGoogle();
      }}
      onLocalSignIn={() => {
        if (!nameInput.trim()) return;
        trackEvent("login", { method: "name" });
        signIn(nameInput);
        window.location.reload();
      }}
      onSignOut={async () => {
        if (auth.authenticated) await logoutGoogle();
        else signOut();
        window.location.reload();
      }}
      onDeleteTripHistory={() => void deleteTripHistory()}
      onClearAllData={() => void clearAllData()}
      onDeleteAccount={() => void deleteAccount()}
    />,
    document.body,
  );
}
