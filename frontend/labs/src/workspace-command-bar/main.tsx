import React, { useState } from "react";
import ReactDOM from "react-dom/client";
import {
  ArrowLeft,
  Check,
  ChevronDown,
  EyeOff,
  Focus,
  LayoutGrid,
  Map,
  Maximize2,
  MessageCircle,
  Minimize2,
  MoreHorizontal,
  PanelLeft,
  PanelRight,
  Plus,
  RotateCcw,
  Settings,
  UserRound,
} from "lucide-react";
import "../../../src/index.css";
import { DecisionCapture } from "../shared/DecisionCapture";
import { LabScope } from "../shared/LabScope";
import "../shared/experiment-layout.css";

type PaneId = "itinerary" | "map" | "details" | "assistant";
type VariantId = "direct" | "segmented" | "layout-menu";

type Visibility = Record<PaneId, boolean>;

interface Variant {
  id: VariantId;
  label: string;
  shortLabel: string;
  summary: string;
  rationale: string;
}

const variants: Variant[] = [
  {
    id: "direct",
    label: "A · Direct pane toggles",
    shortLabel: "Direct",
    summary: "Every pane remains one click away in the command bar.",
    rationale: "Fastest for repeated expert use, but the row carries the most controls.",
  },
  {
    id: "segmented",
    label: "B · Segmented view group",
    shortLabel: "Segmented",
    summary: "Pane visibility reads as one coherent workspace mode control.",
    rationale: "Best balance of scan speed, explicit state, and compact width.",
  },
  {
    id: "layout-menu",
    label: "C · Layout popover",
    shortLabel: "Layout menu",
    summary: "One Layout command opens visibility and focus controls together.",
    rationale: "Calmest top row, but pane changes require opening a menu first.",
  },
];

const panes: Array<{ id: PaneId; label: string; icon: typeof Map; tone: string }> = [
  { id: "itinerary", label: "Itinerary", icon: PanelLeft, tone: "bg-rose-50 text-brand" },
  { id: "map", label: "Map", icon: Map, tone: "bg-teal-50 text-accent" },
  { id: "details", label: "Details", icon: PanelRight, tone: "bg-amber-50 text-amber-700" },
  { id: "assistant", label: "Assistant", icon: MessageCircle, tone: "bg-sky-50 text-sky-700" },
];

const initialVisibility: Visibility = {
  itinerary: true,
  map: true,
  details: true,
  assistant: false,
};

function IconButton({
  label,
  active = false,
  disabled = false,
  onClick,
  children,
  className = "",
}: {
  label: string;
  active?: boolean;
  disabled?: boolean;
  onClick?: () => void;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      aria-pressed={active}
      disabled={disabled}
      onClick={onClick}
      className={`grid h-8 w-8 shrink-0 place-items-center rounded-md ring-1 transition disabled:cursor-not-allowed disabled:opacity-30 ${
        active
          ? "bg-slate-900 text-white ring-slate-900"
          : "bg-white text-slate-500 ring-slate-200 hover:bg-slate-50 hover:text-ink"
      } ${className}`}
    >
      {children}
    </button>
  );
}

function GlobalActions() {
  return (
    <div className="flex items-center gap-1">
      <IconButton label="Trip actions"><MoreHorizontal size={15} aria-hidden /></IconButton>
      <IconButton label="Account"><UserRound size={15} aria-hidden /></IconButton>
      <IconButton label="Travel preferences"><Settings size={15} aria-hidden /></IconButton>
    </div>
  );
}

function DirectBar({ visibility, toggle }: { visibility: Visibility; toggle: (pane: PaneId) => void }) {
  return (
    <>
      <button data-lab-change="New-trip command representation" type="button" className="inline-flex h-8 items-center gap-1.5 rounded-md bg-brand px-3 text-xs font-semibold text-white">
        <Plus size={14} aria-hidden /> New trip
      </button>
      <div className="mx-1 h-5 w-px bg-slate-200" />
      <div data-lab-change="Pane visibility controls" className="flex items-center gap-1" aria-label="Pane visibility">
        {panes.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => toggle(id)}
            aria-pressed={visibility[id]}
            className={`inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-xs font-medium ring-1 transition ${
              visibility[id] ? "bg-slate-100 text-ink ring-slate-200" : "bg-white text-slate-400 ring-slate-200"
            }`}
          >
            <Icon size={14} aria-hidden /> <span className="hidden xl:inline">{label}</span>
          </button>
        ))}
      </div>
    </>
  );
}

function SegmentedBar({ visibility, toggle }: { visibility: Visibility; toggle: (pane: PaneId) => void }) {
  return (
    <>
      <IconButton label="Start new trip"><Plus size={15} aria-hidden /></IconButton>
      <div data-lab-change="Pane visibility controls" className="flex overflow-hidden rounded-md bg-slate-100 p-0.5 ring-1 ring-slate-200" aria-label="Visible workspace panes">
        {panes.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => toggle(id)}
            aria-label={`${visibility[id] ? "Hide" : "Show"} ${label}`}
            aria-pressed={visibility[id]}
            className={`relative grid h-7 w-8 place-items-center rounded text-xs transition ${
              visibility[id] ? "bg-white text-ink shadow-sm" : "text-slate-400 hover:text-slate-600"
            }`}
            title={`${visibility[id] ? "Hide" : "Show"} ${label}`}
          >
            <Icon size={14} aria-hidden />
            <span className={`absolute bottom-0.5 h-0.5 w-3 rounded-full ${visibility[id] ? "bg-brand" : "bg-transparent"}`} />
          </button>
        ))}
      </div>
    </>
  );
}

function LayoutMenuBar({
  visibility,
  toggle,
  focus,
  menuOpen,
  setMenuOpen,
}: {
  visibility: Visibility;
  toggle: (pane: PaneId) => void;
  focus: (pane: PaneId) => void;
  menuOpen: boolean;
  setMenuOpen: (open: boolean) => void;
}) {
  const visibleCount = panes.filter(({ id }) => visibility[id]).length;
  return (
    <>
      <IconButton label="Start new trip"><Plus size={15} aria-hidden /></IconButton>
      <div data-lab-change="Layout and pane visibility menu" className="relative">
        <button
          type="button"
          onClick={() => setMenuOpen(!menuOpen)}
          aria-expanded={menuOpen}
          className={`inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-xs font-semibold ring-1 ${
            menuOpen ? "bg-slate-900 text-white ring-slate-900" : "bg-white text-slate-700 ring-slate-200"
          }`}
        >
          <LayoutGrid size={14} aria-hidden /> Layout <span className="text-[10px] opacity-60">{visibleCount}</span><ChevronDown size={12} aria-hidden />
        </button>
        {menuOpen && (
          <div className="absolute left-0 top-10 z-30 w-64 rounded-md bg-white p-2 shadow-pop ring-1 ring-slate-200">
            <div className="flex items-center justify-between px-2 pb-2 pt-1">
              <p className="text-[10px] font-bold uppercase text-slate-400">Workspace panes</p>
              <button type="button" onClick={() => panes.forEach(({ id }) => !visibility[id] && toggle(id))} className="text-[10px] font-semibold text-brand">Show all</button>
            </div>
            {panes.map(({ id, label, icon: Icon }) => (
              <div key={id} className="flex items-center gap-2 rounded px-2 py-1.5 hover:bg-slate-50">
                <button type="button" onClick={() => toggle(id)} className="flex min-w-0 flex-1 items-center gap-2 text-left text-xs font-medium text-slate-700">
                  <span className={`grid h-5 w-5 place-items-center rounded ring-1 ${visibility[id] ? "bg-brand text-white ring-brand" : "bg-white text-transparent ring-slate-200"}`}><Check size={12} aria-hidden /></span>
                  <Icon size={14} className="text-slate-400" aria-hidden /> {label}
                </button>
                <button type="button" onClick={() => focus(id)} className="grid h-6 w-6 place-items-center rounded text-slate-400 hover:bg-white hover:text-ink" aria-label={`Focus ${label}`} title={`Focus ${label}`}><Focus size={13} aria-hidden /></button>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}

function Pane({
  pane,
  maximized,
  hide,
  maximize,
}: {
  pane: (typeof panes)[number];
  maximized: boolean;
  hide: () => void;
  maximize: () => void;
}) {
  const Icon = pane.icon;
  return (
    <section className={`flex min-h-0 flex-col overflow-hidden rounded-md bg-white ring-1 ring-slate-200 ${maximized ? "col-span-full row-span-full" : ""}`}>
      <header className="flex h-9 shrink-0 items-center gap-2 border-b border-slate-100 px-2.5">
        <span className={`grid h-5 w-5 place-items-center rounded ${pane.tone}`}><Icon size={12} aria-hidden /></span>
        <h3 className="text-[11px] font-semibold text-slate-700">{pane.label}</h3>
        <div className="ml-auto flex gap-1">
          <button type="button" onClick={hide} className="grid h-6 w-6 place-items-center rounded text-slate-400 hover:bg-slate-100 hover:text-ink" aria-label={`Hide ${pane.label}`} title={`Hide ${pane.label}`}><EyeOff size={13} aria-hidden /></button>
          <button type="button" onClick={maximize} className="grid h-6 w-6 place-items-center rounded text-slate-400 hover:bg-slate-100 hover:text-ink" aria-label={`${maximized ? "Restore" : "Maximize"} ${pane.label}`} title={maximized ? "Restore" : "Maximize"}>{maximized ? <Minimize2 size={13} aria-hidden /> : <Maximize2 size={13} aria-hidden />}</button>
        </div>
      </header>
      <div className="grid min-h-0 flex-1 place-items-center bg-[linear-gradient(135deg,#fff_0%,#f8fafc_100%)] p-3">
        <div className="text-center">
          <Icon size={20} className="mx-auto text-slate-300" aria-hidden />
          <p className="mt-1 text-[10px] font-medium text-slate-400">{pane.label} workspace</p>
        </div>
      </div>
    </section>
  );
}

function WorkspacePreview({ variant }: { variant: VariantId }) {
  const [visibility, setVisibility] = useState<Visibility>(initialVisibility);
  const [maximized, setMaximized] = useState<PaneId | null>(null);
  const [menuOpen, setMenuOpen] = useState(variant === "layout-menu");

  const toggle = (pane: PaneId) => {
    setVisibility((current) => {
      const visibleCount = Object.values(current).filter(Boolean).length;
      if (current[pane] && visibleCount === 1) return current;
      return { ...current, [pane]: !current[pane] };
    });
    if (maximized === pane) setMaximized(null);
  };
  const focus = (pane: PaneId) => {
    setVisibility((current) => ({ ...current, [pane]: true }));
    setMaximized(pane);
    setMenuOpen(false);
  };
  const visiblePanes = panes.filter(({ id }) => visibility[id] && (!maximized || maximized === id));
  const gridTemplateColumns = maximized || visiblePanes.length === 1
    ? "minmax(0, 1fr)"
    : visiblePanes.length === 2
      ? "repeat(2, minmax(0, 1fr))"
      : "minmax(0, 0.9fr) minmax(0, 1.35fr) minmax(0, 0.9fr)";

  return (
    <div className="overflow-x-auto rounded-md bg-surface shadow-card ring-1 ring-slate-200">
      <div style={{ minWidth: 760 }}>
      <header className="relative z-20 flex h-12 items-center gap-2 border-b border-slate-200 bg-white px-2.5">
        <button type="button" className="flex min-w-28 items-center gap-2 rounded-md px-2 py-1.5 text-left hover:bg-slate-50">
          <span className="grid h-6 w-6 place-items-center rounded bg-brand text-[10px] font-bold text-white">P</span>
          <span className="min-w-0"><span className="block truncate text-[11px] font-semibold text-ink">Paris · Sep 2026</span><span className="block text-[9px] text-emerald-700">Plan updated</span></span>
        </button>
        <div className="mr-auto min-w-0 flex-1">
          <p className="truncate text-[10px] font-medium text-emerald-700">Museum day rebalanced · 2 bookings remain</p>
        </div>
        {variant === "direct" && <DirectBar visibility={visibility} toggle={toggle} />}
        {variant === "segmented" && <SegmentedBar visibility={visibility} toggle={toggle} />}
        {variant === "layout-menu" && <LayoutMenuBar visibility={visibility} toggle={toggle} focus={focus} menuOpen={menuOpen} setMenuOpen={setMenuOpen} />}
        <GlobalActions />
      </header>
      <div className="grid h-72 gap-2 p-2" style={{ gridTemplateColumns }}>
        {visiblePanes.map((pane) => <Pane key={pane.id} pane={pane} maximized={maximized === pane.id} hide={() => toggle(pane.id)} maximize={() => setMaximized((current) => current === pane.id ? null : pane.id)} />)}
      </div>
      <div className="flex items-center justify-between border-t border-slate-200 bg-white px-3 py-2 text-[10px] text-slate-500">
        <span>{visiblePanes.length} visible · Hide and Maximize stay in each pane header</span>
        <button type="button" onClick={() => { setVisibility(initialVisibility); setMaximized(null); }} className="inline-flex items-center gap-1 font-semibold text-slate-600 hover:text-ink"><RotateCcw size={11} aria-hidden /> Reset preview</button>
      </div>
      </div>
    </div>
  );
}

function Lab() {
  const [active, setActive] = useState<VariantId>("segmented");
  const selected = variants.find((variant) => variant.id === active)!;
  return (
    <main className="min-h-full bg-[linear-gradient(180deg,#f8fafc_0,#fafaf9_22rem)] px-4 py-6 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl">
        <header className="border-b border-slate-200 pb-5">
          <a href="./catalog.html" className="inline-flex items-center gap-1 text-xs font-semibold text-slate-500 hover:text-brand"><ArrowLeft size={14} aria-hidden /> Back to All Labs</a>
          <p className="mt-4 text-xs font-bold uppercase text-brand">Active experiment · Workspace toolbar</p>
          <h1 className="display mt-1 text-3xl font-semibold text-ink">Command bar and pane controls</h1>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-600">The standard term for the top row is <strong className="font-semibold text-ink">workspace command bar</strong>. Compare how it should expose pane visibility while Hide and Maximize remain predictable local actions in every pane header.</p>
        </header>

        <LabScope labId="workspace-command-bar" />

        <div className="lab-variant-grid mt-5" role="tablist" aria-label="Command bar variants">
          {variants.map((variant) => (
            <button key={variant.id} type="button" role="tab" aria-selected={active === variant.id} onClick={() => setActive(variant.id)} className={`rounded-md p-3 text-left ring-1 transition ${active === variant.id ? "bg-white shadow-card ring-brand/30" : "bg-white/70 ring-slate-200 hover:bg-white"}`}>
              <span className="text-sm font-semibold text-ink">{variant.label}</span>
              <span className="mt-1 block text-xs leading-relaxed text-slate-500">{variant.summary}</span>
            </button>
          ))}
        </div>

        <section className="mt-6" aria-labelledby="active-preview">
          <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
            <div><p className="text-[10px] font-bold uppercase text-slate-400">Interactive preview</p><h2 id="active-preview" className="mt-0.5 text-lg font-semibold text-ink">{selected.label}</h2></div>
            <p className="max-w-xl text-right text-xs text-slate-500">{selected.rationale}</p>
          </div>
          <WorkspacePreview key={active} variant={active} />
        </section>

        <div className="mt-6">
          <DecisionCapture labId="workspace-command-bar" labTitle="Workspace command bar controls" options={variants} activeOption={active} onChoose={(id) => setActive(id as VariantId)} />
        </div>
      </div>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><Lab /></React.StrictMode>);
