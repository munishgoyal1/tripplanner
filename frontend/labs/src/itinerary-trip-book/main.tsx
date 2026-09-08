import React, { useCallback, useEffect, useState } from "react";
import ReactDOM from "react-dom/client";
import {
  BookOpen,
  Check,
  ChevronRight,
  CircleAlert,
  Clock3,
  CloudSun,
  Compass,
  FileCheck2,
  FileText,
  Heart,
  LifeBuoy,
  Map,
  MapPin,
  Plane,
  QrCode,
  ShieldCheck,
  Sparkles,
  Wallet,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import "../../../src/index.css";
import { DecisionCapture } from "../shared/DecisionCapture";
import { LabNavigation } from "../shared/LabNavigation";
import { LabScope } from "../shared/LabScope";
import { OptionContrast } from "../shared/OptionContrast";
import { DayCircuitMap, TripOverviewMap, dayColor, tripAreas } from "./TripBookMap";

type Variant = "binder" | "layered" | "visual";
type MapMode = "off" | "day" | "book";
type Section = "contents" | "overview" | "day" | "maps" | "essentials" | "documents" | "guide";

const variants: Array<{ id: Variant; label: string; note: string; pages: number }> = [
  { id: "layered", label: "B · Layered Trip Book", note: "Recommended: quick trip control, executable day spreads, then evidence and documents.", pages: 18 },
  { id: "binder", label: "A · Operations binder", note: "Dense, checklist-led, and optimized for the shortest printable packet.", pages: 14 },
  { id: "visual", label: "C · Visual journey book", note: "More photography and destination context while retaining the complete operational appendix.", pages: 24 },
];

const mapModes: Array<{ id: MapMode; label: string; note: string; pages: number }> = [
  { id: "off", label: "No map", note: "Text-only packet. Sequence exists, but never as a picture.", pages: 0 },
  { id: "day", label: "Day circuit inset", note: "Every day spread carries its own numbered hotel-to-hotel circuit.", pages: 0 },
  { id: "book", label: "Circuit inset + map pages", note: "Adds a trip overview map and one full-page labelled day circuit.", pages: 2 },
];

const sections: Array<{ id: Section; label: string; range: string; icon: LucideIcon; mapOnly?: boolean }> = [
  { id: "contents", label: "Contents", range: "1", icon: BookOpen },
  { id: "overview", label: "Trip brief", range: "2–3", icon: Plane },
  { id: "maps", label: "Trip and day maps", range: "4–5", icon: Compass, mapOnly: true },
  { id: "day", label: "Day 3 · London", range: "6–7", icon: Map },
  { id: "essentials", label: "Essentials and help", range: "10–11", icon: LifeBuoy },
  { id: "documents", label: "Travel documents", range: "12–15", icon: FileCheck2 },
  { id: "guide", label: "Place guide", range: "16–18", icon: Sparkles },
];

const documents = [
  { name: "British Airways · DEL–LHR", detail: "E-ticket · BA142 · 24 Aug", status: "Included", icon: Plane },
  { name: "Wilde Aparthotels Aldgate", detail: "Stay voucher · 24–31 Aug", status: "Included", icon: FileText },
  { name: "Travel insurance", detail: "Family policy · all travelers", status: "Included", icon: ShieldCheck },
  { name: "UK ETA · Munish", detail: "Application reference required", status: "Action needed", icon: CircleAlert },
];

const stops = [
  { time: "09:10", end: "11:30", name: "Tower of London", where: "St Katharine's & Wapping EC3N 4AB", travel: "Taxi · 18 min", state: "Confirmed", ref: "HRP-8842014" },
  { time: "12:05", end: "13:20", name: "Dishoom Shoreditch", where: "7 Boundary St E2 7JE · +44 20 7420 9324", travel: "Walk · 14 min", state: "Booked", ref: "DSH-26AUG-4" },
  { time: "14:00", end: "16:15", name: "Young V&A", where: "Cambridge Heath Rd E2 9PA", travel: "Metro · 26 min", state: "Free entry", ref: "No ticket needed" },
  { time: "17:10", end: "18:30", name: "Sky Garden", where: "1 Sky Garden Walk EC3M 8AF", travel: "Metro · 31 min", state: "Confirmed", ref: "SKY-7731902" },
];

const help = [
  { label: "Emergency (UK)", value: "999 · 112", tone: "urgent" },
  { label: "Insurance 24h", value: "+91 124 415 0000 · policy TG-4471", tone: "urgent" },
  { label: "Hotel front desk", value: "Wilde Aldgate · +44 20 3319 7460", tone: "calm" },
  { label: "Indian High Commission", value: "India House, Aldwych · +44 20 7836 8484", tone: "calm" },
  { label: "Card block · HDFC / Amex", value: "+91 22 6160 6161 · +1 336 393 1111", tone: "calm" },
];

const practical = [
  { label: "Money", value: "GBP · contactless everywhere · tipping 10–12.5% only if not already added" },
  { label: "Transport", value: "Tap the same card in and out · daily cap £8.90 zones 1–2 · no paper tickets" },
  { label: "Power and data", value: "Type G, 230 V · eSIM active on both phones from landing" },
  { label: "Rhythm", value: "IST −4:30 · sunset 20:05 · museums close 17:45" },
];

function visibleSections(mapMode: MapMode) {
  return sections.filter((section) => !section.mapOnly || mapMode === "book");
}


function PageFrame({ variant, page, title, children }: { variant: Variant; page: number; title: string; children: React.ReactNode }) {
  const visual = variant === "visual";
  const binder = variant === "binder";
  return (
    <article className={`relative mx-auto aspect-[210/270] w-full max-w-[720px] overflow-hidden bg-white text-slate-800 shadow-[0_22px_65px_rgba(15,23,42,0.22)] ring-1 ring-slate-200 ${visual ? "font-serif" : ""}`}>
      <div className={`absolute inset-x-0 top-0 h-1.5 ${binder ? "bg-slate-800" : visual ? "bg-amber-600" : "bg-brand"}`} />
      <div className="flex h-full flex-col px-[6%] pb-[4%] pt-[5%]">
        <div className="flex items-center justify-between border-b border-slate-200 pb-2 text-[clamp(8px,1vw,11px)]">
          <span className="font-semibold uppercase text-slate-500">London · 24–31 August 2026</span>
          <span className="text-slate-400">Goyal family trip</span>
        </div>
        <div className="min-h-0 flex-1">{children}</div>
        <footer className="flex items-center justify-between border-t border-slate-200 pt-2 text-[clamp(7px,.9vw,10px)] text-slate-400">
          <span>{title}</span>
          <span className="hidden sm:inline">Generated 3 Sep 2026 · plan revision 14 · matches the live workspace</span>
          <span>{page}</span>
        </footer>
      </div>
    </article>
  );
}

function ContentsPage({ variant, mapMode }: { variant: Variant; mapMode: MapMode }) {
  const config = variants.find((item) => item.id === variant)!;
  const visual = variant === "visual";
  const listed = visibleSections(mapMode).slice(1);
  return (
    <PageFrame variant={variant} page={1} title="Contents">
      <div className={`mt-[4%] grid h-[88%] gap-[4%] ${visual ? "grid-rows-[38%_1fr]" : "grid-cols-[1.05fr_.95fr]"}`}>
        <div className={`relative overflow-hidden ${visual ? "" : "border-r border-slate-200 pr-[8%]"}`}>
          {visual && <img src="https://images.unsplash.com/photo-1513635269975-59663e0ac1ad?auto=format&fit=crop&w=1200&q=82" alt="London skyline and Tower Bridge" className="absolute inset-0 h-full w-full object-cover" />}
          <div className={visual ? "absolute inset-0 flex flex-col justify-end bg-gradient-to-t from-black/75 via-black/10 to-transparent p-[5%] text-white" : ""}>
            <p className={`text-[clamp(8px,1vw,11px)] font-bold uppercase ${visual ? "text-amber-200" : "text-brand"}`}>Your complete travel book</p>
            <h2 className="display mt-2 text-[clamp(26px,4vw,48px)] font-semibold leading-none">London,<br />ready to go.</h2>
            <p className={`mt-3 max-w-sm text-[clamp(9px,1.2vw,13px)] leading-relaxed ${visual ? "text-white/80" : "text-slate-500"}`}>Eight days, four travelers, one carry-along plan with every confirmation attached.</p>
          </div>
        </div>
        <div className={visual ? "grid grid-cols-[1fr_auto] gap-x-6 px-[2%]" : "pl-[4%]"}>
          <p className="mb-2 text-[clamp(8px,1vw,11px)] font-bold uppercase text-slate-400">Contents · {config.pages + mapModes.find((item) => item.id === mapMode)!.pages} pages</p>
          {listed.map((section, index) => (
            <div key={section.id} className={`flex items-center gap-3 border-b border-slate-100 py-[2.4%] ${visual ? (index % 2 ? "col-start-2" : "col-start-1") : ""}`}>
              <span className="grid h-6 w-6 place-items-center rounded-full bg-slate-100 text-[10px] font-bold">{index + 1}</span>
              <span className="min-w-0 flex-1 text-[clamp(9px,1.2vw,13px)] font-semibold">{section.label}</span>
              <span className="text-[clamp(8px,1vw,11px)] text-slate-400">{section.range}</span>
            </div>
          ))}
          <div className={`mt-[5%] border-l-2 px-3 py-2 ${variant === "binder" ? "border-slate-700 bg-slate-50" : "border-emerald-500 bg-emerald-50"}`}>
            <div className="flex items-center gap-2 text-[clamp(9px,1.1vw,12px)] font-semibold text-emerald-800"><Check size={13} /> 3 of 4 document groups ready</div>
            <p className="mt-1 text-[clamp(7px,.9vw,10px)] text-slate-500">UK ETA reference still needs to be attached.</p>
          </div>
        </div>
      </div>
    </PageFrame>
  );
}

function OverviewPage({ variant }: { variant: Variant }) {
  const visual = variant === "visual";
  return (
    <PageFrame variant={variant} page={2} title="Trip brief">
      <div className="mt-[4%]">
        <p className="text-[clamp(8px,1vw,11px)] font-bold uppercase text-brand">At a glance</p>
        <h2 className="display mt-1 text-[clamp(24px,3.3vw,42px)] font-semibold leading-tight">Everything needed before departure</h2>
        <div className={`mt-[4%] grid gap-3 ${variant === "binder" ? "grid-cols-4" : "grid-cols-2"}`}>
          {[['Depart','24 Aug · 02:45'],['Return','31 Aug · 20:15'],['Stay','Wilde Aldgate'],['Budget','₹5.8L planned']].map(([label, value]) => <div key={label} className="border-t border-slate-300 pt-2"><p className="text-[clamp(7px,.9vw,10px)] font-bold uppercase text-slate-400">{label}</p><p className="mt-1 text-[clamp(9px,1.15vw,13px)] font-semibold">{value}</p></div>)}
        </div>
        <div className={`mt-[5%] grid gap-[4%] ${visual ? "grid-cols-[1fr_1.15fr]" : "grid-cols-[1.25fr_.75fr]"}`}>
          <div>
            <h3 className="text-[clamp(10px,1.4vw,15px)] font-semibold">Before you leave</h3>
            {["Download this book to every phone", "Add UK ETA reference", "Check in online · opens 23 Aug 02:45", "Carry prescriptions in cabin baggage"].map((item, index) => <div key={item} className="flex items-start gap-2 border-b border-slate-100 py-[3%] text-[clamp(8px,1.05vw,12px)]"><span className={`mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full ${index === 1 ? "bg-amber-100 text-amber-700" : "bg-emerald-100 text-emerald-700"}`}>{index === 1 ? "!" : "✓"}</span>{item}</div>)}
          </div>
          <div className={`${visual ? "bg-amber-50" : "bg-teal-50"} p-[7%]`}>
            <div className="flex items-center gap-2 text-[clamp(8px,1vw,11px)] font-bold uppercase text-teal-800"><Heart size={13} /> For your family</div>
            <p className="mt-3 text-[clamp(10px,1.35vw,15px)] font-semibold leading-snug">Keep the first morning unhurried after the overnight flight.</p>
            <p className="mt-2 text-[clamp(8px,1vw,11px)] leading-relaxed text-slate-600">The plan starts nearby at 11:30 and keeps a 90-minute hotel reset before dinner.</p>
            <p className="mt-3 text-[clamp(7px,.85vw,9px)] font-semibold uppercase text-teal-700">Saved pace preference + flight arrival</p>
          </div>
        </div>
      </div>
    </PageFrame>
  );
}

function EndpointRow({ time, label, note }: { time: string; label: string; note: string }) {
  return (
    <div className="grid grid-cols-[3.3rem_1fr_auto] items-center gap-2 border-b border-slate-100 py-[2%] text-[clamp(8px,1.05vw,12px)]">
      <strong>{time}</strong>
      <span className="flex items-center gap-1.5 font-semibold">
        <span className="grid h-3.5 w-3.5 place-items-center rounded-full bg-slate-700 text-[7px] font-bold text-white">H</span>
        {label}
      </span>
      <span className="text-[clamp(6px,.8vw,9px)] text-slate-400">{note}</span>
    </div>
  );
}

function DayPage({ variant, mapMode }: { variant: Variant; mapMode: MapMode }) {
  const mono = variant === "binder";
  return (
    <PageFrame variant={variant} page={6} title="Day 3 · Tower, Shoreditch and skyline">
      <div className="mt-[3%]">
        <div className="flex items-end justify-between gap-4">
          <div><p className="text-[clamp(8px,1vw,11px)] font-bold uppercase text-brand">Tuesday · 26 August</p><h2 className="display mt-1 text-[clamp(22px,3vw,38px)] font-semibold">London through time</h2></div>
          <div className="text-right text-[clamp(7px,.95vw,10px)] text-slate-500"><strong className="block text-[clamp(9px,1.1vw,12px)] text-slate-700">09:10–18:30</strong>Travel 1 hr 29 · 16.8 km</div>
        </div>
        <div className={`mt-[3%] grid gap-[5%] ${variant === "binder" ? "grid-cols-[1fr_.72fr]" : "grid-cols-[1.15fr_.85fr]"}`}>
          <div>
            <EndpointRow time="07:40" label="Leave Wilde Aldgate" note="Breakfast from 07:00" />
            {stops.map((stop, index) => (
              <div key={stop.name} className="relative grid grid-cols-[3.3rem_1fr_auto] gap-2 border-b border-slate-100 py-[2.6%] text-[clamp(8px,1.05vw,12px)]">
                <div><strong>{stop.time}</strong><span className="block text-[clamp(7px,.85vw,9px)] text-slate-400">to {stop.end}</span></div>
                <div>
                  <p className="font-semibold"><span className="mr-1 text-brand">{index + 1}</span>{stop.name}</p>
                  <p className="mt-0.5 text-[clamp(6px,.82vw,9px)] text-slate-400">{stop.where}</p>
                  <p className="mt-0.5 text-[clamp(7px,.9vw,10px)] text-teal-700">{stop.travel}</p>
                </div>
                <div className="text-right">
                  <span className="inline-block bg-emerald-50 px-1.5 py-1 text-[clamp(6px,.8vw,9px)] font-semibold text-emerald-700">{stop.state}</span>
                  <span className="mt-1 block text-[clamp(6px,.75vw,8px)] tabular-nums text-slate-400">{stop.ref}</span>
                </div>
              </div>
            ))}
            <EndpointRow time="19:20" label="Back at Wilde Aldgate" note="Family dinner 20:15, walk" />
            <div className="mt-[3%] flex items-center gap-3 text-[clamp(6px,.85vw,9px)] text-slate-500">
              <span className="flex items-center gap-1"><CloudSun size={11} className="text-amber-600" /> 17–23 °C · light rain after 16:00</span>
              <span className="flex items-center gap-1"><Wallet size={11} className="text-slate-500" /> Prepaid £164 · expect £45 on the day</span>
            </div>
          </div>
          <div className="space-y-[4%]">
            {mapMode === "off" ? (
              <div className="relative aspect-[4/3] overflow-hidden bg-slate-100">
                <img src="https://images.unsplash.com/photo-1529655683826-aba9b3e77383?auto=format&fit=crop&w=800&q=80" alt="Tower Bridge in London" className={`h-full w-full object-cover ${mono ? "grayscale" : ""}`} />
                <span className="absolute bottom-2 left-2 bg-white/90 px-2 py-1 text-[clamp(7px,.85vw,9px)] font-semibold">Sequence is written, not drawn</span>
              </div>
            ) : (
              <figure className="border border-slate-200">
                <DayCircuitMap mono={mono} className="block aspect-[4/3] w-full" />
                <figcaption className="flex items-center justify-between gap-2 border-t border-slate-200 px-2 py-1.5 text-[clamp(6px,.8vw,9px)] text-slate-500">
                  <span><strong className="text-slate-700">H</strong> hotel · <strong className="text-slate-700">1–4</strong> in the order above</span>
                  <span className="flex items-center gap-1"><QrCode size={11} /> Open day in Maps</span>
                </figcaption>
              </figure>
            )}
            <div className="border-l-2 border-amber-500 bg-amber-50 p-[5%]">
              <div className="flex items-center gap-1.5 text-[clamp(7px,.9vw,10px)] font-bold uppercase text-amber-800"><Sparkles size={12} /> Worth knowing</div>
              <p className="mt-1.5 text-[clamp(8px,1.05vw,12px)] font-semibold">Young V&A’s Imagine Gallery has the hands-on design activities Aarav usually enjoys.</p>
              <p className="mt-1.5 text-[clamp(7px,.82vw,9px)] uppercase text-amber-700">Saved interest + official venue programme</p>
            </div>
          </div>
        </div>
      </div>
    </PageFrame>
  );
}

function MapsPage({ variant }: { variant: Variant }) {
  const mono = variant === "binder";
  return (
    <PageFrame variant={variant} page={4} title="Trip and day maps">
      <div className="mt-[4%]">
        <p className="text-[clamp(8px,1vw,11px)] font-bold uppercase text-brand">Where the trip happens</p>
        <div className="mt-1 flex items-end justify-between gap-4">
          <h2 className="display text-[clamp(22px,3vw,38px)] font-semibold leading-tight">One base, eight day circuits</h2>
          <span className="text-[clamp(7px,.9vw,10px)] text-slate-500">Same order, numbers and hotel endpoints as the day pages</span>
        </div>
        <div className="mt-[3%] grid grid-cols-2 gap-[4%]">
          <figure className="border border-slate-200">
            <TripOverviewMap mono={mono} className="block aspect-[4/3] w-full" />
            <figcaption className="border-t border-slate-200 px-2 py-1.5 text-[clamp(6px,.8vw,9px)] text-slate-500">Trip overview · every day, one marker</figcaption>
          </figure>
          <figure className="border border-slate-200">
            <DayCircuitMap mono={mono} labels caption="Day 3 · 16.8 km · 1 hr 29" className="block aspect-[4/3] w-full" />
            <figcaption className="flex items-center justify-between gap-2 border-t border-slate-200 px-2 py-1.5 text-[clamp(6px,.8vw,9px)] text-slate-500">
              <span>Day 3 circuit, named</span>
              <span className="flex items-center gap-1"><QrCode size={11} /> Scan for the live route</span>
            </figcaption>
          </figure>
        </div>
        <div className="mt-[4%] grid grid-cols-4 gap-x-3">
          {tripAreas.map((area) => (
            <div key={area.day} className="flex items-center gap-1.5 border-b border-slate-100 py-[2.5%] text-[clamp(6px,.85vw,9px)]">
              <span className="grid h-4 w-4 shrink-0 place-items-center rounded-full text-[7px] font-bold text-white" style={{ backgroundColor: mono ? "#334155" : dayColor(area.day) }}>{area.day}</span>
              <span className="min-w-0 flex-1 truncate font-medium text-slate-600">{area.label}</span>
            </div>
          ))}
        </div>
        <div className="mt-[4%] grid grid-cols-3 gap-[3%] border-t border-slate-200 pt-2 text-[clamp(7px,.9vw,10px)] leading-relaxed text-slate-500">
          <p><strong className="text-slate-700">Numbers are the agenda.</strong> 1 to n is the order you walk it, never a ranking.</p>
          <p><strong className="text-slate-700">H is your bed.</strong> Every ordinary day opens and closes at the same hotel marker.</p>
          <p><strong className="text-slate-700">Distance is straight-line.</strong> Treat it as the shape of the day, not a driving estimate.</p>
        </div>
      </div>
    </PageFrame>
  );
}

function EssentialsPage({ variant }: { variant: Variant }) {
  return (
    <PageFrame variant={variant} page={10} title="Essentials and help">
      <div className="mt-[4%]">
        <p className="text-[clamp(8px,1vw,11px)] font-bold uppercase text-brand">If plans slip</p>
        <h2 className="display mt-1 text-[clamp(22px,3.1vw,40px)] font-semibold leading-tight">Everything you would otherwise search for</h2>
        <div className="mt-[4%] grid gap-[5%] grid-cols-[1.05fr_.95fr]">
          <div>
            <h3 className="flex items-center gap-1.5 text-[clamp(9px,1.2vw,13px)] font-semibold"><LifeBuoy size={13} className="text-rose-600" /> Reach someone</h3>
            {help.map((item) => (
              <div key={item.label} className="border-b border-slate-100 py-[3%]">
                <p className={`text-[clamp(7px,.9vw,10px)] font-bold uppercase ${item.tone === "urgent" ? "text-rose-700" : "text-slate-400"}`}>{item.label}</p>
                <p className="mt-0.5 text-[clamp(8px,1.05vw,12px)] font-semibold tabular-nums">{item.value}</p>
              </div>
            ))}
          </div>
          <div>
            <h3 className="flex items-center gap-1.5 text-[clamp(9px,1.2vw,13px)] font-semibold"><Compass size={13} className="text-teal-700" /> How things work here</h3>
            {practical.map((item) => (
              <div key={item.label} className="border-b border-slate-100 py-[3%]">
                <p className="text-[clamp(7px,.9vw,10px)] font-bold uppercase text-slate-400">{item.label}</p>
                <p className="mt-0.5 text-[clamp(8px,1vw,11px)] leading-relaxed text-slate-600">{item.value}</p>
              </div>
            ))}
            <div className="mt-[6%] bg-slate-50 p-[6%]">
              <p className="text-[clamp(7px,.9vw,10px)] font-bold uppercase text-slate-500">Travelling party</p>
              <p className="mt-1 text-[clamp(8px,1.05vw,12px)] font-semibold">Munish · Ritu · Aarav (11) · Sana (7)</p>
              <p className="mt-1 text-[clamp(7px,.85vw,9px)] text-slate-500">Passports valid past 28 Feb 2027. Numbers stay out of the printed book by design.</p>
            </div>
          </div>
        </div>
        <div className="mt-[4%] border-t border-slate-200 pt-2 text-[clamp(7px,.9vw,10px)] text-slate-500">
          Getting home: check out 11:00 on 31 Aug · bags at the hotel until 15:00 · Heathrow T5 by 17:15 for BA143.
        </div>
      </div>
    </PageFrame>
  );
}

function DocumentsPage({ variant }: { variant: Variant }) {
  return (
    <PageFrame variant={variant} page={12} title="Travel documents">
      <div className="mt-[4%]">
        <p className="text-[clamp(8px,1vw,11px)] font-bold uppercase text-brand">Document wallet</p>
        <div className="mt-1 flex items-end justify-between"><h2 className="display text-[clamp(24px,3.3vw,42px)] font-semibold">Confirmations and entry</h2><span className="text-[clamp(8px,1vw,11px)] font-semibold text-amber-700">1 action needed</span></div>
        <div className={`mt-[4%] grid gap-[4%] ${variant === "visual" ? "grid-cols-[.9fr_1.1fr]" : "grid-cols-[1.1fr_.9fr]"}`}>
          <div>
            {documents.map((document) => {
              const Icon = document.icon;
              const pending = document.status === "Action needed";
              return <div key={document.name} className="flex items-center gap-3 border-b border-slate-100 py-[4%]"><span className={`grid h-8 w-8 shrink-0 place-items-center ${pending ? "bg-amber-50 text-amber-700" : "bg-slate-100 text-slate-600"}`}><Icon size={15} /></span><div className="min-w-0 flex-1"><p className="truncate text-[clamp(8px,1.05vw,12px)] font-semibold">{document.name}</p><p className="mt-0.5 text-[clamp(7px,.85vw,9px)] text-slate-400">{document.detail}</p></div><span className={`text-[clamp(6px,.8vw,9px)] font-bold uppercase ${pending ? "text-amber-700" : "text-emerald-700"}`}>{document.status}</span></div>;
            })}
          </div>
          <div className="border border-slate-200 bg-slate-50 p-[6%] shadow-sm">
            <div className="flex justify-between border-b border-dashed border-slate-300 pb-3"><div><p className="text-[clamp(7px,.9vw,10px)] font-bold uppercase text-blue-800">British Airways</p><p className="mt-1 text-[clamp(10px,1.4vw,16px)] font-semibold">Delhi → London</p></div><Plane size={24} className="text-blue-800" /></div>
            <div className="mt-[7%] grid grid-cols-3 gap-2 text-[clamp(7px,.9vw,10px)]"><div><span className="block text-slate-400">Flight</span><strong>BA142</strong></div><div><span className="block text-slate-400">Seat</span><strong>18A–D</strong></div><div><span className="block text-slate-400">Status</span><strong className="text-emerald-700">Confirmed</strong></div></div>
            <div className="mt-[8%] h-10 bg-[repeating-linear-gradient(90deg,#0f172a_0_2px,transparent_2px_5px)]" />
            <p className="mt-3 text-[clamp(7px,.85vw,9px)] text-slate-400">Original 2-page e-ticket follows this index page.</p>
          </div>
        </div>
      </div>
    </PageFrame>
  );
}

function GuidePage({ variant }: { variant: Variant }) {
  return (
    <PageFrame variant={variant} page={16} title="Place guide · London">
      <div className="mt-[4%]">
        <div className={`grid gap-[5%] ${variant === "binder" ? "grid-cols-[.8fr_1.2fr]" : "grid-cols-[1.15fr_.85fr]"}`}>
          <div className="relative min-h-[180px] overflow-hidden">
            <img src="https://images.unsplash.com/photo-1513635269975-59663e0ac1ad?auto=format&fit=crop&w=900&q=80" alt="London street and red bus" className={`absolute inset-0 h-full w-full object-cover ${variant === "binder" ? "grayscale" : ""}`} />
            <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent p-[7%] text-white"><p className="text-[clamp(7px,.9vw,10px)] font-bold uppercase text-amber-200">Optional reference</p><h2 className="display mt-1 text-[clamp(22px,3vw,38px)] font-semibold">London, your way</h2></div>
          </div>
          <div><p className="text-[clamp(8px,1.05vw,12px)] leading-relaxed text-slate-600">Keep this section for context that helps in the moment without crowding the daily plan.</p><div className="mt-[8%] border-t border-slate-200 pt-3"><p className="text-[clamp(7px,.9vw,10px)] font-bold uppercase text-brand">City rhythm</p><p className="mt-2 text-[clamp(9px,1.2vw,13px)] font-semibold leading-snug">Book timed attractions, but leave neighbourhood meals flexible.</p></div></div>
        </div>
        <div className="mt-[5%] grid grid-cols-3 gap-[3%]">
          {[['For Aarav','Young V&A and the Postal Museum put hands-on exhibits first.'],['For the family','Vegetarian options are pinned beside each day, not in a separate food list.'],['At the hotel','Laundry is available on level 1; use the quieter 20:00 slot after Day 4.']].map(([title, copy], index) => <div key={title} className={`${index === 1 ? "bg-teal-50" : "bg-slate-50"} p-[7%]`}><Heart size={13} className={index === 1 ? "text-teal-700" : "text-brand"} /><h3 className="mt-2 text-[clamp(8px,1vw,11px)] font-semibold">{title}</h3><p className="mt-2 text-[clamp(7px,.9vw,10px)] leading-relaxed text-slate-500">{copy}</p><p className="mt-3 text-[clamp(6px,.72vw,8px)] font-bold uppercase text-slate-400">Preference + verified source</p></div>)}
        </div>
      </div>
    </PageFrame>
  );
}

function Preview({ variant, section, mapMode }: { variant: Variant; section: Section; mapMode: MapMode }) {
  if (section === "contents") return <ContentsPage variant={variant} mapMode={mapMode} />;
  if (section === "overview") return <OverviewPage variant={variant} />;
  if (section === "maps") return <MapsPage variant={variant} />;
  if (section === "day") return <DayPage variant={variant} mapMode={mapMode} />;
  if (section === "essentials") return <EssentialsPage variant={variant} />;
  if (section === "documents") return <DocumentsPage variant={variant} />;
  return <GuidePage variant={variant} />;
}

/** The honest answer to "is everything in here", kept beside the preview so the
 * cut list is judged at the same time as the content. */
const audit = {
  carried: [
    "Day-by-day agenda with times, transfers, durations and booking state",
    "Numbered hotel-to-hotel circuit map for every day, matching the agenda order",
    "Address and confirmation reference on every stop, for a driver or a doorman",
    "Flights, stay, insurance and entry documents, with the one gap named up front",
    "Emergency, insurance, hotel, consulate and card-block numbers on one page",
    "Money, transport, power and daily-rhythm practicals for the destination",
    "Weather band and expected on-the-day spend per day",
    "Personal guidance that names its preference evidence and verified source",
    "Generation date and plan revision on every page footer",
  ],
  excluded: [
    "Guidebook prose and per-place photo galleries beyond one context page",
    "Alternatives that were considered and not chosen",
    "Live prices, availability and provider terms that expire before you travel",
    "Full passport, card and policy numbers, which stay out of a printable file",
    "The original PDF attachments themselves, indexed here but merged separately",
  ],
};

function App() {
  const [variant, setVariant] = useState<Variant>("layered");
  const [mapMode, setMapMode] = useState<MapMode>("day");
  const [section, setSection] = useState<Section>("contents");
  const choose = useCallback((value: string) => setVariant(value as Variant), []);
  const activeVariant = variants.find((item) => item.id === variant)!;
  const activeMap = mapModes.find((item) => item.id === mapMode)!;
  const shownSections = visibleSections(mapMode);

  useEffect(() => {
    if (mapMode !== "book" && section === "maps") setSection("day");
  }, [mapMode, section]);

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top_left,#fff7ed_0,transparent_30%),linear-gradient(180deg,#f8fafc_0,#e2e8f0_100%)] px-4 py-7 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl">
        <LabNavigation detail labId="itinerary-trip-book" />
        <div className="mt-4 flex flex-col gap-4 border-b border-slate-200 pb-6 lg:flex-row lg:items-end lg:justify-between">
          <div><p className="text-[10px] font-bold uppercase text-brand">Active itinerary experiment</p><h1 className="display mt-1 text-3xl font-semibold text-ink sm:text-4xl">Execution-ready Trip Book</h1><p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-600">Compare how one complete, printable trip can stay concise enough to use on the move while carrying every booking, entry document, day circuit map, and evidence-backed family insight.</p></div>
          <div className="flex items-center gap-2 text-xs text-slate-500"><FileText size={15} /><strong className="text-ink">{activeVariant.pages + activeMap.pages} pages</strong><span>· A4 + phone PDF</span></div>
        </div>

        <LabScope labId="itinerary-trip-book" />
        <OptionContrast labId="itinerary-trip-book" />

        <div className="mt-5 grid gap-2 lg:grid-cols-3">{variants.map((item) => <button key={item.id} type="button" onClick={() => setVariant(item.id)} className={`rounded-md p-4 text-left ring-1 transition ${variant === item.id ? "bg-white shadow-card ring-brand/40" : "bg-white/60 ring-slate-200 hover:bg-white"}`}><div className="flex items-center justify-between gap-2"><strong className="text-sm text-ink">{item.label}</strong><span className="text-[10px] font-semibold text-slate-400">{item.pages}p</span></div><span className="mt-1.5 block text-xs leading-relaxed text-slate-500">{item.note}</span></button>)}</div>

        <div data-lab-change="Map snapshot in the exported book" className="mt-3 rounded-md bg-white p-3 shadow-card ring-1 ring-slate-200">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <p className="text-[10px] font-bold uppercase text-slate-400">Map snapshot · independent of the three structures</p>
            <p className="text-[11px] text-slate-500">{activeMap.note}</p>
          </div>
          <div className="mt-2 grid gap-2 sm:grid-cols-3">
            {mapModes.map((item) => (
              <button key={item.id} type="button" onClick={() => setMapMode(item.id)} className={`rounded-md px-3 py-2 text-left text-xs ring-1 transition ${mapMode === item.id ? "bg-brand-50 text-brand ring-brand/40" : "bg-white text-slate-600 ring-slate-200 hover:bg-slate-50"}`}>
                <span className="flex items-center justify-between gap-2 font-semibold"><span className="flex items-center gap-1.5"><Compass size={13} />{item.label}</span><span className="text-[10px] opacity-70">{item.pages ? `+${item.pages}p` : "+0p"}</span></span>
              </button>
            ))}
          </div>
        </div>

        <section data-lab-change="Trip Book structure and page composition" className="mt-5 grid gap-4 lg:grid-cols-[210px_minmax(0,1fr)]" aria-label="Trip Book page explorer">
          <nav className="h-fit rounded-md bg-white p-2 shadow-card ring-1 ring-slate-200" aria-label="Trip Book sections">
            <p className="px-2 pb-2 pt-1 text-[10px] font-bold uppercase text-slate-400">Preview section</p>
            <div className="flex gap-2 overflow-x-auto lg:flex-col lg:overflow-visible">{shownSections.map((item) => { const Icon = item.icon; return <button key={item.id} type="button" onClick={() => setSection(item.id)} className={`flex min-w-40 items-center gap-2 rounded-md px-3 py-2.5 text-left text-xs transition lg:min-w-0 ${section === item.id ? "bg-brand-50 text-brand" : "text-slate-600 hover:bg-slate-50"}`}><Icon size={14} /><span className="min-w-0 flex-1 truncate font-medium">{item.label}</span><span className="text-[10px] opacity-60">{item.range}</span><ChevronRight size={12} /></button>; })}</div>
          </nav>
          <div className="rounded-md bg-slate-800/95 p-3 shadow-pop sm:p-6 lg:p-8"><Preview variant={variant} section={section} mapMode={mapMode} /></div>
        </section>

        <div className="mt-6 grid gap-3 md:grid-cols-3">
          <div className="rounded-md bg-white p-4 ring-1 ring-slate-200"><Clock3 size={16} className="text-brand" /><h2 className="mt-2 text-sm font-semibold">Find it under pressure</h2><p className="mt-1 text-xs leading-relaxed text-slate-500">A traveler should reach today’s plan, any confirmation, or a phone number in under ten seconds.</p></div>
          <div className="rounded-md bg-white p-4 ring-1 ring-slate-200"><ShieldCheck size={16} className="text-teal-700" /><h2 className="mt-2 text-sm font-semibold">Facts stay auditable</h2><p className="mt-1 text-xs leading-relaxed text-slate-500">Personal advice names the preference and verified travel source behind it.</p></div>
          <div className="rounded-md bg-white p-4 ring-1 ring-slate-200"><MapPin size={16} className="text-amber-700" /><h2 className="mt-2 text-sm font-semibold">One itinerary truth</h2><p className="mt-1 text-xs leading-relaxed text-slate-500">Times, booking states, sequence, and the map circuit match the live workspace.</p></div>
        </div>

        <section className="mt-4 grid gap-3 rounded-md bg-white p-4 shadow-card ring-1 ring-slate-200 md:grid-cols-[1.2fr_.8fr]" aria-label="Completeness audit">
          <div>
            <h2 className="text-sm font-semibold text-ink">What the book carries</h2>
            <ul className="mt-2 space-y-1.5">
              {audit.carried.map((item) => (
                <li key={item} className="flex gap-2 text-xs leading-relaxed text-slate-600"><Check size={13} className="mt-0.5 shrink-0 text-emerald-600" />{item}</li>
              ))}
            </ul>
          </div>
          <div>
            <h2 className="text-sm font-semibold text-ink">Left out on purpose</h2>
            <ul className="mt-2 space-y-1.5">
              {audit.excluded.map((item) => (
                <li key={item} className="flex gap-2 text-xs leading-relaxed text-slate-500"><span className="mt-2 h-px w-3 shrink-0 bg-slate-300" />{item}</li>
              ))}
            </ul>
            <p className="mt-3 text-[11px] leading-relaxed text-slate-400">The cut list is what keeps the packet at {activeVariant.pages + activeMap.pages} pages. Anything moved out of it has to displace something above.</p>
          </div>
        </section>

        <div className="mt-6"><DecisionCapture labId="itinerary-trip-book" labTitle="Execution-ready Trip Book" options={variants.map(({ id, label }) => ({ id, label }))} activeOption={variant} onChoose={choose} /></div>
      </div>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><App /></React.StrictMode>);
