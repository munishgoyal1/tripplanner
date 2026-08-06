import React, { useCallback, useState } from "react";
import ReactDOM from "react-dom/client";
import { ArrowLeft, Map as MapIcon, Maximize2 } from "lucide-react";
import "../../../src/index.css";
import { DecisionCapture } from "../shared/DecisionCapture";
import { LabNavigation } from "../shared/LabNavigation";
import { LabScope } from "../shared/LabScope";
import { WorkspaceFrame, kindMeta } from "../shared/WorkspaceFrame";
import { dayThree, dayTotals, trip } from "../shared/tripFixture";
import "../shared/experiment-layout.css";
import { MapCanvas } from "./MapCanvas";
import type { MapOption } from "./MapCanvas";

const LAB_ID = "map-canvas";

const variants: Array<{ id: MapOption; label: string; summary: string; delta: string }> = [
  {
    id: "deck",
    label: "A · Floating deck",
    summary:
      "The map runs edge to edge. Day scope, search and the day's facts float as glass cards over it, so the whole pane is geography and the controls feel weightless.",
    delta: "Most map per pixel. Controls overlap the canvas, which can cover pins in a narrow pane.",
  },
  {
    id: "dock",
    label: "B · Route dock",
    summary:
      "The map stays clean while a dock at the bottom carries day tabs, the day's facts and a horizontal route timeline of every stop with times and travel legs. Searching is one button that opens in place.",
    delta: "Turns the map into a route-planning surface. Costs about 7rem at the bottom.",
  },
  {
    id: "ribbon",
    label: "C · Command ribbon",
    summary:
      "Today's three stacked control rows collapse into one command row plus a single day-coloured fact ribbon, then the map takes everything below it.",
    delta: "Smallest change from today and the safest to ship; least new capability.",
  },
  {
    id: "compose",
    label: "D · Search-first dock",
    summary:
      "B's bottom dock without the resident stop list. A real search field sits in the dock at all times, so it is obvious you can type; tapping a dashed pin on the map fills that same field with the place name. Type and day only appear once there is a place to add, and the route timeline is a Sequence toggle rather than permanent furniture.",
    delta: "Bottom controls without duplicating the itinerary. One composer fed two ways; the timeline stays available but stops charging rent.",
  },
];

const dilemmas = [
  {
    question: "B's route timeline repeats the itinerary and eats the dock.",
    answer:
      "D drops it from the resting state and puts it behind a Sequence toggle in the same dock. The strip is identical when opened, so a sandbox round can settle whether it earns its 4rem — especially when the map is maximised and the itinerary is not on screen.",
  },
  {
    question: "Does an Add a place button say you can type into it?",
    answer:
      "No. A pill labelled + Add a place reads as open a form or add something now, not type here. D replaces it with a field that already looks like a search box, carries a magnifier and a placeholder, and returns live results — the affordance states its own behaviour instead of promising it.",
  },
  {
    question: "Can a place picked on the map still be added intuitively?",
    answer:
      "Yes, and it should feed the same composer rather than a parallel one. In D the dashed pins are places not yet in the trip; tapping one writes its name into the search field and reveals type, day and Add. Typing and tapping are two ways to fill one control, so there is only ever one add flow to learn.",
  },
];

const requirements = [
  "Day scope keeps All days plus every day, in the day's own route colour.",
  "Adding a place keeps all three inputs: free-text search, optional type, and target day including Best day, plus the Add action. An option may reveal them progressively, but none may be dropped.",
  "The day context line keeps the day label, schedule duration, start and end with the est. marker, and route-only travel duration, distance and mode.",
  "A selected pin keeps its photo, name, rating, address, Open details, and either move-day plus remove for planned stops or day select plus Add to trip for new ones.",
  "Route colour, numbered markers and the day polyline keep matching the itinerary pane exactly.",
  "The loading and failure states keep their message and Retry affordance.",
];

const criteria = [
  { title: "Map surface", detail: "How much of the pane is actually geography once controls are placed?" },
  { title: "Time to add a stop", detail: "From intent to Add, how many interactions and how much hunting?" },
  { title: "Day comprehension", detail: "Can the owner tell the shape and cost of Day 3 without leaving the map?" },
  { title: "Itinerary agreement", detail: "Does a pin, its colour and its number read as the same object as the itinerary row?" },
  { title: "Narrow-pane survival", detail: "Does the option still work when the map is the secondary pane?" },
  { title: "Duplication with the itinerary", detail: "Does the map repeat what the itinerary already says, and is that repetition worth its space?" },
];

const guardrails = [
  "Floating chrome must never permanently obscure the selected pin or the route.",
  "Colours come from the existing day palette, brand coral and teal accent only.",
  "No control may be removed to gain map space; it may only move or collapse behind a visible affordance.",
  "An affordance must describe what it does: a control that accepts typing must look like it accepts typing.",
  "Pin numbering and day colour must stay identical to the itinerary pane.",
];

function ContextItinerary() {
  const totals = dayTotals(dayThree);
  return (
    <div className="h-full overflow-y-auto bg-surface">
      <div className="border-b border-slate-200 bg-white px-4 py-3">
        <p className="text-[10px] font-bold uppercase text-brand">{trip.status}</p>
        <h2 className="display text-lg font-semibold text-ink">{trip.destination}</h2>
        <p className="text-[11px] text-slate-500">{trip.dateRange} · {trip.travelers} travelers · {trip.totalCost}</p>
      </div>
      <div className="px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="grid h-7 w-7 place-items-center rounded-lg text-[11px] font-bold text-white" style={{ backgroundColor: dayThree.color }}>
            {dayThree.day}
          </span>
          <div className="min-w-0">
            <p className="text-[10px] font-bold uppercase text-slate-400">{dayThree.weekday} · {dayThree.date}</p>
            <p className="display truncate text-sm font-semibold text-ink">{dayThree.title}</p>
          </div>
        </div>
        <p className="mt-1.5 text-[11px] text-slate-500">
          {totals.planned} stops · {dayThree.schedule.duration} · {dayThree.route.duration} travel
        </p>
        <ol className="mt-2 space-y-1">
          {dayThree.stops.map((stop) => {
            const { Icon } = kindMeta[stop.kind];
            return (
              <li key={stop.id} className="flex items-center gap-2 rounded-xl bg-white px-2.5 py-2 shadow-card ring-1 ring-slate-200/70">
                <span
                  className="grid h-5 w-5 shrink-0 place-items-center rounded-full border text-[10px] font-bold"
                  style={{ borderColor: dayThree.color, color: dayThree.color }}
                >
                  {stop.marker ?? <Icon size={10} aria-hidden />}
                </span>
                <span className="w-10 shrink-0 text-[11px] font-semibold tabular-nums text-slate-500">{stop.time}</span>
                <span className="min-w-0 flex-1 truncate text-xs font-semibold text-ink">{stop.name}</span>
                {stop.bookable && (
                  <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${stop.booked ? "bg-emerald-500" : "bg-amber-400"}`} />
                )}
              </li>
            );
          })}
        </ol>
      </div>
    </div>
  );
}

function useQueryPreview(): MapOption | null {
  const requested = new URLSearchParams(window.location.search).get("preview");
  const match = variants.find((variant) => variant.id === requested);
  return match ? match.id : null;
}

function Lab() {
  const previewOption = useQueryPreview();
  const [option, setOption] = useState<MapOption>("compose");
  const [baseline, setBaseline] = useState(false);
  const [showError, setShowError] = useState(false);
  const handleChoose = useCallback((next: string) => {
    const match = variants.find((variant) => variant.id === next);
    if (match) setOption(match.id);
  }, []);

  if (previewOption) {
    return (
      <div className="h-[100dvh] w-full">
        <a
          href="./lab-18-map-canvas.html"
          className="fixed bottom-4 left-4 z-[100] inline-flex items-center gap-1.5 rounded-full bg-ink px-3 py-2 text-xs font-semibold text-white shadow-pop"
        >
          <ArrowLeft size={13} aria-hidden /> Exit full-size preview
        </a>
        <WorkspaceFrame
          emphasis="map"
          itinerary={<ContextItinerary />}
          map={<MapCanvas option={previewOption} />}
        />
      </div>
    );
  }

  return (
    <main className="min-h-full bg-[linear-gradient(180deg,#f8fafc_0,#fafaf9_24rem)] px-4 py-6 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-[92rem]">
        <LabNavigation detail labId={LAB_ID} />

        <header className="mt-5 border-b border-slate-200 pb-6">
          <div className="flex items-center gap-2 text-brand">
            <MapIcon size={18} aria-hidden />
            <p className="text-xs font-bold uppercase">Map interaction</p>
          </div>
          <h1 className="display mt-2 text-3xl font-semibold text-ink sm:text-4xl">Map canvas, reimagined</h1>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-600">
            Today three stacked control rows sit above the map and consume roughly a fifth of the pane
            before a single pin is drawn. Four options rebalance chrome and geography while keeping
            every control, fact and state the production map already provides.
          </p>
        </header>

        <LabScope labId={LAB_ID} />

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
          <p className="text-[10px] font-bold uppercase text-brand">Open questions option D answers</p>
          <h2 className="mt-1 text-lg font-semibold text-ink">Three things the first three options left unresolved</h2>
          <div className="mt-3 grid gap-3 lg:grid-cols-3">
            {dilemmas.map((item) => (
              <div key={item.question} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-card">
                <p className="text-sm font-semibold text-ink">{item.question}</p>
                <p className="mt-1.5 text-xs leading-relaxed text-slate-600">{item.answer}</p>
              </div>
            ))}
          </div>
          <p className="mt-3 text-xs text-slate-500">
            None of this is settled here. D exists so the bottom-bar placement can be kept while the
            duplication and the add affordance are argued separately, and so a sandbox round has
            something concrete to iterate on.
          </p>
        </section>

        <section className="mt-8">
          <div className="lab-variant-grid" role="tablist" aria-label="Map canvas options">
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
                {baseline ? "Today's map pane" : variants.find((variant) => variant.id === option)?.label}
              </h2>
              <p className="mt-1 text-xs text-slate-500">
                {option === "compose" && !baseline
                  ? "Day 3 is scoped by default. Tap a numbered pin for its card, or a dashed pin to fill the search field."
                  : "Click a pin to open its card. Day 3 is scoped by default."}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setShowError((value) => !value)}
                aria-pressed={showError}
                className={`h-9 rounded-full px-3 text-xs font-semibold ring-1 transition ${
                  showError ? "bg-rose-600 text-white ring-rose-600" : "bg-white text-slate-600 ring-slate-200 hover:ring-slate-300"
                }`}
              >
                Failure state
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
                href={`./lab-18-map-canvas.html?preview=${option}`}
                className="inline-flex h-9 items-center gap-1.5 rounded-full bg-white px-3 text-xs font-semibold text-slate-600 ring-1 ring-slate-200 transition hover:ring-slate-300"
              >
                <Maximize2 size={13} aria-hidden /> Full-size preview
              </a>
            </div>
          </div>
          <div className="mt-3 h-[42rem] overflow-hidden rounded-2xl shadow-pop ring-1 ring-slate-200">
            <WorkspaceFrame
              emphasis="map"
              itinerary={<ContextItinerary />}
              map={<MapCanvas key={baseline ? "today" : option} option={baseline ? "today" : option} showError={showError} />}
            />
          </div>
          <p className="mt-2 text-xs text-slate-500">
            The toolbar, itinerary and Details panes are unchanged context. Only the map pane varies.
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
            labTitle="Map canvas, reimagined"
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
