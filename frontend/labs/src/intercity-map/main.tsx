import React, { useState } from "react";
import ReactDOM from "react-dom/client";
import {
  ArrowLeft,
  CarFront,
  Check,
  Circle,
  Map,
  Plane,
  Route,
  TrainFront,
} from "lucide-react";
import "../../../src/index.css";
import { DecisionCapture } from "../shared/DecisionCapture";
import { LabScope } from "../shared/LabScope";
import "../shared/experiment-layout.css";

type VariantId = "full-journey" | "journey-strip" | "layer-toggle";
type TravelMode = "road" | "train" | "flight";

const variants = [
  { id: "full-journey" as const, label: "A · Connected day journey", summary: "Fit both cities, their local circuits, and the inter-city leg in one complete day view." },
  { id: "journey-strip" as const, label: "B · Journey strip + local map", summary: "Keep a useful destination-city map scale and summarize the long leg in a pinned strip." },
  { id: "layer-toggle" as const, label: "C · Optional inter-city layer", summary: "Show both scales by default but let the user independently hide local or inter-city geometry." },
];

const modes = {
  road: { label: "Private car", icon: CarFront, duration: "6 hr 30 min", distance: "397 km", detail: "NH 48 via Bhilwara" },
  train: { label: "Intercity train", icon: TrainFront, duration: "7 hr 10 min", distance: "430 km", detail: "Jaipur Junction → Udaipur City" },
  flight: { label: "Flight", icon: Plane, duration: "1 hr 10 min", distance: "330 km air", detail: "JAI → UDR · transfers shown separately" },
};

function ModeControl({ mode, onChange }: { mode: TravelMode; onChange: (mode: TravelMode) => void }) {
  return <div className="grid grid-cols-3 gap-1 rounded-md bg-slate-100 p-1" role="group" aria-label="Inter-city map mode">{(Object.keys(modes) as TravelMode[]).map((id) => { const Icon = modes[id].icon; return <button key={id} type="button" onClick={() => onChange(id)} aria-pressed={mode === id} className={`flex h-8 items-center justify-center gap-1.5 rounded-[5px] text-[11px] font-semibold capitalize ${mode === id ? "bg-white text-ink shadow-sm" : "text-slate-500"}`}><Icon size={13} aria-hidden />{id}</button>; })}</div>;
}

function Hub({ city, hotel, className, destination = false }: { city: string; hotel: string; className: string; destination?: boolean }) {
  return <div className={`absolute z-20 ${className}`}><div className={`grid h-10 w-10 place-items-center rounded-full border-4 border-white text-xs font-bold text-white shadow-pop ${destination ? "bg-brand" : "bg-teal-700"}`}>H</div><div className="absolute left-1/2 top-11 w-36 -translate-x-1/2 bg-white/95 px-2 py-1.5 text-center shadow-card"><p className="text-[10px] font-bold text-ink">{city}</p><p className="truncate text-[9px] text-slate-500">{hotel}</p></div></div>;
}

function LocalCircuit({ className, color, reverse = false }: { className: string; color: string; reverse?: boolean }) {
  return <div className={`absolute h-24 w-28 rounded-[50%] border-2 border-dashed ${className}`} style={{ borderColor: color }}><span className={`absolute grid h-6 w-6 place-items-center rounded-full border-2 bg-white text-[9px] font-bold ${reverse ? "bottom-0 right-1" : "left-1 top-0"}`} style={{ borderColor: color, color }}>1</span><span className={`absolute grid h-6 w-6 place-items-center rounded-full border-2 bg-white text-[9px] font-bold ${reverse ? "left-0 top-2" : "bottom-1 right-0"}`} style={{ borderColor: color, color }}>2</span></div>;
}

function Connector({ mode }: { mode: TravelMode }) {
  const config = modes[mode];
  const Icon = config.icon;
  const lineStyle = mode === "road" ? "bg-brand" : mode === "train" ? "border-t-4 border-dashed border-brand" : "border-t-4 border-dotted border-sky-600";
  return <div className="absolute left-[28%] top-[48%] z-10 h-16 w-[47%] -rotate-[10deg]"><div className={`absolute left-0 top-7 h-1 w-full ${lineStyle}`} /><div className="absolute left-1/2 top-0 -translate-x-1/2 rotate-[10deg] bg-white px-2 py-1.5 text-center shadow-card"><Icon size={15} className={mode === "flight" ? "mx-auto text-sky-700" : "mx-auto text-brand"} aria-hidden /><p className="mt-0.5 text-[9px] font-bold text-ink">{config.duration}</p><p className="text-[8px] text-slate-500">{config.distance}</p></div></div>;
}

function Terminals({ mode }: { mode: TravelMode }) {
  if (mode === "road") return null;
  const Icon = mode === "flight" ? Plane : TrainFront;
  return <><span className="absolute left-[31%] top-[43%] z-20 grid h-7 w-7 place-items-center rounded-md bg-white text-sky-700 shadow-card"><Icon size={14} aria-hidden /></span><span className="absolute right-[25%] top-[53%] z-20 grid h-7 w-7 place-items-center rounded-md bg-white text-sky-700 shadow-card"><Icon size={14} aria-hidden /></span></>;
}

function MapCanvas({ mode, localVisible = true, intercityVisible = true, destinationOnly = false }: { mode: TravelMode; localVisible?: boolean; intercityVisible?: boolean; destinationOnly?: boolean }) {
  return <div className="relative h-[31rem] overflow-hidden bg-[#e8e2d4]" data-lab-change="Inter-city journey geometry and day framing"><img src="https://images.unsplash.com/photo-1526778548025-fa2f459cd5c1?auto=format&fit=crop&w=1400&q=70" alt="Map texture" className="absolute inset-0 h-full w-full object-cover opacity-25 mix-blend-multiply" /><div className="absolute inset-0 bg-[linear-gradient(120deg,rgba(240,253,250,.72),rgba(255,247,237,.68))]" />{!destinationOnly && <Hub city="Jaipur" hotel="Rambagh Palace · checkout 08:30" className="left-[17%] top-[28%]" />}{!destinationOnly && localVisible && <LocalCircuit className="left-[11%] top-[19%]" color="#0f766e" />}{localVisible && <LocalCircuit className={destinationOnly ? "left-[39%] top-[35%]" : "right-[12%] top-[57%]"} color="#e11d48" reverse />}{destinationOnly ? <Hub city="Udaipur" hotel="The Leela Palace · check-in 16:00" className="left-[49%] top-[48%]" destination /> : <Hub city="Udaipur" hotel="The Leela Palace · check-in 16:00" className="right-[18%] top-[64%]" destination />}{!destinationOnly && intercityVisible && <><Connector mode={mode} /><Terminals mode={mode} /></>}<div className="absolute bottom-3 left-3 flex gap-2 bg-white/95 px-2.5 py-2 text-[9px] text-slate-600 shadow-card"><span className="inline-flex items-center gap-1"><Circle size={8} fill="#0f766e" className="text-teal-700" aria-hidden /> Jaipur local</span><span className="inline-flex items-center gap-1"><Circle size={8} fill="#e11d48" className="text-brand" aria-hidden /> Udaipur local</span>{intercityVisible && <span className="inline-flex items-center gap-1"><Route size={10} className="text-brand" aria-hidden /> Inter-city</span>}</div></div>;
}

function JourneyStrip({ mode }: { mode: TravelMode }) {
  const config = modes[mode];
  const Icon = config.icon;
  return <div><div data-lab-change="Persistent inter-city journey strip" className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 border-b border-slate-200 bg-white px-4 py-3"><div><p className="text-[9px] font-bold uppercase text-slate-400">08:30 · Check out</p><p className="text-xs font-semibold text-ink">Rambagh Palace · Jaipur</p></div><div className="min-w-40 text-center"><Icon size={15} className="mx-auto text-brand" aria-hidden /><p className="mt-1 text-[9px] font-bold text-ink">{config.duration} · {config.distance}</p><div className="mt-1 h-px bg-brand" /></div><div className="text-right"><p className="text-[9px] font-bold uppercase text-slate-400">16:00 · Check in</p><p className="text-xs font-semibold text-ink">The Leela Palace · Udaipur</p></div></div><MapCanvas mode={mode} destinationOnly /></div>;
}

function LayeredMap({ mode }: { mode: TravelMode }) {
  const [localVisible, setLocalVisible] = useState(true);
  const [intercityVisible, setIntercityVisible] = useState(true);
  return <div><div data-lab-change="Independent route layers" className="flex items-center gap-2 border-b border-slate-200 bg-white px-4 py-2"><p className="mr-auto text-xs font-semibold text-ink">Day 4 route layers</p><label className="inline-flex items-center gap-1.5 text-[10px] font-semibold text-slate-600"><input type="checkbox" checked={localVisible} onChange={(event) => setLocalVisible(event.target.checked)} /> Local plans</label><label className="inline-flex items-center gap-1.5 text-[10px] font-semibold text-slate-600"><input type="checkbox" checked={intercityVisible} onChange={(event) => setIntercityVisible(event.target.checked)} /> Inter-city travel</label></div><MapCanvas mode={mode} localVisible={localVisible} intercityVisible={intercityVisible} /></div>;
}

function Preview({ variant }: { variant: VariantId }) {
  const [mode, setMode] = useState<TravelMode>("road");
  const config = modes[mode];
  const Icon = config.icon;
  return <div className="overflow-hidden rounded-md bg-white ring-1 ring-slate-200" style={{ minWidth: 800 }}><header className="flex h-12 items-center gap-3 border-b border-slate-200 px-4"><Map size={15} className="text-brand" aria-hidden /><div><p className="text-[9px] font-bold uppercase text-brand">Day 4 · Transfer day</p><h2 className="text-sm font-semibold text-ink">Jaipur → Udaipur</h2></div><div className="ml-auto w-64"><ModeControl mode={mode} onChange={setMode} /></div></header>{variant === "full-journey" ? <MapCanvas mode={mode} /> : variant === "journey-strip" ? <JourneyStrip mode={mode} /> : <LayeredMap mode={mode} />}<footer className="flex items-center gap-2 border-t border-slate-100 px-4 py-2.5 text-[10px] text-slate-600"><Icon size={13} className="text-brand" aria-hidden /><strong className="text-ink">{config.label}:</strong> {config.detail}<span className="ml-auto font-semibold text-emerald-700">Open journey · no forced return to Jaipur</span></footer></div>;
}

function Lab() {
  const [active, setActive] = useState<VariantId>("full-journey");
  return <main className="min-h-full bg-[linear-gradient(180deg,#f8fafc_0,#fafaf9_22rem)] px-4 py-6 sm:px-6 lg:px-8"><div className="mx-auto max-w-7xl"><header className="border-b border-slate-200 pb-5"><a href="./catalog.html" className="inline-flex items-center gap-1 text-xs font-semibold text-slate-500 hover:text-brand"><ArrowLeft size={14} aria-hidden /> Back to All Labs</a><div className="mt-4 flex items-center gap-2 text-brand"><Map size={15} aria-hidden /><p className="text-xs font-bold uppercase">Active experiment · Map completeness</p></div><h1 className="display mt-1 text-3xl font-semibold text-ink">Inter-city travel on the day map</h1><p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-600">Reconsider the rule that removes inter-city travel from the map circuit. Compare complete transfer-day framing while preserving ordinary hotel-return loops and using distinct geometry for road, rail, and flight.</p></header><LabScope labId="intercity-map" /><div className="lab-variant-grid mt-5" role="tablist" aria-label="Inter-city map variants">{variants.map((variant) => <button key={variant.id} type="button" role="tab" aria-selected={active === variant.id} onClick={() => setActive(variant.id)} className={`rounded-md p-3 text-left ring-1 ${active === variant.id ? "bg-white shadow-card ring-brand/30" : "bg-white/70 ring-slate-200 hover:bg-white"}`}><span className="text-sm font-semibold text-ink">{variant.label}</span><span className="mt-1 block text-xs leading-relaxed text-slate-500">{variant.summary}</span></button>)}</div><section className="mt-6"><div className="mb-3 flex items-center justify-between"><div><p className="text-[10px] font-bold uppercase text-slate-400">Interactive production-scale preview</p><h2 className="mt-0.5 text-lg font-semibold text-ink">{variants.find((item) => item.id === active)?.label}</h2></div>{active === "full-journey" && <p className="text-xs font-semibold text-emerald-700"><Check size={13} className="inline" aria-hidden /> Recommended for day completeness</p>}</div><div className="overflow-x-auto pb-2"><Preview key={active} variant={active} /></div></section><div className="mt-6"><DecisionCapture labId="intercity-map" labTitle="Inter-city travel on the day map" options={variants} activeOption={active} onChoose={(id) => setActive(id as VariantId)} /></div></div></main>;
}

ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><Lab /></React.StrictMode>);