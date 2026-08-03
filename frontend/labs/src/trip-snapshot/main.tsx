import React, { useState } from "react";
import ReactDOM from "react-dom/client";
import {
  BedDouble,
  CalendarDays,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  CloudSun,
  Compass,
  Plane,
  Sparkles,
  Umbrella,
} from "lucide-react";
import "../../../src/index.css";
import { DecisionCapture } from "../shared/DecisionCapture";
import { LabNavigation } from "../shared/LabNavigation";
import { LabScope } from "../shared/LabScope";
import "../shared/experiment-layout.css";

type VariantId = "ledger" | "brief" | "progressive";

interface Variant {
  id: VariantId;
  label: string;
  summary: string;
  rationale: string;
}

const variants: Variant[] = [
  {
    id: "ledger",
    label: "A · Scan ledger",
    summary: "Dense facts stay visible in a stable, left-to-right hierarchy.",
    rationale: "Fastest for repeat scanning, with less room for trip character or guidance.",
  },
  {
    id: "brief",
    label: "B · Decision brief",
    summary: "Identity, readiness, weather, and budget form one compact planning brief.",
    rationale: "Balances useful context with a clear story about what still needs attention.",
  },
  {
    id: "progressive",
    label: "C · Progressive summary",
    summary: "Core trip identity stays compact; secondary context expands on demand.",
    rationale: "Protects itinerary space, but important constraints can remain hidden.",
  },
];

const facts = [
  { label: "Days", value: "6", icon: CalendarDays },
  { label: "Stay", value: "1", icon: BedDouble },
  { label: "Places", value: "14", icon: Compass },
  { label: "Flights", value: "2", icon: Plane },
];

function Identity({ compact = false }: { compact?: boolean }) {
  return (
    <div className="min-w-0">
      <div className="flex items-center gap-2">
        <p className="text-[10px] font-bold uppercase text-brand">Trip snapshot</p>
        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[9px] font-bold uppercase text-slate-600 ring-1 ring-slate-200">Draft</span>
      </div>
      <h2 className={`display mt-1 truncate font-semibold text-ink ${compact ? "text-xl" : "text-2xl"}`}>Honolulu, Oʻahu</h2>
      <p className="mt-1 text-xs text-slate-500">From Pune · 12–17 September 2026 · 4 travelers</p>
    </div>
  );
}

function Readiness({ compact = false }: { compact?: boolean }) {
  return (
    <div className={compact ? "" : "border-t border-slate-200 pt-3"}>
      <div className="flex items-center justify-between gap-3 text-xs">
        <span className="inline-flex items-center gap-1.5 font-semibold text-ink"><CheckCircle2 size={13} className="text-emerald-600" aria-hidden /> 7 of 10 ready</span>
        <span className="text-amber-700">3 need booking</span>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-emerald-500" style={{ width: "70%" }} /></div>
    </div>
  );
}

function WeatherStrip() {
  const days = [
    ["D1", "29°", "Sunny"],
    ["D2", "28°", "Light rain"],
    ["D3", "29°", "Sunny"],
    ["D4", "28°", "Cloudy"],
    ["D5", "29°", "Sunny"],
    ["D6", "28°", "Showers"],
  ];
  return (
    <div>
      <div className="flex items-center justify-between"><p className="text-[10px] font-bold uppercase text-slate-400">Live forecast</p><p className="text-[9px] text-slate-400">Open-Meteo</p></div>
      <div className="mt-2 grid gap-1" style={{ gridTemplateColumns: "repeat(6, minmax(0, 1fr))" }}>
        {days.map(([day, temp, condition]) => (
          <div key={day} title={`${day}: ${condition}`} className="rounded bg-sky-50 px-1 py-1.5 text-center ring-1 ring-sky-100">
            <CloudSun size={13} className="mx-auto text-sky-700" aria-hidden />
            <p className="mt-0.5 text-[9px] font-semibold text-slate-600">{day}</p>
            <p className="text-[10px] font-bold tabular-nums text-ink">{temp}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function BudgetLine() {
  return (
    <div>
      <div className="flex items-end justify-between gap-3">
        <div><p className="text-[10px] font-bold uppercase text-slate-400">Trip spend</p><p className="mt-0.5 text-base font-semibold text-ink">$6,840 <span className="text-xs font-normal text-slate-400">/ $8,000</span></p></div>
        <p className="text-right text-xs text-emerald-700">$1,160 left</p>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-amber-400" style={{ width: "86%" }} /></div>
    </div>
  );
}

function FactGrid({ quiet = false }: { quiet?: boolean }) {
  return (
    <div className={`grid grid-cols-4 divide-x divide-slate-200 ${quiet ? "border-y border-slate-200 py-2" : "rounded-md bg-slate-50 py-2.5 ring-1 ring-slate-200"}`}>
      {facts.map(({ label, value, icon: Icon }) => (
        <div key={label} className="min-w-0 px-2 first:pl-0 first:ml-2 last:pr-0">
          <div className="flex items-center gap-1 text-slate-400"><Icon size={12} aria-hidden /><span className="truncate text-[9px] font-semibold uppercase">{label}</span></div>
          <p className="mt-0.5 text-sm font-semibold tabular-nums text-ink">{value}</p>
        </div>
      ))}
    </div>
  );
}

function LedgerSnapshot() {
  return (
    <section aria-label="Scan ledger trip snapshot" className="border-b border-slate-200 bg-white p-4">
      <div className="flex items-start justify-between gap-3">
        <Identity compact />
        <p className="shrink-0 text-right text-sm font-semibold text-ink">$6,840<br /><span className="text-[10px] font-normal text-emerald-700">$1,160 left</span></p>
      </div>
      <div className="mt-3"><FactGrid quiet /></div>
      <div className="lab-ledger-row mt-3 sm:items-center">
        <Readiness compact />
        <div className="flex flex-wrap justify-start gap-1 sm:justify-end">
          <span className="chip">Family of 4</span><span className="chip">Vegetarian</span><span className="chip">Relaxed pace</span>
        </div>
      </div>
      <div className="mt-3 flex items-center gap-2 border-t border-slate-100 pt-2.5 text-[11px] text-slate-600"><CloudSun size={13} className="text-sky-700" aria-hidden /><strong className="font-semibold text-ink">28–29°C</strong><span>Warm with brief showers</span><span className="ml-auto inline-flex items-center gap-1 text-slate-500"><Umbrella size={12} aria-hidden /> Pack light rain layers</span></div>
    </section>
  );
}

function BriefSnapshot() {
  return (
    <section aria-label="Decision brief trip snapshot" className="border-b border-slate-200 bg-white p-4">
      <div className="flex items-start justify-between gap-3">
        <Identity />
        <span className="shrink-0 rounded-md bg-amber-50 px-2.5 py-1.5 text-right ring-1 ring-amber-200"><span className="block text-[9px] font-bold uppercase text-amber-700">Next decision</span><span className="text-[11px] font-semibold text-ink">Book Pearl Harbor</span></span>
      </div>
      <p className="mt-3 text-sm leading-relaxed text-slate-600">Six easy-paced island days balancing Waikīkī, history, North Shore scenery, and family beach time.</p>
      <div className="mt-3"><Readiness /></div>
      <div className="mt-3"><FactGrid /></div>
      <div className="lab-two-column mt-3 border-t border-slate-200 pt-3">
        <WeatherStrip />
        <div className="space-y-3"><BudgetLine /><p className="text-[11px] leading-relaxed text-slate-600"><strong className="font-semibold text-slate-700">Trip fit:</strong> Vegetarian-friendly · low-transfer days · one early start.</p></div>
      </div>
      <p className="mt-3 flex items-start gap-1.5 rounded bg-sky-50 px-2.5 py-2 text-[11px] leading-relaxed text-slate-600 ring-1 ring-sky-100"><Umbrella size={13} className="mt-0.5 shrink-0 text-sky-700" aria-hidden /><span><strong className="font-semibold text-slate-700">Pack:</strong> reef-safe sunscreen, compact umbrella, breathable layers, and closed shoes for Diamond Head.</span></p>
    </section>
  );
}

function ProgressiveSnapshot() {
  const [expanded, setExpanded] = useState(false);
  return (
    <section aria-label="Progressive trip snapshot" className="border-b border-slate-200 bg-white">
      <div className="p-4">
        <div className="flex items-start justify-between gap-3"><Identity compact /><p className="shrink-0 text-right text-sm font-semibold text-ink">$6,840<br /><span className="text-[10px] font-normal text-amber-700">3 to book</span></p></div>
        <div className="mt-3"><FactGrid quiet /></div>
        <button type="button" onClick={() => setExpanded(!expanded)} aria-expanded={expanded} className="mt-3 flex w-full items-center justify-between rounded-md bg-slate-50 px-3 py-2 text-left ring-1 ring-slate-200">
          <span><span className="block text-xs font-semibold text-ink">Weather, budget, and trip fit</span><span className="mt-0.5 block text-[10px] text-slate-500">28–29°C · $1,160 left · family-ready</span></span>
          {expanded ? <ChevronUp size={15} className="text-slate-400" aria-hidden /> : <ChevronDown size={15} className="text-slate-400" aria-hidden />}
        </button>
      </div>
      {expanded && (
        <div className="lab-two-column border-t border-slate-200 bg-slate-50/70 p-4">
          <WeatherStrip />
          <div className="space-y-3"><Readiness compact /><BudgetLine /><p className="text-[11px] text-slate-600"><strong className="font-semibold text-slate-700">For this trip:</strong> Vegetarian meals · relaxed pace · avoid long midday walks.</p></div>
        </div>
      )}
    </section>
  );
}

function AgendaContext() {
  const rows = [
    ["D1", "Arrive and settle into Waikīkī", "4 stops"],
    ["D2", "Pearl Harbor and historic Honolulu", "5 stops"],
  ];
  return (
    <div className="bg-surface px-4 py-3">
      <p className="text-[9px] font-bold uppercase text-slate-400">Itinerary continues</p>
      <div className="mt-2 divide-y divide-slate-200 border-y border-slate-200">
        {rows.map(([day, title, count]) => <div key={day} className="grid items-center gap-2 py-2 text-xs" style={{ gridTemplateColumns: "2rem minmax(0, 1fr) auto" }}><span className="grid h-6 w-6 place-items-center rounded bg-brand text-[10px] font-bold text-white">{day}</span><span className="truncate font-medium text-slate-700">{title}</span><span className="text-[10px] text-slate-400">{count}</span></div>)}
      </div>
    </div>
  );
}

function Preview({ variant }: { variant: VariantId }) {
  return (
    <div data-lab-change="Trip snapshot hierarchy" className="mx-auto max-w-2xl overflow-hidden rounded-md shadow-card ring-1 ring-slate-200">
      {variant === "ledger" && <LedgerSnapshot />}
      {variant === "brief" && <BriefSnapshot />}
      {variant === "progressive" && <ProgressiveSnapshot />}
      <AgendaContext />
    </div>
  );
}

function Lab() {
  const [active, setActive] = useState<VariantId>("brief");
  const selected = variants.find((variant) => variant.id === active)!;
  return (
    <main className="min-h-full bg-[linear-gradient(180deg,#f8fafc_0,#fafaf9_22rem)] px-4 py-6 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-6xl">
        <LabNavigation detail labId="trip-snapshot-hierarchy" />
        <header className="border-b border-slate-200 pb-5">
          <div className="mt-4 flex items-center gap-2 text-brand"><Sparkles size={15} aria-hidden /><p className="text-xs font-bold uppercase">Active experiment · Itinerary overview</p></div>
          <h1 className="display mt-1 text-3xl font-semibold text-ink">Trip snapshot hierarchy</h1>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-600">The standard product term is <strong className="font-semibold text-ink">trip snapshot</strong>: a whole-trip summary band at the top of Itinerary. It is not a generic panel and it is distinct from each day’s Day brief.</p>
        </header>

        <LabScope labId="trip-snapshot-hierarchy" />

        <div className="lab-variant-grid mt-5" role="tablist" aria-label="Trip snapshot variants">
          {variants.map((variant) => (
            <button key={variant.id} type="button" role="tab" aria-selected={active === variant.id} onClick={() => setActive(variant.id)} className={`rounded-md p-3 text-left ring-1 transition ${active === variant.id ? "bg-white shadow-card ring-brand/30" : "bg-white/70 ring-slate-200 hover:bg-white"}`}>
              <span className="text-sm font-semibold text-ink">{variant.label}</span>
              <span className="mt-1 block text-xs leading-relaxed text-slate-500">{variant.summary}</span>
            </button>
          ))}
        </div>

        <section className="mt-6" aria-labelledby="snapshot-preview">
          <div className="mb-3 flex flex-wrap items-end justify-between gap-3"><div><p className="text-[10px] font-bold uppercase text-slate-400">In-pane preview</p><h2 id="snapshot-preview" className="mt-0.5 text-lg font-semibold text-ink">{selected.label}</h2></div><p className="max-w-lg text-right text-xs text-slate-500">{selected.rationale}</p></div>
          <Preview key={active} variant={active} />
        </section>

        <div className="mt-6"><DecisionCapture labId="trip-snapshot-hierarchy" labTitle="Trip snapshot hierarchy" options={variants} activeOption={active} onChoose={(id) => setActive(id as VariantId)} /></div>
      </div>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><Lab /></React.StrictMode>);
