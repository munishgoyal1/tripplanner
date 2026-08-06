import { useMemo, useState } from "react";
import {
  AlertTriangle,
  BedDouble,
  Camera,
  Car,
  Check,
  ChevronDown,
  ListChecks,
  MapPin,
  MessageSquare,
  Plane,
  Route,
  ShieldAlert,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Undo2,
  Utensils,
  X,
} from "lucide-react";
import { DESTINATION, dayMeta, declaredRules } from "./fixture";
import type { Stop, StopKind } from "./fixture";
import {
  diffStops,
  fmtMin,
  scenarios,
  sortStops,
  startingTrip,
  toMin,
  validate,
} from "./planEngine";
import type { Change, Proposal } from "./planEngine";

export type AgencyOption = "proposal" | "guarded" | "console" | "today";
export type Channel = "chat" | "map" | "itinerary" | "details";

const kindIcon: Record<StopKind, typeof Camera> = {
  flight: Plane,
  stay: BedDouble,
  transfer: Car,
  attraction: Camera,
  meal: Utensils,
};

const channelMeta: Record<Channel, { label: string; Icon: typeof Camera }> = {
  chat: { label: "Chat", Icon: MessageSquare },
  map: { label: "Map", Icon: MapPin },
  itinerary: { label: "Itinerary", Icon: ListChecks },
  details: { label: "Details", Icon: SlidersHorizontal },
};

interface Receipt {
  id: string;
  intent: string;
  changes: Change[];
  why: string[];
  before: Stop[];
  channel: Channel;
}

interface Message { role: "owner" | "agent"; text: string }

/* --------------------------------- map ------------------------------------- */

function MiniMap({ stops, highlight, selected, onSelect }: {
  stops: Stop[];
  highlight: Set<string>;
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const points = stops.filter((stop) => stop.kind !== "flight");
  const lats = points.map((stop) => stop.lat);
  const lngs = points.map((stop) => stop.lng);
  const minLat = Math.min(...lats);
  const maxLat = Math.max(...lats);
  const minLng = Math.min(...lngs);
  const maxLng = Math.max(...lngs);
  const spanLat = Math.max(maxLat - minLat, 0.01);
  const spanLng = Math.max(maxLng - minLng, 0.01);
  const project = (stop: Stop) => ({
    x: 6 + ((stop.lng - minLng) / spanLng) * 88,
    y: 92 - ((stop.lat - minLat) / spanLat) * 84,
  });

  return (
    <div className="relative h-full w-full overflow-hidden bg-[radial-gradient(circle_at_30%_20%,#ecfeff_0,#f1f5f9_60%,#e2e8f0_100%)]">
      <svg className="absolute inset-0 h-full w-full" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
        {dayMeta.map((meta) => {
          const dayPoints = points.filter((stop) => stop.day === meta.day).map(project);
          if (dayPoints.length < 2) return null;
          return (
            <polyline
              key={meta.day}
              points={dayPoints.map((point) => `${point.x},${point.y}`).join(" ")}
              fill="none"
              stroke={meta.color}
              strokeWidth={1.4}
              strokeLinecap="round"
              strokeLinejoin="round"
              opacity={0.65}
              vectorEffect="non-scaling-stroke"
            />
          );
        })}
      </svg>
      {points.map((stop) => {
        const point = project(stop);
        const meta = dayMeta.find((entry) => entry.day === stop.day)!;
        const index = points.filter((entry) => entry.day === stop.day).indexOf(stop) + 1;
        const isNew = highlight.has(stop.id);
        return (
          <button
            key={stop.id}
            type="button"
            onClick={() => onSelect(stop.id)}
            title={`${stop.title} · day ${stop.day} ${stop.start}`}
            className={`absolute grid h-6 w-6 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border-2 border-white text-[10px] font-bold text-white shadow-card transition ${
              selected === stop.id ? "scale-125 ring-2 ring-ink/60" : "hover:scale-110"
            } ${isNew ? "animate-pulse ring-2 ring-brand" : ""}`}
            style={{ left: `${point.x}%`, top: `${point.y}%`, backgroundColor: meta.color }}
          >
            {index}
          </button>
        );
      })}
    </div>
  );
}

/* ------------------------------ agency card -------------------------------- */

function StatusChip({ status }: { status: Proposal["status"] }) {
  const map = {
    ready: { text: "Ready to apply", className: "bg-emerald-50 text-emerald-700 ring-emerald-200", Icon: ShieldCheck },
    "needs-consent": { text: "Needs your word", className: "bg-amber-50 text-amber-700 ring-amber-200", Icon: AlertTriangle },
    blocked: { text: "Blocked", className: "bg-rose-50 text-rose-700 ring-rose-200", Icon: ShieldAlert },
  } as const;
  const entry = map[status];
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ring-1 ${entry.className}`}>
      <entry.Icon size={11} aria-hidden /> {entry.text}
    </span>
  );
}

function ProposalCard({ proposal, option, onApply, onCancel, onPick }: {
  proposal: Proposal;
  option: AgencyOption;
  onApply: () => void;
  onCancel: () => void;
  onPick: (index: number) => void;
}) {
  const [showRejected, setShowRejected] = useState(false);
  const naiveStop = proposal.naive.stops.find((stop) => stop.id === "patalpani");

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-3.5 shadow-pop">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[10px] font-bold uppercase text-brand">{proposal.operation}</p>
          <p className="display truncate text-sm font-semibold text-ink">{proposal.intent}</p>
        </div>
        <StatusChip status={proposal.status} />
      </div>

      <p className="mt-2 text-xs leading-relaxed text-slate-600">{proposal.narration}</p>

      {proposal.chosen && (
        <div className="mt-3 rounded-xl bg-accent-50 p-3 ring-1 ring-accent/20">
          <p className="text-[10px] font-bold uppercase text-accent">Chosen slot</p>
          <p className="mt-0.5 text-sm font-semibold text-ink">
            Day {proposal.chosen.day} · {proposal.chosen.time}
          </p>
          <ul className="mt-1.5 space-y-1">
            {proposal.chosen.reasons.map((reason) => (
              <li key={reason} className="flex gap-1.5 text-[11px] leading-relaxed text-slate-600">
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-accent" aria-hidden />
                {reason}
              </li>
            ))}
          </ul>
        </div>
      )}

      {proposal.alternatives.length > 0 && (
        <div className="mt-2.5">
          <p className="text-[10px] font-bold uppercase text-slate-400">Instead of that</p>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {proposal.alternatives.map((alternative, index) => (
              <button
                key={`${alternative.day}-${alternative.time}`}
                type="button"
                onClick={() => onPick(index)}
                className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-semibold text-slate-700 transition hover:bg-slate-200"
              >
                Day {alternative.day} · {alternative.time}
                {alternative.adjustment ? " (with one move)" : ""}
              </button>
            ))}
          </div>
        </div>
      )}

      {proposal.collateral.length > 0 && (
        <div className="mt-2.5 rounded-xl bg-rose-50 p-3 ring-1 ring-rose-200">
          <p className="flex items-center gap-1.5 text-[10px] font-bold uppercase text-rose-700">
            <ShieldAlert size={12} aria-hidden /> Outside this change's blast radius
          </p>
          <p className="mt-1 text-[11px] text-rose-800">
            This operation declared it may touch {proposal.blastRadius.join(" and ")}. The naive rewrite also:
          </p>
          <ul className="mt-1 space-y-0.5">
            {proposal.collateral.map((change) => (
              <li key={change.id} className="text-[11px] font-semibold text-rose-800">
                {change.verb} {change.title} — {change.detail}
              </li>
            ))}
          </ul>
          <p className="mt-1.5 text-[11px] text-rose-700">Refused. Your return leg stays.</p>
        </div>
      )}

      {proposal.consent.length > 0 && (
        <div className="mt-2.5 rounded-xl bg-amber-50 p-3 ring-1 ring-amber-200">
          <p className="text-[10px] font-bold uppercase text-amber-700">Consequences you should know</p>
          <ul className="mt-1 space-y-1">
            {proposal.consent.map((item) => (
              <li key={item} className="flex gap-1.5 text-[11px] leading-relaxed text-amber-900">
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-amber-500" aria-hidden />
                {item}
              </li>
            ))}
          </ul>
        </div>
      )}

      {proposal.rejected.length > 0 && (
        <div className="mt-2.5">
          <button
            type="button"
            onClick={() => setShowRejected((value) => !value)}
            className="inline-flex items-center gap-1 text-[11px] font-semibold text-slate-500 hover:text-ink"
          >
            <ChevronDown size={12} className={showRejected ? "rotate-180 transition" : "transition"} aria-hidden />
            {proposal.rejected.length} slots ruled out
          </button>
          {showRejected && (
            <ul className="mt-1.5 space-y-1 rounded-xl bg-slate-50 p-2.5 ring-1 ring-slate-200">
              {proposal.rejected.map((rejection, index) => (
                <li key={`${rejection.day}-${rejection.window}-${index}`} className="text-[11px] leading-relaxed text-slate-600">
                  <span className="font-semibold text-ink">Day {rejection.day} {rejection.window}</span>
                  <span className="ml-1.5 rounded bg-white px-1 py-px font-mono text-[9px] font-bold text-slate-500 ring-1 ring-slate-200">
                    {rejection.code}
                  </span>{" "}
                  {rejection.message}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {naiveStop && (
        <p className="mt-2.5 rounded-xl bg-slate-900 p-2.5 text-[11px] leading-relaxed text-slate-300">
          Today's planner answers day {naiveStop.day} at {naiveStop.start} — after your {fmtMin(toMin("15:40") + 115)} landing in
          Bengaluru — because it scores days on route length and load only.
        </p>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={onApply}
          disabled={proposal.status === "blocked"}
          className="inline-flex h-8 items-center gap-1.5 rounded-full bg-brand px-3.5 text-xs font-semibold text-white transition hover:bg-brand-600 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          <Check size={13} aria-hidden />
          {proposal.status === "needs-consent" ? "Apply the safe version" : "Apply"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="inline-flex h-8 items-center gap-1.5 rounded-full bg-white px-3 text-xs font-semibold text-slate-600 ring-1 ring-slate-200 transition hover:ring-slate-300"
        >
          <X size={13} aria-hidden /> Cancel
        </button>
        {option === "guarded" && (
          <span className="text-[10px] font-medium text-slate-400">Stopped here because a rule was at risk</span>
        )}
      </div>
    </div>
  );
}

function ReceiptCard({ receipt, onUndo }: { receipt: Receipt; onUndo: () => void }) {
  const [showWhy, setShowWhy] = useState(false);
  return (
    <div className="rounded-2xl border border-emerald-200 bg-emerald-50/70 p-3 shadow-card">
      <div className="flex items-start justify-between gap-2">
        <p className="flex items-center gap-1.5 text-[10px] font-bold uppercase text-emerald-700">
          <ShieldCheck size={12} aria-hidden /> Applied · {channelMeta[receipt.channel].label}
        </p>
        <button
          type="button"
          onClick={onUndo}
          className="inline-flex items-center gap-1 rounded-full bg-white px-2 py-0.5 text-[11px] font-semibold text-slate-600 ring-1 ring-slate-200 transition hover:ring-slate-300"
        >
          <Undo2 size={11} aria-hidden /> Undo
        </button>
      </div>
      <p className="mt-1 text-sm font-semibold text-ink">{receipt.intent}</p>
      <ul className="mt-1.5 space-y-0.5">
        {receipt.changes.map((change) => (
          <li key={`${change.id}-${change.verb}`} className="text-[11px] text-slate-700">
            <span className="font-semibold capitalize text-ink">{change.verb}</span> {change.title}{" "}
            <span className="text-slate-500">({change.detail})</span>
          </li>
        ))}
      </ul>
      {receipt.why.length > 0 && (
        <>
          <button
            type="button"
            onClick={() => setShowWhy((value) => !value)}
            className="mt-1.5 inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-800 hover:text-emerald-900"
          >
            <ChevronDown size={12} className={showWhy ? "rotate-180 transition" : "transition"} aria-hidden /> Why here
          </button>
          {showWhy && (
            <ul className="mt-1 space-y-0.5">
              {receipt.why.map((reason) => (
                <li key={reason} className="text-[11px] leading-relaxed text-emerald-900">· {reason}</li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

/* ------------------------------- workspace --------------------------------- */

export function AgenticWorkspace({ option, channel, onChannelChange }: {
  option: AgencyOption;
  channel: Channel;
  onChannelChange: (next: Channel) => void;
}) {
  const [stops, setStops] = useState<Stop[]>(startingTrip);
  const [pending, setPending] = useState<Proposal | null>(null);
  const [receipts, setReceipts] = useState<Receipt[]>([]);
  const [highlight, setHighlight] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([
    { role: "agent", text: `Your ${DESTINATION} trip is loaded. Ask for a change from any pane.` },
  ]);

  const violations = useMemo(() => validate(stops), [stops]);
  const latestReceipt = receipts[0] ?? null;

  const reset = () => {
    setStops(startingTrip);
    setPending(null);
    setReceipts([]);
    setHighlight(new Set());
    setMessages([{ role: "agent", text: `Your ${DESTINATION} trip is loaded. Ask for a change from any pane.` }]);
  };

  const commit = (proposal: Proposal, source: Stop[]) => {
    const after = proposal.apply(source);
    const changes = diffStops(source, after);
    setStops(after);
    setHighlight(new Set(changes.map((change) => change.id)));
    setReceipts((current) => [
      {
        id: `${proposal.operation}-${current.length}`,
        intent: proposal.intent,
        changes,
        why: proposal.chosen?.reasons ?? proposal.consent,
        before: source,
        channel,
      },
      ...current,
    ]);
    setPending(null);
    setMessages((current) => [
      ...current,
      { role: "agent", text: `${proposal.narration} Applied, with an undo on the receipt.` },
    ]);
  };

  const run = (scenarioId: string) => {
    const scenario = scenarios.find((entry) => entry.id === scenarioId)!;
    const proposal = scenario.build(stops);
    setMessages((current) => [...current, { role: "owner", text: scenario.label }]);

    if (option === "today") {
      const after = sortStops(proposal.naive.stops);
      const changes = diffStops(stops, after);
      setStops(after);
      setHighlight(new Set(changes.filter((change) => change.verb !== "removed").map((change) => change.id)));
      setMessages((current) => [
        ...current,
        {
          role: "agent",
          text:
            proposal.operation === "placeStop"
              ? "Done. I added it to the best day for your route."
              : "Done. I updated your Indore hotel to a 3-star.",
        },
      ]);
      return;
    }

    if (option === "proposal" || proposal.status !== "ready") {
      setPending(proposal);
      setMessages((current) => [...current, { role: "agent", text: proposal.narration }]);
      return;
    }
    commit(proposal, stops);
  };

  const pickAlternative = (index: number) => {
    if (!pending?.alternatives[index]) return;
    const alternative = pending.alternatives[index];
    setPending({
      ...pending,
      chosen: alternative,
      alternatives: [pending.chosen!, ...pending.alternatives.filter((_, i) => i !== index)].filter(Boolean),
      consent: alternative.adjustment ? [alternative.adjustment] : [],
      status: alternative.adjustment ? "needs-consent" : "ready",
    });
  };

  const undo = (receipt: Receipt) => {
    setStops(receipt.before);
    setReceipts((current) => current.filter((entry) => entry.id !== receipt.id));
    setHighlight(new Set());
    setMessages((current) => [...current, { role: "agent", text: `Reverted: ${receipt.intent}.` }]);
  };

  const agency =
    pending !== null ? (
      <ProposalCard
        proposal={pending}
        option={option}
        onApply={() => commit(pending, stops)}
        onCancel={() => {
          setPending(null);
          setMessages((current) => [...current, { role: "agent", text: "Cancelled. Nothing was written." }]);
        }}
        onPick={pickAlternative}
      />
    ) : latestReceipt && option !== "today" ? (
      <ReceiptCard receipt={latestReceipt} onUndo={() => undo(latestReceipt)} />
    ) : null;

  const slotFor = (target: Channel) => (channel === target ? agency : null);

  return (
    <div className="flex h-full flex-col bg-surface">
      {/* Lab harness. Not part of the proposed product chrome. */}
      <div className="flex flex-wrap items-center gap-2 border-b border-dashed border-slate-300 bg-slate-100/80 px-3 py-2">
        <span className="text-[10px] font-bold uppercase text-slate-500">Run from</span>
        <div className="flex rounded-full bg-white p-0.5 ring-1 ring-slate-200">
          {(Object.keys(channelMeta) as Channel[]).map((entry) => {
            const { label, Icon } = channelMeta[entry];
            return (
              <button
                key={entry}
                type="button"
                onClick={() => onChannelChange(entry)}
                aria-pressed={channel === entry}
                className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-semibold transition ${
                  channel === entry ? "bg-ink text-white" : "text-slate-600 hover:bg-slate-100"
                }`}
              >
                <Icon size={11} aria-hidden /> {label}
              </button>
            );
          })}
        </div>
        {scenarios.map((scenario) => (
          <button
            key={scenario.id}
            type="button"
            onClick={() => run(scenario.id)}
            title={scenario.detail}
            className="rounded-full bg-white px-2.5 py-1 text-[11px] font-semibold text-slate-700 ring-1 ring-slate-200 transition hover:ring-brand"
          >
            {scenario.label}
          </button>
        ))}
        <button
          type="button"
          onClick={reset}
          className="ml-auto rounded-full px-2.5 py-1 text-[11px] font-semibold text-slate-500 transition hover:text-ink"
        >
          Reset trip
        </button>
      </div>

      <div className="flex h-12 shrink-0 items-center gap-3 border-b border-slate-200 bg-white px-3">
        <Sparkles size={15} className="text-brand" aria-hidden />
        <div className="min-w-0">
          <p className="display truncate text-sm font-semibold text-ink">Indore, Madhya Pradesh</p>
          <p className="truncate text-[10px] text-slate-500">5–9 Nov 2026 · 2 travelers · ₹78,600</p>
        </div>
        {option !== "today" && (
          <span
            className={`ml-auto inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ring-1 ${
              violations.length === 0
                ? "bg-emerald-50 text-emerald-700 ring-emerald-200"
                : "bg-rose-50 text-rose-700 ring-rose-200"
            }`}
          >
            {violations.length === 0 ? <ShieldCheck size={11} aria-hidden /> : <ShieldAlert size={11} aria-hidden />}
            {violations.length === 0 ? "Plan is sound" : `${violations.length} rule breaks`}
          </span>
        )}
      </div>

      <div className="flex min-h-0 flex-1">
        <section className="flex min-w-0 flex-1 flex-col">
          <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
            {slotFor("itinerary") && <div className="mb-3">{slotFor("itinerary")}</div>}
            {dayMeta.map((meta) => {
              const dayStops = stops.filter((stop) => stop.day === meta.day);
              return (
                <div key={meta.day} className="mb-3">
                  <div className="flex items-center gap-2">
                    <span
                      className="grid h-6 w-6 place-items-center rounded-lg text-[11px] font-bold text-white"
                      style={{ backgroundColor: meta.color }}
                    >
                      {meta.day}
                    </span>
                    <p className="text-[10px] font-bold uppercase text-slate-400">
                      {meta.weekday} · {meta.date}
                    </p>
                    <span className="text-[10px] text-slate-400">{dayStops.length} stops</span>
                  </div>
                  <ol className="mt-1.5 space-y-1">
                    {dayStops.map((stop) => {
                      const Icon = kindIcon[stop.kind];
                      const isNew = highlight.has(stop.id);
                      const broken = violations.some((violation) => violation.stopId === stop.id);
                      return (
                        <li
                          key={stop.id}
                          className={`flex items-center gap-2 rounded-xl px-2.5 py-2 shadow-card ring-1 transition ${
                            broken
                              ? "bg-rose-50 ring-rose-300"
                              : isNew
                                ? "bg-brand-50 ring-brand/40"
                                : "bg-white ring-slate-200/70"
                          }`}
                        >
                          <span className="w-10 shrink-0 text-[11px] font-semibold tabular-nums text-slate-500">
                            {stop.start}
                          </span>
                          <Icon size={13} className="shrink-0 text-slate-400" aria-hidden />
                          <span className="min-w-0 flex-1 truncate text-xs font-semibold text-ink">{stop.title}</span>
                          {stop.locked && (
                            <span className="shrink-0 rounded bg-slate-100 px-1 py-px text-[9px] font-bold uppercase text-slate-500">
                              anchor
                            </span>
                          )}
                          {broken && <AlertTriangle size={12} className="shrink-0 text-rose-600" aria-hidden />}
                        </li>
                      );
                    })}
                  </ol>
                </div>
              );
            })}
          </div>

          <div className="shrink-0 border-t border-slate-200 bg-white px-3 py-2.5">
            {slotFor("chat") && <div className="mb-2">{slotFor("chat")}</div>}
            <div className="max-h-24 space-y-1 overflow-y-auto">
              {messages.slice(-4).map((message, index) => (
                <p
                  key={`${message.role}-${index}`}
                  className={`text-[11px] leading-relaxed ${
                    message.role === "owner" ? "font-semibold text-ink" : "text-slate-600"
                  }`}
                >
                  {message.role === "owner" ? "You: " : "Planner: "}
                  {message.text}
                </p>
              ))}
            </div>
            <div className="mt-2 flex h-8 items-center gap-2 rounded-full bg-slate-100 px-3 text-[11px] text-slate-400">
              <MessageSquare size={12} aria-hidden /> Ask the planner…
            </div>
          </div>
        </section>

        <aside className="hidden w-[19rem] shrink-0 flex-col border-l border-slate-200 lg:flex">
          <div className="min-h-0 flex-1">
            <MiniMap stops={stops} highlight={highlight} selected={selected} onSelect={setSelected} />
          </div>
          {slotFor("map") && (
            <div className="max-h-[60%] overflow-y-auto border-t border-slate-200 bg-white p-2.5">{slotFor("map")}</div>
          )}
        </aside>

        <aside className="hidden w-[20rem] shrink-0 flex-col overflow-y-auto border-l border-slate-200 bg-white xl:flex">
          {option === "console" ? (
            <div className="p-3">
              <p className="text-[10px] font-bold uppercase text-brand">Your rules</p>
              <ul className="mt-1.5 space-y-1">
                {declaredRules.map((rule) => (
                  <li key={rule.id} className="rounded-lg bg-slate-50 px-2.5 py-1.5 ring-1 ring-slate-200">
                    <p className="text-[11px] font-semibold text-ink">{rule.label}</p>
                    <p className="text-[10px] text-slate-500">{rule.detail}</p>
                  </li>
                ))}
              </ul>

              <p className="mt-3 text-[10px] font-bold uppercase text-brand">Plan integrity</p>
              {violations.length === 0 ? (
                <p className="mt-1 text-[11px] text-emerald-700">All eight invariants hold.</p>
              ) : (
                <ul className="mt-1 space-y-1">
                  {violations.slice(0, 4).map((violation, index) => (
                    <li key={`${violation.code}-${index}`} className="rounded-lg bg-rose-50 px-2.5 py-1.5 text-[11px] text-rose-800 ring-1 ring-rose-200">
                      <span className="font-mono text-[9px] font-bold">{violation.code}</span> {violation.message}
                    </li>
                  ))}
                </ul>
              )}

              <p className="mt-3 text-[10px] font-bold uppercase text-brand">Change ledger</p>
              {receipts.length === 0 ? (
                <p className="mt-1 text-[11px] text-slate-500">Nothing changed yet.</p>
              ) : (
                <div className="mt-1.5 space-y-2">
                  {receipts.map((receipt) => (
                    <ReceiptCard key={receipt.id} receipt={receipt} onUndo={() => undo(receipt)} />
                  ))}
                </div>
              )}
              {slotFor("details") && <div className="mt-3">{slotFor("details")}</div>}
            </div>
          ) : (
            <div className="p-3">
              <p className="text-[10px] font-bold uppercase text-brand">Details</p>
              <p className="mt-1 text-[11px] leading-relaxed text-slate-600">
                {selected
                  ? stops.find((stop) => stop.id === selected)?.title
                  : "Select a pin or a row to edit it here. Edits made here go through the same engine as chat."}
              </p>
              {selected && (
                <div className="mt-2 rounded-xl bg-slate-50 p-2.5 text-[11px] text-slate-600 ring-1 ring-slate-200">
                  {(() => {
                    const stop = stops.find((entry) => entry.id === selected);
                    if (!stop) return null;
                    return (
                      <>
                        <p>Day {stop.day} · {stop.start} · {stop.durationMin} min</p>
                        {stop.openFrom && <p className="mt-0.5">Open {stop.openFrom}–{stop.openTo}</p>}
                        {stop.ref && <p className="mt-0.5">{stop.ref}</p>}
                        {stop.note && <p className="mt-0.5 text-slate-500">{stop.note}</p>}
                      </>
                    );
                  })()}
                </div>
              )}
              {slotFor("details") && <div className="mt-3">{slotFor("details")}</div>}
              {option !== "today" && receipts.length > 0 && channel !== "details" && (
                <>
                  <p className="mt-3 flex items-center gap-1.5 text-[10px] font-bold uppercase text-brand">
                    <Route size={11} aria-hidden /> Recent changes
                  </p>
                  <div className="mt-1.5 space-y-2">
                    {receipts.map((receipt) => (
                      <ReceiptCard key={receipt.id} receipt={receipt} onUndo={() => undo(receipt)} />
                    ))}
                  </div>
                </>
              )}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
