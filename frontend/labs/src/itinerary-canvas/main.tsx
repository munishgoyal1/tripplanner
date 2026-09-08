import React, { useCallback, useState } from "react";
import ReactDOM from "react-dom/client";
import { ArrowLeft, ListChecks, Maximize2 } from "lucide-react";
import "../../../src/index.css";
import { DecisionCapture } from "../shared/DecisionCapture";
import { LabNavigation } from "../shared/LabNavigation";
import { LabScope } from "../shared/LabScope";
import { OptionContrast } from "../shared/OptionContrast";
import { StylizedMap } from "../shared/StylizedMap";
import { WorkspaceFrame } from "../shared/WorkspaceFrame";
import { days } from "../shared/tripFixture";
import "../shared/experiment-layout.css";
import { ItineraryCanvas } from "./ItineraryCanvas";
import type { ItineraryOption } from "./ItineraryCanvas";

const LAB_ID = "itinerary-canvas";

const variants: Array<{ id: ItineraryOption; label: string; summary: string; delta: string }> = [
  {
    id: "cards",
    label: "B · Layered stop cards",
    summary:
      "Each stop is a calm card. Time, name, and booking status are the only always-loud facts; costs, hours and ratings sit in one quiet chip row, and long notes open in place.",
    delta: "Highest scan speed. Notes and tips are one click away rather than always printed.",
  },
  {
    id: "spine",
    label: "A · Journey spine",
    summary:
      "One continuous time rail carries the whole trip. Travel legs sit on the line between stops, so the day reads as a single movement instead of a stack of rows.",
    delta: "Best for feeling the shape of a day; the rail costs about 5rem of horizontal space.",
  },
  {
    id: "editorial",
    label: "C · Editorial agenda",
    summary:
      "Magazine typography with Morning, Afternoon and Evening chapters. Every stop fact is compressed into a single meta line under a Fraunces title.",
    delta: "Most elegant to read end to end; densest single line of facts per stop.",
  },
];

const requirements = [
  "Every production fact stays present: timing label, time and est. marker, visit or transfer duration, end time, travel mode with distance, duration, detail, estimated arrival and buffer or conflict.",
  "Every stop keeps its map marker and colour, kind, booking state, cost, opening hours, rating with review count, must-visit score, concerns, notes and insights.",
  "Every day keeps its date, title, weather, summary, planned stop count, schedule duration and span, day travel total, confirmed and to-book counts, travel rhythm and Open route link.",
  "The trip header keeps destination, origin, dates, travelers, status, total cost, readiness, counts, weather, packing, family pills, constraints and budget.",
  "Booking, remove, focus and show-on-map stay reachable from the row without opening another surface.",
];

const criteria = [
  { title: "Time to find one stop", detail: "How fast can the owner locate Belém Tower on Day 3 and see that it is not booked?" },
  { title: "Risk visibility", detail: "Does the 16-minute ferry conflict surface without a click, on every option?" },
  { title: "Vertical cost", detail: "How much scrolling separates Day 1 from Day 4 at a real pane width?" },
  { title: "Calm at density", detail: "With 20 stops on screen, does the pane still feel considered rather than crowded?" },
  { title: "Theme fit", detail: "Does it read as the same product as the toolbar, Map and Details beside it?" },
];

const guardrails = [
  "No new colours. Coral brand, teal accent, ink, surface and the existing emerald and amber status tones only.",
  "Fraunces stays reserved for trip and day titles; everything else is Inter.",
  "Progressive disclosure is allowed, information removal is not. Concerns never collapse.",
  "The pane must stay usable at 20rem wide, which is the narrowest production itinerary column.",
];

function ContextMap() {
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-1 border-b border-slate-200 bg-white px-3 py-1.5">
        <button type="button" className="rounded-md px-2 py-1 text-[11px] font-semibold text-slate-500">All days</button>
        {days.map((day) => (
          <button
            key={day.day}
            type="button"
            className={`rounded-md px-2 py-1 text-[11px] font-semibold ${day.day === 3 ? "text-white" : "text-slate-500"}`}
            style={day.day === 3 ? { backgroundColor: day.color } : undefined}
          >
            Day {day.day}
          </button>
        ))}
      </div>
      <div className="min-h-0 flex-1">
        <StylizedMap activeDay={3} selectedId="d3-tower" />
      </div>
    </div>
  );
}

function useQueryPreview(): ItineraryOption | null {
  const requested = new URLSearchParams(window.location.search).get("preview");
  const match = variants.find((variant) => variant.id === requested);
  return match ? match.id : null;
}

function Lab() {
  const previewOption = useQueryPreview();
  const [option, setOption] = useState<ItineraryOption>("cards");
  const [baseline, setBaseline] = useState(false);
  const handleChoose = useCallback((next: string) => {
    const match = variants.find((variant) => variant.id === next);
    if (match) setOption(match.id);
  }, []);

  if (previewOption) {
    return (
      <div className="h-[100dvh] w-full">
        <a
          href={`./lab-17-itinerary-canvas.html`}
          className="fixed bottom-4 left-4 z-[100] inline-flex items-center gap-1.5 rounded-full bg-ink px-3 py-2 text-xs font-semibold text-white shadow-pop"
        >
          <ArrowLeft size={13} aria-hidden /> Exit full-size preview
        </a>
        <WorkspaceFrame
          emphasis="itinerary"
          itinerary={<ItineraryCanvas option={previewOption} />}
          map={<ContextMap />}
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
            <ListChecks size={18} aria-hidden />
            <p className="text-xs font-bold uppercase">Itinerary layout</p>
          </div>
          <h1 className="display mt-2 text-3xl font-semibold text-ink sm:text-4xl">
            Itinerary canvas, reimagined
          </h1>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-600">
            The itinerary pane currently prints every known fact at the same volume. Three options
            re-rank the same information so a five-day Lisbon plan reads quickly and calmly, without
            losing a single production fact. Compare each against today's presentation before choosing.
          </p>
        </header>

        <LabScope labId={LAB_ID} />
        <OptionContrast labId={LAB_ID} />

        <section className="mt-8">
          <p className="text-[10px] font-bold uppercase text-brand">The improvement, measured on this fixture</p>
          <h2 className="mt-1 text-lg font-semibold text-ink">Same 20 stops, four presentations</h2>
          <div className="mt-3 grid gap-3 sm:grid-cols-3">
            {[
              { value: "20 stops", label: "across 4 detailed days, including one 8-stop day" },
              { value: "31 facts", label: "per fully-specified stop and day, all retained in every option" },
              { value: "1 risk", label: "the 16-minute ferry conflict must stay visible without a click" },
            ].map((metric) => (
              <div key={metric.value} className="rounded-2xl bg-white p-4 shadow-card ring-1 ring-slate-200">
                <p className="display text-xl font-semibold text-ink">{metric.value}</p>
                <p className="mt-1 text-xs leading-relaxed text-slate-600">{metric.label}</p>
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
          <div className="lab-variant-grid" role="tablist" aria-label="Itinerary canvas options">
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
                {baseline ? "Today's itinerary pane" : variants.find((variant) => variant.id === option)?.label}
              </h2>
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
                href={`./lab-17-itinerary-canvas.html?preview=${option}`}
                className="inline-flex h-9 items-center gap-1.5 rounded-full bg-white px-3 text-xs font-semibold text-slate-600 ring-1 ring-slate-200 transition hover:ring-slate-300"
              >
                <Maximize2 size={13} aria-hidden /> Full-size preview
              </a>
            </div>
          </div>
          <div className="mt-3 h-[46rem] overflow-hidden rounded-2xl shadow-pop ring-1 ring-slate-200">
            <WorkspaceFrame
              emphasis="itinerary"
              itinerary={<ItineraryCanvas option={baseline ? "today" : option} />}
              map={<ContextMap />}
            />
          </div>
          <p className="mt-2 text-xs text-slate-500">
            The toolbar, Map and Details panes are unchanged context. Only the itinerary pane varies.
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
            labTitle="Itinerary canvas, reimagined"
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
