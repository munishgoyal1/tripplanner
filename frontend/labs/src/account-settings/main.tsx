import React, { useState } from "react";
import ReactDOM from "react-dom/client";
import {
  ArrowLeft,
  BarChart3,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleUserRound,
  LogOut,
  Map,
  MessageCircle,
  PanelLeft,
  PanelRight,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  UserRound,
  X,
} from "lucide-react";
import "../../../src/index.css";
import { DecisionCapture } from "../shared/DecisionCapture";
import { LabScope } from "../shared/LabScope";
import "../shared/experiment-layout.css";

type VariantId = "unified-menu" | "split-ownership" | "account-hub";
type Surface = "closed" | "account" | "settings";
type AnalyticsPreference = "granted" | "denied";

interface Variant {
  id: VariantId;
  label: string;
  summary: string;
  rationale: string;
}

const variants: Variant[] = [
  {
    id: "unified-menu",
    label: "A · Unified account menu",
    summary: "One avatar owns identity, travel profile, analytics, privacy, and sign-out.",
    rationale: "Removes the redundant gear and keeps all person-level controls in one compact menu.",
  },
  {
    id: "split-ownership",
    label: "B · Clear account/settings split",
    summary: "Profile owns identity only; Settings owns preferences, analytics, and privacy.",
    rationale: "Retains two familiar icons but removes every duplicated destination between them.",
  },
  {
    id: "account-hub",
    label: "C · Account settings hub",
    summary: "One labeled identity command opens a larger, sectioned settings sheet.",
    rationale: "Most scalable for future controls, with a larger interaction footprint than a popover.",
  },
];

function AnalyticsPreferences({
  preference,
  onChange,
  onBack,
}: {
  preference: AnalyticsPreference;
  onChange: (preference: AnalyticsPreference) => void;
  onBack: () => void;
}) {
  return (
    <div data-lab-change="Working Analytics preferences destination" className="p-4">
      <button type="button" onClick={onBack} className="inline-flex items-center gap-1 text-xs font-semibold text-slate-500 hover:text-ink">
        <ChevronLeft size={13} aria-hidden /> Back
      </button>
      <div className="mt-4 flex items-start gap-3">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-teal-50 text-teal-700"><BarChart3 size={17} aria-hidden /></span>
        <div>
          <h3 className="text-sm font-semibold text-ink">Anonymous usage analytics</h3>
          <p className="mt-1 text-xs leading-relaxed text-slate-500">Choose whether anonymous interaction events help improve the planning flow. Trip details, messages, identity, and shared links are never sent.</p>
        </div>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-2" role="group" aria-label="Analytics preference">
        {(["denied", "granted"] as const).map((value) => (
          <button
            key={value}
            type="button"
            onClick={() => onChange(value)}
            aria-pressed={preference === value}
            className={`flex h-10 items-center justify-center gap-1.5 rounded-md text-xs font-semibold ring-1 ${preference === value ? "bg-ink text-white ring-ink" : "bg-white text-slate-600 ring-slate-200 hover:ring-slate-300"}`}
          >
            {preference === value && <Check size={13} aria-hidden />}
            {value === "granted" ? "Allow analytics" : "No thanks"}
          </button>
        ))}
      </div>
      <p role="status" className="mt-3 text-[11px] text-emerald-700">Preference set to {preference === "granted" ? "allowed" : "not allowed"}. This control remains available even when analytics collection is not configured.</p>
    </div>
  );
}

function MenuRow({ icon: Icon, label, detail, onClick }: { icon: typeof UserRound; label: string; detail?: string; onClick?: () => void }) {
  return (
    <button type="button" onClick={onClick} className="flex w-full items-center gap-3 px-3 py-2.5 text-left hover:bg-slate-50">
      <Icon size={15} className="shrink-0 text-slate-400" aria-hidden />
      <span className="min-w-0 flex-1"><span className="block text-xs font-semibold text-slate-700">{label}</span>{detail && <span className="mt-0.5 block text-[10px] text-slate-400">{detail}</span>}</span>
      <ChevronRight size={13} className="shrink-0 text-slate-300" aria-hidden />
    </button>
  );
}

function IdentityHeader() {
  return (
    <div className="flex items-center gap-3 border-b border-slate-100 p-3">
      <span className="grid h-9 w-9 place-items-center rounded-full bg-brand text-xs font-bold text-white">MG</span>
      <span className="min-w-0"><span className="block truncate text-xs font-semibold text-ink">Munish Goyal</span><span className="block truncate text-[10px] text-slate-400">munish@example.com</span></span>
    </div>
  );
}

function UnifiedMenu({ analyticsOpen, openAnalytics, closeAnalytics, preference, setPreference }: { analyticsOpen: boolean; openAnalytics: () => void; closeAnalytics: () => void; preference: AnalyticsPreference; setPreference: (preference: AnalyticsPreference) => void }) {
  return (
    <div className="absolute right-3 top-12 z-30 w-80 overflow-hidden rounded-md bg-white shadow-pop ring-1 ring-slate-200">
      {analyticsOpen ? <AnalyticsPreferences preference={preference} onChange={setPreference} onBack={closeAnalytics} /> : <>
        <IdentityHeader />
        <div className="divide-y divide-slate-100">
          <MenuRow icon={SlidersHorizontal} label="Travel profile" detail="Preferences, family, pace, and accessibility" />
          <MenuRow icon={BarChart3} label="Analytics preferences" detail={preference === "granted" ? "Anonymous analytics allowed" : "Anonymous analytics off"} onClick={openAnalytics} />
          <MenuRow icon={ShieldCheck} label="Privacy and data" detail="History, exports, and deletion" />
        </div>
        <button type="button" className="flex w-full items-center gap-2 border-t border-slate-100 px-3 py-2.5 text-xs font-semibold text-slate-500 hover:bg-slate-50"><LogOut size={14} aria-hidden /> Sign out</button>
      </>}
    </div>
  );
}

function SplitMenu({ surface, analyticsOpen, openAnalytics, closeAnalytics, preference, setPreference }: { surface: Surface; analyticsOpen: boolean; openAnalytics: () => void; closeAnalytics: () => void; preference: AnalyticsPreference; setPreference: (preference: AnalyticsPreference) => void }) {
  return (
    <div className="absolute right-3 top-12 z-30 w-80 overflow-hidden rounded-md bg-white shadow-pop ring-1 ring-slate-200">
      {analyticsOpen ? <AnalyticsPreferences preference={preference} onChange={setPreference} onBack={closeAnalytics} /> : surface === "account" ? <>
        <IdentityHeader />
        <button type="button" className="flex w-full items-center gap-2 px-3 py-2.5 text-xs font-semibold text-slate-500 hover:bg-slate-50"><LogOut size={14} aria-hidden /> Sign out</button>
      </> : <>
        <div className="border-b border-slate-100 px-3 py-3"><p className="text-[10px] font-bold uppercase text-brand">Settings</p><h3 className="mt-0.5 text-sm font-semibold text-ink">Personalization and privacy</h3></div>
        <MenuRow icon={SlidersHorizontal} label="Travel profile" detail="Preferences, family, pace, and accessibility" />
        <MenuRow icon={BarChart3} label="Analytics preferences" detail={preference === "granted" ? "Anonymous analytics allowed" : "Anonymous analytics off"} onClick={openAnalytics} />
        <MenuRow icon={ShieldCheck} label="Privacy and data" detail="History, exports, and deletion" />
      </>}
    </div>
  );
}

function AccountHub({ analyticsOpen, openAnalytics, closeAnalytics, preference, setPreference, close }: { analyticsOpen: boolean; openAnalytics: () => void; closeAnalytics: () => void; preference: AnalyticsPreference; setPreference: (preference: AnalyticsPreference) => void; close: () => void }) {
  return (
    <div className="absolute inset-y-0 right-0 z-30 w-[23rem] border-l border-slate-200 bg-white shadow-pop">
      <div className="flex h-12 items-center border-b border-slate-200 px-4"><h3 className="text-sm font-semibold text-ink">Account settings</h3><button type="button" onClick={close} className="ml-auto grid h-7 w-7 place-items-center rounded text-slate-400 hover:bg-slate-100" aria-label="Close account settings"><X size={15} aria-hidden /></button></div>
      {analyticsOpen ? <AnalyticsPreferences preference={preference} onChange={setPreference} onBack={closeAnalytics} /> : <>
        <IdentityHeader />
        <nav className="divide-y divide-slate-100" aria-label="Account settings sections">
          <MenuRow icon={CircleUserRound} label="Profile and sign-in" detail="Identity and account access" />
          <MenuRow icon={SlidersHorizontal} label="Travel profile" detail="Preferences, family, pace, and accessibility" />
          <MenuRow icon={BarChart3} label="Analytics preferences" detail={preference === "granted" ? "Anonymous analytics allowed" : "Anonymous analytics off"} onClick={openAnalytics} />
          <MenuRow icon={ShieldCheck} label="Privacy and data" detail="History, exports, and deletion" />
        </nav>
      </>}
    </div>
  );
}

function WorkspaceContext() {
  const panes = [{ label: "Itinerary", icon: PanelLeft }, { label: "Map", icon: Map }, { label: "Details", icon: PanelRight }];
  return (
    <div className="grid h-[21rem] grid-cols-[0.9fr_1.35fr_0.9fr] gap-2 p-2">
      {panes.map(({ label, icon: Icon }) => <section key={label} className="flex min-w-0 flex-col overflow-hidden rounded-md bg-white ring-1 ring-slate-200"><header className="flex h-9 items-center gap-2 border-b border-slate-100 px-3"><Icon size={13} className="text-slate-400" aria-hidden /><h3 className="text-[11px] font-semibold text-slate-700">{label}</h3></header><div className="grid flex-1 place-items-center bg-[linear-gradient(135deg,#fff_0%,#f8fafc_100%)] text-[10px] text-slate-300">Existing {label} workspace</div></section>)}
    </div>
  );
}

function Preview({ variant }: { variant: VariantId }) {
  const [surface, setSurface] = useState<Surface>(variant === "split-ownership" ? "settings" : "account");
  const [analyticsOpen, setAnalyticsOpen] = useState(false);
  const [preference, setPreference] = useState<AnalyticsPreference>("denied");
  const closeAnalytics = () => setAnalyticsOpen(false);
  const toggleSurface = (next: Surface) => {
    setAnalyticsOpen(false);
    setSurface((current) => current === next ? "closed" : next);
  };
  return (
    <div className="relative overflow-hidden rounded-md bg-slate-50 shadow-card ring-1 ring-slate-200" style={{ minWidth: 760 }}>
      <header className="relative z-20 flex h-12 items-center gap-2 border-b border-slate-200 bg-white px-3">
        <button type="button" className="flex min-w-32 items-center gap-2 text-left"><span className="grid h-7 w-7 place-items-center rounded bg-brand text-[10px] font-bold text-white">R</span><span><span className="block text-[11px] font-semibold text-ink">Rajasthan · Oct 2026</span><span className="block text-[9px] text-emerald-700">Plan updated</span></span></button>
        <div className="mr-auto flex items-center gap-1"><span className="grid h-8 w-8 place-items-center rounded-md bg-slate-100 text-slate-500"><PanelLeft size={14} aria-hidden /></span><span className="grid h-8 w-8 place-items-center rounded-md bg-slate-100 text-slate-500"><Map size={14} aria-hidden /></span><span className="grid h-8 w-8 place-items-center rounded-md bg-slate-100 text-slate-500"><PanelRight size={14} aria-hidden /></span><span className="grid h-8 w-8 place-items-center rounded-md text-slate-400"><MessageCircle size={14} aria-hidden /></span></div>
        <div data-lab-change="Account and settings command ownership" className="flex items-center gap-1">
          {variant === "unified-menu" && <button type="button" onClick={() => toggleSurface("account")} aria-expanded={surface === "account"} className={`relative grid h-8 w-8 place-items-center rounded-md ${surface === "account" ? "bg-ink text-white" : "text-slate-500 hover:bg-slate-50"}`} aria-label="Account and settings"><UserRound size={15} aria-hidden /><span className="absolute bottom-1 right-1 h-1.5 w-1.5 rounded-full bg-emerald-500 ring-1 ring-white" /></button>}
          {variant === "split-ownership" && <><button type="button" onClick={() => toggleSurface("account")} aria-expanded={surface === "account"} className={`grid h-8 w-8 place-items-center rounded-md ${surface === "account" ? "bg-ink text-white" : "text-slate-500 hover:bg-slate-50"}`} aria-label="Profile"><UserRound size={15} aria-hidden /></button><button type="button" onClick={() => toggleSurface("settings")} aria-expanded={surface === "settings"} className={`grid h-8 w-8 place-items-center rounded-md ${surface === "settings" ? "bg-ink text-white" : "text-slate-500 hover:bg-slate-50"}`} aria-label="Settings"><Settings size={15} aria-hidden /></button></>}
          {variant === "account-hub" && <button type="button" onClick={() => toggleSurface("account")} aria-expanded={surface === "account"} className={`inline-flex h-8 items-center gap-2 rounded-md px-2.5 text-xs font-semibold ${surface === "account" ? "bg-ink text-white" : "text-slate-600 hover:bg-slate-50"}`}><span className="grid h-5 w-5 place-items-center rounded-full bg-brand text-[9px] font-bold text-white">MG</span> Munish <ChevronDown size={12} aria-hidden /></button>}
        </div>
      </header>
      <WorkspaceContext />
      {surface !== "closed" && variant === "unified-menu" && <UnifiedMenu analyticsOpen={analyticsOpen} openAnalytics={() => setAnalyticsOpen(true)} closeAnalytics={closeAnalytics} preference={preference} setPreference={setPreference} />}
      {surface !== "closed" && variant === "split-ownership" && <SplitMenu surface={surface} analyticsOpen={analyticsOpen} openAnalytics={() => setAnalyticsOpen(true)} closeAnalytics={closeAnalytics} preference={preference} setPreference={setPreference} />}
      {surface !== "closed" && variant === "account-hub" && <AccountHub analyticsOpen={analyticsOpen} openAnalytics={() => setAnalyticsOpen(true)} closeAnalytics={closeAnalytics} preference={preference} setPreference={setPreference} close={() => setSurface("closed")} />}
    </div>
  );
}

function Lab() {
  const [active, setActive] = useState<VariantId>("unified-menu");
  const selected = variants.find((variant) => variant.id === active)!;
  return (
    <main className="min-h-full bg-[linear-gradient(180deg,#f8fafc_0,#fafaf9_22rem)] px-4 py-6 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl">
        <header className="border-b border-slate-200 pb-5">
          <a href="./catalog.html" className="inline-flex items-center gap-1 text-xs font-semibold text-slate-500 hover:text-brand"><ArrowLeft size={14} aria-hidden /> Back to All Labs</a>
          <div className="mt-4 flex items-center gap-2 text-brand"><CircleUserRound size={15} aria-hidden /><p className="text-xs font-bold uppercase">Active experiment · Account controls</p></div>
          <h1 className="display mt-1 text-3xl font-semibold text-ink">Account and settings ownership</h1>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-600">Compare how identity, travel preferences, analytics consent, privacy, and sign-out should be grouped without duplicating Account and Settings destinations. Each option makes Analytics preferences a working, inspectable destination.</p>
        </header>

        <LabScope labId="account-settings" />

        <div className="lab-variant-grid mt-5" role="tablist" aria-label="Account and settings variants">
          {variants.map((variant) => <button key={variant.id} type="button" role="tab" aria-selected={active === variant.id} onClick={() => setActive(variant.id)} className={`rounded-md p-3 text-left ring-1 transition ${active === variant.id ? "bg-white shadow-card ring-brand/30" : "bg-white/70 ring-slate-200 hover:bg-white"}`}><span className="text-sm font-semibold text-ink">{variant.label}</span><span className="mt-1 block text-xs leading-relaxed text-slate-500">{variant.summary}</span></button>)}
        </div>

        <section className="mt-6" aria-labelledby="account-settings-preview">
          <div className="mb-3 flex flex-wrap items-end justify-between gap-3"><div><p className="text-[10px] font-bold uppercase text-slate-400">Interactive workspace preview</p><h2 id="account-settings-preview" className="mt-0.5 text-lg font-semibold text-ink">{selected.label}</h2></div><p className="max-w-xl text-right text-xs text-slate-500">{selected.rationale}</p></div>
          <div className="overflow-x-auto pb-2"><Preview key={active} variant={active} /></div>
        </section>

        <div className="mt-6"><DecisionCapture labId="account-settings" labTitle="Account and settings ownership" options={variants} activeOption={active} onChoose={(id) => setActive(id as VariantId)} /></div>
      </div>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><Lab /></React.StrictMode>);