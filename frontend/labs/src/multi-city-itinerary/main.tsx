import React, { useState } from "react";
import ReactDOM from "react-dom/client";
import {
  CarFront,
  Check,
  Clock3,
  MapPin,
  Plane,
  Route,
  TrainFront,
} from "lucide-react";
import "../../../src/index.css";
import { DecisionCapture } from "../shared/DecisionCapture";
import { LabNavigation } from "../shared/LabNavigation";
import { LabScope } from "../shared/LabScope";
import { OptionContrast } from "../shared/OptionContrast";
import "../shared/experiment-layout.css";

type VariantId = "transition-spine" | "stay-handoff" | "city-chapters";
type TravelMode = "road" | "train" | "flight";

interface Journey {
  label: string;
  icon: typeof CarFront;
  depart: string;
  arrive: string;
  duration: string;
  distance: string;
  origin: string;
  destination: string;
  detail: string;
  checkIn: string;
}

const journeys: Record<TravelMode, Journey> = {
  road: {
    label: "Private car",
    icon: CarFront,
    depart: "09:00",
    arrive: "15:30",
    duration: "6 hr 30 min",
    distance: "397 km",
    origin: "Rambagh Palace",
    destination: "The Leela Palace Udaipur",
    detail: "Door to door via NH 48 · comfort stop near Bhilwara",
    checkIn: "16:00",
  },
  train: {
    label: "Intercity train",
    icon: TrainFront,
    depart: "09:35",
    arrive: "16:45",
    duration: "7 hr 10 min",
    distance: "430 km",
    origin: "Jaipur Junction",
    destination: "Udaipur City station",
    detail: "Hotel transfer 25 min before departure · 18 min after arrival",
    checkIn: "17:20",
  },
  flight: {
    label: "Flight",
    icon: Plane,
    depart: "10:25",
    arrive: "11:35",
    duration: "1 hr 10 min",
    distance: "330 km air",
    origin: "Jaipur Airport (JAI)",
    destination: "Maharana Pratap Airport (UDR)",
    detail: "Leave hotel 07:45 · airport transfer after landing 45 min",
    checkIn: "13:15",
  },
};

const variants = [
  {
    id: "transition-spine" as const,
    label: "A · Transition spine",
    summary: "One chronological chain makes checkout, travel, arrival, and check-in auditable.",
    delta: "Changes only the row hierarchy: every event stays in one ordered timeline. Unlike B, hotels are not paired as cards; unlike C, the day is not split into city chapters.",
  },
  {
    id: "stay-handoff" as const,
    label: "B · Stay handoff",
    summary: "The old and new stays frame one prominent transfer object between them.",
    delta: "Changes only the stay grouping: origin and destination hotels become a paired handoff above the journey. Unlike A, this is not one timeline; unlike C, there are no Morning/Journey/Evening sections.",
  },
  {
    id: "city-chapters" as const,
    label: "C · City chapters",
    summary: "Morning, Journey, and Evening sections emphasize the change in destination context.",
    delta: "Changes only the day grouping: content is divided into origin, journey, and destination chapters. Unlike A, there is no continuous spine; unlike B, the two hotels are not paired.",
  },
];

function ModeControl({ mode, onChange }: { mode: TravelMode; onChange: (mode: TravelMode) => void }) {
  return <div className="grid grid-cols-3 gap-1 rounded-md bg-slate-100 p-1" role="group" aria-label="Transfer mode">{(Object.keys(journeys) as TravelMode[]).map((id) => { const Icon = journeys[id].icon; return <button key={id} type="button" onClick={() => onChange(id)} aria-pressed={mode === id} className={`flex h-8 items-center justify-center gap-1.5 rounded-[5px] text-[11px] font-semibold capitalize ${mode === id ? "bg-white text-ink shadow-sm" : "text-slate-500"}`}><Icon size={13} aria-hidden />{id}</button>; })}</div>;
}

function HotelRow({ type, time, name, city, image }: { type: "Check out" | "Check in"; time: string; name: string; city: string; image: string }) {
  return <div className="grid grid-cols-[3.4rem_3.75rem_minmax(0,1fr)] gap-2 border-b border-slate-100 py-3 last:border-0"><div><p className="text-[9px] font-bold uppercase text-slate-400">{type}</p><p className="mt-0.5 text-xs font-bold text-ink">{time}</p></div><img src={image} alt="" className="h-12 w-[3.75rem] rounded-md object-cover" /><div className="min-w-0 self-center"><div className="flex items-center gap-1.5"><span className="grid h-5 w-5 place-items-center rounded-full border border-rose-300 text-[10px] font-bold text-brand">H</span><p className="truncate text-sm font-semibold text-ink">{name}</p></div><p className="mt-1 text-[10px] text-slate-500"><MapPin size={10} className="inline" aria-hidden /> {city}</p></div></div>;
}

function TravelBlock({ journey, compact = false }: { journey: Journey; compact?: boolean }) {
  const Icon = journey.icon;
  return <div className={`border-y border-teal-100 bg-teal-50/70 ${compact ? "px-3 py-2.5" : "px-3 py-3"}`}><div className="flex items-center gap-2"><span className="grid h-8 w-8 shrink-0 place-items-center rounded-md bg-white text-teal-700 shadow-sm"><Icon size={16} aria-hidden /></span><div className="min-w-0 flex-1"><div className="flex items-center justify-between gap-2"><p className="text-xs font-bold text-ink">{journey.label} · Jaipur → Udaipur</p><span className="shrink-0 text-[10px] font-semibold text-teal-800">{journey.duration}</span></div><p className="mt-0.5 truncate text-[10px] text-slate-600">{journey.distance} · {journey.detail}</p></div></div><div className="mt-2 grid grid-cols-[auto_1fr_auto] items-center gap-2 text-[10px]"><span><strong className="block text-xs text-ink">{journey.depart}</strong>{journey.origin}</span><span className="h-px bg-teal-300" /><span className="text-right"><strong className="block text-xs text-ink">{journey.arrive}</strong>{journey.destination}</span></div></div>;
}

function TransitionSpine({ journey }: { journey: Journey }) {
  return <div data-lab-change="Chronological multi-city transition day"><HotelRow type="Check out" time="08:30" name="Rambagh Palace" city="Jaipur" image="https://images.unsplash.com/photo-1564501049412-61c2a3083791?auto=format&fit=crop&w=300&q=80" /><TravelBlock journey={journey} /><HotelRow type="Check in" time={journey.checkIn} name="The Leela Palace Udaipur" city="Udaipur" image="https://images.unsplash.com/photo-1613490493576-7fde63acd811?auto=format&fit=crop&w=300&q=80" /><div className="grid grid-cols-[3.4rem_1.25rem_minmax(0,1fr)] gap-2 py-3"><div><p className="text-[9px] font-bold uppercase text-slate-400">Arrive</p><p className="mt-0.5 text-xs font-bold text-ink">19:30</p></div><span className="grid h-5 w-5 place-items-center rounded-full border border-rose-300 text-[10px] font-bold text-brand">1</span><div><p className="text-sm font-semibold text-ink">Ambrai · lakeside dinner</p><p className="mt-1 text-[10px] text-slate-500">10 min taxi from hotel · reservation needed</p></div></div></div>;
}

function StayHandoff({ journey }: { journey: Journey }) {
  return <div data-lab-change="Stay-to-stay handoff"><div className="grid grid-cols-2 gap-2"><div className="overflow-hidden rounded-md ring-1 ring-slate-200"><img src="https://images.unsplash.com/photo-1564501049412-61c2a3083791?auto=format&fit=crop&w=500&q=80" alt="" className="h-24 w-full object-cover" /><div className="p-2"><p className="text-[9px] font-bold uppercase text-slate-400">Leaving Jaipur · 08:30</p><p className="mt-1 text-xs font-semibold text-ink">Rambagh Palace</p><p className="mt-1 text-[10px] text-slate-500">Checkout · bags with driver</p></div></div><div className="overflow-hidden rounded-md ring-1 ring-slate-200"><img src="https://images.unsplash.com/photo-1613490493576-7fde63acd811?auto=format&fit=crop&w=500&q=80" alt="" className="h-24 w-full object-cover" /><div className="p-2"><p className="text-[9px] font-bold uppercase text-slate-400">Arriving Udaipur · {journey.checkIn}</p><p className="mt-1 text-xs font-semibold text-ink">The Leela Palace</p><p className="mt-1 text-[10px] text-slate-500">Check-in · lake transfer ready</p></div></div></div><div className="mt-3"><TravelBlock journey={journey} compact /></div><div className="mt-3 rounded-md bg-slate-50 px-3 py-2 text-[10px] text-slate-600"><strong className="text-ink">Evening remains visible:</strong> settle in, then Ambrai dinner at 19:30.</div></div>;
}

function CityChapters({ journey }: { journey: Journey }) {
  return <div data-lab-change="Origin, journey, and destination chapters" className="space-y-2"><section className="border-l-4 border-amber-400 bg-amber-50/50 px-3 py-3"><p className="text-[9px] font-bold uppercase text-amber-800">Morning · Jaipur</p><h3 className="mt-1 text-sm font-semibold text-ink">Close the Jaipur stay</h3><p className="mt-1 text-xs text-slate-600">08:00 breakfast · 08:30 Rambagh Palace checkout</p></section><section className="border-l-4 border-teal-500 bg-teal-50/60 px-3 py-3"><p className="text-[9px] font-bold uppercase text-teal-800">Journey · Jaipur to Udaipur</p><div className="mt-2"><TravelBlock journey={journey} compact /></div></section><section className="border-l-4 border-rose-400 bg-rose-50/40 px-3 py-3"><p className="text-[9px] font-bold uppercase text-brand">Evening · Udaipur</p><h3 className="mt-1 text-sm font-semibold text-ink">Start the lake stay</h3><p className="mt-1 text-xs text-slate-600">{journey.checkIn} The Leela Palace check-in · 19:30 Ambrai dinner</p></section></div>;
}

function Preview({ variant }: { variant: VariantId }) {
  const [mode, setMode] = useState<TravelMode>("road");
  const journey = journeys[mode];
  return <div className="grid min-h-[39rem] grid-cols-[25rem_minmax(0,1fr)] overflow-hidden rounded-md bg-slate-100 ring-1 ring-slate-200" style={{ minWidth: 800 }}><aside className="bg-white"><header className="border-b border-slate-100 px-4 py-3"><p className="text-[9px] font-bold uppercase text-brand">Day 4 · Tue, 13 Oct</p><h2 className="display mt-1 text-lg font-semibold text-ink">Jaipur → Udaipur</h2><div className="mt-2 flex items-center gap-3 text-[10px] text-slate-500"><span><Clock3 size={11} className="inline" aria-hidden /> 08:30–20:45</span><span><Route size={11} className="inline" aria-hidden /> Transfer day</span></div></header><div className="border-b border-slate-100 p-3"><ModeControl mode={mode} onChange={setMode} /></div><div className="p-4">{variant === "transition-spine" ? <TransitionSpine journey={journey} /> : variant === "stay-handoff" ? <StayHandoff journey={journey} /> : <CityChapters journey={journey} />}</div></aside><div className="relative overflow-hidden"><img src="https://images.unsplash.com/photo-1595658658481-d53d3f999875?auto=format&fit=crop&w=1200&q=80" alt="Udaipur lake and palace" className="h-full w-full object-cover" /><div className="absolute inset-x-5 bottom-5 bg-white/90 p-4 shadow-pop backdrop-blur"><p className="text-[10px] font-bold uppercase text-brand">Map remains context only in this Lab</p><p className="mt-1 text-sm font-semibold text-ink">The transition day must read completely before opening its route.</p></div></div></div>;
}

function Lab() {
  const [active, setActive] = useState<VariantId>("transition-spine");
  const activeVariant = variants.find((item) => item.id === active)!;
  return <main className="min-h-full bg-[linear-gradient(180deg,#f8fafc_0,#fafaf9_22rem)] px-4 py-6 sm:px-6 lg:px-8"><div className="mx-auto max-w-7xl"><header className="border-b border-slate-200 pb-5"><LabNavigation detail labId="multi-city-itinerary" /><div className="mt-4 flex items-center gap-2 text-brand"><Route size={15} aria-hidden /><p className="text-xs font-bold uppercase">Active experiment · Multi-city itinerary</p></div><h1 className="display mt-1 text-3xl font-semibold text-ink">Transition-day itinerary design</h1><p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-600">Compare how a multi-city day should show checkout from the old stay, the complete road, rail, or flight journey, check-in at the new stay, and any usable destination time afterward.</p></header><LabScope labId="multi-city-itinerary" /><OptionContrast labId="multi-city-itinerary" /><div className="lab-variant-grid mt-5" role="tablist" aria-label="Transition-day variants">{variants.map((variant) => <button key={variant.id} type="button" role="tab" aria-selected={active === variant.id} onClick={() => setActive(variant.id)} className={`rounded-md p-3 text-left ring-1 ${active === variant.id ? "bg-white shadow-card ring-brand/30" : "bg-white/70 ring-slate-200 hover:bg-white"}`}><span className="text-sm font-semibold text-ink">{variant.label}</span><span className="mt-1 block text-xs leading-relaxed text-slate-500">{variant.summary}</span><span className="mt-2 block border-t border-slate-100 pt-2 text-[11px] leading-relaxed text-slate-600"><strong className="text-ink">Exact delta:</strong> {variant.delta}</span></button>)}</div><section className="mt-6"><div className="mb-3 flex items-start justify-between gap-4"><div><p className="text-[10px] font-bold uppercase text-slate-400">Interactive production-scale preview</p><h2 className="mt-0.5 text-lg font-semibold text-ink">{activeVariant.label}</h2><p className="mt-1 max-w-3xl text-xs leading-relaxed text-slate-600"><strong className="text-ink">This preview changes:</strong> {activeVariant.delta}</p></div>{active === "transition-spine" && <p className="shrink-0 text-xs font-semibold text-emerald-700"><Check size={13} className="inline" aria-hidden /> Recommended for schedule auditability</p>}</div><div className="overflow-x-auto pb-2"><Preview key={active} variant={active} /></div></section><div className="mt-6"><DecisionCapture labId="multi-city-itinerary" labTitle="Transition-day itinerary design" options={variants} activeOption={active} onChoose={(id) => setActive(id as VariantId)} /></div></div></main>;
}

ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><Lab /></React.StrictMode>);