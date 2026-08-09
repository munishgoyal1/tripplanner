import { useState } from "react";
import {
  BarChart3,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleUserRound,
  FileText,
  LogOut,
  ShieldCheck,
  SlidersHorizontal,
  X,
} from "lucide-react";
import type { AuthSession } from "../api";
import { AnalyticsPreferences } from "./AnalyticsConsent";
import SettingsModal from "./SettingsModal";
import TravelDocumentsVault from "./TravelDocumentsVault";

export type AccountDestination = "menu" | "profile" | "travel" | "documents" | "analytics" | "privacy";

interface Props {
  auth: AuthSession;
  googleEnabled: boolean;
  localIdentityActive: boolean;
  nameInput: string;
  privacyBusy: boolean;
  initialDestination?: AccountDestination;
  onNameInputChange: (value: string) => void;
  onClose: () => void;
  onGoogleSignIn: () => void;
  onLocalSignIn: () => void;
  onSignOut: () => void;
  onDeleteTripHistory: () => void;
  onClearAllData: () => void;
  onDeleteAccount: () => void;
}

function MenuRow({ icon: Icon, label, detail, onClick }: {
  icon: typeof CircleUserRound;
  label: string;
  detail: string;
  onClick: () => void;
}) {
  return (
    <button type="button" onClick={onClick} className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-slate-50">
      <Icon size={16} className="shrink-0 text-slate-400" aria-hidden />
      <span className="min-w-0 flex-1">
        <span className="block text-xs font-semibold text-slate-700">{label}</span>
        <span className="mt-0.5 block text-[11px] text-slate-400">{detail}</span>
      </span>
      <ChevronRight size={14} className="shrink-0 text-slate-300" aria-hidden />
    </button>
  );
}

function BackButton({ onClick }: { onClick: () => void }) {
  return <button type="button" onClick={onClick} className="inline-flex items-center gap-1 text-xs font-semibold text-slate-500 hover:text-ink"><ChevronLeft size={14} aria-hidden /> Back to settings</button>;
}

export default function AccountSettingsHub({
  auth,
  googleEnabled,
  localIdentityActive,
  nameInput,
  privacyBusy,
  initialDestination = "menu",
  onNameInputChange,
  onClose,
  onGoogleSignIn,
  onLocalSignIn,
  onSignOut,
  onDeleteTripHistory,
  onClearAllData,
  onDeleteAccount,
}: Props) {
  const [destination, setDestination] = useState<AccountDestination>(initialDestination);

  return (
    <aside aria-label="Account settings" className="fixed inset-y-0 right-0 z-[100] flex w-full max-w-sm flex-col border-l border-slate-200 bg-white shadow-xl">
      <header className="flex h-14 shrink-0 items-center border-b border-slate-200 px-4">
        <h2 className="text-sm font-semibold text-ink">Account settings</h2>
        <button type="button" onClick={onClose} className="ml-auto grid h-8 w-8 place-items-center rounded-md text-slate-400 hover:bg-slate-100 hover:text-ink" aria-label="Close account settings"><X size={16} aria-hidden /></button>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {destination === "menu" && <>
          <div className="flex items-center gap-3 border-b border-slate-100 p-4">
            {auth.picture ? <img src={auth.picture} alt="" referrerPolicy="no-referrer" className="h-10 w-10 rounded-full" /> : <span className="grid h-10 w-10 place-items-center rounded-full bg-brand text-xs font-bold text-white">{(auth.display_name || nameInput || "G").slice(0, 2).toUpperCase()}</span>}
            <span className="min-w-0"><span className="block truncate text-xs font-semibold text-ink">{auth.authenticated ? auth.display_name || "Signed in" : localIdentityActive ? nameInput || "Local traveler" : "Guest traveler"}</span><span className="block truncate text-[11px] text-slate-400">{auth.email || (localIdentityActive ? "Local identity" : "Sign in to sync across devices")}</span></span>
          </div>
          <nav className="divide-y divide-slate-100" aria-label="Account settings sections">
            <MenuRow icon={CircleUserRound} label="Profile and sign-in" detail="Identity and account access" onClick={() => setDestination("profile")} />
            <MenuRow icon={SlidersHorizontal} label="Travel profile" detail="Preferences, travel style, and accessibility" onClick={() => setDestination("travel")} />
            <MenuRow icon={FileText} label="Travel documents" detail="Passports, visas, and details reused by every trip" onClick={() => setDestination("documents")} />
            <MenuRow icon={BarChart3} label="Analytics preferences" detail="Anonymous product analytics choice" onClick={() => setDestination("analytics")} />
            <MenuRow icon={ShieldCheck} label="Privacy and data" detail="History, erasure, and account deletion" onClick={() => setDestination("privacy")} />
          </nav>
        </>}

        {destination === "profile" && <div className="p-4">
          <BackButton onClick={() => setDestination("menu")} />
          <div className="mt-4 flex items-start gap-3"><span className="grid h-9 w-9 place-items-center rounded-md bg-teal-50 text-teal-700"><CircleUserRound size={17} aria-hidden /></span><div><p className="text-[10px] font-bold uppercase text-brand">Identity and access</p><h3 className="mt-0.5 text-sm font-semibold text-ink">Profile and sign-in</h3><p className="mt-1 text-xs leading-relaxed text-slate-500">Your signed identity owns saved trips, conversations, and travel preferences across supported devices.</p></div></div>
          {auth.authenticated ? <>
            <div className="mt-4 flex items-center gap-3 rounded-md bg-slate-50 p-3 ring-1 ring-slate-200">
              {auth.picture ? <img src={auth.picture} alt="" referrerPolicy="no-referrer" className="h-11 w-11 rounded-full" /> : <span className="grid h-11 w-11 place-items-center rounded-full bg-brand text-xs font-bold text-white">{(auth.display_name || "A").slice(0, 2).toUpperCase()}</span>}
              <div className="min-w-0"><p className="truncate text-sm font-semibold text-ink">{auth.display_name || "Signed in"}</p>{auth.email && <p className="truncate text-xs text-slate-500">{auth.email}</p>}<p className="mt-1 inline-flex items-center gap-1 text-[10px] font-semibold text-emerald-700"><Check size={11} aria-hidden /> Google account connected</p></div>
            </div>
            <button type="button" onClick={onSignOut} disabled={privacyBusy} className="mt-4 inline-flex h-9 items-center gap-2 rounded-md px-3 text-xs font-semibold text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50 disabled:opacity-50"><LogOut size={14} aria-hidden /> Sign out</button>
          </> : <div className="mt-4 space-y-3">
            {googleEnabled && <button type="button" onClick={onGoogleSignIn} className="flex h-10 w-full items-center justify-center rounded-md bg-white text-xs font-semibold text-slate-700 ring-1 ring-slate-300 hover:bg-slate-50">Sign in with Google</button>}
            <div><label htmlFor="account-display-name" className="text-xs font-semibold text-slate-600">Display name</label><input id="account-display-name" value={nameInput} onChange={(event) => onNameInputChange(event.target.value)} onKeyDown={(event) => event.key === "Enter" && nameInput.trim() && onLocalSignIn()} className="mt-1 h-9 w-full rounded-md border border-slate-200 px-3 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/20" placeholder="Your name" /></div>
            <div className="flex items-center gap-2"><button type="button" onClick={onLocalSignIn} disabled={!nameInput.trim()} className="h-9 rounded-md bg-brand px-4 text-xs font-semibold text-white disabled:opacity-40">{localIdentityActive ? "Update name" : "Sign in"}</button>{localIdentityActive && <button type="button" onClick={onSignOut} className="h-9 rounded-md px-3 text-xs font-semibold text-slate-500 hover:bg-slate-50">Sign out</button>}</div>
          </div>}
          <div className="mt-5 border-t border-slate-100 pt-4">
            <p className="mb-2 text-xs font-semibold uppercase text-brand">Display defaults</p>
            <SettingsModal embedded onClose={() => setDestination("menu")} />
          </div>
        </div>}

        {destination === "travel" && <div className="p-4">
          <BackButton onClick={() => setDestination("menu")} />
          <div className="mt-4 flex items-start gap-3"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-teal-50 text-teal-700"><SlidersHorizontal size={17} aria-hidden /></span><div><p className="text-[10px] font-bold uppercase text-brand">Reusable defaults</p><h3 className="mt-0.5 text-sm font-semibold text-ink">Travel profile</h3><p className="mt-1 text-xs leading-relaxed text-slate-500">Keep your travel style and preferences available for future plans.</p></div></div>
          <div className="mt-4"><SettingsModal embedded onClose={() => setDestination("menu")} /></div>
        </div>}

        {destination === "documents" && <div className="flex min-h-full flex-col p-4">
          <BackButton onClick={() => setDestination("menu")} />
          <div className="mt-4 flex items-start gap-3"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-teal-50 text-teal-700"><FileText size={17} aria-hidden /></span><div><p className="text-[10px] font-bold uppercase text-brand">Account · used by every trip</p><h3 className="mt-0.5 text-sm font-semibold text-ink">Travel documents</h3><p className="mt-1 text-xs leading-relaxed text-slate-500">Details belong to you, not to one trip. Each trip only shows the gaps.</p></div></div>
          <div className="mt-4 flex min-h-0 flex-1 flex-col"><TravelDocumentsVault /></div>
        </div>}

        {destination === "analytics" && <AnalyticsPreferences onBack={() => setDestination("menu")} />}

        {destination === "privacy" && <div className="p-4">
          <BackButton onClick={() => setDestination("menu")} />
          <div className="mt-4 flex items-start gap-3"><span className="grid h-9 w-9 place-items-center rounded-md bg-teal-50 text-teal-700"><ShieldCheck size={17} aria-hidden /></span><div><p className="text-[10px] font-bold uppercase text-brand">Your data</p><h3 className="mt-0.5 text-sm font-semibold text-ink">Privacy and data</h3><p className="mt-1 text-xs leading-relaxed text-slate-500">Control persisted trip, conversation, preference, and account data. Destructive actions require confirmation.</p></div></div>
          <div className="mt-4 divide-y divide-slate-100 rounded-md ring-1 ring-slate-200">
            <button type="button" onClick={onDeleteTripHistory} disabled={privacyBusy} className="w-full p-3 text-left hover:bg-slate-50 disabled:opacity-50"><span className="block text-xs font-semibold text-slate-700">Delete trip and chat history</span><span className="mt-1 block text-[11px] leading-relaxed text-slate-400">Remove saved trips and related conversations while retaining your account and travel profile.</span></button>
            <button type="button" onClick={onClearAllData} disabled={privacyBusy} className="w-full p-3 text-left hover:bg-rose-50 disabled:opacity-50"><span className="block text-xs font-semibold text-rose-700">Clear all app data</span><span className="mt-1 block text-[11px] leading-relaxed text-slate-400">Erase trips, conversations, and preferences while retaining sign-in access.</span></button>
            <button type="button" onClick={onDeleteAccount} disabled={privacyBusy} className="w-full p-3 text-left hover:bg-rose-50 disabled:opacity-50"><span className="block text-xs font-semibold text-rose-800">Delete account data</span><span className="mt-1 block text-[11px] leading-relaxed text-slate-400">Erase all app data and disconnect this account. This cannot be undone.</span></button>
          </div>
        </div>}
      </div>
    </aside>
  );
}