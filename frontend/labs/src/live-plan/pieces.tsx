// Shared machinery for Lab 22. The stage engine, the day cards, the hotel strip and the
// transport comparison are used by all four options, so the options differ only in what
// they ask the visitor to do — not in the facts they are arguing over.

import {
  ArrowRight,
  BedDouble,
  Bus,
  Camera,
  Car,
  Check,
  ChevronRight,
  Clock3,
  Copy,
  Footprints,
  Hotel,
  Link2,
  Loader2,
  MapPin,
  Plane,
  RotateCcw,
  Ship,
  ShieldCheck,
  SkipForward,
  TrainFront,
  TramFront,
  TriangleAlert,
  UserRound,
  UtensilsCrossed,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import { toneStyles, type Tone } from "../first-visit/pieces";
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
} from "./fixture";
import { trustPoints } from "./fixture";

export { toneStyles };
export type { Tone };

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

export const stopIcons: Record<StopKind, typeof Plane> = {
  flight: Plane,
  hotel: BedDouble,
  attraction: Camera,
  meal: UtensilsCrossed,
  transport: TrainFront,
};

export function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(query.matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  return reduced;
}

// A visitor who has asked the operating system to stop animations gets the finished plan,
// not a slower version of the same performance.
export function useStageRun(total: number, resetKey = "") {
  const reduced = usePrefersReducedMotion();
  const [step, setStep] = useState(() => (reduced ? total : 0));

  useEffect(() => {
    setStep(reduced ? total : 0);
  }, [resetKey, reduced, total]);

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

export function StageProgress({ step, total, tone }: { step: number; total: number; tone: Tone }) {
  const s = toneStyles[tone];
  const pct = Math.round((step / total) * 100);
  return (
    <div>
      <div className="flex items-center justify-between gap-2">
        <span className={`text-[11px] font-semibold ${s.body}`}>
          {step >= total ? `${total} of ${total} steps done` : `Step ${step + 1} of ${total}`}
        </span>
        <span className={`text-[11px] tabular-nums ${s.muted}`}>{pct}%</span>
      </div>
      <div className={`mt-1 h-1 overflow-hidden rounded-full ${tone === "dark" ? "bg-white/10" : "bg-slate-200"}`}>
        <div
          className="h-full rounded-full bg-brand transition-[width] duration-500"
          style={{ width: `${Math.max(4, pct)}%` }}
        />
      </div>
    </div>
  );
}

export function LegChips({ legs, tone }: { legs: StageLeg[]; tone: Tone }) {
  const s = toneStyles[tone];
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {legs.map((leg) => {
        const Icon = modeIcons[leg.mode];
        return (
          <span
            key={leg.label}
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

function Marker({ stop, color, tone }: { stop: StageStop; color: string; tone: Tone }) {
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
      className={`grid h-5 w-5 shrink-0 place-items-center rounded-full border text-[10px] font-bold ${tone === "dark" ? "" : ""}`}
      style={{ borderColor: color, color }}
      aria-hidden
    >
      {stop.marker ?? <Icon size={10} />}
    </span>
  );
}

export function StopRow({ stop, color, tone, detail = false }: { stop: StageStop; color: string; tone: Tone; detail?: boolean }) {
  const s = toneStyles[tone];
  return (
    <li className="flex items-start gap-2 py-1">
      <Marker stop={stop} color={color} tone={tone} />
      <span className={`w-10 shrink-0 pt-0.5 text-[11px] font-semibold tabular-nums ${s.muted}`}>{stop.time}</span>
      <span className="min-w-0 flex-1">
        <span className={`block truncate text-xs font-medium ${s.heading}`}>{stop.name}</span>
        {detail && stop.detail && <span className={`block text-[11px] ${s.body}`}>{stop.detail}</span>}
      </span>
      {stop.cost && <span className={`shrink-0 pt-0.5 text-[11px] tabular-nums ${s.body}`}>{stop.cost}</span>}
    </li>
  );
}

export function StageDayCard({ day, tone, stops = 3 }: { day: StageDay; tone: Tone; stops?: number }) {
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
        {day.stops.slice(0, stops).map((stop) => (
          <StopRow key={`${day.day}-${stop.time}`} stop={stop} color={day.color} tone={tone} />
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
              {hotel.source} · checked {hotel.checked} · beat {hotel.beat}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}

export function ModeCompareCard({ compare, tone, open = true }: { compare: ModeCompare; tone: Tone; open?: boolean }) {
  const s = toneStyles[tone];
  return (
    <div className={`overflow-hidden rounded-xl ${s.panel} ${s.panelRing}`}>
      <div className={`flex flex-wrap items-center justify-between gap-2 border-b px-3 py-2 ${s.divider}`}>
        <p className={`text-xs font-semibold ${s.heading}`}>{compare.subject}</p>
        <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold ${tone === "dark" ? "bg-emerald-400/15 text-emerald-300" : "bg-emerald-50 text-emerald-700"}`}>
          <Check size={10} aria-hidden /> {compare.chosen}
        </span>
      </div>
      {open && (
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
      )}
      <p className={`border-t px-3 py-2 text-[11px] leading-relaxed ${s.divider} ${s.body}`}>{compare.why}</p>
    </div>
  );
}

export function SavingsRow({ trip, tone, caption = false }: { trip: StageTrip; tone: Tone; caption?: boolean }) {
  const s = toneStyles[tone];
  return (
    <div className={`rounded-xl px-3.5 py-2.5 ${tone === "dark" ? "bg-emerald-400/10 ring-1 ring-emerald-400/30" : "bg-emerald-50 ring-1 ring-emerald-200"}`}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className={`text-[11px] font-bold uppercase ${tone === "dark" ? "text-emerald-300" : "text-emerald-700"}`}>Best total so far</span>
        <span className={`text-sm font-semibold line-through tabular-nums ${s.muted}`}>{trip.first}</span>
        <span className={`text-lg font-bold tabular-nums ${s.heading}`}>{trip.best}</span>
        <span className={`text-xs font-semibold ${tone === "dark" ? "text-emerald-300" : "text-emerald-700"}`}>saved {trip.saved}</span>
        <span className={`text-[11px] ${s.body}`}>{trip.sources}</span>
      </div>
      {caption && (
        <p className={`mt-1 text-[11px] ${s.body}`}>
          It started at {trip.first} and stopped falling at {trip.best}. The {trip.saved} came from a
          cheaper flight pairing, a re-priced stay and taking the train instead of the second flight.
        </p>
      )}
    </div>
  );
}

export function PriceTableLive({ trip, tone, compact = false }: { trip: StageTrip; tone: Tone; compact?: boolean }) {
  const s = toneStyles[tone];
  return (
    <div className={`overflow-hidden rounded-xl ${s.panel} ${s.panelRing}`}>
      <table className="w-full text-left">
        <caption className="sr-only">What the trip costs and where each price came from</caption>
        <thead>
          <tr className={`border-b ${s.divider}`}>
            <th scope="col" className={`px-3 py-2 text-[10px] font-bold uppercase ${s.muted}`}>Line</th>
            <th scope="col" className={`px-3 py-2 text-right text-[10px] font-bold uppercase ${s.muted}`}>Price</th>
            {!compact && <th scope="col" className={`px-3 py-2 text-[10px] font-bold uppercase ${s.muted}`}>Source · checked</th>}
            {!compact && <th scope="col" className={`px-3 py-2 text-[10px] font-bold uppercase ${s.muted}`}>What it beat</th>}
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
              {!compact && (
                <td className={`px-3 py-2 align-top text-[11px] ${s.body}`}>
                  {line.source}
                  <span className={`block ${s.muted}`}>{line.checked}</span>
                </td>
              )}
              {!compact && <td className={`px-3 py-2 align-top text-[11px] ${s.muted}`}>{line.beat}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ItineraryFull({ trip, tone }: { trip: StageTrip; tone: Tone }) {
  const s = toneStyles[tone];
  return (
    <div className="space-y-2">
      {trip.days.map((day) => (
        <article key={day.day} className={`rounded-xl p-3 ${s.panel} ${s.panelRing}`}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: day.color }} aria-hidden />
              <p className={`text-xs font-bold ${s.heading}`}>
                Day {day.day} · <span className={s.body}>{day.weekday} {day.date}</span>
              </p>
              <span className={`text-[11px] ${s.muted}`}>{day.city}</span>
            </div>
            <span className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-bold ${tone === "dark" ? "bg-violet-500/20 text-violet-200" : "bg-violet-50 text-violet-700"}`}>
              <BedDouble size={10} aria-hidden /> {day.hotel}
            </span>
          </div>
          <p className={`mt-0.5 text-[13px] font-semibold ${s.heading}`}>{day.title}</p>
          <div className="mt-1.5">
            <LegChips legs={day.legs} tone={tone} />
          </div>
          <ul className="mt-1.5">
            {day.stops.map((stop) => (
              <StopRow key={`${day.day}-${stop.time}`} stop={stop} color={day.color} tone={tone} detail />
            ))}
          </ul>
        </article>
      ))}
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

export function StaleNotice({ tone }: { tone: Tone }) {
  return (
    <p className={`flex items-start gap-1.5 rounded-lg px-3 py-2 text-[11px] leading-relaxed ${tone === "dark" ? "bg-amber-400/10 text-amber-200 ring-1 ring-amber-400/30" : "bg-amber-50 text-amber-800 ring-1 ring-amber-200"}`}>
      <TriangleAlert size={13} className="mt-0.5 shrink-0" aria-hidden />
      The Duffel quote is 22 minutes old and one hotel rate could not be re-checked. The page
      says so instead of showing a number it cannot defend.
    </p>
  );
}

export function StageControls({
  tone,
  running,
  onReplay,
  onFinish,
  skipLabel = "Show the finished plan",
}: {
  tone: Tone;
  running: boolean;
  onReplay: () => void;
  onFinish: () => void;
  skipLabel?: string;
}) {
  const base = tone === "dark"
    ? "bg-white/10 text-slate-200 hover:bg-white/20"
    : "bg-slate-100 text-slate-700 hover:bg-slate-200";
  return (
    <div className="flex items-center gap-1.5">
      {running && (
        <button type="button" onClick={onFinish} className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-semibold ${base}`}>
          <SkipForward size={11} aria-hidden /> {skipLabel}
        </button>
      )}
      <button type="button" onClick={onReplay} className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-semibold ${base}`}>
        <RotateCcw size={11} aria-hidden /> Replay
      </button>
    </div>
  );
}

export function BrowserFrame({ url, tone, children }: { url: string; tone: Tone; children: ReactNode }) {
  return (
    <div className={`overflow-hidden rounded-xl ${tone === "dark" ? "bg-[#0f1720] ring-1 ring-white/10" : "bg-slate-100 ring-1 ring-slate-200"}`}>
      <div className={`flex items-center gap-2 px-3 py-1.5 ${tone === "dark" ? "bg-white/5" : "bg-slate-200/70"}`}>
        <span className="flex gap-1" aria-hidden>
          <span className="h-2 w-2 rounded-full bg-rose-400" />
          <span className="h-2 w-2 rounded-full bg-amber-400" />
          <span className="h-2 w-2 rounded-full bg-emerald-400" />
        </span>
        <span className={`truncate rounded px-2 py-0.5 font-mono text-[10px] ${tone === "dark" ? "bg-black/40 text-slate-400" : "bg-white text-slate-500"}`}>{url}</span>
      </div>
      {children}
    </div>
  );
}

export function LinkPreview({ trip }: { trip: StageTrip }) {
  return (
    <div className="overflow-hidden rounded-xl bg-white ring-1 ring-slate-200">
      <div className="h-20 bg-[linear-gradient(120deg,#0f766e33,#e11d4866)]" aria-hidden />
      <div className="p-3">
        <p className="text-[10px] font-bold uppercase text-slate-400">{trip.shareUrl}</p>
        <p className="mt-0.5 text-sm font-semibold text-ink">{trip.title} · {trip.best}</p>
        <p className="mt-0.5 text-[11px] leading-relaxed text-slate-600">
          {trip.summary} · every price carries its source. Flights, rail, road and coach compared on
          each hop.
        </p>
      </div>
    </div>
  );
}

export function SignInCard({
  moment,
  tone,
}: {
  moment: { when: string; copy: string; risk: string };
  tone: Tone;
}) {
  const s = toneStyles[tone];
  return (
    <div className={`rounded-2xl p-4 ${s.panel} ${s.panelRing}`}>
      <p className={`flex items-center gap-1.5 text-sm font-semibold ${s.heading}`}>
        <UserRound size={15} aria-hidden /> Keep this trip
      </p>
      <p className={`mt-1 text-xs leading-relaxed ${s.body}`}>{moment.copy}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <span className="inline-flex items-center gap-1.5 rounded-xl bg-ink px-3 py-1.5 text-[13px] font-semibold text-white">
          Continue with Google <ArrowRight size={13} aria-hidden />
        </span>
        <span className={`inline-flex items-center rounded-xl px-3 py-1.5 text-[13px] font-semibold ${s.chip}`}>
          Stay a guest
        </span>
      </div>
      <p className={`mt-2 text-[11px] ${s.muted}`}>Asked {moment.when.toLowerCase()}.</p>
    </div>
  );
}

export function ShareBar({ trip, tone }: { trip: StageTrip; tone: Tone }) {
  const s = toneStyles[tone];
  return (
    <div className={`flex flex-wrap items-center gap-2 rounded-xl px-3 py-2 ${s.panel} ${s.panelRing}`}>
      <Link2 size={14} className={s.muted} aria-hidden />
      <span className={`min-w-0 flex-1 truncate font-mono text-[11px] ${s.body}`}>{trip.shareUrl}</span>
      <span className={`inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] font-semibold ${s.chip}`}>
        <Copy size={11} aria-hidden /> Copy link
      </span>
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

export function Composer({
  tone,
  value,
  placeholder,
  action,
  note,
  size = "lg",
}: {
  tone: Tone;
  value?: string;
  placeholder: string;
  action: string;
  note?: ReactNode;
  size?: "lg" | "sm";
}) {
  const s = toneStyles[tone];
  const tall = size === "lg";
  return (
    <div>
      <div className={`flex items-center gap-2 rounded-2xl px-3 ${tall ? "py-2.5" : "py-1.5"} ${s.fieldShell} shadow-card`}>
        <MapPin size={tall ? 18 : 15} className={s.muted} aria-hidden />
        <p className={`min-w-0 flex-1 truncate ${tall ? "text-[15px]" : "text-[13px]"} ${value ? s.fieldText : `${s.fieldText} opacity-60`}`}>
          {value || placeholder}
        </p>
        <span className={`inline-flex shrink-0 items-center gap-1.5 rounded-xl bg-brand px-3.5 ${tall ? "py-2" : "py-1.5"} text-[13px] font-semibold text-white`}>
          {action} <ArrowRight size={14} aria-hidden />
        </span>
      </div>
      {note && <p className={`mt-2 text-xs ${s.muted}`}>{note}</p>}
    </div>
  );
}

export function Crumb({ tone, children }: { tone: Tone; children: ReactNode }) {
  const s = toneStyles[tone];
  return (
    <p className={`flex items-center gap-1 text-[11px] ${s.muted}`}>
      <ChevronRight size={11} aria-hidden />
      {children}
    </p>
  );
}

export function Stat({ tone, label, value }: { tone: Tone; label: string; value: string }) {
  const s = toneStyles[tone];
  return (
    <div className={`rounded-xl px-3 py-2 ${s.panel} ${s.panelRing}`}>
      <p className={`text-[10px] font-bold uppercase ${s.muted}`}>{label}</p>
      <p className={`mt-0.5 text-sm font-semibold ${s.heading}`}>{value}</p>
    </div>
  );
}

export function ClockNote({ tone, children }: { tone: Tone; children: ReactNode }) {
  const s = toneStyles[tone];
  return (
    <p className={`flex items-center gap-1 text-[11px] ${s.muted}`}>
      <Clock3 size={11} aria-hidden /> {children}
    </p>
  );
}
