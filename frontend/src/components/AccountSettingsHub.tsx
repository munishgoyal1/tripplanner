import { useState } from "react";
import {
  BarChart3,
  Check,
  CircleUserRound,
  FileText,
  LogOut,
  ShieldCheck,
  SlidersHorizontal,
  UsersRound,
  X,
} from "lucide-react";
import type { AuthSession } from "../api";
import { AnalyticsPreferences } from "./AnalyticsConsent";
import SettingsModal from "./SettingsModal";
import TravelDocumentsVault from "./TravelDocumentsVault";
import TravellerProfile from "./TravellerProfile";

export type AccountDestination = "menu" | "profile" | "travel" | "family" | "documents" | "analytics" | "privacy";
/** The rail always shows every reachable section; "menu" only exists for callers that don't name one. */
type Section = Exclude<AccountDestination, "menu">;

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

const SECTIONS: { id: Section; label: string; detail: string; icon: typeof CircleUserRound }[] = [
  { id: "profile", label: "Profile and sign-in", detail: "Identity and account access", icon: CircleUserRound },
  { id: "travel", label: "Travel profile", detail: "Pace, budget, food, stays, and flights", icon: SlidersHorizontal },
  { id: "family", label: "Travellers", detail: "Family facts learned while planning", icon: UsersRound },
  { id: "documents", label: "Travel documents", detail: "Passports, visas, and details reused by every trip", icon: FileText },
  { id: "analytics", label: "Analytics preferences", detail: "Anonymous product analytics choice", icon: BarChart3 },
  { id: "privacy", label: "Privacy and data", detail: "History, erasure, and account deletion", icon: ShieldCheck },
];

function SectionRail({ active, onSelect }: { active: Section; onSelect: (id: Section) => void }) {
  return (
    <nav aria-label="Profile sections" className="flex shrink-0 gap-1 overflow-x-auto border-b border-slate-200 bg-slate-50/60 p-2 lg:w-64 lg:flex-col lg:gap-0.5 lg:overflow-visible lg:border-b-0 lg:border-r lg:p-3">
      {SECTIONS.map(({ id, label, detail, icon: Icon }) => (
        <button
          key={id}
          type="button"
          onClick={() => onSelect(id)}
          className={`flex shrink-0 items-center gap-3 rounded-lg px-3 py-2.5 text-left transition ${
            active === id ? "bg-white shadow-sm ring-1 ring-slate-200" : "hover:bg-white/70"
          }`}
        >
          <Icon size={16} className={active === id ? "shrink-0 text-brand" : "shrink-0 text-slate-400"} aria-hidden />
          <span className="min-w-0">
            <span className="block whitespace-nowrap text-xs font-semibold text-slate-700">{label}</span>
            <span className="mt-0.5 hidden truncate text-[11px] text-slate-400 lg:block">{detail}</span>
          </span>
        </button>
      ))}
    </nav>
  );
}

function SectionHeader({ icon: Icon, eyebrow, title, description }: {
  icon: typeof CircleUserRound;
  eyebrow: string;
  title: string;
  description: string;
}) {
  return (
    <div className="mb-5 flex items-start gap-3">
      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-teal-50 text-teal-700"><Icon size={17} aria-hidden /></span>
      <div>
        <p className="text-[10px] font-bold uppercase text-brand">{eyebrow}</p>
        <h3 className="mt-0.5 text-sm font-semibold text-ink">{title}</h3>
        <p className="mt-1 text-xs leading-relaxed text-slate-500">{description}</p>
      </div>
    </div>
  );
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
  const [destination, setDestination] = useState<Section>(
    initialDestination === "menu" ? "profile" : initialDestination,
  );

  return (
    <aside aria-label="Account settings" className="fixed inset-0 z-[100] flex flex-col bg-white">
      <header className="flex h-14 shrink-0 items-center border-b border-slate-200 px-4 lg:px-6">
        <div className="flex items-center gap-3">
          {auth.picture ? <img src={auth.picture} alt="" referrerPolicy="no-referrer" className="h-8 w-8 rounded-full" /> : <span className="grid h-8 w-8 place-items-center rounded-full bg-brand text-xs font-bold text-white">{(auth.display_name || nameInput || "G").slice(0, 2).toUpperCase()}</span>}
          <div className="min-w-0"><h2 className="truncate text-sm font-semibold text-ink">{auth.authenticated ? auth.display_name || "Signed in" : localIdentityActive ? nameInput || "Local traveler" : "Guest traveler"}</h2><p className="truncate text-[11px] text-slate-400">{auth.email || (localIdentityActive ? "Local identity" : "Sign in to sync across devices")}</p></div>
        </div>
        <button type="button" onClick={onClose} className="ml-auto grid h-8 w-8 shrink-0 place-items-center rounded-md text-slate-400 hover:bg-slate-100 hover:text-ink" aria-label="Close account settings"><X size={16} aria-hidden /></button>
      </header>

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <SectionRail active={destination} onSelect={setDestination} />

        <div className="min-h-0 flex-1 overflow-y-auto p-4 lg:p-8">
          <div className="mx-auto max-w-3xl">
            {destination === "profile" && <>
              <SectionHeader icon={CircleUserRound} eyebrow="Identity and access" title="Profile and sign-in" description="Your signed identity owns saved trips, conversations, and travel preferences across supported devices." />
              {auth.authenticated ? <>
                <div className="flex items-center gap-3 rounded-md bg-slate-50 p-3 ring-1 ring-slate-200">
                  {auth.picture ? <img src={auth.picture} alt="" referrerPolicy="no-referrer" className="h-11 w-11 rounded-full" /> : <span className="grid h-11 w-11 place-items-center rounded-full bg-brand text-xs font-bold text-white">{(auth.display_name || "A").slice(0, 2).toUpperCase()}</span>}
                  <div className="min-w-0"><p className="truncate text-sm font-semibold text-ink">{auth.display_name || "Signed in"}</p>{auth.email && <p className="truncate text-xs text-slate-500">{auth.email}</p>}<p className="mt-1 inline-flex items-center gap-1 text-[10px] font-semibold text-emerald-700"><Check size={11} aria-hidden /> Google account connected</p></div>
                </div>
                <button type="button" onClick={onSignOut} disabled={privacyBusy} className="mt-4 inline-flex h-9 items-center gap-2 rounded-md px-3 text-xs font-semibold text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50 disabled:opacity-50"><LogOut size={14} aria-hidden /> Sign out</button>
              </> : <div className="space-y-3">
                {googleEnabled && <button type="button" onClick={onGoogleSignIn} className="flex h-10 w-full items-center justify-center rounded-md bg-white text-xs font-semibold text-slate-700 ring-1 ring-slate-300 hover:bg-slate-50">Sign in with Google</button>}
                <div><label htmlFor="account-display-name" className="text-xs font-semibold text-slate-600">Display name</label><input id="account-display-name" value={nameInput} onChange={(event) => onNameInputChange(event.target.value)} onKeyDown={(event) => event.key === "Enter" && nameInput.trim() && onLocalSignIn()} className="mt-1 h-9 w-full rounded-md border border-slate-200 px-3 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/20" placeholder="Your name" /></div>
                <div className="flex items-center gap-2"><button type="button" onClick={onLocalSignIn} disabled={!nameInput.trim()} className="h-9 rounded-md bg-brand px-4 text-xs font-semibold text-white disabled:opacity-40">{localIdentityActive ? "Update name" : "Sign in"}</button>{localIdentityActive && <button type="button" onClick={onSignOut} className="h-9 rounded-md px-3 text-xs font-semibold text-slate-500 hover:bg-slate-50">Sign out</button>}</div>
              </div>}
              <div className="mt-6 border-t border-slate-100 pt-5">
                <p className="mb-3 text-xs font-semibold uppercase text-brand">Display defaults</p>
                <SettingsModal embedded onClose={() => setDestination("profile")} />
              </div>
            </>}

            {destination === "travel" && <>
              <SectionHeader icon={SlidersHorizontal} eyebrow="Reusable defaults" title="Travel profile" description="Keep your travel style and preferences available for future plans. A single trip can still override any of them." />
              <SettingsModal embedded onClose={() => setDestination("travel")} />
            </>}

            {destination === "family" && <>
              <SectionHeader icon={UsersRound} eyebrow="People, not a nested block" title="Travellers" description="Facts about who you usually travel with, noticed in chat and confirmed before they become durable." />
              <TravellerProfile />
            </>}

            {destination === "documents" && <>
              <SectionHeader icon={FileText} eyebrow="Account · used by every trip" title="Travel documents" description="Details belong to you, not to one trip. Each trip only shows the gaps." />
              <TravelDocumentsVault />
            </>}

            {destination === "analytics" && <AnalyticsPreferences onBack={() => setDestination("profile")} />}

            {destination === "privacy" && <>
              <SectionHeader icon={ShieldCheck} eyebrow="Your data" title="Privacy and data" description="Control persisted trip, conversation, preference, and account data. Destructive actions require confirmation." />
              <div className="divide-y divide-slate-100 rounded-md ring-1 ring-slate-200">
                <button type="button" onClick={onDeleteTripHistory} disabled={privacyBusy} className="w-full p-3 text-left hover:bg-slate-50 disabled:opacity-50"><span className="block text-xs font-semibold text-slate-700">Delete trip and chat history</span><span className="mt-1 block text-[11px] leading-relaxed text-slate-400">Remove saved trips and related conversations while retaining your account and travel profile.</span></button>
                <button type="button" onClick={onClearAllData} disabled={privacyBusy} className="w-full p-3 text-left hover:bg-rose-50 disabled:opacity-50"><span className="block text-xs font-semibold text-rose-700">Clear all app data</span><span className="mt-1 block text-[11px] leading-relaxed text-slate-400">Erase trips, conversations, and preferences while retaining sign-in access.</span></button>
                <button type="button" onClick={onDeleteAccount} disabled={privacyBusy} className="w-full p-3 text-left hover:bg-rose-50 disabled:opacity-50"><span className="block text-xs font-semibold text-rose-800">Delete account data</span><span className="mt-1 block text-[11px] leading-relaxed text-slate-400">Erase all app data and disconnect this account. This cannot be undone.</span></button>
              </div>
            </>}
          </div>
        </div>
      </div>
    </aside>
  );
}
