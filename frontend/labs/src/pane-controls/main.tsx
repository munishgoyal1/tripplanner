import React, { useCallback, useState } from "react";
import ReactDOM from "react-dom/client";
import {
  ArrowLeft,
  Check,
  ChevronDown,
  EyeOff,
  ListChecks,
  Map,
  Maximize2,
  Menu,
  Minimize2,
  PanelRight,
  RotateCcw,
  Sparkles,
} from "lucide-react";
import "../../../src/index.css";
import { DecisionCapture } from "../shared/DecisionCapture";
import { LabNavigation } from "../shared/LabNavigation";
import { LabScope } from "../shared/LabScope";

type Variant = "semantic" | "pair" | "menu";
type Pane = "itinerary" | "map" | "details";

const variants: Array<{ id: Variant; label: string; note: string; strength: string }> = [
  {
    id: "semantic",
    label: "A · Compact semantic actions",
    note: "Short icon-and-text actions make both commands explicit without looking like utility dots.",
    strength: "Clearest at a glance and easiest to learn.",
  },
  {
    id: "pair",
    label: "B · Restrained icon pair",
    note: "Two quiet icons share a light local group, with precise tooltips and accessible names.",
    strength: "Smallest direct treatment while preserving one-click access.",
  },
  {
    id: "menu",
    label: "C · Pane action menu",
    note: "One calm pane-local trigger reveals clearly labeled Hide and Maximize actions.",
    strength: "Lowest header noise when commands are occasional.",
  },
];

const paneLabels: Record<Pane, string> = {
  itinerary: "Itinerary",
  map: "Map",
  details: "Details",
};

function PaneActions({ pane, variant, maximized, onHide, onMaximize }: {
  pane: Pane;
  variant: Variant;
  maximized: boolean;
  onHide: () => void;
  onMaximize: () => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const maximizeLabel = maximized ? "Restore" : "Maximize";
  const MaximizeIcon = maximized ? Minimize2 : Maximize2;

  if (variant === "semantic") {
    return (
      <div data-lab-change="Pane-local action presentation" className="ml-auto flex shrink-0 items-center gap-1">
        <button type="button" onClick={onHide} className="inline-flex h-7 items-center gap-1 rounded-sm px-2 text-[11px] font-semibold text-slate-500 hover:bg-slate-100 hover:text-ink" aria-label={`Hide ${paneLabels[pane]}`}>
          <EyeOff size={13} aria-hidden /> Hide
        </button>
        <button type="button" onClick={onMaximize} className="inline-flex h-7 items-center gap-1 rounded-sm px-2 text-[11px] font-semibold text-slate-500 hover:bg-slate-100 hover:text-ink" aria-label={`${maximizeLabel} ${paneLabels[pane]}`}>
          <MaximizeIcon size={13} aria-hidden /> {maximizeLabel}
        </button>
      </div>
    );
  }

  if (variant === "pair") {
    return (
      <div data-lab-change="Pane-local action presentation" className="ml-auto flex shrink-0 items-center rounded-md bg-slate-50 p-0.5 ring-1 ring-inset ring-slate-200/80">
        <button type="button" onClick={onHide} className="grid h-7 w-7 place-items-center rounded-[5px] text-slate-500 hover:bg-white hover:text-ink hover:shadow-sm" aria-label={`Hide ${paneLabels[pane]}`} title={`Hide ${paneLabels[pane]}`}>
          <EyeOff size={14} aria-hidden />
        </button>
        <button type="button" onClick={onMaximize} className="grid h-7 w-7 place-items-center rounded-[5px] text-slate-500 hover:bg-white hover:text-ink hover:shadow-sm" aria-label={`${maximizeLabel} ${paneLabels[pane]}`} title={`${maximizeLabel} ${paneLabels[pane]}`}>
          <MaximizeIcon size={14} aria-hidden />
        </button>
      </div>
    );
  }

  return (
    <div data-lab-change="Pane-local action presentation" className="relative ml-auto shrink-0">
      <button type="button" onClick={() => setMenuOpen((open) => !open)} className="inline-flex h-7 items-center gap-1 rounded-sm px-2 text-[11px] font-semibold text-slate-500 hover:bg-slate-100 hover:text-ink" aria-expanded={menuOpen} aria-label={`${paneLabels[pane]} pane actions`}>
        <Menu size={14} aria-hidden /> Actions <ChevronDown size={12} aria-hidden />
      </button>
      {menuOpen && (
        <div className="absolute right-0 top-8 z-50 w-36 rounded-md bg-white p-1 shadow-pop ring-1 ring-slate-200">
          <button type="button" onClick={() => { onHide(); setMenuOpen(false); }} className="flex h-8 w-full items-center gap-2 rounded-sm px-2 text-xs text-slate-600 hover:bg-slate-50 hover:text-ink"><EyeOff size={13} /> Hide pane</button>
          <button type="button" onClick={() => { onMaximize(); setMenuOpen(false); }} className="flex h-8 w-full items-center gap-2 rounded-sm px-2 text-xs text-slate-600 hover:bg-slate-50 hover:text-ink"><MaximizeIcon size={13} /> {maximizeLabel}</button>
        </div>
      )}
    </div>
  );
}

function PaneFrame({ pane, variant, maximized, onHide, onMaximize, children }: React.PropsWithChildren<{
  pane: Pane;
  variant: Variant;
  maximized: boolean;
  onHide: () => void;
  onMaximize: () => void;
}>) {
  const Icon = pane === "itinerary" ? ListChecks : pane === "map" ? Map : PanelRight;
  return (
    <section className="flex min-h-0 flex-col overflow-hidden rounded-md bg-white shadow-card ring-1 ring-slate-200">
      <header className="flex h-10 shrink-0 items-center gap-2 border-b border-slate-100 px-3">
        <Icon size={13} className="text-slate-400" aria-hidden />
        <h2 className="text-[11px] font-semibold uppercase text-slate-500">{paneLabels[pane]}</h2>
        <PaneActions pane={pane} variant={variant} maximized={maximized} onHide={onHide} onMaximize={onMaximize} />
      </header>
      <div className="min-h-0 flex-1">{children}</div>
    </section>
  );
}

function PlannerWorkspace({ variant }: { variant: Variant }) {
  const [hidden, setHidden] = useState<Pane[]>([]);
  const [maximized, setMaximized] = useState<Pane | null>(null);
  const visible = (pane: Pane) => !hidden.includes(pane);
  const hide = (pane: Pane) => {
    setHidden((current) => [...current.filter((item) => item !== pane), pane]);
    setMaximized((current) => current === pane ? null : current);
  };
  const toggleMaximize = (pane: Pane) => setMaximized((current) => current === pane ? null : pane);
  const showAll = () => { setHidden([]); setMaximized(null); };

  return (
    <div className="flex h-full min-h-0 flex-col bg-slate-100 p-2">
      <header className="mb-2 flex h-11 shrink-0 items-center gap-2 rounded-md bg-white px-3 shadow-card ring-1 ring-slate-200">
        <strong className="text-sm text-ink">Paris family trip</strong>
        <span className="hidden text-xs text-slate-400 sm:inline">26-30 Aug · 5 days</span>
        {hidden.length > 0 && <button type="button" onClick={showAll} className="btn-ghost ml-auto"><RotateCcw size={13} /> Restore hidden panes</button>}
        {hidden.length === 0 && <span className="ml-auto inline-flex items-center gap-1 text-[10px] font-semibold uppercase text-emerald-700"><Check size={12} /> All panes visible</span>}
      </header>
      <div className={`grid min-h-0 flex-1 gap-2 ${maximized ? "grid-cols-1" : "grid-cols-[minmax(15rem,0.8fr)_minmax(22rem,1.6fr)_minmax(16rem,0.9fr)]"}`}>
        {visible("itinerary") && (!maximized || maximized === "itinerary") && <PaneFrame pane="itinerary" variant={variant} maximized={maximized === "itinerary"} onHide={() => hide("itinerary")} onMaximize={() => toggleMaximize("itinerary")}><div className="space-y-2 overflow-y-auto p-3">{["Louvre and Tuileries", "Lunch at Café de Flore", "Musée de l'Orangerie", "Eiffel Tower at sunset"].map((item, index) => <div key={item} className="border-l-2 border-teal-600 pl-3"><p className="text-[10px] font-bold uppercase text-slate-400">{9 + index * 3}:00</p><p className="text-xs font-semibold text-ink">{item}</p></div>)}</div></PaneFrame>}
        {visible("map") && (!maximized || maximized === "map") && <PaneFrame pane="map" variant={variant} maximized={maximized === "map"} onHide={() => hide("map")} onMaximize={() => toggleMaximize("map")}><div className="relative h-full min-h-[24rem] overflow-hidden bg-[#e6eee9]"><div className="absolute inset-0 opacity-60" style={{ backgroundImage: "linear-gradient(30deg,transparent 47%,white 48%,white 51%,transparent 52%),linear-gradient(120deg,transparent 47%,#cedbd1 48%,#cedbd1 51%,transparent 52%)", backgroundSize: "110px 90px,160px 130px" }} /><div className="absolute left-[46%] top-[42%] grid h-9 w-8 place-items-center rounded-t-full rounded-br-full bg-brand text-xs font-bold text-white shadow-pop ring-2 ring-white">2</div><div className="absolute bottom-3 left-3 rounded-sm bg-white/90 px-2 py-1 text-[10px] text-slate-500 shadow-card">Day 2 · 23 km · 1 hr 38 travel</div></div></PaneFrame>}
        {visible("details") && (!maximized || maximized === "details") && <PaneFrame pane="details" variant={variant} maximized={maximized === "details"} onHide={() => hide("details")} onMaximize={() => toggleMaximize("details")}><div className="p-3"><div className="h-28 rounded-md bg-[linear-gradient(135deg,#dcefe9,#fef3c7)]" /><p className="mt-3 text-sm font-semibold text-ink">Musée de l'Orangerie</p><p className="mt-1 text-xs leading-relaxed text-slate-500">Focused place details remain unchanged while only pane action presentation varies.</p></div></PaneFrame>}
      </div>
    </div>
  );
}

function PaneControlsLab() {
  const params = new URLSearchParams(window.location.search);
  const preview = params.get("preview");
  const fullPreview = variants.some((item) => item.id === preview);
  const [variant, setVariant] = useState<Variant>(fullPreview ? preview as Variant : "pair");
  const choose = useCallback((value: string) => setVariant(value as Variant), []);

  if (fullPreview) return <main className="relative h-[100dvh] min-h-[40rem] overflow-hidden"><PlannerWorkspace variant={variant} /><a href="./lab-10-pane-controls.html" className="fixed bottom-4 left-4 z-[80] inline-flex items-center gap-2 rounded-md bg-ink px-3 py-2 text-xs font-semibold text-white shadow-pop"><ArrowLeft size={14} /> Exit full-size preview</a></main>;

  return (
    <main className="min-h-full bg-[linear-gradient(180deg,#f8fafc_0,#ecfdf5_32rem,#f8fafc_100%)] px-4 py-7 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-[92rem]">
        <LabNavigation detail labId="pane-control-polish" />
        <header className="mt-4 flex flex-wrap items-end justify-between gap-5 border-b border-slate-200 pb-5"><div><div className="flex items-center gap-2 text-accent"><Sparkles size={17} /><p className="text-[10px] font-bold uppercase">Enhancements and polishing Lab</p></div><h1 className="display mt-2 text-3xl font-semibold text-ink">Pane control polish</h1><p className="mt-2 max-w-4xl text-sm leading-relaxed text-slate-600">Compare quieter, clearer ways to present each pane's own Hide and Maximize actions without changing pane ownership, behavior, layout, or recovery.</p></div></header>
        <LabScope labId="pane-control-polish" />
        <div className="mt-5 grid gap-3 md:grid-cols-3" role="tablist" aria-label="Pane control variants">{variants.map((item) => <button key={item.id} role="tab" aria-selected={variant === item.id} onClick={() => setVariant(item.id)} className={`rounded-md bg-white p-4 text-left shadow-card ring-1 transition ${variant === item.id ? "ring-2 ring-accent" : "ring-slate-200 hover:ring-slate-300"}`}><strong className="block text-sm text-ink">{item.label}</strong><span className="mt-2 block text-xs leading-relaxed text-slate-600">{item.note}</span><span className="mt-3 block border-t border-slate-100 pt-2 text-[10px] font-semibold text-accent">{item.strength}</span></button>)}</div>
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3"><div><p className="text-xs font-semibold text-ink">Interactive production-scale preview</p><p className="mt-0.5 text-[11px] text-slate-500">Try Hide, Maximize, Restore, and pane recovery independently in all three panes.</p></div><a href={`?preview=${variant}`} className="btn-primary"><Maximize2 size={14} /> Open full-size preview</a></div>
        <section className="mt-2 h-[680px] max-h-[76vh] min-h-[560px] overflow-hidden rounded-md bg-white shadow-pop ring-1 ring-slate-200" aria-label="Pane controls preview"><PlannerWorkspace key={variant} variant={variant} /></section>
        <section className="mt-6 grid gap-3 md:grid-cols-3"><article className="rounded-md bg-white p-4 ring-1 ring-slate-200"><EyeOff size={16} className="text-brand" /><h2 className="mt-2 text-sm font-semibold">Independent ownership</h2><p className="mt-1 text-xs leading-relaxed text-slate-500">Every pane retains its own Hide action and recovery path.</p></article><article className="rounded-md bg-white p-4 ring-1 ring-slate-200"><Maximize2 size={16} className="text-accent" /><h2 className="mt-2 text-sm font-semibold">Stable behavior</h2><p className="mt-1 text-xs leading-relaxed text-slate-500">Maximize and Restore preserve the same state transitions in every option.</p></article><article className="rounded-md bg-white p-4 ring-1 ring-slate-200"><Sparkles size={16} className="text-amber-700" /><h2 className="mt-2 text-sm font-semibold">Visual restraint</h2><p className="mt-1 text-xs leading-relaxed text-slate-500">Only label, grouping, and disclosure vary; pane headers and content stay fixed.</p></article></section>
        <div className="mt-6"><DecisionCapture labId="pane-control-polish" labTitle="Pane control polish" options={variants} activeOption={variant} onChoose={choose} /></div>
      </div>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><PaneControlsLab /></React.StrictMode>);
