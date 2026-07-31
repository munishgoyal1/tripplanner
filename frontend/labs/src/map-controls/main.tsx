import React, { useCallback, useState } from "react";
import ReactDOM from "react-dom/client";
import {
  ArrowLeft,
  CalendarDays,
  Check,
  Clock3,
  Compass,
  Hotel,
  ListFilter,
  Map,
  MapPin,
  Maximize2,
  Navigation,
  PanelTop,
  Plus,
  Route,
  Search,
  Utensils,
  X,
} from "lucide-react";
import "../../../src/index.css";
import { DecisionCapture } from "../shared/DecisionCapture";
import { LabNavigation } from "../shared/LabNavigation";
import { LabScope } from "../shared/LabScope";

type Variant = "ribbon" | "deck" | "schedule";
type Scope = "all" | number;

interface DayPlan {
  day: number;
  short: string;
  date: string;
  title: string;
  color: string;
  start: string;
  end: string;
  schedule: string;
  travel: string;
  distance: string;
  mode: string;
  stops: number;
  confirmed: number;
}

const variants: Array<{ id: Variant; label: string; note: string; strength: string }> = [
  { id: "ribbon", label: "A · Unified route ribbon", note: "Recommended. Scope, Add stop, and a structured route brief share two stable rows.", strength: "Fastest scan with the fewest moving parts." },
  { id: "deck", label: "B · Contextual command deck", note: "A quiet primary bar opens focused drawers for adding and route evidence.", strength: "Maximum map area when commands are idle." },
  { id: "schedule", label: "C · Schedule-first strip", note: "A bottom timeline makes day sequence and operational timing the dominant control.", strength: "Best day-to-day comparison and travel rhythm." },
];

const days: DayPlan[] = [
  { day: 1, short: "Wed", date: "26 Aug", title: "Arrival and the Left Bank", color: "#dc5a4a", start: "14:10", end: "20:30", schedule: "6 hr 20", travel: "52 min", distance: "14.2 km", mode: "Car + walk", stops: 3, confirmed: 2 },
  { day: 2, short: "Thu", date: "27 Aug", title: "Icons along the Seine", color: "#0f766e", start: "08:45", end: "20:10", schedule: "11 hr 25", travel: "1 hr 38", distance: "23.1 km", mode: "Metro + walk", stops: 4, confirmed: 2 },
  { day: 3, short: "Fri", date: "28 Aug", title: "Montmartre and the arcades", color: "#b45309", start: "09:20", end: "21:05", schedule: "11 hr 45", travel: "1 hr 22", distance: "18.7 km", mode: "Metro + walk", stops: 4, confirmed: 1 },
  { day: 4, short: "Sat", date: "29 Aug", title: "Versailles day trip", color: "#2563eb", start: "08:10", end: "19:40", schedule: "11 hr 30", travel: "2 hr 05", distance: "47.8 km", mode: "RER + walk", stops: 3, confirmed: 3 },
  { day: 5, short: "Sun", date: "30 Aug", title: "Markets and departure", color: "#7c3aed", start: "08:30", end: "13:20", schedule: "4 hr 50", travel: "48 min", distance: "12.4 km", mode: "Taxi + walk", stops: 2, confirmed: 1 },
];

const pinData = [
  { id: "hotel", label: "H", name: "Hôtel Le Six", day: 0, left: "42%", top: "61%" },
  { id: "louvre", label: "1", name: "Louvre Museum", day: 2, left: "48%", top: "41%" },
  { id: "tuileries", label: "2", name: "Tuileries Garden", day: 2, left: "41%", top: "37%" },
  { id: "orangerie", label: "3", name: "Musée de l'Orangerie", day: 2, left: "35%", top: "43%" },
  { id: "eiffel", label: "4", name: "Eiffel Tower", day: 2, left: "27%", top: "57%" },
  { id: "sacre", label: "1", name: "Sacré-Cœur", day: 3, left: "57%", top: "19%" },
  { id: "versailles", label: "1", name: "Palace of Versailles", day: 4, left: "10%", top: "69%" },
];

function DayButtons({ scope, onScope, compact = false }: { scope: Scope; onScope: (scope: Scope) => void; compact?: boolean }) {
  return (
    <div className="flex min-w-0 items-center gap-1 overflow-x-auto" aria-label="Map day scope">
      <button type="button" onClick={() => onScope("all")} className={`shrink-0 rounded-sm px-2.5 py-1.5 text-[11px] font-semibold ${scope === "all" ? "bg-ink text-white" : "bg-slate-100 text-slate-600"}`}>All days</button>
      {days.map((day) => (
        <button key={day.day} type="button" onClick={() => onScope(day.day)} aria-label={`Focus Day ${day.day}, ${day.title}`} className={`shrink-0 rounded-sm px-2 py-1.5 text-[11px] font-semibold ${scope === day.day ? "text-white" : "bg-white text-slate-600 ring-1 ring-inset ring-slate-200"}`} style={scope === day.day ? { backgroundColor: day.color } : undefined}>
          {compact ? day.day : `Day ${day.day}`}
        </button>
      ))}
    </div>
  );
}

function ScopeSummary({ scope, dense = false }: { scope: Scope; dense?: boolean }) {
  const day = typeof scope === "number" ? days[scope - 1] : null;
  if (!day) {
    return (
      <div className={`grid min-w-0 items-center gap-3 ${dense ? "grid-cols-3" : "grid-cols-[1.15fr_1fr_1fr]"}`}>
        <div className="min-w-0"><p className="text-[9px] font-bold uppercase text-slate-400">Trip scope</p><p className="truncate text-xs font-semibold text-ink">5 daily circuits · Paris</p></div>
        <Metric icon={Route} label="Route travel" value="6 hr 45 · 116 km" />
        <Metric icon={Check} label="Readiness" value="9 of 16 confirmed" />
      </div>
    );
  }
  return (
    <div className={`grid min-w-0 items-center gap-3 ${dense ? "grid-cols-3" : "grid-cols-[1.2fr_1fr_1fr]"}`}>
      <div className="min-w-0"><p className="text-[9px] font-bold uppercase" style={{ color: day.color }}>Day {day.day} · {day.date}</p><p className="truncate text-xs font-semibold text-ink">{day.title}</p></div>
      <Metric icon={Clock3} label="Full schedule" value={`${day.start}–${day.end} · ${day.schedule}`} />
      <Metric icon={Route} label="Route-only travel" value={`${day.travel} · ${day.distance} · ${day.mode}`} />
    </div>
  );
}

function Metric({ icon: Icon, label, value }: { icon: typeof Route; label: string; value: string }) {
  return <div className="min-w-0 border-l border-slate-200 pl-3"><p className="flex items-center gap-1 text-[9px] font-bold uppercase text-slate-400"><Icon size={10} /> {label}</p><p className="truncate text-[11px] font-semibold text-slate-700">{value}</p></div>;
}

function AddStopForm({ scope, onClose, onAdd }: { scope: Scope; onClose?: () => void; onAdd: (name: string) => void }) {
  const [name, setName] = useState("");
  const [kind, setKind] = useState("Attraction");
  const [target, setTarget] = useState(scope === "all" ? "Best day" : `Day ${scope}`);
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="relative min-w-[12rem] flex-1"><Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" /><input value={name} onChange={(event) => setName(event.target.value)} placeholder="Search a Paris place" className="h-8 w-full rounded-sm border-0 bg-slate-50 pl-8 pr-3 text-xs ring-1 ring-inset ring-slate-200 focus:ring-2 focus:ring-brand/30" /></div>
      <select value={kind} onChange={(event) => setKind(event.target.value)} aria-label="Stop type" className="h-8 rounded-sm border-0 bg-white px-2 text-xs text-slate-600 ring-1 ring-inset ring-slate-200"><option>Attraction</option><option>Restaurant</option><option>Hotel</option></select>
      <select value={target} onChange={(event) => setTarget(event.target.value)} aria-label="Add stop to day" className="h-8 rounded-sm border-0 bg-white px-2 text-xs text-slate-600 ring-1 ring-inset ring-slate-200"><option>Best day</option>{days.map((day) => <option key={day.day}>Day {day.day}</option>)}</select>
      <button type="button" disabled={!name.trim()} onClick={() => { onAdd(`${name} · ${kind} · ${target}`); setName(""); }} className="btn-primary h-8 disabled:opacity-40"><Plus size={13} /> Add</button>
      {onClose && <button type="button" onClick={onClose} className="grid h-8 w-8 place-items-center rounded-sm text-slate-400 hover:bg-slate-100" title="Close Add stop"><X size={14} /></button>}
    </div>
  );
}

function MapCanvas({ scope, selected, onPin }: { scope: Scope; selected: string | null; onPin: (id: string) => void }) {
  const visiblePins = pinData.filter((pin) => scope === "all" || pin.day === 0 || pin.day === scope);
  return (
    <div className="absolute inset-0 overflow-hidden bg-[#e8eee9]">
      <div className="absolute inset-0 opacity-90" style={{ backgroundImage: "linear-gradient(25deg,transparent 46%,#fff 47%,#fff 50%,transparent 51%),linear-gradient(102deg,transparent 47%,#fff 48%,#fff 51%,transparent 52%),linear-gradient(154deg,transparent 46%,#d4ded6 47%,#d4ded6 50%,transparent 51%)", backgroundSize: "180px 150px,240px 190px,120px 110px" }} />
      <div className="absolute -bottom-20 left-[46%] h-[130%] w-16 -rotate-[11deg] bg-[#b8dbe6] opacity-90" />
      <div className="absolute left-[8%] top-[12%] h-28 w-36 rounded-[45%] bg-[#c5dfc2]" />
      <div className="absolute right-[8%] top-[8%] text-[10px] font-bold uppercase tracking-widest text-slate-400">Paris</div>
      <div className="absolute left-[30%] top-[29%] text-[9px] font-semibold text-slate-400">8th arrondissement</div>
      <div className="absolute left-[50%] top-[54%] text-[9px] font-semibold text-slate-400">Latin Quarter</div>
      {scope !== "all" && <svg className="absolute inset-0 h-full w-full" viewBox="0 0 100 100" preserveAspectRatio="none"><path d="M42 61 C44 52 47 48 48 41 S39 40 35 43 S29 51 27 57 S37 64 42 61" fill="none" stroke={days[Number(scope) - 1].color} strokeWidth="0.7" strokeDasharray="2 1" /></svg>}
      {visiblePins.map((pin) => {
        const color = pin.day ? days[pin.day - 1].color : "#334155";
        const focused = selected === pin.id;
        return <button key={pin.id} type="button" onClick={() => onPin(pin.id)} title={pin.name} className={`absolute z-10 grid h-8 w-7 -translate-x-1/2 -translate-y-full place-items-center rounded-t-full rounded-br-full border-2 border-white text-[10px] font-bold text-white shadow-md transition ${focused ? "scale-125 ring-2 ring-ink ring-offset-1" : "hover:scale-110"}`} style={{ left: pin.left, top: pin.top, backgroundColor: color }}>{pin.label}</button>;
      })}
      <div className="absolute bottom-3 left-3 rounded-sm bg-white/90 px-2 py-1 text-[9px] font-medium text-slate-500 shadow-card">Visual route mock · interaction semantics match production</div>
    </div>
  );
}

interface ControlsProps { scope: Scope; onScope: (scope: Scope) => void; addOpen: boolean; setAddOpen: (open: boolean) => void; onAdd: (name: string) => void; }

function RibbonControls({ scope, onScope, addOpen, setAddOpen, onAdd }: ControlsProps) {
  return <div className="absolute inset-x-0 top-0 z-30 border-b border-slate-200 bg-white/95 shadow-card backdrop-blur"><div className="flex h-11 items-center gap-2 px-3"><DayButtons scope={scope} onScope={onScope} /><span className="ml-auto h-5 border-l border-slate-200" /><button type="button" onClick={() => setAddOpen(!addOpen)} className={`btn-ghost h-8 shrink-0 ${addOpen ? "bg-brand-50 text-brand" : ""}`}><Plus size={14} /> Add stop</button></div><div className="border-t border-slate-100 px-3 py-2"><ScopeSummary scope={scope} />{addOpen && <div className="mt-2 border-t border-slate-100 pt-2"><AddStopForm scope={scope} onClose={() => setAddOpen(false)} onAdd={onAdd} /></div>}</div></div>;
}

function DeckControls({ scope, onScope, addOpen, setAddOpen, onAdd }: ControlsProps) {
  const [summaryOpen, setSummaryOpen] = useState(true);
  return <><div className="absolute left-3 right-3 top-3 z-30 flex min-h-11 flex-wrap items-center gap-2 rounded-md bg-white/95 p-1.5 shadow-pop ring-1 ring-slate-200 backdrop-blur"><div className="flex items-center gap-1 px-1 text-xs font-semibold text-ink"><Map size={14} className="text-accent" /> Paris map</div><span className="h-5 border-l border-slate-200" /><DayButtons scope={scope} onScope={onScope} compact /><div className="ml-auto flex items-center gap-1"><button type="button" onClick={() => setSummaryOpen(!summaryOpen)} className={`grid h-8 w-8 place-items-center rounded-sm ${summaryOpen ? "bg-slate-100 text-ink" : "text-slate-500"}`} title="Route summary"><ListFilter size={14} /></button><button type="button" onClick={() => setAddOpen(!addOpen)} className="btn-primary h-8"><Plus size={14} /> Add stop</button></div></div>{summaryOpen && <div className="absolute left-3 top-[4.25rem] z-20 w-[min(34rem,calc(100%-1.5rem))] rounded-md bg-white/95 p-3 shadow-pop ring-1 ring-slate-200 backdrop-blur"><ScopeSummary scope={scope} dense /></div>}{addOpen && <div className="absolute left-3 right-3 top-[4.25rem] z-40 rounded-md bg-white p-3 shadow-pop ring-1 ring-brand/20"><div className="mb-2 flex items-center justify-between"><p className="text-xs font-semibold text-ink">Add a stop without leaving the map</p><button onClick={() => setAddOpen(false)} title="Close"><X size={14} /></button></div><AddStopForm scope={scope} onAdd={onAdd} /></div>}</>;
}

function ScheduleControls({ scope, onScope, addOpen, setAddOpen, onAdd }: ControlsProps) {
  return <><div className="absolute right-3 top-3 z-30 flex items-center gap-1 rounded-md bg-white/95 p-1.5 shadow-pop ring-1 ring-slate-200"><button type="button" className="grid h-8 w-8 place-items-center rounded-sm text-slate-600" title="Search map"><Search size={15} /></button><button type="button" onClick={() => setAddOpen(!addOpen)} className="btn-primary h-8"><Plus size={14} /> Add stop</button></div>{addOpen && <div className="absolute left-3 right-3 top-14 z-40 rounded-md bg-white p-3 shadow-pop ring-1 ring-brand/20"><AddStopForm scope={scope} onClose={() => setAddOpen(false)} onAdd={onAdd} /></div>}<div className="absolute inset-x-3 bottom-3 z-30 overflow-hidden rounded-md bg-white/95 shadow-pop ring-1 ring-slate-200 backdrop-blur"><div className="flex overflow-x-auto border-b border-slate-100"><button onClick={() => onScope("all")} className={`min-w-24 border-r border-slate-100 px-3 py-2 text-left ${scope === "all" ? "bg-ink text-white" : ""}`}><span className="block text-[9px] font-bold uppercase opacity-60">Trip</span><strong className="text-xs">All 5 days</strong></button>{days.map((day) => <button key={day.day} onClick={() => onScope(day.day)} className={`min-w-28 border-r border-slate-100 px-3 py-2 text-left ${scope === day.day ? "text-white" : "text-slate-600"}`} style={scope === day.day ? { backgroundColor: day.color } : undefined}><span className="block text-[9px] font-bold uppercase opacity-70">{day.short} · {day.date}</span><strong className="text-xs">Day {day.day}</strong></button>)}</div><div className="px-3 py-2"><ScopeSummary scope={scope} /></div></div></>;
}

function MapWorkspace({ variant }: { variant: Variant }) {
  const [scope, setScope] = useState<Scope>(2);
  const [addOpen, setAddOpen] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const selectScope = (next: Scope) => { setScope(next); setSelected(null); };
  const selectedPin = pinData.find((pin) => pin.id === selected);
  const controls = { scope, onScope: selectScope, addOpen, setAddOpen, onAdd: (name: string) => { setNotice(`${name} ready for itinerary review`); setAddOpen(false); } };
  return (
    <div className="grid h-full min-h-0 grid-cols-1 bg-white lg:grid-cols-[17rem_minmax(0,1fr)_19rem]">
      <aside className="hidden min-h-0 overflow-y-auto border-r border-slate-200 bg-white lg:block"><div className="border-b border-slate-100 p-3"><p className="text-[9px] font-bold uppercase text-brand">Paris · 26–30 Aug</p><h2 className="mt-1 text-sm font-semibold text-ink">Five-day family itinerary</h2></div>{days.map((day) => <button key={day.day} onClick={() => selectScope(day.day)} className={`w-full border-b border-slate-100 p-3 text-left ${scope === day.day ? "bg-slate-50" : "hover:bg-slate-50/50"}`}><div className="flex items-center gap-2"><span className="grid h-6 w-6 place-items-center rounded-full text-[10px] font-bold text-white" style={{ backgroundColor: day.color }}>{day.day}</span><div className="min-w-0"><p className="text-[9px] font-bold uppercase text-slate-400">{day.short} · {day.date}</p><p className="truncate text-xs font-semibold text-ink">{day.title}</p></div></div><p className="mt-2 text-[10px] text-slate-500">{day.start}–{day.end} · {day.stops} stops · {day.confirmed} confirmed</p></button>)}</aside>
      <section className="relative min-h-[38rem] min-w-0 overflow-hidden lg:min-h-0"><MapCanvas scope={scope} selected={selected} onPin={setSelected} />{variant === "ribbon" ? <RibbonControls {...controls} /> : variant === "deck" ? <DeckControls {...controls} /> : <ScheduleControls {...controls} />}{notice && <div className="absolute bottom-4 left-1/2 z-50 flex -translate-x-1/2 items-center gap-2 rounded-md bg-ink px-3 py-2 text-xs text-white shadow-pop"><Check size={13} /> {notice}<button onClick={() => setNotice("")}><X size={12} /></button></div>}</section>
      <aside className="hidden min-h-0 overflow-y-auto border-l border-slate-200 bg-white lg:block"><div className="border-b border-slate-100 p-3"><p className="text-[9px] font-bold uppercase text-slate-400">Details</p><h2 className="mt-1 text-sm font-semibold text-ink">{selectedPin?.name || "Day 2 circuit"}</h2></div>{selectedPin ? <div className="p-3"><div className="grid h-32 place-items-center rounded-md bg-[linear-gradient(135deg,#dcefe9,#fef3c7)]"><MapPin size={28} className="text-brand" /></div><p className="mt-3 text-xs leading-relaxed text-slate-600">Focused occurrence on Day {selectedPin.day || 2}. Map focus is exclusive from aggregate day focus.</p><button className="btn-primary mt-3 w-full"><Navigation size={13} /> Open route</button></div> : <div className="p-3"><p className="text-xs leading-relaxed text-slate-600">A complete hotel-to-hotel circuit along the Seine, balancing reserved icons with flexible outdoor time.</p><div className="mt-4 space-y-3"><Detail icon={Hotel} title="Hôtel Le Six" note="Depart 08:45 · Return 20:10 est." /><Detail icon={Compass} title="4 planned stops" note="Louvre → Tuileries → Orangerie → Eiffel" /><Detail icon={Utensils} title="Dinner near the hotel" note="Needs booking · 20:15 target" /></div></div>}</aside>
    </div>
  );
}

function Detail({ icon: Icon, title, note }: { icon: typeof Hotel; title: string; note: string }) { return <div className="flex gap-2"><span className="grid h-7 w-7 shrink-0 place-items-center rounded-sm bg-slate-100 text-slate-500"><Icon size={13} /></span><div><p className="text-xs font-semibold text-ink">{title}</p><p className="text-[10px] text-slate-500">{note}</p></div></div>; }

function VariantDiagram({ variant }: { variant: Variant }) {
  return <div className="relative h-20 overflow-hidden rounded-sm bg-[#e6eee9] ring-1 ring-slate-200"><div className="absolute inset-0 opacity-40" style={{ backgroundImage: "linear-gradient(30deg,transparent 47%,white 48%,white 51%,transparent 52%)", backgroundSize: "55px 45px" }} />{variant === "ribbon" && <><div className="absolute inset-x-0 top-0 h-4 bg-white" /><div className="absolute inset-x-0 top-4 h-5 border-t border-slate-100 bg-white/90" /></>}{variant === "deck" && <><div className="absolute left-2 right-2 top-2 h-5 rounded-sm bg-white shadow" /><div className="absolute left-2 top-9 h-7 w-1/2 rounded-sm bg-white shadow" /></>}{variant === "schedule" && <><div className="absolute right-2 top-2 h-5 w-16 rounded-sm bg-white shadow" /><div className="absolute inset-x-2 bottom-2 h-8 rounded-sm bg-white shadow" /></>}<MapPin size={14} className="absolute left-1/2 top-1/2 text-brand" /></div>;
}

function MapControlsLab() {
  const params = new URLSearchParams(window.location.search);
  const preview = params.get("preview");
  const fullPreview = variants.some((item) => item.id === preview);
  const [variant, setVariant] = useState<Variant>(fullPreview ? preview as Variant : "ribbon");
  const choose = useCallback((value: string) => setVariant(value as Variant), []);
  if (fullPreview) return <main className="relative h-[100dvh] min-h-[40rem] overflow-hidden bg-white"><MapWorkspace variant={variant} /><a href="./map-controls.html" className="fixed bottom-4 left-4 z-[80] inline-flex items-center gap-2 rounded-md bg-ink px-3 py-2 text-xs font-semibold text-white shadow-pop ring-1 ring-white/30"><ArrowLeft size={14} /> Exit full-size preview</a></main>;
  return (
    <main className="min-h-full bg-[linear-gradient(180deg,#f8fafc_0,#ecfdf5_32rem,#f8fafc_100%)] px-4 py-7 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-[92rem]">
        <header className="flex flex-wrap items-end justify-between gap-5 border-b border-slate-200 pb-5"><div><div className="flex items-center gap-2 text-accent"><Map size={17} /><p className="text-[10px] font-bold uppercase">Active UX Lab</p></div><h1 className="display mt-2 text-3xl font-semibold text-ink">Map commands and day context</h1><p className="mt-2 max-w-4xl text-sm leading-relaxed text-slate-600">Compare three complete control systems for the Map’s most frequent work: switch between all circuits and one day, understand full schedule versus route-only travel, add a stop to an explicit day, and inspect an exact place without losing context.</p></div><LabNavigation detail /></header>
        <LabScope labId="map-controls" />
        <div className="mt-5 grid gap-3 md:grid-cols-3" role="tablist" aria-label="Map control variants">{variants.map((item) => <button key={item.id} role="tab" aria-selected={variant === item.id} onClick={() => setVariant(item.id)} className={`rounded-md bg-white p-3 text-left shadow-card ring-1 transition ${variant === item.id ? "ring-2 ring-accent" : "ring-slate-200 hover:ring-slate-300"}`}><VariantDiagram variant={item.id} /><strong className="mt-3 block text-sm text-ink">{item.label}</strong><span className="mt-1 block text-xs leading-relaxed text-slate-600">{item.note}</span><span className="mt-3 block border-t border-slate-100 pt-2 text-[10px] font-semibold text-accent">{item.strength}</span></button>)}</div>
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3"><div><p className="text-xs font-semibold text-ink">Live production-scale preview</p><p className="mt-0.5 text-[11px] text-slate-500">Try day scope, exact pins, Add stop, summary expansion, and narrow widths.</p></div><a href={`?preview=${variant}`} className="btn-primary"><Maximize2 size={14} /> Open full-size preview</a></div>
        <section className="mt-2 h-[720px] max-h-[78vh] min-h-[620px] overflow-hidden rounded-md bg-white shadow-pop ring-1 ring-slate-200" aria-label="Interactive Map controls preview"><MapWorkspace key={variant} variant={variant} /></section>
        <section className="mt-6 grid gap-3 md:grid-cols-3"><article className="rounded-md bg-white p-4 ring-1 ring-slate-200"><PanelTop size={16} className="text-brand" /><h2 className="mt-2 text-sm font-semibold">Command hierarchy</h2><p className="mt-1 text-xs leading-relaxed text-slate-500">Can you find All days, a specific day, and Add stop without three equal-weight toolbar rows?</p></article><article className="rounded-md bg-white p-4 ring-1 ring-slate-200"><Clock3 size={16} className="text-accent" /><h2 className="mt-2 text-sm font-semibold">Truthful time evidence</h2><p className="mt-1 text-xs leading-relaxed text-slate-500">Full schedule and route-only travel remain separately labeled, with start/end estimates visible.</p></article><article className="rounded-md bg-white p-4 ring-1 ring-slate-200"><CalendarDays size={16} className="text-amber-700" /><h2 className="mt-2 text-sm font-semibold">State continuity</h2><p className="mt-1 text-xs leading-relaxed text-slate-500">Day scope seeds Add stop placement; exact-pin focus remains distinct from aggregate circuit focus.</p></article></section>
        <div className="mt-6"><DecisionCapture labId="map-controls" labTitle="Map commands and day context" options={variants} activeOption={variant} onChoose={choose} /></div>
      </div>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><MapControlsLab /></React.StrictMode>);