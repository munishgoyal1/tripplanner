import React from "react";
import ReactDOM from "react-dom/client";
import {
  Check,
  GitBranch,
  Map,
  MessageSquare,
  PanelRight,
  Route,
} from "lucide-react";
import "../../../src/index.css";
import { LabNavigation } from "../shared/LabNavigation";
import { LabScope } from "../shared/LabScope";

interface Option {
  id: string;
  name: string;
  hypothesis: string;
  primary: string;
  supporting: string;
  strength: string;
  tradeoff: string;
  branch: string;
  selected?: boolean;
  layout: "map" | "story" | "spatial";
}

const options: Option[] = [
  {
    id: "A",
    name: "Map-first",
    hypothesis: "Location flow first would make place-level editing faster.",
    primary: "Map and Details stayed persistent and dominant.",
    supporting: "Itinerary and Chat shared a secondary support column.",
    strength: "Strong for map click → details check → itinerary verify loops.",
    tradeoff: "Day-by-day narrative and conversation had less visual authority.",
    branch: "exp/ux-shell-a-map-first · 3ece004",
    layout: "map",
  },
  {
    id: "B",
    name: "Story-first",
    hypothesis: "Itinerary prominence would improve continuity for day-by-day planning.",
    primary: "Itinerary became the dominant planning spine.",
    supporting: "Details stayed nearby; Chat and Map occupied the secondary lane.",
    strength: "Strong for reading, adjusting, and validating a multi-day narrative.",
    tradeoff: "The map became support rather than a persistent spatial canvas.",
    branch: "exp/ux-shell-b-story-first · 65769d8",
    layout: "story",
  },
  {
    id: "C",
    name: "Spatial workspace",
    hypothesis: "Independent resizable panes would preserve context across planning modes.",
    primary: "Itinerary on the left, a dominant persistent Map in the center, and Details on the right.",
    supporting: "Assistant lived in a compact lower-right dock; panes could hide, resize, and maximize.",
    strength: "Balanced map inspection, itinerary navigation, contextual details, and conversation without page scrolling.",
    tradeoff: "Required stronger pane-state, responsive-overlay, and resize behavior.",
    branch: "exp/ux-shell-c-compact-mobile · f8d02a1 onward",
    selected: true,
    layout: "spatial",
  },
];

function Pane({ label, icon: Icon, className }: { label: string; icon: typeof Map; className: string }) {
  return (
    <div className={`flex min-h-12 items-center justify-center gap-1 rounded-sm text-[10px] font-semibold ring-1 ${className}`}>
      <Icon size={12} aria-hidden /> {label}
    </div>
  );
}

function LayoutDiagram({ layout }: { layout: Option["layout"] }) {
  if (layout === "map") {
    return (
      <div className="grid h-32 grid-cols-[1.5fr_1fr] gap-1 rounded-md bg-slate-100 p-2 ring-1 ring-slate-200" aria-label="Map-first pane arrangement">
        <div className="grid grid-rows-[1.4fr_1fr] gap-1"><Pane label="Map" icon={Map} className="bg-teal-50 text-accent ring-teal-200" /><Pane label="Details" icon={PanelRight} className="bg-white text-slate-600 ring-slate-200" /></div>
        <div className="grid grid-rows-2 gap-1"><Pane label="Itinerary" icon={Route} className="bg-white text-slate-600 ring-slate-200" /><Pane label="Chat" icon={MessageSquare} className="bg-white text-slate-600 ring-slate-200" /></div>
      </div>
    );
  }
  if (layout === "story") {
    return (
      <div className="grid h-32 grid-cols-[1.45fr_1fr] gap-1 rounded-md bg-slate-100 p-2 ring-1 ring-slate-200" aria-label="Story-first pane arrangement">
        <div className="grid grid-rows-[1.4fr_1fr] gap-1"><Pane label="Itinerary" icon={Route} className="bg-brand-50 text-brand ring-brand-100" /><Pane label="Details" icon={PanelRight} className="bg-white text-slate-600 ring-slate-200" /></div>
        <div className="grid grid-rows-2 gap-1"><Pane label="Chat" icon={MessageSquare} className="bg-white text-slate-600 ring-slate-200" /><Pane label="Map" icon={Map} className="bg-white text-slate-600 ring-slate-200" /></div>
      </div>
    );
  }
  return (
    <div className="grid h-32 grid-cols-[0.9fr_1.5fr_1fr] gap-1 rounded-md bg-slate-100 p-2 ring-1 ring-slate-200" aria-label="Selected spatial workspace pane arrangement">
      <Pane label="Itinerary" icon={Route} className="bg-white text-slate-600 ring-slate-200" />
      <Pane label="Map" icon={Map} className="bg-teal-50 text-accent ring-teal-200" />
      <div className="grid grid-rows-[1.25fr_0.75fr] gap-1"><Pane label="Details" icon={PanelRight} className="bg-white text-slate-600 ring-slate-200" /><Pane label="Assistant" icon={MessageSquare} className="bg-white text-slate-600 ring-slate-200" /></div>
    </div>
  );
}

function OptionCard({ option }: { option: Option }) {
  return (
    <article className={`rounded-md bg-white p-4 shadow-card ring-1 ${option.selected ? "ring-emerald-300" : "ring-slate-200"}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className={`text-[10px] font-bold uppercase ${option.selected ? "text-emerald-700" : "text-slate-400"}`}>Option {option.id}</p>
          <h2 className="mt-0.5 text-lg font-semibold text-ink">{option.name}</h2>
        </div>
        {option.selected && <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-1 text-[10px] font-bold uppercase text-emerald-700 ring-1 ring-emerald-200"><Check size={11} aria-hidden /> Selected</span>}
      </div>
      <p className="mt-2 min-h-10 text-xs leading-relaxed text-slate-500">{option.hypothesis}</p>
      <div className="mt-4"><LayoutDiagram layout={option.layout} /></div>
      <dl className="mt-4 space-y-3 text-xs">
        <div><dt className="font-bold uppercase text-[10px] text-slate-400">Primary workflow</dt><dd className="mt-0.5 leading-relaxed text-slate-600">{option.primary}</dd></div>
        <div><dt className="font-bold uppercase text-[10px] text-slate-400">Supporting workflow</dt><dd className="mt-0.5 leading-relaxed text-slate-600">{option.supporting}</dd></div>
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-1">
          <div className="rounded-sm bg-emerald-50/70 p-2.5 ring-1 ring-emerald-100"><dt className="font-bold uppercase text-[10px] text-emerald-700">Strength</dt><dd className="mt-0.5 leading-relaxed text-slate-600">{option.strength}</dd></div>
          <div className="rounded-sm bg-slate-50 p-2.5 ring-1 ring-slate-100"><dt className="font-bold uppercase text-[10px] text-slate-500">Tradeoff</dt><dd className="mt-0.5 leading-relaxed text-slate-600">{option.tradeoff}</dd></div>
        </div>
      </dl>
      <p className="mt-4 flex items-center gap-1 border-t border-slate-100 pt-3 text-[10px] text-slate-400"><GitBranch size={11} aria-hidden /> {option.branch}</p>
    </article>
  );
}

function HistoricalLab() {
  return (
    <main className="min-h-full bg-[linear-gradient(180deg,#f8fafc_0,#fafaf9_20rem)] px-4 py-7 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl">
        <header className="border-b border-slate-200 pb-5">
          <LabNavigation detail />
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <p className="text-xs font-bold uppercase text-emerald-700">Historical decision record</p>
            <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-bold uppercase text-emerald-700 ring-1 ring-emerald-200">Decided 23 Jul 2026</span>
          </div>
          <h1 className="display mt-2 text-3xl font-semibold text-ink">Workspace shell layout</h1>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-600">The original experiment ran on preserved branches before standalone lab pages existed. This page reconstructs the verified option intent and pane arrangements from those records; it is a read-only design archive, not a live version switcher.</p>
        </header>

        <LabScope labId="workspace-shell" />

        <div className="mt-6 grid gap-4 xl:grid-cols-3">
          {options.map((option) => <OptionCard key={option.id} option={option} />)}
        </div>

        <section className="mt-6 rounded-md bg-emerald-50 p-4 ring-1 ring-emerald-200 sm:p-5">
          <p className="text-[10px] font-bold uppercase text-emerald-700">Final decision</p>
          <h2 className="mt-1 text-base font-semibold text-ink">Keep Option C · Spatial workspace</h2>
          <p className="mt-2 max-w-4xl text-sm leading-relaxed text-slate-600">The selected direction combines a map-first canvas with an itinerary planning spine and a details-first right rail. Independent hide, resize, and maximize behavior lets the workspace adapt without changing the underlying pane ownership. Responsive layouts preserve context by overlaying the inspector at tablet widths and using on-demand surfaces on mobile.</p>
        </section>
      </div>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><HistoricalLab /></React.StrictMode>);