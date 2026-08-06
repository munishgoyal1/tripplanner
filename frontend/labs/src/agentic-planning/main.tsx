import React, { useCallback, useState } from "react";
import ReactDOM from "react-dom/client";
import { ArrowLeft, Maximize2, ShieldCheck, Workflow } from "lucide-react";
import "../../../src/index.css";
import { DecisionCapture } from "../shared/DecisionCapture";
import { LabNavigation } from "../shared/LabNavigation";
import { LabScope } from "../shared/LabScope";
import { OptionContrast } from "../shared/OptionContrast";
import "../shared/experiment-layout.css";
import { AgenticWorkspace } from "./AgenticWorkspace";
import type { AgencyOption, Channel } from "./AgenticWorkspace";
import { dayScores, invariants, startingTrip } from "./planEngine";

const LAB_ID = "agentic-planning";

const variants: Array<{ id: AgencyOption; label: string; summary: string; delta: string }> = [
  {
    id: "guarded",
    label: "B · Guarded autonomy",
    summary:
      "Safe changes apply immediately with an inline receipt carrying Undo and a why-here disclosure. Anything that breaks an invariant, or reaches outside its declared blast radius, hard-stops into a proposal instead.",
    delta: "Keeps the speed of today for ordinary edits and makes the dangerous class impossible.",
  },
  {
    id: "proposal",
    label: "A · Proposal first",
    summary:
      "Every non-trivial change comes back as a proposal in the pane you asked from: the slot it chose, why that slot, what else it touches, and the alternatives. Nothing is written until you apply.",
    delta: "Highest trust, zero silent damage. Costs one extra interaction on changes that were always safe.",
  },
  {
    id: "console",
    label: "C · Plan console",
    summary:
      "A standing rail holds the rules you declared, the live status of every invariant, and a chronological ledger of changes with per-entry revert. The agent negotiates against rules you can read.",
    delta: "Best for a long trip you keep editing. Costs a permanent 20rem rail.",
  },
];

const defects = [
  {
    title: "A new attraction landed after the departure flight",
    observed:
      "Asked to add an attraction on the best day. It was appended to the last day, after the flight home had already landed in Bengaluru.",
    cause:
      "_place_selected_stop scores days as route_km × 2.5 + stops × 18 + minutes × 0.35, then subtracts 30 for a near-empty day. A departure day is the lightest day of any trip, so it wins. _closest_insert_index then returns len(stops) whenever the new place has no cached coordinates, which appends after the flight, and _infer_stop_time sets the clock to the previous stop plus two hours.",
    missing: "There is no trip envelope, no notion of which city you are in at a given minute, and no anchor concept anywhere in the placement path.",
  },
  {
    title: "Changing the hotel deleted the return flight, silently",
    observed:
      "Asked to move the Indore stay to a 3-star. The stay changed, and the Bengaluru return connection disappeared with no mention of it.",
    cause:
      "_rebalance_day calls _remove_candidate whenever a day looks packed. That helper only protects stops that are already booked or whose kind is outside attraction and other, so a connection stored as other is a legal deletion target.",
    missing: "No operation declares what it is allowed to touch, so nothing can tell an intended edit from collateral damage.",
  },
];

const layers = [
  {
    step: "1 · Intent",
    owner: "Model",
    text: "Turn a sentence, a map click, a drag or a details edit into one typed operation with arguments. This is the only place the model is trusted.",
  },
  {
    step: "2 · Resolve",
    owner: "Engine",
    text: "Bind names to real entities and coordinates. An unresolved place fails here instead of silently defaulting to the end of a day.",
  },
  {
    step: "3 · Plan",
    owner: "Engine",
    text: "Enumerate every legal window across the trip, score each on detour, load, opening hours and slack, and keep the reasons attached to the score.",
  },
  {
    step: "4 · Validate",
    owner: "Engine",
    text: "Run all eight invariants over the candidate result. A hard break is not a warning, it removes the candidate.",
  },
  {
    step: "5 · Blast radius",
    owner: "Engine",
    text: "Diff the candidate against the entities the operation declared. Anything else is collateral, and collateral is refused or escalated, never applied.",
  },
  {
    step: "6 · Explain",
    owner: "Model",
    text: "Narrate the engine's decision in the owner's language. The model may describe the outcome; it may not change it.",
  },
];

const requirements = [
  "Every applied change produces a receipt naming what moved, what it cost, and how to revert it.",
  "A change may only touch the entities its operation declared; everything else is refused or escalated for consent.",
  "A refused or escalated change must state which rule stopped it, in words, not a code.",
  "Chat, map, itinerary and details all issue the same typed operation and get the same verdict.",
  "Anchors — booked flights and stays — change only through their own operation.",
  "Rejected slots stay inspectable, so the owner can see the reasoning rather than trust it.",
  "Undo restores the exact prior state, including entities the change moved rather than created.",
];

const criteria = [
  { title: "Silent damage", detail: "Can any single request still change something the owner did not name?" },
  { title: "Placement quality", detail: "Is the chosen slot the one a careful human would pick, and is the reason legible?" },
  { title: "Speed on safe edits", detail: "How much friction is added to the ordinary change that was never risky?" },
  { title: "Recoverability", detail: "After three changes, can the owner see and undo exactly the one that was wrong?" },
  { title: "Channel parity", detail: "Does the same intent from map, itinerary or details behave identically to chat?" },
  { title: "Explanation trust", detail: "Does the narration match what the engine actually did, or is it model prose over an unknown action?" },
];

const guardrails = [
  "The model never writes trip state. It emits an operation and reads back the engine's verdict.",
  "Invariants are code, not prompt text, and are evaluated on the candidate result before anything persists.",
  "Nothing outside the declared blast radius is written, even when the model is confident.",
  "A booked entity is never deleted as a side effect of another operation.",
  "Explanations are generated from the engine's own reasons; the model may rephrase but not invent.",
];

function useQueryPreview(): AgencyOption | null {
  const requested = new URLSearchParams(window.location.search).get("preview");
  const match = variants.find((variant) => variant.id === requested);
  return match ? match.id : null;
}

function Lab() {
  const previewOption = useQueryPreview();
  const [option, setOption] = useState<AgencyOption>("guarded");
  const [baseline, setBaseline] = useState(false);
  const [channel, setChannel] = useState<Channel>("chat");
  const scores = dayScores(startingTrip);
  const handleChoose = useCallback((next: string) => {
    const match = variants.find((variant) => variant.id === next);
    if (match) setOption(match.id);
  }, []);

  if (previewOption) {
    return (
      <div className="h-[100dvh] w-full">
        <a
          href="./lab-19-agentic-planning.html"
          className="fixed bottom-4 left-4 z-[100] inline-flex items-center gap-1.5 rounded-full bg-ink px-3 py-2 text-xs font-semibold text-white shadow-pop"
        >
          <ArrowLeft size={13} aria-hidden /> Exit full-size preview
        </a>
        <AgenticWorkspace option={previewOption} channel={channel} onChannelChange={setChannel} />
      </div>
    );
  }

  return (
    <main className="min-h-full bg-[linear-gradient(180deg,#f8fafc_0,#fafaf9_24rem)] px-4 py-6 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-[92rem]">
        <LabNavigation detail labId={LAB_ID} />

        <header className="mt-5 border-b border-slate-200 pb-6">
          <div className="flex items-center gap-2 text-brand">
            <Workflow size={18} aria-hidden />
            <p className="text-xs font-bold uppercase">Agent behaviour</p>
          </div>
          <h1 className="display mt-2 text-3xl font-semibold text-ink sm:text-4xl">
            An itinerary that cannot be edited into nonsense
          </h1>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-600">
            Two real failures on one Indore trip: an attraction placed after the flight home had landed, and a hotel
            change that deleted the return leg without saying so. Both come from the same root — the model is allowed
            to write the itinerary directly, and nothing between the sentence and the database knows what a trip is.
          </p>
          <p className="mt-3 max-w-3xl rounded-2xl bg-white p-3.5 text-sm leading-relaxed text-ink shadow-card ring-1 ring-slate-200">
            <span className="font-semibold">Yes, a separate layer is required.</span> Not a bigger prompt and not a
            better model. A deterministic <span className="font-semibold">plan engine</span> that owns placement,
            validation and persistence, with the model on either side of it: intent in, explanation out. Everything
            below is that engine running for real in the browser — the scoring, the invariants and the blast-radius
            check are executable code, not a mock.
          </p>
        </header>

        <LabScope labId={LAB_ID} />
        <OptionContrast labId={LAB_ID} />

        <section className="mt-8">
          <p className="text-[10px] font-bold uppercase text-brand">What actually went wrong</p>
          <h2 className="mt-1 text-lg font-semibold text-ink">Both defects, traced to production code</h2>
          <div className="mt-3 grid gap-3 lg:grid-cols-2">
            {defects.map((defect) => (
              <article key={defect.title} className="rounded-2xl bg-white p-4 shadow-card ring-1 ring-slate-200">
                <h3 className="text-sm font-semibold text-ink">{defect.title}</h3>
                <p className="mt-1.5 text-xs leading-relaxed text-slate-600">
                  <span className="font-semibold text-slate-700">Observed. </span>{defect.observed}
                </p>
                <p className="mt-1.5 text-xs leading-relaxed text-slate-600">
                  <span className="font-semibold text-slate-700">Cause. </span>{defect.cause}
                </p>
                <p className="mt-1.5 rounded-xl bg-rose-50 p-2.5 text-xs leading-relaxed text-rose-800">
                  <span className="font-semibold">Missing. </span>{defect.missing}
                </p>
              </article>
            ))}
          </div>
        </section>

        <section className="mt-8">
          <p className="text-[10px] font-bold uppercase text-brand">Why the departure day always wins</p>
          <h2 className="mt-1 text-lg font-semibold text-ink">Today's best-day score on this trip</h2>
          <div className="mt-3 overflow-hidden rounded-2xl bg-white shadow-card ring-1 ring-slate-200">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-[10px] font-bold uppercase text-slate-500">
                <tr>
                  <th className="px-3 py-2">Day</th>
                  <th className="px-3 py-2">Stops</th>
                  <th className="px-3 py-2">Route km</th>
                  <th className="px-3 py-2">Planned minutes</th>
                  <th className="px-3 py-2">Score</th>
                </tr>
              </thead>
              <tbody>
                {scores.map((row) => (
                  <tr key={row.day} className={row.chosen ? "bg-rose-50 font-semibold text-rose-900" : "text-slate-600"}>
                    <td className="px-3 py-1.5">Day {row.day}</td>
                    <td className="px-3 py-1.5">{row.count}</td>
                    <td className="px-3 py-1.5">{row.routeKm.toFixed(1)}</td>
                    <td className="px-3 py-1.5">{row.durationMin}</td>
                    <td className="px-3 py-1.5">
                      {row.score.toFixed(1)}
                      {row.chosen ? " · chosen" : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-xs text-slate-500">
            The departure day holds a check-out and a flight, so it is always the lightest day and always the winner.
            The score is a geography heuristic being asked a question about time and place that it cannot answer.
          </p>
        </section>

        <section className="mt-8">
          <p className="text-[10px] font-bold uppercase text-brand">The proposal</p>
          <h2 className="mt-1 text-lg font-semibold text-ink">One pipeline, two trusted roles</h2>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {layers.map((layer) => (
              <div key={layer.step} className="rounded-2xl bg-white p-4 shadow-card ring-1 ring-slate-200">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-semibold text-ink">{layer.step}</p>
                  <span
                    className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ring-1 ${
                      layer.owner === "Engine"
                        ? "bg-accent-50 text-accent ring-accent/20"
                        : "bg-brand-50 text-brand-700 ring-brand/20"
                    }`}
                  >
                    {layer.owner}
                  </span>
                </div>
                <p className="mt-1.5 text-xs leading-relaxed text-slate-600">{layer.text}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="mt-8">
          <p className="text-[10px] font-bold uppercase text-brand">The rules the engine owns</p>
          <h2 className="mt-1 text-lg font-semibold text-ink">Eight invariants, evaluated as code</h2>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {invariants.map((invariant) => (
              <div key={invariant.code} className="flex gap-2.5 rounded-2xl bg-white p-3 shadow-card ring-1 ring-slate-200">
                <span className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-lg bg-ink text-[10px] font-bold text-white">
                  {invariant.code}
                </span>
                <div className="min-w-0">
                  <p className="text-xs font-semibold text-ink">{invariant.rule}</p>
                  <p className="mt-0.5 text-[11px] leading-relaxed text-slate-600">{invariant.text}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="mt-8">
          <p className="text-[10px] font-bold uppercase text-brand">Required in every option</p>
          <h2 className="mt-1 text-lg font-semibold text-ink">Nothing here may be dropped</h2>
          <ul className="mt-3 space-y-1.5">
            {requirements.map((requirement) => (
              <li key={requirement} className="flex gap-2 text-sm leading-relaxed text-slate-600">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" aria-hidden />
                {requirement}
              </li>
            ))}
          </ul>
        </section>

        <section className="mt-8">
          <div className="lab-variant-grid" role="tablist" aria-label="Agent behaviour options">
            {variants.map((variant) => (
              <button
                key={variant.id}
                type="button"
                role="tab"
                aria-selected={option === variant.id}
                onClick={() => { setOption(variant.id); setBaseline(false); }}
                className={`rounded-2xl border p-4 text-left transition ${
                  option === variant.id
                    ? "border-brand bg-white shadow-pop ring-1 ring-brand/30"
                    : "border-slate-200 bg-white hover:border-slate-300"
                }`}
              >
                <p className="text-sm font-semibold text-ink">{variant.label}</p>
                <p className="mt-1.5 text-xs leading-relaxed text-slate-600">{variant.summary}</p>
                <p className="mt-2 text-xs font-medium text-accent">{variant.delta}</p>
              </button>
            ))}
          </div>
        </section>

        <section className="mt-6">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="text-[10px] font-bold uppercase text-brand">Production-scale preview</p>
              <h2 className="mt-1 text-lg font-semibold text-ink">
                {baseline ? "Today's agent" : variants.find((variant) => variant.id === option)?.label}
              </h2>
              <p className="mt-1 max-w-2xl text-xs text-slate-500">
                Pick a channel, then run either failing request. The engine is identical in all four channels; only the
                surface that answers you changes. Compare with today to watch both defects reproduce.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setBaseline((value) => !value)}
                aria-pressed={baseline}
                className={`h-9 rounded-full px-3 text-xs font-semibold ring-1 transition ${
                  baseline ? "bg-ink text-white ring-ink" : "bg-white text-slate-600 ring-slate-200 hover:ring-slate-300"
                }`}
              >
                {baseline ? "Showing today" : "Compare with today"}
              </button>
              <a
                href={`./lab-19-agentic-planning.html?preview=${option}`}
                className="inline-flex h-9 items-center gap-1.5 rounded-full bg-white px-3 text-xs font-semibold text-slate-600 ring-1 ring-slate-200 transition hover:ring-slate-300"
              >
                <Maximize2 size={13} aria-hidden /> Full-size preview
              </a>
            </div>
          </div>
          <div className="mt-3 h-[46rem] overflow-hidden rounded-2xl shadow-pop ring-1 ring-slate-200">
            <AgenticWorkspace
              key={baseline ? "today" : option}
              option={baseline ? "today" : option}
              channel={channel}
              onChannelChange={setChannel}
            />
          </div>
          <p className="mt-2 flex items-center gap-1.5 text-xs text-slate-500">
            <ShieldCheck size={13} className="text-accent" aria-hidden />
            The dashed strip is lab harness, not proposed chrome. Everything below it is the product.
          </p>
        </section>

        <section className="mt-9">
          <p className="text-[10px] font-bold uppercase text-brand">How to judge</p>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {criteria.map((criterion) => (
              <div key={criterion.title} className="rounded-2xl bg-white p-4 shadow-card ring-1 ring-slate-200">
                <p className="text-sm font-semibold text-ink">{criterion.title}</p>
                <p className="mt-1 text-xs leading-relaxed text-slate-600">{criterion.detail}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="mt-9">
          <p className="text-[10px] font-bold uppercase text-brand">Guardrails</p>
          <ul className="mt-3 space-y-1.5">
            {guardrails.map((guardrail) => (
              <li key={guardrail} className="flex gap-2 text-sm leading-relaxed text-slate-600">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-brand" aria-hidden />
                {guardrail}
              </li>
            ))}
          </ul>
        </section>

        <div className="mt-10">
          <DecisionCapture
            labId={LAB_ID}
            labTitle="An itinerary that cannot be edited into nonsense"
            options={variants.map((variant) => ({ id: variant.id, label: variant.label }))}
            activeOption={option}
            onChoose={handleChoose}
          />
        </div>
      </div>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Lab />
  </React.StrictMode>,
);
