import React, { useState } from "react";
import ReactDOM from "react-dom/client";
import {
  ArrowRight,
  BusFront,
  CalendarCheck2,
  CarTaxiFront,
  Check,
  ChevronRight,
  Clock3,
  ExternalLink,
  Footprints,
  MapPin,
  Route,
  Sparkles,
  TrainFront,
} from "lucide-react";
import "../index.css";

type Variant = "timeline" | "agenda" | "cards";

interface Leg {
  mode: "walk" | "metro" | "taxi" | "bus";
  label: string;
  duration: string;
  distance: string;
  detail: string;
}

interface Stop {
  time: string;
  name: string;
  kind: string;
  duration: string;
  detail: string;
  booked: boolean;
  leg?: Leg;
}

const variants: Array<{ id: Variant; label: string; summary: string }> = [
  {
    id: "timeline",
    label: "A · Journey timeline",
    summary: "Transport becomes the connector between destinations.",
  },
  {
    id: "agenda",
    label: "B · Compact agenda",
    summary: "Time-first rows optimize scanning and planning density.",
  },
  {
    id: "cards",
    label: "C · Guided place cards",
    summary: "Labeled sections prioritize clarity and first-time use.",
  },
];

const stops: Stop[] = [
  {
    time: "9:00 AM",
    name: "Le Roch Hotel & Spa",
    kind: "Stay",
    duration: "Start",
    detail: "Breakfast and depart from your hotel.",
    booked: true,
  },
  {
    time: "10:00 AM",
    name: "Louvre Museum",
    kind: "Attraction",
    duration: "2 hr 30 min",
    detail: "Enter through Carrousel du Louvre; focus on Denon and Sully wings.",
    booked: true,
    leg: {
      mode: "walk",
      label: "Walk",
      duration: "12 min",
      distance: "900 m",
      detail: "Mostly flat via Avenue de l'Opera",
    },
  },
  {
    time: "1:15 PM",
    name: "Le Comptoir de la Gastronomie",
    kind: "Lunch",
    duration: "1 hr 15 min",
    detail: "Classic French lunch; vegetarian dishes available.",
    booked: false,
    leg: {
      mode: "metro",
      label: "Metro",
      duration: "18 min",
      distance: "2.4 km",
      detail: "Line 1, then a 6-minute walk",
    },
  },
  {
    time: "3:15 PM",
    name: "Musee de l'Orangerie",
    kind: "Attraction",
    duration: "1 hr 30 min",
    detail: "Monet's Water Lilies first, then the lower-level collection.",
    booked: false,
    leg: {
      mode: "taxi",
      label: "Taxi",
      duration: "14 min",
      distance: "3.1 km",
      detail: "Best when conserving energy after lunch",
    },
  },
  {
    time: "6:00 PM",
    name: "Le Roch Hotel & Spa",
    kind: "Stay",
    duration: "Return",
    detail: "Rest before dinner near the hotel.",
    booked: true,
    leg: {
      mode: "bus",
      label: "Local bus",
      duration: "20 min",
      distance: "2.2 km",
      detail: "Direct central route plus a short walk",
    },
  },
];

const modeIcon = {
  walk: Footprints,
  metro: TrainFront,
  taxi: CarTaxiFront,
  bus: BusFront,
};

function BookingAction({ booked }: { booked: boolean }) {
  return (
    <button
      type="button"
      className={`inline-flex h-7 shrink-0 items-center gap-1.5 rounded-full px-2.5 text-[11px] font-semibold ring-1 transition ${
        booked
          ? "bg-emerald-50 text-emerald-700 ring-emerald-200 hover:bg-emerald-100"
          : "bg-white text-slate-600 ring-slate-200 hover:text-brand hover:ring-brand/30"
      }`}
      aria-label={booked ? "Booking confirmed" : "Mark booking confirmed"}
    >
      {booked ? <Check size={12} aria-hidden /> : <CalendarCheck2 size={12} aria-hidden />}
      {booked ? "Confirmed" : "Needs booking"}
    </button>
  );
}

function LegStrip({ leg, compact = false }: { leg: Leg; compact?: boolean }) {
  const Icon = modeIcon[leg.mode];
  return (
    <div className={`flex items-center gap-2 text-xs ${compact ? "py-1.5" : "rounded-md bg-teal-50/70 px-2.5 py-2 ring-1 ring-teal-100"}`}>
      <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-white text-accent ring-1 ring-teal-200">
        <Icon size={13} aria-hidden />
      </span>
      <span className="font-semibold text-accent-600">{leg.label}</span>
      <span className="text-slate-600">{leg.duration}</span>
      <span className="text-slate-300" aria-hidden>·</span>
      <span className="text-slate-500">{leg.distance}</span>
      {!compact && <span className="ml-auto hidden text-slate-500 sm:inline">{leg.detail}</span>}
    </div>
  );
}

function DayHeader() {
  return (
    <div className="border-b border-slate-200 bg-white px-4 py-4 sm:px-5">
      <div className="flex items-start gap-3">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-brand text-sm font-bold text-white">2</span>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold uppercase text-brand">Saturday · 12 September 2026</p>
          <h2 className="display mt-0.5 text-xl font-semibold text-ink">Masterpieces and central Paris</h2>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
            <span className="inline-flex items-center gap-1"><MapPin size={12} aria-hidden /> 5 stops</span>
            <span className="inline-flex items-center gap-1"><Clock3 size={12} aria-hidden /> 7 hr planned</span>
            <span className="inline-flex items-center gap-1"><Route size={12} aria-hidden /> 8.6 km · mixed local travel</span>
            <a href="#" onClick={(event) => event.preventDefault()} className="inline-flex items-center gap-1 font-semibold text-brand">
              <ExternalLink size={12} aria-hidden /> Open route
            </a>
          </div>
        </div>
      </div>
      <div className="mt-4 grid gap-2 sm:grid-cols-2">
        <section aria-label="Getting around" className="rounded-md bg-teal-50 px-3 py-2.5 ring-1 ring-teal-100">
          <p className="text-[10px] font-bold uppercase text-accent">Getting around</p>
          <p className="mt-1 text-xs leading-relaxed text-slate-600">Walk in the museum quarter; use Metro or a short taxi for the longer midday legs.</p>
        </section>
        <section aria-label="Day overview" className="rounded-md bg-slate-50 px-3 py-2.5 ring-1 ring-slate-100">
          <p className="text-[10px] font-bold uppercase text-slate-500">Day overview</p>
          <p className="mt-1 text-xs leading-relaxed text-slate-600">A focused art day with a long lunch and a lighter late-afternoon museum.</p>
        </section>
      </div>
    </div>
  );
}

function TimelineVariant() {
  return (
    <div className="px-4 py-4 sm:px-5">
      {stops.map((stop, index) => (
        <React.Fragment key={`${stop.name}-${index}`}>
          {stop.leg && (
            <div className="relative ml-[1.15rem] border-l-2 border-dashed border-teal-200 py-2 pl-6">
              <LegStrip leg={stop.leg} />
            </div>
          )}
          <article className="relative flex gap-3 rounded-md bg-white p-3 ring-1 ring-slate-200">
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full border-2 border-brand bg-white text-xs font-bold text-brand">{index === 0 || index === stops.length - 1 ? "H" : index}</span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-start gap-2">
                <div className="min-w-0 flex-1">
                  <p className="text-[11px] font-semibold text-slate-400">{stop.time} · {stop.duration}</p>
                  <h3 className="truncate text-sm font-semibold text-ink">{stop.name}</h3>
                </div>
                <BookingAction booked={stop.booked} />
              </div>
              <p className="mt-1 text-xs leading-relaxed text-slate-500">{stop.detail}</p>
            </div>
          </article>
        </React.Fragment>
      ))}
    </div>
  );
}

function AgendaVariant() {
  return (
    <div className="divide-y divide-slate-100 px-4 sm:px-5">
      {stops.map((stop, index) => (
        <article key={`${stop.name}-${index}`} className="grid grid-cols-[4.5rem_minmax(0,1fr)] gap-3 py-3">
          <div className="pt-0.5 text-right">
            <p className="text-xs font-bold text-ink">{stop.time}</p>
            <p className="mt-0.5 text-[10px] text-slate-400">{stop.duration}</p>
          </div>
          <div className="min-w-0">
            {stop.leg && <LegStrip leg={stop.leg} compact />}
            <div className="flex items-start gap-2">
              <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-brand text-[10px] font-bold text-white">{index === 0 || index === stops.length - 1 ? "H" : index}</span>
              <div className="min-w-0 flex-1">
                <p className="text-[10px] font-bold uppercase text-slate-400">{stop.kind}</p>
                <h3 className="truncate text-sm font-semibold text-ink">{stop.name}</h3>
                <p className="mt-0.5 line-clamp-2 text-xs text-slate-500">{stop.detail}</p>
              </div>
              <BookingAction booked={stop.booked} />
            </div>
          </div>
        </article>
      ))}
    </div>
  );
}

function CardsVariant() {
  return (
    <div className="space-y-3 px-4 py-4 sm:px-5">
      {stops.map((stop, index) => (
        <article key={`${stop.name}-${index}`} className="overflow-hidden rounded-md bg-white ring-1 ring-slate-200">
          {stop.leg && (
            <div className="border-b border-teal-100 bg-teal-50/70 px-3 py-2">
              <p className="mb-1 text-[10px] font-bold uppercase text-accent">Travel from previous stop</p>
              <LegStrip leg={stop.leg} compact />
              <p className="pl-8 text-[11px] text-slate-500">{stop.leg.detail}</p>
            </div>
          )}
          <div className="p-3">
            <div className="flex items-start gap-3">
              <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-brand text-xs font-bold text-white">{index === 0 || index === stops.length - 1 ? "H" : index}</span>
              <div className="min-w-0 flex-1">
                <p className="text-[10px] font-bold uppercase text-slate-400">{stop.kind} · {stop.time}</p>
                <h3 className="text-sm font-semibold text-ink">{stop.name}</h3>
              </div>
              <BookingAction booked={stop.booked} />
            </div>
            <div className="mt-3 grid gap-2 sm:grid-cols-[7rem_minmax(0,1fr)]">
              <div>
                <p className="text-[10px] font-bold uppercase text-slate-400">Time here</p>
                <p className="mt-0.5 text-xs font-semibold text-slate-700">{stop.duration}</p>
              </div>
              <div>
                <p className="text-[10px] font-bold uppercase text-slate-400">Plan</p>
                <p className="mt-0.5 text-xs leading-relaxed text-slate-600">{stop.detail}</p>
              </div>
            </div>
          </div>
        </article>
      ))}
    </div>
  );
}

function VariantPreview({ variant }: { variant: Variant }) {
  return (
    <section className="overflow-hidden rounded-md bg-surface shadow-card ring-1 ring-slate-200">
      <DayHeader />
      {variant === "timeline" && <TimelineVariant />}
      {variant === "agenda" && <AgendaVariant />}
      {variant === "cards" && <CardsVariant />}
    </section>
  );
}

function Scorecard({ variant }: { variant: Variant }) {
  const key = `tripplanner-ux-lab-itinerary-${variant}`;
  const [scores, setScores] = useState<Record<string, number>>(() => {
    try {
      return JSON.parse(localStorage.getItem(key) || "{}") as Record<string, number>;
    } catch {
      return {};
    }
  });
  const dimensions = ["Scan speed", "Transport clarity", "Booking clarity", "Information hierarchy", "Mobile fit"];
  const update = (dimension: string, score: number) => {
    const next = { ...scores, [dimension]: score };
    setScores(next);
    localStorage.setItem(key, JSON.stringify(next));
  };
  return (
    <aside className="rounded-md bg-white p-4 ring-1 ring-slate-200">
      <div className="flex items-center gap-2">
        <Sparkles size={15} className="text-brand" aria-hidden />
        <h2 className="text-sm font-semibold text-ink">Local scorecard</h2>
      </div>
      <p className="mt-1 text-xs text-slate-500">Scores stay only in this browser.</p>
      <div className="mt-4 space-y-3">
        {dimensions.map((dimension) => (
          <fieldset key={dimension} className="flex items-center justify-between gap-3">
            <legend className="text-xs font-medium text-slate-600">{dimension}</legend>
            <div className="flex gap-1">
              {[1, 2, 3, 4, 5].map((score) => (
                <button
                  key={score}
                  type="button"
                  onClick={() => update(dimension, score)}
                  aria-label={`${dimension}: ${score} of 5`}
                  className={`grid h-7 w-7 place-items-center rounded-full text-[11px] font-semibold ring-1 ${scores[dimension] === score ? "bg-brand text-white ring-brand" : "bg-white text-slate-500 ring-slate-200 hover:ring-brand/30"}`}
                >
                  {score}
                </button>
              ))}
            </div>
          </fieldset>
        ))}
      </div>
    </aside>
  );
}

function Lab() {
  const [variant, setVariant] = useState<Variant>("timeline");
  const [compare, setCompare] = useState(false);
  return (
    <main className="min-h-full bg-[linear-gradient(180deg,#f8fafc_0,#fafaf9_18rem)] px-4 py-6 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl">
        <header className="flex flex-col gap-4 border-b border-slate-200 pb-5 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-xs font-bold uppercase text-brand">Internal · Itinerary UX experiment</p>
            <h1 className="display mt-1 text-3xl font-semibold text-ink">Choose how a travel day should read</h1>
            <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-600">All variants use the same itinerary facts. Compare hierarchy, transport guidance, weekday visibility, and an explicit booking-state action before changing the product.</p>
          </div>
          <button type="button" onClick={() => setCompare((value) => !value)} className="btn-ghost self-start lg:self-auto">
            {compare ? "Inspect one" : "Compare all"} <ChevronRight size={14} aria-hidden />
          </button>
        </header>

        {!compare && (
          <div className="mt-5 grid gap-2 sm:grid-cols-3" role="tablist" aria-label="Itinerary design variants">
            {variants.map((item) => (
              <button
                key={item.id}
                type="button"
                role="tab"
                aria-selected={variant === item.id}
                onClick={() => setVariant(item.id)}
                className={`rounded-md p-3 text-left ring-1 transition ${variant === item.id ? "bg-white text-ink shadow-card ring-brand/30" : "bg-white/60 text-slate-600 ring-slate-200 hover:bg-white"}`}
              >
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
                <div className="mb-3 flex items-center gap-2">
                  <ArrowRight size={14} className="text-brand" aria-hidden />
                  <h2 className="text-sm font-semibold text-ink">{item.label}</h2>
                </div>
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

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Lab />
  </React.StrictMode>,
);