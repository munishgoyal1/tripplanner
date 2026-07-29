import React, { useState } from "react";
import ReactDOM from "react-dom/client";
import {
  AlertTriangle,
  ArrowRight,
  Check,
  ChevronRight,
  Clock3,
  ExternalLink,
  Footprints,
  MapPin,
  Navigation,
  Route,
  Sparkles,
  TicketCheck,
  TrainFront,
} from "lucide-react";
import "../index.css";

type Variant = "overview" | "brief" | "actions";

const variants: Array<{ id: Variant; label: string; summary: string }> = [
  {
    id: "overview",
    label: "A · Operational overview",
    summary: "A structured facts band makes workload and readiness immediately scannable.",
  },
  {
    id: "brief",
    label: "B · Narrative brief",
    summary: "The purpose and rhythm of the day lead; logistics remain secondary.",
  },
  {
    id: "actions",
    label: "C · Action strip",
    summary: "Route, booking gaps, and cautions are promoted above descriptive context.",
  },
];

const facts = [
  { icon: MapPin, label: "Stops", value: "5" },
  { icon: Clock3, label: "Planned", value: "7 hr" },
  { icon: Route, label: "Travel", value: "8.6 km" },
  { icon: TicketCheck, label: "Confirmed", value: "3 of 5" },
];

function DateIdentity({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex items-start gap-3">
      <span className={`${compact ? "h-9 w-9" : "h-11 w-11"} grid shrink-0 place-items-center rounded-full bg-brand text-sm font-bold text-white`}>2</span>
      <div className="min-w-0">
        <p className="text-[11px] font-bold uppercase text-brand">Saturday · 12 September 2026</p>
        <h2 className={`display mt-0.5 font-semibold text-ink ${compact ? "text-lg" : "text-xl"}`}>Masterpieces and central Paris</h2>
      </div>
    </div>
  );
}

function FactGrid() {
  return (
    <dl className="grid grid-cols-2 overflow-hidden rounded-md bg-slate-50 ring-1 ring-slate-200 sm:grid-cols-4">
      {facts.map(({ icon: Icon, label, value }) => (
        <div key={label} className="border-b border-r border-slate-200 px-3 py-2.5 last:border-r-0 sm:border-b-0">
          <dt className="flex items-center gap-1 text-[10px] font-bold uppercase text-slate-400"><Icon size={11} aria-hidden /> {label}</dt>
          <dd className="mt-0.5 text-sm font-semibold text-ink">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function RouteAction() {
  return (
    <a href="#" onClick={(event) => event.preventDefault()} className="inline-flex h-8 items-center gap-1.5 rounded-full bg-brand px-3 text-xs font-semibold text-white shadow-sm">
      <Navigation size={13} aria-hidden /> Open route <ExternalLink size={11} aria-hidden />
    </a>
  );
}

function OperationalOverview() {
  return (
    <section className="space-y-4 bg-white p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <DateIdentity />
        <RouteAction />
      </div>
      <FactGrid />
      <div className="grid gap-2 sm:grid-cols-2">
        <div className="rounded-md bg-teal-50 px-3 py-2.5 ring-1 ring-teal-100">
          <p className="flex items-center gap-1 text-[10px] font-bold uppercase text-accent"><TrainFront size={11} aria-hidden /> Getting around</p>
          <p className="mt-1 text-xs leading-relaxed text-slate-600">Walk in the museum quarter; use Metro or a short taxi for the longer midday legs.</p>
        </div>
        <div className="rounded-md bg-slate-50 px-3 py-2.5 ring-1 ring-slate-100">
          <p className="text-[10px] font-bold uppercase text-slate-500">Day overview</p>
          <p className="mt-1 text-xs leading-relaxed text-slate-600">A focused art day with a long lunch and a lighter late-afternoon museum.</p>
        </div>
      </div>
    </section>
  );
}

function NarrativeBrief() {
  return (
    <section className="bg-white p-4 sm:p-5">
      <DateIdentity />
      <p className="display mt-4 max-w-2xl text-lg leading-relaxed text-slate-700">A focused art day in central Paris, pairing two essential collections with a relaxed French lunch and an easier finish.</p>
      <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 border-y border-slate-100 py-3 text-xs text-slate-500">
        <span className="font-semibold text-ink">5 stops</span>
        <span>7 hr planned</span>
        <span>8.6 km</span>
        <span className="inline-flex items-center gap-1 text-emerald-700"><Check size={12} aria-hidden /> 3 confirmed</span>
        <RouteAction />
      </div>
      <div className="mt-4 flex items-start gap-3">
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-teal-50 text-accent ring-1 ring-teal-100"><Footprints size={15} aria-hidden /></span>
        <div>
          <p className="text-xs font-semibold text-ink">Travel rhythm</p>
          <p className="mt-0.5 text-xs leading-relaxed text-slate-500">Begin on foot, take Metro after the Louvre, then use a taxi if energy is running low.</p>
        </div>
      </div>
    </section>
  );
}

function ActionStrip() {
  return (
    <section className="bg-white">
      <div className="p-4 sm:p-5">
        <DateIdentity compact />
      </div>
      <div className="grid border-y border-slate-200 bg-slate-50 sm:grid-cols-3">
        <a href="#" onClick={(event) => event.preventDefault()} className="flex items-center gap-3 border-b border-slate-200 px-4 py-3 hover:bg-white sm:border-b-0 sm:border-r">
          <span className="grid h-8 w-8 place-items-center rounded-full bg-brand text-white"><Navigation size={14} aria-hidden /></span>
          <span><strong className="block text-xs text-ink">Open route</strong><small className="text-[11px] text-slate-500">8.6 km · mixed travel</small></span>
        </a>
        <button type="button" className="flex items-center gap-3 border-b border-slate-200 px-4 py-3 text-left hover:bg-white sm:border-b-0 sm:border-r">
          <span className="grid h-8 w-8 place-items-center rounded-full bg-amber-50 text-amber-700 ring-1 ring-amber-200"><TicketCheck size={14} aria-hidden /></span>
          <span><strong className="block text-xs text-ink">2 need booking</strong><small className="text-[11px] text-slate-500">Lunch and Orangerie</small></span>
        </button>
        <button type="button" className="flex items-center gap-3 px-4 py-3 text-left hover:bg-white">
          <span className="grid h-8 w-8 place-items-center rounded-full bg-rose-50 text-rose-700 ring-1 ring-rose-200"><AlertTriangle size={14} aria-hidden /></span>
          <span><strong className="block text-xs text-ink">1 timing note</strong><small className="text-[11px] text-slate-500">Allow entry queue time</small></span>
        </button>
      </div>
      <div className="grid gap-3 p-4 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] sm:p-5">
        <div>
          <p className="text-[10px] font-bold uppercase text-slate-400">Plan</p>
          <p className="mt-1 text-xs leading-relaxed text-slate-600">A focused art day with a long lunch and a lighter late-afternoon museum.</p>
        </div>
        <div>
          <p className="text-[10px] font-bold uppercase text-accent">Transport</p>
          <p className="mt-1 text-xs leading-relaxed text-slate-600">Walk nearby legs; use Metro or taxi across the central districts.</p>
        </div>
      </div>
    </section>
  );
}

function CompactAgendaContext() {
  const rows = [
    ["9:00 AM", "H", "Le Roch Hotel & Spa", "Start"],
    ["10:00 AM", "1", "Louvre Museum", "Confirmed"],
    ["1:15 PM", "2", "Le Comptoir de la Gastronomie", "Needs booking"],
  ];
  return (
    <div className="border-t border-slate-200 bg-surface px-4 py-3 sm:px-5">
      <p className="mb-2 text-[10px] font-bold uppercase text-slate-400">Locked context · Compact agenda</p>
      <div className="divide-y divide-slate-200">
        {rows.map(([time, marker, name, status]) => (
          <div key={name} className="grid grid-cols-[4.5rem_1.5rem_minmax(0,1fr)_auto] items-center gap-2 py-2 text-xs">
            <strong className="text-right text-ink">{time}</strong>
            <span className="grid h-5 w-5 place-items-center rounded-full bg-brand text-[10px] font-bold text-white">{marker}</span>
            <span className="truncate font-medium text-slate-700">{name}</span>
            <span className={status === "Needs booking" ? "text-amber-700" : "text-slate-400"}>{status}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function VariantPreview({ variant }: { variant: Variant }) {
  return (
    <div className="overflow-hidden rounded-md shadow-card ring-1 ring-slate-200">
      {variant === "overview" && <OperationalOverview />}
      {variant === "brief" && <NarrativeBrief />}
      {variant === "actions" && <ActionStrip />}
      <CompactAgendaContext />
    </div>
  );
}

function Scorecard({ variant }: { variant: Variant }) {
  const key = `tripplanner-ux-lab-summary-${variant}`;
  const [scores, setScores] = useState<Record<string, number>>(() => {
    try {
      return JSON.parse(localStorage.getItem(key) || "{}") as Record<string, number>;
    } catch {
      return {};
    }
  });
  const dimensions = ["Day comprehension", "Action visibility", "Travel clarity", "Visual calm", "Mobile fit"];
  const update = (dimension: string, score: number) => {
    const next = { ...scores, [dimension]: score };
    setScores(next);
    localStorage.setItem(key, JSON.stringify(next));
  };
  return (
    <aside className="rounded-md bg-white p-4 ring-1 ring-slate-200">
      <div className="flex items-center gap-2"><Sparkles size={15} className="text-brand" aria-hidden /><h2 className="text-sm font-semibold text-ink">Local scorecard</h2></div>
      <p className="mt-1 text-xs text-slate-500">Scores stay only in this browser.</p>
      <div className="mt-4 space-y-3">
        {dimensions.map((dimension) => (
          <fieldset key={dimension} className="flex items-center justify-between gap-3">
            <legend className="text-xs font-medium text-slate-600">{dimension}</legend>
            <div className="flex gap-1">
              {[1, 2, 3, 4, 5].map((score) => (
                <button key={score} type="button" onClick={() => update(dimension, score)} aria-label={`${dimension}: ${score} of 5`} className={`grid h-7 w-7 place-items-center rounded-full text-[11px] font-semibold ring-1 ${scores[dimension] === score ? "bg-brand text-white ring-brand" : "bg-white text-slate-500 ring-slate-200 hover:ring-brand/30"}`}>{score}</button>
              ))}
            </div>
          </fieldset>
        ))}
      </div>
    </aside>
  );
}

function Lab() {
  const [variant, setVariant] = useState<Variant>("overview");
  const [compare, setCompare] = useState(false);
  return (
    <main className="min-h-full bg-[linear-gradient(180deg,#f8fafc_0,#fafaf9_18rem)] px-4 py-6 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl">
        <header className="flex flex-col gap-4 border-b border-slate-200 pb-5 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <a href="/labs.html" className="mb-3 inline-flex items-center gap-1 text-xs font-semibold text-slate-500 hover:text-brand">← All UX labs</a>
            <p className="text-xs font-bold uppercase text-brand">Internal · Itinerary summary experiment</p>
            <h1 className="display mt-1 text-3xl font-semibold text-ink">Choose what the day summary should prioritize</h1>
            <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-600">Each option sits above the selected Compact Agenda treatment. Compare how quickly the summary explains the day, exposes travel and readiness, and leads into the schedule.</p>
          </div>
          <button type="button" onClick={() => setCompare((value) => !value)} className="btn-ghost self-start lg:self-auto">{compare ? "Inspect one" : "Compare all"} <ChevronRight size={14} aria-hidden /></button>
        </header>

        {!compare && (
          <div className="mt-5 grid gap-2 sm:grid-cols-3" role="tablist" aria-label="Itinerary summary variants">
            {variants.map((item) => (
              <button key={item.id} type="button" role="tab" aria-selected={variant === item.id} onClick={() => setVariant(item.id)} className={`rounded-md p-3 text-left ring-1 transition ${variant === item.id ? "bg-white text-ink shadow-card ring-brand/30" : "bg-white/60 text-slate-600 ring-slate-200 hover:bg-white"}`}>
                <span className="text-sm font-semibold">{item.label}</span>
                <span className="mt-1 block text-xs leading-relaxed text-slate-500">{item.summary}</span>
              </button>
            ))}
          </div>
        )}

        {compare ? (
          <div className="mt-6 grid gap-6 xl:grid-cols-3">
            {variants.map((item) => (
              <div key={item.id} className="min-w-0">
                <div className="mb-3 flex items-center gap-2"><ArrowRight size={14} className="text-brand" aria-hidden /><h2 className="text-sm font-semibold text-ink">{item.label}</h2></div>
                <VariantPreview variant={item.id} />
              </div>
            ))}
          </div>
        ) : (
          <div className="mt-6 grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
            <VariantPreview variant={variant} />
            <Scorecard key={variant} variant={variant} />
          </div>
        )}
      </div>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><Lab /></React.StrictMode>);