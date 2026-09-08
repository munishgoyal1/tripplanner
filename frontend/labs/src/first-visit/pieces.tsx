// Building blocks shared by all four first-visit options. Each block renders the same facts
// in a light or dark tone so option D can look completely different without inventing
// different promises.

import {
  ArrowRight,
  BedDouble,
  Camera,
  Check,
  Clock3,
  MapPin,
  Plane,
  ShieldCheck,
  Train,
  UtensilsCrossed,
} from "lucide-react";
import type { ReactNode } from "react";

import type { Stop, StopKind } from "../shared/tripFixture";
import {
  destinations,
  footerColumns,
  priceLines,
  product,
  proof,
  sampleDays,
  savings,
  trustPoints,
} from "./fixture";

export type Tone = "light" | "dark";

export const stopIcons: Record<StopKind, typeof MapPin> = {
  hotel: BedDouble,
  attraction: Camera,
  meal: UtensilsCrossed,
  transport: Train,
  flight: Plane,
  airport: Plane,
};

interface ToneStyle {
  page: string;
  panel: string;
  panelRing: string;
  heading: string;
  body: string;
  muted: string;
  chip: string;
  divider: string;
  accent: string;
  fieldShell: string;
  fieldText: string;
}

export const toneStyles: Record<Tone, ToneStyle> = {
  light: {
    page: "bg-white text-ink",
    panel: "bg-white",
    panelRing: "ring-1 ring-slate-200",
    heading: "text-ink",
    body: "text-slate-600",
    muted: "text-slate-400",
    chip: "bg-slate-100 text-slate-600",
    divider: "border-slate-200",
    accent: "text-brand",
    fieldShell: "bg-white ring-1 ring-slate-300",
    fieldText: "text-ink placeholder:text-slate-400",
  },
  dark: {
    page: "bg-[#080b11] text-white",
    panel: "bg-white/[0.04]",
    panelRing: "ring-1 ring-white/10",
    heading: "text-white",
    body: "text-slate-300",
    muted: "text-slate-500",
    chip: "bg-white/10 text-slate-200",
    divider: "border-white/10",
    accent: "text-emerald-300",
    fieldShell: "bg-white/[0.06] ring-1 ring-white/20",
    fieldText: "text-white placeholder:text-slate-500",
  },
};

export function Masthead({ tone, cta = "Sign in", links }: { tone: Tone; cta?: string; links: string[] }) {
  const s = toneStyles[tone];
  return (
    <header className={`flex items-center justify-between border-b px-6 py-3.5 ${s.divider}`}>
      <div className="flex items-center gap-2">
        <span className="grid h-7 w-7 place-items-center rounded-md bg-brand text-[13px] font-bold text-white">T</span>
        <span className={`display text-base font-semibold ${s.heading}`}>{product.name}</span>
      </div>
      <nav className="hidden items-center gap-5 md:flex" aria-label="Site">
        {links.map((link) => (
          <span key={link} className={`text-[13px] font-medium ${s.body}`}>{link}</span>
        ))}
      </nav>
      <div className="flex items-center gap-2">
        <span className={`hidden rounded-full px-2.5 py-1 text-[11px] font-semibold sm:inline ${s.chip}`}>{product.beta}</span>
        <span className={`rounded-full px-3 py-1.5 text-[13px] font-semibold ${tone === "dark" ? "bg-white text-ink" : "bg-ink text-white"}`}>{cta}</span>
      </div>
    </header>
  );
}

export function Composer({
  tone,
  size = "lg",
  value,
  placeholder,
  action = "Plan it",
  note,
}: {
  tone: Tone;
  size?: "lg" | "sm";
  value?: string;
  placeholder: string;
  action?: string;
  note?: ReactNode;
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
        <span className={`inline-flex items-center gap-1.5 rounded-xl bg-brand px-3.5 ${tall ? "py-2" : "py-1.5"} text-[13px] font-semibold text-white`}>
          {action} <ArrowRight size={14} aria-hidden />
        </span>
      </div>
      {note && <p className={`mt-2 text-xs ${s.muted}`}>{note}</p>}
    </div>
  );
}

export function PromptChips({ tone, prompts }: { tone: Tone; prompts: string[] }) {
  const s = toneStyles[tone];
  return (
    <div className="mt-3 flex flex-wrap gap-1.5">
      {prompts.map((prompt) => (
        <span key={prompt} className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${s.chip}`}>{prompt}</span>
      ))}
    </div>
  );
}

// A stylised Lisbon shape. It exists to prove the plan is geographic, not to be a map.
export function ProofMap({ tone, height = "h-44" }: { tone: Tone; height?: string }) {
  const pins = sampleDays[2].stops.filter((stop) => stop.planned).slice(0, 6);
  return (
    <div className={`relative overflow-hidden rounded-xl ${height} ${tone === "dark" ? "bg-[#0f1720]" : "bg-[#eef2f4]"}`}>
      <div className={`absolute inset-0 ${tone === "dark" ? "opacity-30" : "opacity-70"}`} aria-hidden>
        <div className="absolute left-0 top-1/2 h-16 w-full -rotate-6 bg-sky-300/50" />
        <div className="absolute left-1/4 top-0 h-full w-px bg-slate-400/40" />
        <div className="absolute left-2/3 top-0 h-full w-px bg-slate-400/40" />
        <div className="absolute left-0 top-1/4 h-px w-full bg-slate-400/40" />
      </div>
      {pins.map((pin, index) => (
        <span
          key={pin.id}
          className="absolute grid h-5 w-5 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full text-[10px] font-bold text-white shadow-pop"
          style={{ left: `${18 + index * 13}%`, top: `${30 + (index % 3) * 18}%`, backgroundColor: sampleDays[2].color }}
        >
          {pin.marker ?? index + 1}
        </span>
      ))}
      <span className={`absolute bottom-2 left-2 rounded-full px-2 py-0.5 text-[10px] font-semibold ${tone === "dark" ? "bg-black/60 text-slate-200" : "bg-white/85 text-slate-600"}`}>
        Day 3 · {sampleDays[2].route.distance} on foot
      </span>
    </div>
  );
}

export function StopRow({ stop, tone, color }: { stop: Stop; tone: Tone; color: string }) {
  const s = toneStyles[tone];
  const Icon = stopIcons[stop.kind];
  return (
    <li className="flex items-center gap-2 py-1">
      <span
        className="grid h-5 w-5 shrink-0 place-items-center rounded-full border text-[10px] font-bold"
        style={{ borderColor: color, color }}
      >
        {stop.marker ?? <Icon size={10} aria-hidden />}
      </span>
      <span className={`w-10 shrink-0 text-[11px] font-semibold tabular-nums ${s.muted}`}>{stop.time}</span>
      <span className={`min-w-0 flex-1 truncate text-xs font-medium ${s.heading}`}>{stop.name}</span>
      {stop.cost && <span className={`shrink-0 text-[11px] tabular-nums ${s.body}`}>{stop.cost}</span>}
    </li>
  );
}

export function DayCard({ dayIndex, tone, stops = 4 }: { dayIndex: number; tone: Tone; stops?: number }) {
  const s = toneStyles[tone];
  const day = sampleDays[dayIndex];
  return (
    <article className={`rounded-xl p-3 ${s.panel} ${s.panelRing}`}>
      <div className="flex items-baseline justify-between gap-2">
        <p className={`text-xs font-bold ${s.heading}`}>
          Day {day.day} · <span className={s.body}>{day.weekday} {day.date.replace(" 2026", "")}</span>
        </p>
        <span className={`text-[11px] ${s.muted}`}>{day.schedule.start}–{day.schedule.end}</span>
      </div>
      <p className={`mt-0.5 text-[13px] font-semibold ${s.heading}`}>{day.title}</p>
      <ul className="mt-1.5">
        {day.stops.filter((stop) => stop.planned).slice(0, stops).map((stop) => (
          <StopRow key={stop.id} stop={stop} tone={tone} color={day.color} />
        ))}
      </ul>
      <p className={`mt-1.5 flex items-center gap-1 text-[11px] ${s.muted}`}>
        <Clock3 size={11} aria-hidden /> {day.route.duration} moving · {day.route.distance} · {day.route.mode}
      </p>
    </article>
  );
}

export function PriceTable({ tone, compact = false }: { tone: Tone; compact?: boolean }) {
  const s = toneStyles[tone];
  return (
    <div className={`overflow-hidden rounded-xl ${s.panel} ${s.panelRing}`}>
      <table className="w-full text-left">
        <caption className="sr-only">What the sample trip costs and where each price came from</caption>
        <thead>
          <tr className={`border-b ${s.divider}`}>
            <th scope="col" className={`px-3 py-2 text-[10px] font-bold uppercase ${s.muted}`}>Line</th>
            <th scope="col" className={`px-3 py-2 text-right text-[10px] font-bold uppercase ${s.muted}`}>Price</th>
            {!compact && <th scope="col" className={`px-3 py-2 text-[10px] font-bold uppercase ${s.muted}`}>Source · checked</th>}
            {!compact && <th scope="col" className={`px-3 py-2 text-[10px] font-bold uppercase ${s.muted}`}>What it beat</th>}
          </tr>
        </thead>
        <tbody>
          {priceLines.map((line) => (
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
              {!compact && <td className={`px-3 py-2 align-top text-[11px] ${s.muted}`}>{line.alternative}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function SavingsBar({ tone }: { tone: Tone }) {
  const s = toneStyles[tone];
  return (
    <div className={`flex flex-wrap items-center gap-x-4 gap-y-1.5 rounded-xl px-3.5 py-2.5 ${tone === "dark" ? "bg-emerald-400/10 ring-1 ring-emerald-400/30" : "bg-emerald-50 ring-1 ring-emerald-200"}`}>
      <span className={`text-[11px] font-bold uppercase ${tone === "dark" ? "text-emerald-300" : "text-emerald-700"}`}>Best total so far</span>
      <span className={`text-sm font-semibold line-through tabular-nums ${s.muted}`}>{savings.first}</span>
      <span className={`text-lg font-bold tabular-nums ${s.heading}`}>{savings.best}</span>
      <span className={`text-xs font-semibold ${tone === "dark" ? "text-emerald-300" : "text-emerald-700"}`}>saved {savings.saved}</span>
      <span className={`text-[11px] ${s.body}`}>{savings.sources} · {proof.pricesCheckedAt}</span>
    </div>
  );
}

export function TrustList({ tone, columns = 2 }: { tone: Tone; columns?: number }) {
  const s = toneStyles[tone];
  return (
    <ul className={`grid gap-2 ${columns === 2 ? "sm:grid-cols-2" : ""}`}>
      {trustPoints.map((point) => (
        <li key={point} className={`flex gap-2 text-xs leading-relaxed ${s.body}`}>
          <ShieldCheck size={14} className={`mt-0.5 shrink-0 ${s.accent}`} aria-hidden />
          {point}
        </li>
      ))}
    </ul>
  );
}

export function DestinationGrid({ tone, count = 6 }: { tone: Tone; count?: number }) {
  const s = toneStyles[tone];
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {destinations.slice(0, count).map((destination, index) => (
        <article key={destination.city} className={`overflow-hidden rounded-xl ${s.panel} ${s.panelRing}`}>
          <div
            className="h-24"
            style={{
              background: `linear-gradient(135deg, ${["#f43f5e", "#0f766e", "#b45309", "#6d28d9", "#0369a1", "#be123c"][index % 6]}33, ${["#fb7185", "#14b8a6", "#f59e0b", "#8b5cf6", "#0ea5e9", "#f43f5e"][index % 6]}88)`,
            }}
            aria-hidden
          />
          <div className="p-3">
            <p className={`text-sm font-semibold ${s.heading}`}>{destination.city}</p>
            <p className={`text-[11px] ${s.muted}`}>{destination.country} · {destination.days} · {destination.from}</p>
            <p className={`mt-1.5 text-xs leading-relaxed ${s.body}`}>{destination.why}</p>
          </div>
        </article>
      ))}
    </div>
  );
}

export function SiteFooter({ tone }: { tone: Tone }) {
  const s = toneStyles[tone];
  return (
    <footer className={`border-t px-6 py-6 ${s.divider}`}>
      <div className="grid gap-5 sm:grid-cols-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="grid h-6 w-6 place-items-center rounded-md bg-brand text-[11px] font-bold text-white">T</span>
            <span className={`display text-sm font-semibold ${s.heading}`}>{product.name}</span>
          </div>
          <p className={`mt-2 text-[11px] leading-relaxed ${s.muted}`}>
            A planner for people who would rather travel than research. {product.beta}.
          </p>
        </div>
        {footerColumns.map((column) => (
          <div key={column.title}>
            <p className={`text-[10px] font-bold uppercase ${s.muted}`}>{column.title}</p>
            <ul className="mt-1.5 space-y-1">
              {column.links.map((link) => (
                <li key={link} className={`text-[12px] ${s.body}`}>{link}</li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <p className={`mt-5 border-t pt-3 text-[11px] ${s.divider} ${s.muted}`}>
        © 2026 Tripplanner · We never hold your card and never charge you. Bookings complete on the provider's own site.
      </p>
    </footer>
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

export function CheckLine({ tone, children }: { tone: Tone; children: ReactNode }) {
  const s = toneStyles[tone];
  return (
    <li className={`flex gap-2 text-xs leading-relaxed ${s.body}`}>
      <Check size={13} className={`mt-0.5 shrink-0 ${s.accent}`} aria-hidden />
      {children}
    </li>
  );
}
