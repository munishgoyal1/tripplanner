import React, { useCallback, useState } from "react";
import ReactDOM from "react-dom/client";
import { ArrowLeft, ArrowRight, Check, Columns2, Maximize2, MessageSquare, TriangleAlert } from "lucide-react";
import "../../../src/index.css";
import { DecisionCapture } from "../shared/DecisionCapture";
import { LabNavigation } from "../shared/LabNavigation";
import { LabScope } from "../shared/LabScope";
import "../shared/experiment-layout.css";
import { ChatWorkspace } from "./ChatWorkspace";
import { improvementRows, variants, type VariantId } from "./fixture";

const requirements = [
  {
    title: "The session keeps every turn",
    body: "Scroll the transcript to the top in any option. All twelve turns from the last three days are present, grouped by when they happened. Today the transcript is bounded and older turns silently disappear.",
  },
  {
    title: "Reading position is the reader's",
    body: "Scroll up, then press Send. The view must stay where you left it and offer Jump to latest. Today every token of a streaming reply drags you back to the bottom.",
  },
  {
    title: "Every reply keeps its time",
    body: "Each answered turn carries a small badge with the seconds it took, and the running turn shows a live counter that settles into that badge. Today the elapsed time is discarded the moment the turn ends.",
  },
  {
    title: "A turn points at what it changed",
    body: "Each reply lists the stops it touched. Selecting one moves Itinerary, Map, and Details to that stop, so a conversation is navigable rather than only readable.",
  },
];

const criteria = [
  {
    title: "Can you work and converse at once?",
    body: "Ask a question, then edit the day while the answer is being written. Judge whether the option forces you to choose between the plan and the conversation.",
  },
  {
    title: "What does the conversation cost?",
    body: "Compare how much width Itinerary, Map, and Details keep at rest. A permanently docked conversation is only worth it if it is permanently useful.",
  },
  {
    title: "How fast is an old decision found?",
    body: "Find the answer about Friday museum closures without scrolling blindly. Group separators, turn cards, and effect chips are the tools each option gives you.",
  },
  {
    title: "Is the reply's cost legible?",
    body: "Look at the timing badges across the session. A 41 s trip build and an 8 s question should read as clearly different kinds of work.",
  },
];

const guardrails = [
  "The trip agent, its tools, its phases, and the SSE contract are unchanged; this Lab only decides presentation.",
  "Itinerary, Map, and Details keep their existing content design and their independent Hide and Maximize behavior.",
  "Retaining response time is display only. It reuses the turn duration the stream already knows and adds no telemetry.",
  "Nothing here approves a change to persistence limits on the server, or any Azure deployment.",
];

function useQueryPreview() {
  const params = new URLSearchParams(window.location.search);
  const requested = params.get("preview");
  return variants.find((item) => item.id === requested)?.id;
}

function Lab() {
  const previewVariant = useQueryPreview();
  const [variant, setVariant] = useState<VariantId>(previewVariant ?? "turn-thread");
  const [compare, setCompare] = useState(false);
  const choose = useCallback((value: string) => setVariant(value as VariantId), []);
  const activeVariant = variants.find((item) => item.id === variant)!;

  if (previewVariant) {
    return (
      <main className="relative h-[100dvh] min-h-[40rem] overflow-hidden bg-white">
        <ChatWorkspace variant={previewVariant} view="option" height="h-full" />
        <a
          href="./lab-16-chat-agent-workspace.html"
          className="fixed bottom-4 left-4 z-[80] inline-flex items-center gap-2 rounded-md bg-ink px-3 py-2 text-xs font-semibold text-white shadow-pop ring-1 ring-white/30"
        >
          <ArrowLeft size={14} aria-hidden /> Exit full-size preview
        </a>
      </main>
    );
  }

  return (
    <main className="min-h-full bg-[linear-gradient(180deg,#f8fafc_0,#fafaf9_24rem)] px-4 py-6 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-[92rem]">
        <LabNavigation detail labId="chat-agent-workspace" />

        <header className="mt-4 border-b border-slate-200 pb-5">
          <div className="flex items-center gap-2 text-brand">
            <MessageSquare size={15} aria-hidden />
            <p className="text-xs font-bold uppercase">Assistant and workspace layout</p>
          </div>
          <h1 className="display mt-1 text-3xl font-semibold text-ink">Reimagining the chat agent</h1>
          <p className="mt-2 max-w-4xl text-sm leading-relaxed text-slate-600">
            The Assistant builds the trip, but it currently lives in a corner sheet that has to be dismissed to see the plan it
            just changed. Its transcript is bounded, it snaps back to the newest message while you are reading an older one, and
            the time a reply took disappears the moment it finishes. This Lab decides where the conversation lives in the
            workspace, and how a turn, its cost, and its consequences are presented.
          </p>
        </header>

        <LabScope labId="chat-agent-workspace" />

        <section className="mt-5 overflow-hidden rounded-md bg-white shadow-card ring-1 ring-slate-200">
          <div className="border-b border-slate-100 px-4 py-3">
            <p className="text-[10px] font-bold uppercase text-brand">The improvement, measured on this fixture</p>
            <h2 className="mt-0.5 text-sm font-semibold text-ink">What changes for a three-day planning session</h2>
            <p className="mt-1 text-xs leading-relaxed text-slate-500">
              Both previews below render the same twelve-turn session, so the comparison is verifiable rather than asserted.
            </p>
          </div>
          <div className="grid gap-px bg-slate-100 sm:grid-cols-2 lg:grid-cols-4">
            {improvementRows.map((row) => (
              <div key={row.label} className="bg-white px-4 py-3">
                <p className="text-[10px] font-bold uppercase text-slate-400">{row.label}</p>
                <p className="mt-1.5 flex items-center gap-2 text-sm font-semibold text-ink">
                  <span className={row.gain ? "text-slate-400 line-through decoration-slate-300" : "text-slate-500"}>{row.before}</span>
                  <ArrowRight size={13} className="text-slate-400" aria-hidden />
                  <span className={row.gain ? "text-emerald-700" : "text-slate-600"}>{row.after}</span>
                </p>
                {!row.gain && <p className="mt-1 text-[10px] font-semibold text-slate-500">Unchanged by design</p>}
              </div>
            ))}
          </div>
        </section>

        <section className="mt-5 rounded-md bg-white p-4 shadow-card ring-1 ring-slate-200">
          <p className="text-[10px] font-bold uppercase text-brand">Required in every option</p>
          <h2 className="mt-0.5 text-sm font-semibold text-ink">These four are not up for selection</h2>
          <p className="mt-1 text-xs leading-relaxed text-slate-500">
            They are defects or gaps in today's Assistant, so every option implements them identically. Only the layout and the
            presentation of a turn are being chosen.
          </p>
          <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {requirements.map((item) => (
              <article key={item.title} className="rounded-md bg-slate-50 p-3 ring-1 ring-slate-200">
                <h3 className="text-xs font-semibold text-ink">{item.title}</h3>
                <p className="mt-1 text-[11px] leading-relaxed text-slate-600">{item.body}</p>
              </article>
            ))}
          </div>
        </section>

        <div className="lab-variant-grid mt-5" role="tablist" aria-label="Chat agent layout variants">
          {variants.map((item) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={variant === item.id}
              onClick={() => setVariant(item.id)}
              className={`rounded-md p-3 text-left ring-1 transition ${
                variant === item.id ? "bg-white shadow-card ring-brand/30" : "bg-white/70 ring-slate-200 hover:bg-white"
              }`}
            >
              <span className="text-sm font-semibold text-ink">{item.label}</span>
              <span className="mt-1 block text-xs leading-relaxed text-slate-500">{item.summary}</span>
              <span className="mt-2 block border-t border-slate-100 pt-2 text-[11px] leading-relaxed text-slate-600">
                <strong className="text-ink">Exact delta:</strong> {item.delta}
              </span>
            </button>
          ))}
        </div>

        <section className="mt-6">
          <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-[10px] font-bold uppercase text-slate-400">Production-scale preview</p>
              <h2 className="mt-0.5 text-lg font-semibold text-ink">{activeVariant.label}</h2>
              <p className="mt-1 max-w-4xl text-xs leading-relaxed text-slate-600">
                <strong className="text-ink">This preview changes:</strong> {activeVariant.delta}
              </p>
              <p className="mt-1 max-w-4xl text-xs leading-relaxed text-slate-500">
                Scroll the transcript up, then press Send to watch a live turn resolve into a kept duration. Select any chip
                under a reply to move the whole workspace to the stop that reply changed.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                aria-pressed={compare}
                onClick={() => setCompare((value) => !value)}
                className={`btn-ghost ${compare ? "bg-slate-100 text-ink" : ""}`}
              >
                <Columns2 size={14} aria-hidden /> {compare ? "Hide today's behavior" : "Compare with today"}
              </button>
              <a href={`?preview=${variant}`} className="btn-primary">
                <Maximize2 size={14} aria-hidden /> Open full-size preview
              </a>
            </div>
          </div>

          <div className="space-y-4">
            {compare && (
              <figure className="overflow-hidden rounded-md bg-white shadow-card ring-1 ring-slate-200">
                <figcaption className="flex flex-wrap items-center gap-2 border-b border-slate-200 bg-slate-50 px-3 py-2">
                  <TriangleAlert size={13} className="text-amber-600" aria-hidden />
                  <span className="text-xs font-bold text-ink">Today in production</span>
                  <span className="text-[11px] text-slate-500">Corner sheet · bounded history · forced scroll to newest · no kept timing</span>
                </figcaption>
                <ChatWorkspace variant={variant} view="baseline" />
              </figure>
            )}
            <figure className="overflow-hidden rounded-md bg-white shadow-pop ring-1 ring-brand/25">
              <figcaption className="flex flex-wrap items-center gap-2 border-b border-slate-200 bg-brand/5 px-3 py-2">
                <Check size={13} className="text-brand" aria-hidden />
                <span className="text-xs font-bold text-ink">With {activeVariant.label}</span>
                <span className="truncate text-[11px] text-slate-500">Same trip, same session, same twelve turns</span>
              </figcaption>
              <ChatWorkspace key={variant} variant={variant} view="option" />
            </figure>
          </div>
        </section>

        <section className="mt-6 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {criteria.map((item) => (
            <article key={item.title} className="rounded-md bg-white p-4 ring-1 ring-slate-200">
              <h2 className="text-sm font-semibold text-ink">{item.title}</h2>
              <p className="mt-1 text-xs leading-relaxed text-slate-500">{item.body}</p>
            </article>
          ))}
        </section>

        <section className="mt-4 rounded-md bg-white p-4 ring-1 ring-slate-200">
          <h2 className="text-sm font-semibold text-ink">Not changing, whichever option wins</h2>
          <ul className="mt-2 grid gap-1.5 md:grid-cols-2">
            {guardrails.map((item) => (
              <li key={item} className="flex gap-2 text-xs leading-relaxed text-slate-600">
                <span className="text-slate-400">•</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </section>

        <div className="mt-6">
          <DecisionCapture
            labId="chat-agent-workspace"
            labTitle="Chat agent and workspace layout"
            options={variants.map(({ id, label }) => ({ id, label }))}
            activeOption={variant}
            onChoose={choose}
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
