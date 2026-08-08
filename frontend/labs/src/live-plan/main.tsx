import { ArrowLeft, Maximize2, Monitor, Radio, Smartphone } from "lucide-react";
import React, { useCallback, useState } from "react";
import ReactDOM from "react-dom/client";

import { DecisionCapture } from "../shared/DecisionCapture";
import { LabNavigation } from "../shared/LabNavigation";
import { LabScope } from "../shared/LabScope";
import { OptionContrast } from "../shared/OptionContrast";
import { LivePlan, type LivePlanOption, type LivePlanSurface } from "./LivePlan";
import "../../../src/index.css";
import "../shared/experiment-layout.css";

const LAB_ID = "live-plan";

// Ordered best-first, as the contrast table requires. Letters are fixed identifiers and
// never move with the ranking.
const variants: { id: LivePlanOption; label: string; summary: string; delta: string }[] = [
  {
    id: "exact",
    label: "E · Dark stage, argued during the run",
    summary:
      "Lab 21's option D exactly as you saw it — dark console, receipts on the left, day cards assembling on the right — on a five-day trip. Twice, the run pauses itself and puts the choice inside the stream: 'Lisbon → Porto — Train, not the flight' with 'I would rather fly it' next to it. Answer it or ignore it; the plan re-settles in place and names what your preference cost.",
    delta:
      "Exact delta from A: theme unchanged, layout unchanged, page length unchanged. Two inline choice strips appear in the receipt console, the total becomes a re-settled total when you use one, and the button says 'Plan mine'.",
  },
  {
    id: "ledger",
    label: "F · Dark stage, argued after it finishes",
    summary:
      "The same dark stage on the same five-day trip, but the run plays through uninterrupted. When it completes, the console column swaps from the receipt log to 'Two things it decided for you' — both calls in full, with the options they beat and an overrule button. A 'Show the working' control flips back to the receipts.",
    delta:
      "Exact delta from E: same screen, later moment. The choice never interrupts the run, and because it arrives after the plan exists it can show the whole comparison table rather than a one-line strip.",
  },
  {
    id: "argue",
    label: "D · The decision replay",
    summary:
      "The stream is not activity, it is judgement. Three decisions arrive — the Porto leg, the Sintra day, the first hotel — each with the rule it applied and the options it rejected. You can overrule any one and the plan re-settles in front of you, with the cost of your preference named out loud.",
    delta:
      "Exact delta: the visitor acts inside the demo instead of watching it. E and F are the trimmed, decided versions of this idea; D is the maximal one, with the receipt console replaced entirely by decision cards.",
  },
  {
    id: "yours",
    label: "C · Your trip from the first keystroke",
    summary:
      "There is no demo and nothing to take over. The destination is the hero and it is bound: choose Lisbon and Porto, Kyoto and Osaka, or Rome and Florence and the receipts, days, hotels and total all re-run on that trip. Lisbon is simply the state before you type.",
    delta:
      "Exact delta: the sample trip is deleted as a concept. The plan on screen is already the visitor's, so the account is never asked for during planning — only when the plan is worth keeping.",
  },
  {
    id: "plain",
    label: "B · The same stage, said plainly",
    summary:
      "Identical choreography to A, rewritten so nothing reads as a game. 'Take over' becomes 'Plan mine', progress is a step count and a determinate bar, unbuilt days say which day they are building, and the falling price is captioned in words.",
    delta:
      "Exact delta: no new mechanic, only clarity. It is the cheapest option to build and the direct test of whether A's problem was the idea or the wording.",
  },
  {
    id: "asis",
    label: "A · Daylight stage",
    summary:
      "Lab 21's option D with one variable changed: the light theme from option B instead of the dark console. Same copy, same 'Take over' call to action, same choreography — so the darkness can be judged separately from the idea underneath it.",
    delta:
      "Exact delta: theme only. Use the 'Reference · Lab 21 D as shipped' button to flip the same screen back to dark and see what the theme was actually carrying.",
  },
];

const surfaces: { id: LivePlanSurface; label: string; note: string }[] = [
  {
    id: "landing",
    label: "Landing page",
    note: "What an anonymous visitor sees at the root URL, top to bottom, including how it moved you and the footer.",
  },
  {
    id: "first-plan",
    label: "Workspace after planning",
    note: "The app state reached from both Plan mine and Skip to app: the guest trip is already in the workspace, with itinerary, decisions, and the later sign-in moment.",
  },
  {
    id: "share",
    label: "Shared trip page",
    note: "The other front door: the read-only public trip a recipient arrives at, and the preview card a message app renders.",
  },
];

const additions = [
  "‘Take over’ becomes ‘Plan mine’, and the panel says ‘Plan yours instead of Lisbon · same planner, your destination’.",
  "The headline stops being an instruction. ‘This is the planner working. On a real trip, right now.’",
  "A skip control — ‘Show the finished plan’ — because nobody should be made to watch a demo to reach the evidence.",
  "Legible progress: ‘Step 6 of 17’ and a determinate bar, instead of a spinner that could mean anything.",
  "Unbuilt day cards say ‘Building day 4 of 6…’, so a pending card can never be mistaken for a broken one.",
  "The falling total is captioned in words: what it started at, what it stopped at, and which three changes produced the saving.",
  "‘It never books anything and never holds your card’ sits under the composer, where the doubt actually occurs.",
  "A transport legend on the console, so the flight/rail/road/tram icons on the day cards are readable at a glance.",
  "prefers-reduced-motion resolves the whole run instantly rather than playing it slowly — applied to every option.",
];

const requirements = [
  "A visitor can start a real trip with no account, and the page says so before they type.",
  "The first screen names what the product does and what it refuses to do, including never holding a card.",
  "The demo trip is multi-city and multi-modal: two hotels with H markers, and a flight, a train, a hire car and a tram all visible on the day cards.",
  "Every hop shows the options that were compared and lost, not only the one that won.",
  "Every price shows its source and when it was fetched. Estimates are labelled as estimates.",
  "No card may still be a skeleton once the run reports itself complete.",
  "A visitor can reach the finished plan without watching the run, by control or by reduced-motion preference.",
  "Signing in adopts the existing guest trip unchanged; nothing is re-planned and nothing is lost.",
  "A shared trip link renders a readable plan and a correct link preview without running the app.",
  "The whole entry works at 390 px, with the first action reachable without a scroll.",
];

const dilemmas = [
  {
    question: "Is the visitor an audience or an actor?",
    answer:
      "A and B keep them watching and then invite them to type. C removes the performance entirely and plans their trip from the start. D keeps the performance but lets them interrupt it — the only option where the visitor changes the outcome before they have signed up for anything.",
  },
  {
    question: "Was the problem the darkness or the demo?",
    answer:
      "A isolates that variable: identical to Lab 21's D except for the theme. If A reads well in daylight, the dark console was carrying more weight than the mechanic. If it reads flat, the theme was doing the persuading.",
  },
  {
    question: "Does watching someone else's trip ever convert?",
    answer:
      "A trip to Lisbon proves capability but is not your trip. B answers with clearer signposting to the composer, C answers by deleting the sample, D answers by making the sample interactive enough that the mechanic transfers.",
  },
  {
    question: "What does the shared link have to carry?",
    answer:
      "Every option shares a full multi-day, two-city plan. Only D, E and F also carry the reasoning — the rejected flight, the rejected hire car, the rule that produced each answer — which is the part no other itinerary tool can copy.",
  },
];

const criteria = [
  { title: "Ten-second comprehension", detail: "Without scrolling, can a stranger say what this makes, what it costs, and whether it will book anything?" },
  { title: "Call-to-action clarity", detail: "Read the primary button cold. Does it describe an action on your own trip, or a move in someone else's game?" },
  { title: "Reason to believe", detail: "How fast does the page produce evidence a competitor cannot fake — sourced prices, rejected transport options, a plan that spans two cities?" },
  { title: "Never looks stuck", detail: "At every second of the run, is it obvious whether the plan is unfinished or broken? Watch the fourth card." },
  { title: "Escape from the demo", detail: "How many interactions from arrival to a plan of your own destination?" },
  { title: "Account pressure", detail: "Does the ask arrive at the moment it helps the visitor, or the moment it helps us?" },
  { title: "Arrival from a shared link", detail: "A recipient lands mid-product. Does the plan read as real, and does the reasoning survive the trip through a message app?" },
  { title: "390 px survival", detail: "Most first visits are on a phone. Is the hero still one thing and one action?" },
];

const guardrails = [
  "No claim the product cannot honour today. No 'we book it for you', no invented savings, no live price that is really an estimate.",
  "All data is fixture data in this Lab. Nothing here fetches a provider, and no number should be read as a real quote.",
  "Overruling a decision in D, E or F re-settles a scripted outcome. It demonstrates the mechanic; it does not re-run a planner.",
  "This Lab changes no production code. It ends the moment the first plan exists; the workspace itself is out of scope.",
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
  const [option, setOption] = useState<LivePlanOption>("exact");
  const [surface, setSurface] = useState<LivePlanSurface>("landing");
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
          href="./lab-22-live-plan.html"
          className="fixed bottom-4 left-4 z-[100] inline-flex items-center gap-1.5 rounded-full bg-ink px-3 py-2 text-xs font-semibold text-white shadow-pop"
        >
          <ArrowLeft size={13} aria-hidden /> Exit full-size preview
        </a>
        <Viewport mobile={query.mobile}>
          <LivePlan option={query.previewOption} surface={query.surface} />
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
            <Radio size={18} aria-hidden />
            <p className="text-xs font-bold uppercase">Public entry</p>
          </div>
          <h1 className="display mt-2 text-3xl font-semibold text-ink sm:text-4xl">The live plan</h1>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-600">
            Lab 21 chose to prove the product by planning a trip in front of the visitor. The idea
            held; the execution asked the wrong things of them. This Lab takes that stage as the base
            and pushes on it six ways — one that changes only the theme, one that changes only the
            words, two that reopen the question of what a first-time visitor should be doing while the
            planner works, and two exact candidates, E and F, that keep the dark stage you liked and
            add nothing but the right to argue with it. The demo trip spans Lisbon and Porto with two
            hotels, a flight in, a train between the cities, a hire car for the one day that needs one
            and a tram for the day that does not, because a planner that only walks around one city is
            not the planner this product claims to be. Every option covers all three surfaces.
          </p>
        </header>

        <LabScope labId={LAB_ID} />
        <OptionContrast labId={LAB_ID} />

        <section className="mt-8 rounded-2xl border border-brand/25 bg-brand/[0.06] p-4">
          <p className="text-[10px] font-bold uppercase text-brand">Added after your review</p>
          <h2 className="mt-1 text-lg font-semibold text-ink">E and F are the exact ones — pick between these two</h2>
          <p className="mt-1.5 max-w-3xl text-sm leading-relaxed text-slate-700">
            You asked for the combination you saw on screen made concrete instead of assembled from a
            toggle. Both E and F are Lab 21's option D in its dark console, with its layout, its
            choreography and its receipt stream intact. Both add the one thing you wanted kept — that a
            visitor can push back — and both cut it to two choices, <em>I would rather fly it</em> and
            <em> Give me the car anyway</em>. Neither adds a page section, so the page is no longer than
            A's. They differ in one deliberate way: <strong>E offers the choice while the run is still
            going</strong>, inside the receipt console; <strong>F waits until the plan is finished</strong>
            and then swaps the console into a two-item ledger. Everything else about them is identical.
          </p>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <div className="rounded-xl bg-white p-3.5 shadow-card ring-1 ring-slate-200">
              <p className="text-sm font-semibold text-ink">Why the trip is five days now</p>
              <p className="mt-1 text-xs leading-relaxed text-slate-600">
                Six filled the console faster than a first-time visitor could read it. Five is the
                shortest cut that still carries both cities, both hotels, and a flight, an intercity
                train, a regional train, a coach, a tram, the metro, a hire-car day and a walking day:
                land in Lisbon, Sintra by train, north on the Alfa Pendular, the Douro by road, home
                from Porto. Four would force dropping either the second city or the car day, and the
                car day is what makes the Sintra argument mean anything. If you would rather keep six,
                say so — it is a one-line change and A to D still run the six-day version so you can
                compare them side by side.
              </p>
            </div>
            <div className="rounded-xl bg-white p-3.5 shadow-card ring-1 ring-slate-200">
              <p className="text-sm font-semibold text-ink">The one thing E and F did not keep as-is</p>
              <p className="mt-1 text-xs leading-relaxed text-slate-600">
                The primary button says <em>Plan mine</em>, not <em>Take over</em>. That was the single
                clearest failure in Lab 21's wording and it costs nothing to carry over. The headline
                also ends differently — <em>Then change its mind</em> for E, <em>Then see what it
                decided</em> for F — because the original promise, <em>Then take the plan</em>, no longer
                describes what the screen offers. If you want either reverted to the shipped wording,
                that is a two-word edit.
              </p>
            </div>
          </div>
          <p className="mt-3 max-w-3xl text-xs leading-relaxed text-slate-600">
            The <span className="font-semibold text-ink">Reference · Lab 21 D as shipped</span> button below
            is no longer one of the options. It shows the screen these are replacing and deselects
            every option card while it is on, so it can never quietly swap the preview under a
            selected letter again.
          </p>
        </section>

        <section className="mt-8 rounded-2xl border border-amber-200 bg-amber-50/70 p-4">
          <p className="text-[10px] font-bold uppercase text-amber-700">Answered from Lab 21</p>
          <h2 className="mt-1 text-lg font-semibold text-ink">The fourth card was a bug, not a deliberate state</h2>
          <p className="mt-1.5 max-w-3xl text-sm leading-relaxed text-slate-700">
            In Lab 21's option D the number of finished day cards was derived arithmetically from the
            receipt index — <code className="rounded bg-white px-1 py-0.5 text-[11px]">Math.floor((step - 2) / 2)</code>
            {" "}over nine receipts, which reaches three. The run then reported <em>Plan complete</em> with a
            skeleton still on screen, so a finished plan read as a stuck one. It is fixed in Lab 21,
            and this Lab removes the whole class of error: each receipt now declares which day it
            completes, so the cards can only ever finish when the run does. Option B goes further and
            labels the pending card <em>Building day 4 of 6…</em>, so the state is legible while it lasts.
          </p>
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
          <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3" role="tablist" aria-label="Live plan options">
            {variants.map((variant) => (
              <button
                key={variant.id}
                type="button"
                role="tab"
                aria-selected={!baseline && option === variant.id}
                onClick={() => { setOption(variant.id); setBaseline(false); }}
                className={`rounded-2xl border p-4 text-left transition ${
                  !baseline && option === variant.id
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
                {baseline ? "Reference · Lab 21's option D, exactly as it shipped" : activeVariant?.label}
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
                {baseline ? "Leave the reference" : "Reference · Lab 21 D as shipped"}
              </button>
              <a
                href={`./lab-22-live-plan.html?preview=${option}&surface=${surface}${mobile ? "&mobile=1" : ""}`}
                className="inline-flex h-9 items-center gap-1.5 rounded-full bg-white px-3 text-xs font-semibold text-slate-600 ring-1 ring-slate-200 transition hover:ring-slate-300"
              >
                <Maximize2 size={13} aria-hidden /> Full-size preview
              </a>
            </div>
          </div>

          <p className="mt-2 rounded-lg bg-white px-3 py-2 text-xs leading-relaxed text-slate-600 ring-1 ring-slate-200">
            <span className="font-semibold text-ink">Exact delta · </span>
            {baseline
              ? "This is not one of the six options. It is the shipped screen these options are replacing, held here so you can put any of them beside it. No option is selected while it is showing."
              : activeVariant?.delta}
          </p>

          <div className="mt-3 h-[46rem] overflow-hidden rounded-2xl shadow-pop ring-1 ring-slate-200">
            <Viewport mobile={mobile}>
              <LivePlan
                key={`${baseline ? "baseline" : option}-${surface}-${mobile}-${stress}`}
                option={baseline ? "asis" : option}
                surface={surface}
                stress={stress}
                tone={baseline ? "dark" : undefined}
              />
            </Viewport>
          </div>
          <p className="mt-2 text-xs text-slate-500">
            Every option plans from the same fixture, so they argue over what the visitor is asked to
            do, not over the facts. A to D run the six-day trip; E and F run the five-day cut. Prices,
            sources and fetch times are fabricated to be realistic, not live.
          </p>
        </section>

        <section className="mt-9">
          <p className="text-[10px] font-bold uppercase text-brand">Called out, as asked</p>
          <h2 className="mt-1 text-lg font-semibold text-ink">The smaller additions in option B</h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-slate-600">
            None of these are new mechanics. Each one removes a specific way the shipped version could
            be misread, and every one of them is cheap enough to keep even if a different option wins.
          </p>
          <ol className="mt-3 grid gap-2 sm:grid-cols-2">
            {additions.map((addition, index) => (
              <li key={addition} className="flex gap-2.5 rounded-2xl bg-white p-3 text-xs leading-relaxed text-slate-600 shadow-card ring-1 ring-slate-200">
                <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-brand/10 text-[11px] font-bold text-brand">
                  {index + 1}
                </span>
                {addition}
              </li>
            ))}
          </ol>
        </section>

        <section className="mt-9">
          <p className="text-[10px] font-bold uppercase text-brand">The architecture underneath</p>
          <h2 className="mt-1 text-lg font-semibold text-ink">What each option costs to build for real</h2>
          <div className="mt-3 grid gap-3 lg:grid-cols-3">
            <div className="rounded-2xl bg-white p-4 shadow-card ring-1 ring-slate-200">
              <p className="text-sm font-semibold text-ink">A and B · a replayed run</p>
              <p className="mt-1 text-xs leading-relaxed text-slate-600">
                One trip planned in advance and stored as an ordered event log, served as HTML and
                animated on the client. No agent runs per visitor, so it costs nothing per view and
                cannot fail in front of a stranger.
              </p>
            </div>
            <div className="rounded-2xl bg-white p-4 shadow-card ring-1 ring-slate-200">
              <p className="text-sm font-semibold text-ink">C · a real run, per visitor</p>
              <p className="mt-1 text-xs leading-relaxed text-slate-600">
                The honest version of C plans the visitor's actual destination, which means a real
                agent run before an account exists. That is the true cost of this option: rate limits,
                abuse controls and a spend ceiling on anonymous traffic. A small set of pre-planned
                destinations covers the common cases and defers the rest.
              </p>
            </div>
            <div className="rounded-2xl bg-white p-4 shadow-card ring-1 ring-slate-200">
              <p className="text-sm font-semibold text-ink">D, E and F · decisions must be first-class</p>
              <p className="mt-1 text-xs leading-relaxed text-slate-600">
                These only work if the planner records why it chose each hop and each stay — the rule,
                the options and the rejected ones. That record is useful far beyond this page: it is
                what the Details pane, the shared trip and every future explanation would read from.
                E and F need exactly two such records; D needs every one the planner makes.
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
            labTitle="The live plan"
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
