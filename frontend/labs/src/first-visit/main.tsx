import { ArrowLeft, DoorOpen, Maximize2, Monitor, Smartphone } from "lucide-react";
import React, { useCallback, useState } from "react";
import ReactDOM from "react-dom/client";

import { DecisionCapture } from "../shared/DecisionCapture";
import { LabNavigation } from "../shared/LabNavigation";
import { LabScope } from "../shared/LabScope";
import { OptionContrast } from "../shared/OptionContrast";
import { FirstVisit, type FirstVisitOption, type FirstVisitSurface } from "./FirstVisit";
import "../../../src/index.css";
import "../shared/experiment-layout.css";

const LAB_ID = "first-visit";

type Option = Exclude<FirstVisitOption, "today">;

// Ordered best-first, as the contrast table requires. Letters are fixed identifiers and
// never move with the ranking.
const variants: { id: Option; label: string; summary: string; delta: string }[] = [
  {
    id: "magazine",
    label: "B · Proof-first magazine",
    summary:
      "A full plan is the page. The visitor reads four real days, every price with its source, and the rejected alternatives before anything is asked of them. A sticky composer follows the proof down the page.",
    delta:
      "Exact delta: the first screen is a generated plan, not an input. The composer is docked at the bottom rather than being the hero, and destination plans are their own readable pages.",
  },
  {
    id: "stage",
    label: "D · Live agent stage",
    summary:
      "A dark, full-bleed console where the product plans a trip in front of you: research receipts stream, days assemble, and the total falls from €3,833 to €3,480. The call to action is to take over the plan already running.",
    delta:
      "Exact delta: the hero performs rather than describes. It is the only option whose first screen moves on its own, the only one that shows the price falling live, and the only one in a different visual language from the rest of the site.",
  },
  {
    id: "prompt",
    label: "A · Prompt-first hero",
    summary:
      "The planner input is the hero. One sentence of promise, one large field, four example prompts, and the proof — sample plan, prices, savings — lives below the fold in the familiar order.",
    delta:
      "Exact delta: the first and largest element on the page is the thing you type into. Proof is offered as evidence after the ask, not before it.",
  },
  {
    id: "intake",
    label: "C · Guided intake",
    summary:
      "Four structured answers — where, when, who, budget and pace — assemble the first prompt in front of the visitor, with the sentence it will read shown live. For people who do not know what to type.",
    delta:
      "Exact delta: the entry point is a form that writes the prompt for you, and its answers double as the preference profile the account will keep.",
  },
];

const surfaces: { id: FirstVisitSurface; label: string; note: string }[] = [
  {
    id: "landing",
    label: "Landing page",
    note: "What an anonymous visitor sees at the root URL, top to bottom, including footer and legal.",
  },
  {
    id: "first-plan",
    label: "First plan and sign-in",
    note: "The forty seconds from pressing Plan to owning a trip, and exactly where each option asks for an account.",
  },
  {
    id: "share",
    label: "Shared trip page",
    note: "The other front door: the link preview in a message app and the read-only public trip page it opens.",
  },
];

const requirements = [
  "A visitor can start a real trip with no account, and the page says so before they type.",
  "What the product does — and what it refuses to do, including never holding a card or taking a payment — is legible on the first screen.",
  "At least one complete generated plan is reachable, with real times, transfers and place names, not a screenshot of a chat.",
  "Every price shows its source and when it was fetched. Estimates are labelled as estimates.",
  "The best-total story is public: what it compared, what it saved, and what it rejected.",
  "Pressing Plan produces a durable trip URL immediately, and the guest state states its own expiry.",
  "Signing in adopts the existing guest trip unchanged; nothing is re-planned and nothing is lost.",
  "A shared trip link renders a readable plan and a correct link preview without running the app.",
  "The whole entry works at 390 px, with the first action reachable without a scroll.",
  "Privacy, terms and what it costs are one click from the first screen.",
];

const dilemmas = [
  {
    question: "Ask first, or prove first?",
    answer:
      "A composer-first hero converts the already-convinced and looks like every other AI product. A plan-first page proves the claim but delays the one action. B and D answer this differently: B proves with a finished artefact, D proves by working in front of you.",
  },
  {
    question: "When does it ask for an account?",
    answer:
      "Every option keeps a full guest trip, so the ask is about timing, not gating. A, B and C ask at the first save or share; D asks at take-over, which is earlier and riskier but catches the visitor at peak intent.",
  },
  {
    question: "Does the public edge need rendered HTML?",
    answer:
      "The landing page, destination plans and shared trips have to be readable and indexable without the bundle; the workspace does not. B leans hardest on this because its content is the acquisition channel, but the shared trip page makes it a requirement in all four.",
  },
  {
    question: "Is a live demo a differentiator or a gimmick?",
    answer:
      "D is the only option that makes both product goals visible at once — the reasoning and the falling price. It is also the only one that risks reading as theatre, that carries an autoplay accessibility cost, and that shows one destination rather than yours.",
  },
];

const criteria = [
  { title: "Ten-second comprehension", detail: "Without scrolling, can a stranger say what this makes, what it costs, and whether it will book anything?" },
  { title: "Reason to believe", detail: "How quickly does the page produce evidence a competitor cannot fake — real times, sourced prices, rejected alternatives?" },
  { title: "Time to first prompt", detail: "Interactions and scroll distance from arrival to a trip actually being planned." },
  { title: "Account pressure", detail: "Does the account ask arrive at the moment it helps the visitor, or the moment it helps us?" },
  { title: "Arrival from a shared link", detail: "A recipient lands mid-product. Does the page work as a first impression on its own terms?" },
  { title: "390 px survival", detail: "Most first visits are on a phone, often from a message. Is the hero still one thing and one action?" },
  { title: "First paint and indexing", detail: "How much of the page can be served as HTML before the bundle loads, and how much is worth indexing?" },
  { title: "Distance from the workspace", detail: "How jarring is the handoff from this page into the planner the owner already uses?" },
];

const guardrails = [
  "No claim the product cannot honour today. No 'we book it for you', no invented savings, no live price that is really an estimate.",
  "All data is the shared Lisbon fixture. Nothing here fetches a provider, and no number should be read as a real quote.",
  "This Lab changes no production code. It ends the moment the first plan exists; the workspace itself is out of scope.",
  "Choosing an option does not authorize a separate marketing codebase. The public edge stays part of this repository and shares its components.",
  "The account ask may move, but the guest path may not be removed: a plan must always be reachable without signing in.",
];

function useQuery() {
  const params = new URLSearchParams(window.location.search);
  const requested = params.get("preview");
  const match = variants.find((variant) => variant.id === requested);
  const surface = surfaces.find((entry) => entry.id === params.get("surface"));
  return {
    previewOption: match ? match.id : null,
    surface: surface ? surface.id : "landing",
    mobile: params.get("mobile") === "1",
  };
}

function Viewport({ mobile, children }: { mobile: boolean; children: React.ReactNode }) {
  if (!mobile) return <div className="h-full overflow-y-auto">{children}</div>;
  return (
    <div className="flex h-full justify-center overflow-y-auto bg-slate-200 p-4">
      <div className="h-fit w-[390px] shrink-0 overflow-hidden rounded-[1.75rem] bg-white shadow-pop ring-8 ring-slate-900/80">
        {children}
      </div>
    </div>
  );
}

function Lab() {
  const query = useQuery();
  const [option, setOption] = useState<Option>("magazine");
  const [surface, setSurface] = useState<FirstVisitSurface>("landing");
  const [mobile, setMobile] = useState(false);
  const [stress, setStress] = useState(false);
  const [baseline, setBaseline] = useState(false);
  const handleChoose = useCallback((next: string) => {
    const match = variants.find((variant) => variant.id === next);
    if (match) setOption(match.id);
  }, []);

  if (query.previewOption) {
    return (
      <div className="h-[100dvh] w-full">
        <a
          href="./lab-21-first-visit.html"
          className="fixed bottom-4 left-4 z-[100] inline-flex items-center gap-1.5 rounded-full bg-ink px-3 py-2 text-xs font-semibold text-white shadow-pop"
        >
          <ArrowLeft size={13} aria-hidden /> Exit full-size preview
        </a>
        <Viewport mobile={query.mobile}>
          <FirstVisit option={query.previewOption} surface={query.surface} />
        </Viewport>
      </div>
    );
  }

  const activeVariant = variants.find((variant) => variant.id === option);
  const activeSurface = surfaces.find((entry) => entry.id === surface);

  return (
    <main className="min-h-full bg-[linear-gradient(180deg,#f8fafc_0,#fafaf9_24rem)] px-4 py-6 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-[92rem]">
        <LabNavigation detail labId={LAB_ID} />

        <header className="mt-5 border-b border-slate-200 pb-6">
          <div className="flex items-center gap-2 text-brand">
            <DoorOpen size={18} aria-hidden />
            <p className="text-xs font-bold uppercase">Public entry</p>
          </div>
          <h1 className="display mt-2 text-3xl font-semibold text-ink sm:text-4xl">The first visit</h1>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-600">
            Today the root URL boots the workspace into an empty trip. There is no page that says
            what this makes, no proof that the plans are real, no public trip to arrive at, and no
            moment where a guest is invited to keep what they built. Four options rebuild that edge
            end to end — the landing page, the first plan and its sign-in moment, and the shared
            trip a stranger will actually arrive through.
          </p>
        </header>

        <LabScope labId={LAB_ID} />
        <OptionContrast labId={LAB_ID} />

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
          <p className="text-[10px] font-bold uppercase text-brand">What the options disagree about</p>
          <h2 className="mt-1 text-lg font-semibold text-ink">Four questions this Lab has to settle</h2>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            {dilemmas.map((item) => (
              <div key={item.question} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-card">
                <p className="text-sm font-semibold text-ink">{item.question}</p>
                <p className="mt-1.5 text-xs leading-relaxed text-slate-600">{item.answer}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="mt-8">
          <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4" role="tablist" aria-label="First visit options">
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
                {baseline ? "Today · no public page exists" : activeVariant?.label}
              </h2>
              <p className="mt-1 max-w-2xl text-xs text-slate-500">{activeSurface?.note}</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex items-center rounded-full bg-white p-0.5 ring-1 ring-slate-200" role="group" aria-label="Surface">
                {surfaces.map((entry) => (
                  <button
                    key={entry.id}
                    type="button"
                    onClick={() => setSurface(entry.id)}
                    aria-pressed={surface === entry.id}
                    className={`h-8 rounded-full px-3 text-xs font-semibold transition ${
                      surface === entry.id ? "bg-ink text-white" : "text-slate-500 hover:text-ink"
                    }`}
                  >
                    {entry.label}
                  </button>
                ))}
              </div>
              <button
                type="button"
                onClick={() => setMobile((value) => !value)}
                aria-pressed={mobile}
                className={`inline-flex h-9 items-center gap-1.5 rounded-full px-3 text-xs font-semibold ring-1 transition ${
                  mobile ? "bg-ink text-white ring-ink" : "bg-white text-slate-600 ring-slate-200 hover:ring-slate-300"
                }`}
              >
                {mobile ? <Smartphone size={13} aria-hidden /> : <Monitor size={13} aria-hidden />}
                {mobile ? "390 px" : "Desktop"}
              </button>
              <button
                type="button"
                onClick={() => setStress((value) => !value)}
                aria-pressed={stress}
                className={`h-9 rounded-full px-3 text-xs font-semibold ring-1 transition ${
                  stress ? "bg-amber-500 text-white ring-amber-500" : "bg-white text-slate-600 ring-slate-200 hover:ring-slate-300"
                }`}
              >
                Stale-price state
              </button>
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
                href={`./lab-21-first-visit.html?preview=${option}&surface=${surface}${mobile ? "&mobile=1" : ""}`}
                className="inline-flex h-9 items-center gap-1.5 rounded-full bg-white px-3 text-xs font-semibold text-slate-600 ring-1 ring-slate-200 transition hover:ring-slate-300"
              >
                <Maximize2 size={13} aria-hidden /> Full-size preview
              </a>
            </div>
          </div>

          {!baseline && (
            <p className="mt-2 rounded-lg bg-white px-3 py-2 text-xs leading-relaxed text-slate-600 ring-1 ring-slate-200">
              <span className="font-semibold text-ink">Exact delta · </span>
              {activeVariant?.delta}
            </p>
          )}

          <div className="mt-3 h-[46rem] overflow-hidden rounded-2xl shadow-pop ring-1 ring-slate-200">
            <Viewport mobile={mobile}>
              <FirstVisit
                key={`${baseline ? "today" : option}-${surface}-${mobile}`}
                option={baseline ? "today" : option}
                surface={surface}
                stress={stress}
              />
            </Viewport>
          </div>
          <p className="mt-2 text-xs text-slate-500">
            All content is the shared Lisbon fixture, so the four options argue over presentation of
            identical facts. Prices, sources and fetch times are fabricated to be realistic, not live.
          </p>
        </section>

        <section className="mt-9">
          <p className="text-[10px] font-bold uppercase text-brand">The architecture underneath</p>
          <h2 className="mt-1 text-lg font-semibold text-ink">Whichever option wins, the public edge is not the SPA</h2>
          <div className="mt-3 grid gap-3 lg:grid-cols-3">
            <div className="rounded-2xl bg-white p-4 shadow-card ring-1 ring-slate-200">
              <p className="text-sm font-semibold text-ink">Served as HTML</p>
              <p className="mt-1 text-xs leading-relaxed text-slate-600">
                Landing, destination plans and shared trips: readable at first paint, indexable, and
                correct in a link preview without running the bundle.
              </p>
            </div>
            <div className="rounded-2xl bg-white p-4 shadow-card ring-1 ring-slate-200">
              <p className="text-sm font-semibold text-ink">Stays a SPA</p>
              <p className="mt-1 text-xs leading-relaxed text-slate-600">
                The workspace — itinerary, map, details, assistant — is a live multi-pane application
                with one state owner. Nothing here proposes changing it.
              </p>
            </div>
            <div className="rounded-2xl bg-white p-4 shadow-card ring-1 ring-slate-200">
              <p className="text-sm font-semibold text-ink">One repository</p>
              <p className="mt-1 text-xs leading-relaxed text-slate-600">
                The public edge shares this codebase, its components and its trip view-model. A
                separate marketing site would drift from the product within a month.
              </p>
            </div>
          </div>
        </section>

        <section className="mt-9">
          <p className="text-[10px] font-bold uppercase text-brand">How to judge</p>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
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
            labTitle="The first visit"
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
