import React, { useCallback, useMemo, useState } from "react";
import ReactDOM from "react-dom/client";
import { ArrowLeft, ArrowRight, Check, Columns2, Map, Maximize2, ShieldCheck, TriangleAlert } from "lucide-react";
import "../../../src/index.css";
import { DecisionCapture } from "../shared/DecisionCapture";
import { LabNavigation } from "../shared/LabNavigation";
import { LabScope } from "../shared/LabScope";
import { OptionContrast } from "../shared/OptionContrast";
import "../shared/experiment-layout.css";
import { IntercityWorkspace } from "./IntercityWorkspace";
import { improvementRows, scenarios, variants, type ScenarioId, type VariantId } from "./scenarios";

const criteria = [
  {
    title: "Is the day complete?",
    body: "Open the itinerary rail and count the stops flagged Not on the map. A transfer day should have none once the option is applied.",
  },
  {
    title: "Is the mode unmistakable?",
    body: "Switch road, rail, and flight. Solid road, dashed rail, and a dotted air arc must never imply a drivable line between airports.",
  },
  {
    title: "Is the viewport still usable?",
    body: "Check the dashed fit rectangle. Completeness must not force a country-wide zoom that makes destination work impractical.",
  },
  {
    title: "Are ordinary days untouched?",
    body: "Open the Ordinary day (guard) scenario. Its before and after must be identical, including framing and marker style.",
  },
];

const guardrails = [
  "Itinerary timing, stop order, hotel identity, and route facts stay authoritative; the map only renders them.",
  "Terminal pins stay informational. They are not bookable, and they do not become selectable places in this Lab.",
  "Distances and durations keep using endpoint-based geodesic estimates. No billed routing provider is approved here.",
  "Ordinary sightseeing days remain closed hotel circuits with unchanged framing.",
];

function useQueryPreview() {
  const params = new URLSearchParams(window.location.search);
  const previewVariant = params.get("preview");
  const previewScenario = params.get("scenario");
  const variant = variants.find((item) => item.id === previewVariant)?.id;
  const scenario = scenarios.find((item) => item.id === previewScenario)?.id;
  return { variant, scenario };
}

function Lab() {
  const preview = useQueryPreview();
  const [scenarioId, setScenarioId] = useState<ScenarioId>(preview.scenario ?? "road");
  const [variant, setVariant] = useState<VariantId>(preview.variant ?? "full-journey");
  const [compare, setCompare] = useState(true);

  const scenario = useMemo(() => scenarios.find((item) => item.id === scenarioId)!, [scenarioId]);
  const activeVariant = variants.find((item) => item.id === variant)!;
  const rows = useMemo(() => improvementRows(scenario), [scenario]);
  const choose = useCallback((value: string) => setVariant(value as VariantId), []);

  if (preview.variant) {
    return (
      <main className="relative h-[100dvh] min-h-[40rem] overflow-hidden bg-white">
        <IntercityWorkspace scenario={scenario} variant={variant} view="option" height="h-full" />
        <a
          href="./lab-14-intercity-map.html"
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
        <LabNavigation detail labId="intercity-map" />

        <header className="mt-4 border-b border-slate-200 pb-5">
          <div className="flex items-center gap-2 text-brand">
            <Map size={15} aria-hidden />
            <p className="text-xs font-bold uppercase">Map completeness</p>
          </div>
          <h1 className="display mt-1 text-3xl font-semibold text-ink">Inter-city travel on the day map</h1>
          <p className="mt-2 max-w-4xl text-sm leading-relaxed text-slate-600">
            The itinerary already stores the complete checkout, transfer, and check-in sequence. The Map deliberately drops it:
            airports, stations, and the inter-city leg are filtered out, and a transfer day is framed around one city. This Lab
            decides how much of that journey the selected day should show, and how road, rail, and flight are told apart.
          </p>
        </header>

        <LabScope labId="intercity-map" />
        <OptionContrast labId="intercity-map" />

        <section className="mt-5 overflow-hidden rounded-md bg-white shadow-card ring-1 ring-slate-200">
          <div className="border-b border-slate-100 px-4 py-3">
            <p className="text-[10px] font-bold uppercase text-brand">The improvement, measured on this scenario</p>
            <h2 className="mt-0.5 text-sm font-semibold text-ink">What the owner gains on a {scenario.tab.toLowerCase()}</h2>
            <p className="mt-1 text-xs leading-relaxed text-slate-500">
              Counts come from the same fixture rendered in both previews below, so the comparison is verifiable rather than asserted.
            </p>
          </div>
          <div className="grid gap-px bg-slate-100 sm:grid-cols-2 lg:grid-cols-4">
            {rows.map((row) => (
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
          <p className="border-t border-slate-100 bg-slate-50/60 px-4 py-2.5 text-xs leading-relaxed text-slate-600">
            <strong className="text-ink">Why it matters:</strong> today a transfer day can look like an ordinary short day in one
            city, so a missing airport transfer, an unbooked drive, or a wrong-side hotel is invisible on the surface the owner
            uses to sanity-check a plan.
          </p>
        </section>

        <section className="mt-5">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="text-[10px] font-bold uppercase text-slate-400">Scenarios in this Lab</p>
              <h2 className="mt-0.5 text-sm font-semibold text-ink">Every transfer shape, plus the regression guard</h2>
            </div>
          </div>
          <div className="mt-2 flex flex-wrap gap-2" role="tablist" aria-label="Transfer scenarios">
            {scenarios.map((item) => (
              <button
                key={item.id}
                type="button"
                role="tab"
                aria-selected={scenarioId === item.id}
                onClick={() => setScenarioId(item.id)}
                className={`inline-flex items-center gap-1.5 rounded-sm px-3 py-2 text-xs font-semibold ring-1 transition ${
                  scenarioId === item.id ? "bg-ink text-white ring-ink" : "bg-white text-slate-600 ring-slate-200 hover:text-ink"
                }`}
              >
                {item.guard && <ShieldCheck size={13} aria-hidden />}
                {item.tab}
              </button>
            ))}
          </div>
          <p className="mt-2 text-xs leading-relaxed text-slate-600">{scenario.summary}</p>
        </section>

        <div className="lab-variant-grid mt-5" role="tablist" aria-label="Inter-city map variants">
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
              <a href={`?preview=${variant}&scenario=${scenario.id}`} className="btn-primary">
                <Maximize2 size={14} aria-hidden /> Open full-size preview
              </a>
            </div>
          </div>

          {scenario.guard && (
            <p className="mb-3 flex items-start gap-2 rounded-md bg-emerald-50 px-3 py-2 text-xs leading-relaxed text-emerald-900 ring-1 ring-emerald-200">
              <ShieldCheck size={14} className="mt-0.5 shrink-0" aria-hidden />
              Regression guard: both panels must stay identical. If an option changes this day, it is out of scope and should not be approved.
            </p>
          )}

          <div className={`grid gap-4 ${compare ? "xl:grid-cols-2" : ""}`}>
            {compare && (
              <figure className="overflow-hidden rounded-md bg-white shadow-card ring-1 ring-slate-200">
                <figcaption className="flex items-center gap-2 border-b border-slate-200 bg-slate-50 px-3 py-2">
                  <TriangleAlert size={13} className="text-amber-600" aria-hidden />
                  <span className="text-xs font-bold text-ink">Today in production</span>
                  <span className="text-[11px] text-slate-500">Transfer geometry filtered out</span>
                </figcaption>
                <IntercityWorkspace scenario={scenario} variant={variant} view="baseline" />
              </figure>
            )}
            <figure className="overflow-hidden rounded-md bg-white shadow-pop ring-1 ring-brand/25">
              <figcaption className="flex items-center gap-2 border-b border-slate-200 bg-brand/5 px-3 py-2">
                <Check size={13} className="text-brand" aria-hidden />
                <span className="text-xs font-bold text-ink">With {activeVariant.label}</span>
                <span className="truncate text-[11px] text-slate-500">{scenario.framing}</span>
              </figcaption>
              <IntercityWorkspace key={`${scenario.id}-${variant}`} scenario={scenario} variant={variant} view="option" />
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
            labId="intercity-map"
            labTitle="Inter-city travel on the day map"
            options={variants}
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
