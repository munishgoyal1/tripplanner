// Presentation for the public entry stage. Ported from the Lab 22 option E sandbox rather
// than imported, because production code must not depend on frontend/labs.

import {
  ArrowRight,
  BedDouble,
  Bus,
  Camera,
  Car,
  Check,
  Footprints,
  Hotel,
  Loader2,
  Plane,
  RotateCcw,
  ShieldCheck,
  Ship,
  SkipForward,
  TrainFront,
  TramFront,
  UserRound,
  UtensilsCrossed,
} from "lucide-react";
import { useEffect, useState } from "react";

import BrandIdentity from "../components/BrandIdentity";
import { trustPoints } from "./demoRun";
import type {
  ModeCompare,
  StageDay,
  StageHotel,
  StageLeg,
  StageMode,
  StageReceipt,
  StageStop,
  StageTrip,
  StopKind,
} from "./demoRun";

export type Tone = "light" | "dark";

interface ToneStyle {
  panel: string;
  panelRing: string;
  heading: string;
  body: string;
  muted: string;
  chip: string;
  divider: string;
  accent: string;
}

export const toneStyles: Record<Tone, ToneStyle> = {
  light: {
    panel: "bg-white",
    panelRing: "ring-1 ring-slate-200",
    heading: "text-ink",
    body: "text-slate-600",
    muted: "text-slate-400",
    chip: "bg-slate-100 text-slate-600",
    divider: "border-slate-200",
    accent: "text-brand",
  },
  dark: {
    panel: "bg-white/[0.04]",
    panelRing: "ring-1 ring-white/10",
    heading: "text-white",
    body: "text-slate-300",
    muted: "text-slate-500",
    chip: "bg-white/10 text-slate-200",
    divider: "border-white/10",
    accent: "text-emerald-300",
  },
};

export const modeIcons: Record<StageMode, typeof Plane> = {
  flight: Plane,
  train: TrainFront,
  road: Car,
  tram: TramFront,
  metro: TrainFront,
  bus: Bus,
  walk: Footprints,
  ferry: Ship,
};

export const modeLabels: Record<StageMode, string> = {
  flight: "Flight",
  train: "Rail",
  road: "Road",
  tram: "Tram",
  metro: "Metro",
  bus: "Coach",
  walk: "On foot",
  ferry: "Ferry",
};

const stopIcons: Record<StopKind, typeof Plane> = {
  flight: Plane,
  hotel: BedDouble,
  attraction: Camera,
  meal: UtensilsCrossed,
  transport: TrainFront,
};

export function useStageRun(total: number) {
  const [step, setStep] = useState(0);

  useEffect(() => {
    setStep(0);
  }, [total]);

  useEffect(() => {
    if (step >= total) return;
    const timer = window.setTimeout(() => setStep((value) => value + 1), step === 0 ? 350 : 520);
    return () => window.clearTimeout(timer);
  }, [step, total]);

  return {
    step,
    running: step < total,
    replay: () => setStep(0),
    finish: () => setStep(total),
  };
}

// Day cards only appear once the receipt that placed them has been printed, so the grid can
// never show a day the run has not reached.
export function daysBuilt(receipts: StageReceipt[], step: number) {
  return receipts.slice(0, step).filter((receipt) => receipt.day).length;
}

const receiptAccent: Record<StageReceipt["kind"], string> = {
  read: "text-slate-400",
  search: "text-sky-500",
  price: "text-emerald-600",
  hotel: "text-violet-500",
  place: "text-brand",
  compare: "text-amber-600",
  check: "text-emerald-600",
};

const receiptAccentDark: Record<StageReceipt["kind"], string> = {
  read: "text-slate-500",
  search: "text-sky-300",
  price: "text-emerald-300",
  hotel: "text-violet-300",
  place: "text-rose-300",
  compare: "text-amber-300",
  check: "text-emerald-300",
};

export function ReceiptLine({ receipt, tone }: { receipt: StageReceipt; tone: Tone }) {
  const s = toneStyles[tone];
  const accent = tone === "dark" ? receiptAccentDark[receipt.kind] : receiptAccent[receipt.kind];
  return (
    <li className="flex gap-2 font-mono text-[11px] leading-relaxed">
      <span className={`shrink-0 tabular-nums ${accent}`}>{receipt.at}</span>
      <span className={s.body}>{receipt.text}</span>
    </li>
  );
}

function LegChips({ legs, tone }: { legs: StageLeg[]; tone: Tone }) {
  const s = toneStyles[tone];
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {legs.map((leg, index) => {
        const Icon = modeIcons[leg.mode];
        return (
          <span
            key={`${index}-${leg.label}`}
            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${s.chip}`}
            title={leg.label}
          >
            <Icon size={11} aria-hidden />
            {leg.duration}
            {leg.cost && <span className={s.muted}>· {leg.cost}</span>}
          </span>
        );
      })}
    </div>
  );
}

function Marker({ stop, color }: { stop: StageStop; color: string }) {
  if (stop.kind === "hotel") {
    return (
      <span
        className="grid h-5 w-5 shrink-0 place-items-center rounded-md bg-violet-500 text-[9px] font-bold text-white"
        aria-hidden
      >
        {stop.marker ?? <Hotel size={10} />}
      </span>
    );
  }
  const Icon = stopIcons[stop.kind];
  return (
    <span
      className="grid h-5 w-5 shrink-0 place-items-center rounded-full border text-[10px] font-bold"
      style={{ borderColor: color, color }}
      aria-hidden
    >
      {stop.marker ?? <Icon size={10} />}
    </span>
  );
}

function StopRow({ stop, color, tone }: { stop: StageStop; color: string; tone: Tone }) {
  const s = toneStyles[tone];
  return (
    <li className="flex items-start gap-2 py-1">
      <Marker stop={stop} color={color} />
      <span className={`w-10 shrink-0 pt-0.5 text-[11px] font-semibold tabular-nums ${s.muted}`}>{stop.time}</span>
      <span className="min-w-0 flex-1">
        <span className={`block truncate text-xs font-medium ${s.heading}`}>{stop.name}</span>
      </span>
      {stop.cost && <span className={`shrink-0 pt-0.5 text-[11px] tabular-nums ${s.body}`}>{stop.cost}</span>}
    </li>
  );
}

export function StageDayCard({ day, tone }: { day: StageDay; tone: Tone }) {
  const s = toneStyles[tone];
  return (
    <article className={`rounded-xl p-3 ${s.panel} ${s.panelRing}`}>
      <div className="flex items-baseline justify-between gap-2">
        <p className={`text-xs font-bold ${s.heading}`}>
          Day {day.day} · <span className={s.body}>{day.weekday} {day.date}</span>
        </p>
        <span className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-bold ${tone === "dark" ? "bg-violet-500/20 text-violet-200" : "bg-violet-50 text-violet-700"}`}>
          <BedDouble size={10} aria-hidden /> {day.hotel}
        </span>
      </div>
      <p className={`mt-0.5 text-[13px] font-semibold ${s.heading}`}>{day.title}</p>
      <p className={`text-[11px] ${s.muted}`}>{day.city}</p>
      <ul className="mt-1.5">
        {day.stops.slice(0, 3).map((stop, index) => (
          <StopRow key={`${day.day}-${index}-${stop.time}`} stop={stop} color={day.color} tone={tone} />
        ))}
      </ul>
      <div className="mt-2">
        <LegChips legs={day.legs} tone={tone} />
      </div>
    </article>
  );
}

export function PendingDayCard({ tone, label }: { tone: Tone; label?: string }) {
  const s = toneStyles[tone];
  return (
    <div className={`rounded-xl p-3 ${tone === "dark" ? "bg-white/[0.03] ring-1 ring-white/5" : "bg-slate-50 ring-1 ring-slate-200"}`}>
      {label ? (
        <p className={`flex items-center gap-1.5 text-[11px] font-semibold ${s.body}`}>
          <Loader2 size={11} className="animate-spin" aria-hidden /> {label}
        </p>
      ) : (
        <div className={`h-2.5 w-24 rounded ${tone === "dark" ? "bg-white/10" : "bg-slate-200"}`} />
      )}
      <div className="mt-2 space-y-1.5">
        <div className={`h-2 w-full rounded ${tone === "dark" ? "bg-white/5" : "bg-slate-200/70"}`} />
        <div className={`h-2 w-4/5 rounded ${tone === "dark" ? "bg-white/5" : "bg-slate-200/70"}`} />
        <div className={`h-2 w-3/5 rounded ${tone === "dark" ? "bg-white/5" : "bg-slate-200/70"}`} />
      </div>
    </div>
  );
}

export function HotelStrip({ hotels, tone, detail = false }: { hotels: StageHotel[]; tone: Tone; detail?: boolean }) {
  const s = toneStyles[tone];
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {hotels.map((hotel) => (
        <div key={hotel.marker} className={`rounded-xl p-3 ${s.panel} ${s.panelRing}`}>
          <div className="flex items-start gap-2">
            <span className="grid h-6 w-6 shrink-0 place-items-center rounded-md bg-violet-500 text-[10px] font-bold text-white">
              {hotel.marker}
            </span>
            <div className="min-w-0 flex-1">
              <p className={`text-xs font-semibold ${s.heading}`}>{hotel.name}</p>
              <p className={`text-[11px] ${s.muted}`}>{hotel.city} · {hotel.area} · {hotel.nights}</p>
            </div>
            <span className={`shrink-0 text-xs font-bold tabular-nums ${s.heading}`}>{hotel.price}</span>
          </div>
          <p className={`mt-1.5 text-[11px] leading-relaxed ${s.body}`}>{hotel.why}</p>
          {detail && (
            <p className={`mt-1.5 text-[11px] ${s.muted}`}>
              {hotel.source} · checked {hotel.checked}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}

export function ModeCompareCard({ compare, tone }: { compare: ModeCompare; tone: Tone }) {
  const s = toneStyles[tone];
  return (
    <div className={`overflow-hidden rounded-xl ${s.panel} ${s.panelRing}`}>
      <div className={`flex flex-wrap items-center justify-between gap-2 border-b px-3 py-2 ${s.divider}`}>
        <p className={`text-xs font-semibold ${s.heading}`}>{compare.subject}</p>
        <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold ${tone === "dark" ? "bg-emerald-400/15 text-emerald-300" : "bg-emerald-50 text-emerald-700"}`}>
          <Check size={10} aria-hidden /> {compare.chosen}
        </span>
      </div>
      <ul className={`divide-y ${tone === "dark" ? "divide-white/10" : "divide-slate-100"}`}>
        {compare.options.map((option) => {
          const Icon = modeIcons[option.mode];
          return (
            <li
              key={option.label}
              className={`flex items-start gap-2 px-3 py-2 ${option.picked ? (tone === "dark" ? "bg-emerald-400/[0.07]" : "bg-emerald-50/60") : ""}`}
            >
              <Icon size={14} className={`mt-0.5 shrink-0 ${option.picked ? s.accent : s.muted}`} aria-hidden />
              <div className="min-w-0 flex-1">
                <p className={`text-[11px] font-semibold ${option.picked ? s.heading : s.body}`}>
                  {option.label}
                  <span className={`ml-1.5 font-normal ${s.muted}`}>{option.door} · {option.cost}</span>
                </p>
                <p className={`text-[11px] leading-relaxed ${s.muted}`}>{option.verdict}</p>
              </div>
            </li>
          );
        })}
      </ul>
      <p className={`border-t px-3 py-2 text-[11px] leading-relaxed ${s.divider} ${s.body}`}>{compare.why}</p>
    </div>
  );
}

export function SavingsRow({ trip, tone }: { trip: StageTrip; tone: Tone }) {
  const s = toneStyles[tone];
  return (
    <div className={`rounded-xl px-3.5 py-2.5 ${tone === "dark" ? "bg-emerald-400/10 ring-1 ring-emerald-400/30" : "bg-emerald-50 ring-1 ring-emerald-200"}`}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className={`text-[11px] font-bold uppercase ${tone === "dark" ? "text-emerald-300" : "text-emerald-700"}`}>{trip.totalLabel}</span>
        <span className={`text-lg font-bold tabular-nums ${s.heading}`}>{trip.total}</span>
        <span className={`text-[11px] ${s.body}`}>{trip.totalNote}</span>
      </div>
    </div>
  );
}

export function PriceTableLive({ trip, tone }: { trip: StageTrip; tone: Tone }) {
  const s = toneStyles[tone];
  return (
    <div className={`overflow-hidden rounded-xl ${s.panel} ${s.panelRing}`}>
      <table className="w-full text-left">
        <caption className="sr-only">What the trip costs and where each price came from</caption>
        <thead>
          <tr className={`border-b ${s.divider}`}>
            <th scope="col" className={`px-3 py-2 text-[10px] font-bold uppercase ${s.muted}`}>Line</th>
            <th scope="col" className={`px-3 py-2 text-right text-[10px] font-bold uppercase ${s.muted}`}>Price</th>
            <th scope="col" className={`px-3 py-2 text-[10px] font-bold uppercase ${s.muted}`}>Source · checked</th>
          </tr>
        </thead>
        <tbody>
          {trip.lines.map((line) => (
            <tr key={line.label} className={`border-b last:border-0 ${s.divider}`}>
              <th scope="row" className="px-3 py-2 align-top">
                <span className={`block text-xs font-semibold ${s.heading}`}>{line.label}</span>
                <span className={`block text-[11px] font-normal ${s.body}`}>{line.detail}</span>
              </th>
              <td className={`px-3 py-2 text-right align-top text-xs font-semibold tabular-nums ${s.heading}`}>{line.price}</td>
              <td className={`px-3 py-2 align-top text-[11px] ${s.body}`}>
                {line.source}
                <span className={`block ${s.muted}`}>{line.checked}</span>
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className={`border-t ${s.divider}`}>
            <th scope="row" className="px-3 py-2 align-top">
              <span className={`block text-xs font-semibold ${s.heading}`}>{trip.totalLabel}</span>
              <span className={`block text-[11px] font-normal ${s.body}`}>
                {trip.totalNote}
              </span>
            </th>
            <td className={`px-3 py-2 text-right align-top text-xs font-bold tabular-nums ${s.heading}`}>{trip.total}</td>
            <td className={`px-3 py-2 align-top text-[11px] ${s.muted}`}>{trip.sources}</td>
          </tr>
        </tfoot>
      </table>
      <p className={`border-t px-3 py-2 text-[10px] leading-relaxed ${s.divider} ${s.muted}`}>
        Beta pricing is representative: the flight is a provider sandbox fare, while stays and
        daily spend use realistic estimates for these dates. Every estimate is replaced or
        rechecked against a provider before booking.
      </p>
    </div>
  );
}

export function ModeLegend({ tone }: { tone: Tone }) {
  const s = toneStyles[tone];
  const modes: StageMode[] = ["flight", "train", "road", "tram", "metro", "bus", "walk"];
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
      <span className={`text-[10px] font-bold uppercase ${s.muted}`}>Compared on every hop</span>
      {modes.map((mode) => {
        const Icon = modeIcons[mode];
        return (
          <span key={mode} className={`inline-flex items-center gap-1 text-[11px] ${s.body}`}>
            <Icon size={12} aria-hidden /> {modeLabels[mode]}
          </span>
        );
      })}
    </div>
  );
}

export function StageControls({
  tone,
  running,
  onReplay,
  onFinish,
}: {
  tone: Tone;
  running: boolean;
  onReplay: () => void;
  onFinish: () => void;
}) {
  const base = tone === "dark"
    ? "bg-white/10 text-slate-200 hover:bg-white/20"
    : "bg-slate-100 text-slate-700 hover:bg-slate-200";
  return (
    <div className="flex items-center gap-1.5">
      {running && (
        <button type="button" onClick={onFinish} className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-semibold ${base}`}>
          <SkipForward size={11} aria-hidden /> Show the finished plan
        </button>
      )}
      <button type="button" onClick={onReplay} className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-semibold ${base}`}>
        <RotateCcw size={11} aria-hidden /> Replay
      </button>
    </div>
  );
}

export function TrustList({ tone }: { tone: Tone }) {
  const s = toneStyles[tone];
  return (
    <ul className="grid gap-2 sm:grid-cols-2">
      {trustPoints.map((point) => (
        <li key={point} className={`flex gap-2 text-xs leading-relaxed ${s.body}`}>
          <ShieldCheck size={14} className={`mt-0.5 shrink-0 ${s.accent}`} aria-hidden />
          {point}
        </li>
      ))}
    </ul>
  );
}

export function SectionHead({ tone, eyebrow, title, body }: { tone: Tone; eyebrow: string; title: string; body?: string }) {
  const s = toneStyles[tone];
  return (
    <div className="max-w-2xl">
      <p className={`text-[10px] font-bold uppercase ${s.accent}`}>{eyebrow}</p>
      <h2 className={`display mt-1 text-xl font-semibold sm:text-2xl ${s.heading}`}>{title}</h2>
      {body && <p className={`mt-1.5 text-sm leading-relaxed ${s.body}`}>{body}</p>}
    </div>
  );
}

export function Masthead({ tone, onSkip, accountLabel, signedIn }: { tone: Tone; onSkip: () => void; accountLabel: string; signedIn: boolean }) {
  return (
    <header className={`flex items-center justify-between border-b px-6 py-3.5 ${toneStyles[tone].divider}`}>
      <BrandIdentity compact />
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onSkip}
          className={`inline-flex items-center gap-2 rounded-full border px-2 py-1.5 text-[12px] font-semibold transition ${tone === "dark" ? "border-white/25 bg-white/10 text-white hover:bg-white/15" : "border-slate-300 bg-white text-slate-700 hover:bg-slate-100"}`}
          title={`${accountLabel} profile · Open planner account settings`}
          aria-label={`${accountLabel} profile`}
        >
          <span className={`relative grid h-6 w-6 place-items-center rounded-full ${tone === "dark" ? "bg-white text-ink" : "bg-slate-100 text-slate-700"}`}>
            <UserRound size={14} aria-hidden />
            <span className={`absolute -bottom-0.5 -right-1 h-2 w-2 rounded-full ring-2 ${tone === "dark" ? "ring-[#080b11]" : "ring-white"} ${signedIn ? "bg-emerald-400" : "bg-slate-400"}`} aria-hidden />
          </span>
          <span>{accountLabel}</span>
        </button>
        <button
          type="button"
          onClick={onSkip}
          className={`rounded-full px-3 py-1.5 text-[13px] font-semibold transition ${tone === "dark" ? "bg-white text-ink hover:bg-slate-200" : "bg-ink text-white hover:opacity-90"}`}
        >
          Skip to the app <ArrowRight size={13} className="ml-1 inline" aria-hidden />
        </button>
      </div>
    </header>
  );
}

export function SiteFooter({ tone }: { tone: Tone }) {
  const s = toneStyles[tone];
  return (
    <footer className={`border-t px-6 py-6 ${s.divider}`}>
      <p className={`text-[11px] ${s.muted}`}>
        © 2026 AI Tripplanner · We never hold your card and never charge you. Bookings complete on the
        provider's own site.
      </p>
    </footer>
  );
}
