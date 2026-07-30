import React, { useCallback, useState } from "react";
import ReactDOM from "react-dom/client";
import { CalendarCheck2, Check, ChevronDown, Clock3, MapPin, Route } from "lucide-react";
import "../index.css";
import { DecisionCapture } from "../labs/DecisionCapture";

type Variant = "ledger" | "circuit" | "focus";

const variants: Array<{ id: Variant; label: string; note: string }> = [
  { id: "ledger", label: "A · One-line ledger", note: "Maximum simultaneous detail; all circuit endpoints remain rows." },
  { id: "circuit", label: "B · Circuit header", note: "Recommended: hotel endpoints move into one truthful day-level circuit line." },
  { id: "focus", label: "C · Progressive focus", note: "Quiet default rows; one selected stop reveals booking and route detail." },
];

const stops = [
  { marker: "1", time: "10:00", name: "Kew Gardens", kind: "Attraction", duration: "2 hr", travel: "42 min", booked: false },
  { marker: "2", time: "14:00", name: "Tate Modern", kind: "Attraction", duration: "1 hr 30", travel: "47 min", booked: true },
  { marker: "3", time: "18:30", name: "Farmacy", kind: "Dinner", duration: "1 hr", travel: "22 min", booked: false },
];

function Booking({ booked, iconOnly = false }: { booked: boolean; iconOnly?: boolean }) {
  const Icon = booked ? Check : CalendarCheck2;
  return (
    <span className={`inline-flex h-6 items-center gap-1 rounded-full px-2 text-[10px] font-semibold ring-1 ${booked ? "bg-emerald-50 text-emerald-700 ring-emerald-200" : "bg-amber-50 text-amber-700 ring-amber-200"}`}>
      <Icon size={11} aria-hidden />{iconOnly ? null : booked ? "Confirmed" : "To book"}
    </span>
  );
}

function Metrics() {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-600">
      <strong className="text-ink">3 planned stops</strong>
      <span className="inline-flex items-center gap-1"><Clock3 size={11} /> E2E 8 hr 24 min · 09:50–20:14 est.</span>
      <span className="inline-flex items-center gap-1"><Route size={11} /> Travel 2 hr 7 min · 37.9 km</span>
      <span className="text-amber-700">1 confirmed · 2 to book</span>
    </div>
  );
}

function LabHeader() {
  return (
    <header className="border-b border-slate-200 px-3 py-2.5">
      <div className="flex items-center gap-2">
        <span className="grid h-7 w-7 place-items-center rounded-full bg-amber-600 text-xs font-bold text-white">4</span>
        <div className="min-w-0 flex-1">
          <p className="text-[10px] font-bold uppercase text-amber-700">Saturday · 29 August 2026</p>
          <h2 className="truncate text-sm font-semibold text-ink">Nature, modern art and dinner</h2>
        </div>
        <button className="grid h-7 w-7 place-items-center rounded-full text-slate-500 hover:bg-slate-100" title="Show complete circuit"><MapPin size={15} /></button>
      </div>
      <div className="mt-2"><Metrics /></div>
    </header>
  );
}

function Ledger() {
  return (
    <div>
      <LabHeader />
      <div className="divide-y divide-slate-100">
        <div className="grid grid-cols-[3.5rem_1fr_auto] items-center gap-2 px-3 py-1.5 text-xs"><span className="font-semibold text-slate-500">Depart</span><strong className="truncate">H · Wilde Aparthotels</strong><span className="text-slate-400">09:50 est.</span></div>
        {stops.map((stop) => <div key={stop.name} className="grid grid-cols-[3.5rem_minmax(0,1fr)_auto] items-center gap-2 px-3 py-1.5 text-xs"><span><strong>{stop.time}</strong><small className="block text-[9px] text-teal-700">{stop.travel}</small></span><span className="truncate"><b className="mr-1 text-amber-700">{stop.marker}</b>{stop.name}<small className="ml-2 text-slate-400">{stop.duration}</small></span><Booking booked={stop.booked} iconOnly /></div>)}
        <div className="grid grid-cols-[3.5rem_1fr_auto] items-center gap-2 px-3 py-1.5 text-xs"><span className="font-semibold text-slate-500">Return</span><strong className="truncate">H · Wilde Aparthotels</strong><span className="text-slate-400">20:14 est.</span></div>
      </div>
    </div>
  );
}

function Circuit() {
  return (
    <div>
      <LabHeader />
      <div className="flex items-center gap-2 border-b border-teal-100 bg-teal-50/70 px-3 py-1.5 text-[11px] text-teal-800"><Route size={12} /><strong>Wilde Aparthotels</strong><span>Depart 09:50</span><span aria-hidden>→</span><span>Return 20:14 est.</span></div>
      <div className="divide-y divide-slate-100 px-3">
        {stops.map((stop) => <div key={stop.name} className="grid grid-cols-[3.4rem_minmax(0,1fr)_auto] items-center gap-2 py-2"><span className="text-xs font-bold tabular-nums text-ink">{stop.time}<small className="block text-[9px] font-medium text-teal-700">↳ {stop.travel}</small></span><span className="min-w-0"><span className="block truncate text-xs font-semibold"><b className="mr-1.5 text-amber-700">{stop.marker}</b>{stop.name}</span><small className="text-[10px] text-slate-500">{stop.kind} · {stop.duration}</small></span><Booking booked={stop.booked} /></div>)}
      </div>
    </div>
  );
}

function Focus() {
  return (
    <div>
      <LabHeader />
      <div className="divide-y divide-slate-100 px-3">
        {stops.map((stop, index) => <div key={stop.name} className={`py-2 ${index === 1 ? "bg-slate-50 -mx-3 px-3" : ""}`}><div className="grid grid-cols-[3.4rem_minmax(0,1fr)_auto] items-center gap-2"><strong className="text-xs tabular-nums">{stop.time}</strong><span className="truncate text-xs font-semibold"><b className="mr-1.5 text-amber-700">{stop.marker}</b>{stop.name}</span>{index === 1 ? <ChevronDown size={14} className="text-slate-400" /> : <Booking booked={stop.booked} iconOnly />}</div>{index === 1 && <div className="ml-[3.4rem] mt-1.5 flex items-center gap-2 text-[10px] text-slate-500"><span>{stop.kind} · {stop.duration}</span><span className="text-teal-700">Travel {stop.travel}</span><Booking booked={stop.booked} /></div>}</div>)}
      </div>
    </div>
  );
}

function App() {
  const [active, setActive] = useState<Variant>("circuit");
  const choose = useCallback((value: string) => setActive(value as Variant), []);
  return (
    <main className="min-h-screen bg-[linear-gradient(180deg,#f8fafc_0,#fff7ed_100%)] px-4 py-7">
      <div className="mx-auto max-w-5xl">
        <p className="text-[10px] font-bold uppercase text-brand">Active UX experiment</p>
        <h1 className="display mt-1 text-3xl font-semibold text-ink">Compact itinerary density</h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-600">Remove repeated state, preserve truthful circuit timing, and fit a useful day in roughly one-third of a desktop viewport. The 320 px frame below is the constraint.</p>
        <div className="mt-5 grid gap-2 sm:grid-cols-3">{variants.map((variant) => <button key={variant.id} onClick={() => setActive(variant.id)} className={`rounded-md p-3 text-left ring-1 ${active === variant.id ? "bg-white ring-brand/40 shadow-card" : "bg-white/60 ring-slate-200"}`}><strong className="text-xs text-ink">{variant.label}</strong><span className="mt-1 block text-[11px] leading-relaxed text-slate-500">{variant.note}</span></button>)}</div>
        <section className="mt-4 overflow-hidden rounded-md bg-white shadow-pop ring-1 ring-slate-200" style={{ minHeight: 320 }} aria-label="320 pixel itinerary density preview">{active === "ledger" ? <Ledger /> : active === "circuit" ? <Circuit /> : <Focus />}</section>
        <p className="mt-2 text-right text-[10px] font-semibold uppercase text-slate-400">320 px target frame</p>
        <div className="mt-6"><DecisionCapture labId="itinerary-density" labTitle="Compact itinerary density" options={variants.map(({ id, label }) => ({ id, label }))} activeOption={active} onChoose={choose} /></div>
      </div>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><App /></React.StrictMode>);
