import { useEffect, useState } from "react";
import ReactDOM from "react-dom/client";
import { ListChecks } from "lucide-react";
import { publishUnmappedStops } from "../../../src/lib/unmappedStops";
import { DecisionCapture } from "../shared/DecisionCapture";
import { LabNavigation } from "../shared/LabNavigation";
import { LabScope } from "../shared/LabScope";
import { OptionContrast } from "../shared/OptionContrast";
import { unmappedStops } from "./fixture";
import { factMatrix, LAB_ID, options, type OptionId } from "./options";
import { PANES } from "./panes";
import { usePlannerState } from "./state";
import { TodayPane } from "./TodayPane";
import { PaneFrame, Workspace, type PaneWidth } from "./Workspace";
import "../../../src/index.css";
import "./styles.css";

publishUnmappedStops(unmappedStops);

type View = "workspace" | "today" | "compare";

const VISIBILITY_LABEL = { rest: "Visible", tap: "One tap", hover: "Hover" } as const;

function FactMatrix() {
  let lastGroup = "";
  return (
    <div className="ipp-matrix">
      <table>
        <thead>
          <tr>
            <th>Group</th>
            <th>Production fact or control</th>
            <th>Today</th>
            {options.map((option) => <th key={option.id}>{option.label}</th>)}
          </tr>
        </thead>
        <tbody>
          {factMatrix.map((row) => {
            const showGroup = row.group !== lastGroup;
            lastGroup = row.group;
            return (
              <tr key={row.fact}>
                <td className="group">{showGroup ? row.group : ""}</td>
                <td>{row.fact}</td>
                <td><span className={`ipp-dot ${row.today}`}>{VISIBILITY_LABEL[row.today]}</span></td>
                {options.map((option) => (
                  <td key={option.id} className={row[option.id] !== row.today ? "changed" : ""}>
                    <span className={`ipp-dot ${row[option.id]}`}>{VISIBILITY_LABEL[row[option.id]]}</span>
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Segmented<T extends string>({ label, value, choices, onChange }: { label: string; value: T; choices: Array<[T, string]>; onChange: (next: T) => void }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className="ipp-seg-label">{label}</span>
      <span className="ipp-seg" role="group" aria-label={label}>
        {choices.map(([id, text]) => <button key={id} type="button" className={value === id ? "on" : ""} aria-pressed={value === id} onClick={() => onChange(id)}>{text}</button>)}
      </span>
    </span>
  );
}

function readInitialOption(): OptionId {
  const requested = new URLSearchParams(window.location.search).get("option");
  return options.find((option) => option.id === requested)?.id ?? options[0]?.id ?? "crisp";
}

function readInitialView(): View {
  const requested = new URLSearchParams(window.location.search).get("view");
  return requested === "today" || requested === "compare" ? requested : "workspace";
}

function App() {
  const [optionId, setOptionId] = useState<OptionId>(readInitialOption);
  const [view, setView] = useState<View>(readInitialView);
  const [width, setWidth] = useState<PaneWidth>("default");
  const state = usePlannerState();
  const option = options.find((entry) => entry.id === optionId) ?? options[0];
  const Pane = PANES[option.id];

  useEffect(() => {
    const url = new URL(window.location.href);
    url.searchParams.set("option", option.id);
    if (view === "workspace") url.searchParams.delete("view");
    else url.searchParams.set("view", view);
    window.history.replaceState(null, "", url);
  }, [option.id, view]);

  return (
    <main className="ipp-page">
      <div className="ipp-wrap">
        <LabNavigation detail labId={LAB_ID} />
        <header className="ipp-header">
          <div>
            <p className="ipp-kicker"><ListChecks size={16} /> Itinerary pane look and feel</p>
            <h1>A sleeker<br />itinerary pane.</h1>
            <p className="ipp-lede">
              Today's pane is complete but long and dense: every fact is printed at the same volume, in a box, above another box.
              These five options keep every rating, must-visit score, summary, travel leg and control, and change only how the pane
              looks and reads. Three change the pane alone; two also retune the workspace finish around it so the itinerary blends
              in, without moving any pane or control.
            </p>
          </div>
          <div className="ipp-principle">
            <span>The design test</span>
            <strong>Every fact stays.<br />Less effort to read it.</strong>
            <small>Same fixture · same controls · five visual languages</small>
          </div>
        </header>

        <LabScope labId={LAB_ID} />
        <OptionContrast labId={LAB_ID} />

        <section className="ipp-section" aria-label="Options">
          <p className="ipp-kicker">Five options, best first</p>
          <div className="ipp-options">
            {options.map((entry) => (
              <button key={entry.id} type="button" className={`ipp-option ${entry.id === option.id ? "selected" : ""}`} onClick={() => setOptionId(entry.id)} aria-pressed={entry.id === option.id}>
                <span className="ipp-option-top"><i>{entry.label}</i><em>{entry.score}/100</em></span>
                <span className={`ipp-badge ${entry.chrome === "today" ? "pane" : "workspace"}`}>{entry.eyebrow}</span>
                <strong>{entry.summary}</strong>
                <p><b>Exact delta:</b> {entry.delta}</p>
              </button>
            ))}
          </div>
        </section>

        <section className="ipp-section" aria-label="Fact matrix">
          <p className="ipp-kicker">Nothing is removed — where each fact lives</p>
          <FactMatrix />
        </section>

        <section className="ipp-preview-head">
          <div>
            <p className="ipp-kicker">Production-scale preview · 1440 × 900</p>
            <h2>{view === "today" ? "Today · production ItineraryPanel" : option.label}</h2>
            <p>
              {view === "today"
                ? "The unmodified production component rendered with the same fixture, so every option can be compared against what ships today."
                : <><b>Exact delta:</b> {option.delta}</>}
            </p>
          </div>
        </section>
        <div className="ipp-controls">
          <Segmented<View> label="View" value={view} onChange={setView} choices={[["workspace", "In workspace"], ["compare", "Side by side with today"], ["today", "Today only"]]} />
          {view === "workspace" && <Segmented<PaneWidth> label="Pane width" value={width} onChange={setWidth} choices={[["narrow", "340 px"], ["default", "27%"], ["wide", "38%"], ["maximized", "Maximized"]]} />}
          <Segmented label="Plan checks" value={state.scenario} onChange={state.setScenario} choices={[["gaps", "Gaps"], ["contradiction", "Contradiction"]]} />
          <span className="ipp-action" role="status" aria-live="polite">Last action · {state.lastAction}</span>
        </div>
        <div className="ipp-stage">
          {view === "compare" ? (
            <div className="ipp-compare">
              <figure><figcaption>Today</figcaption><div className="frame"><PaneFrame chrome="today" state={state}><TodayPane state={state} /></PaneFrame></div></figure>
              <figure><figcaption>{option.label}</figcaption><div className="frame"><PaneFrame chrome={option.chrome} state={state}><Pane state={state} /></PaneFrame></div></figure>
            </div>
          ) : (
            <Workspace
              chrome={view === "today" ? "today" : option.chrome}
              state={state}
              width={width}
              onWidth={setWidth}
              itinerary={view === "today" ? <TodayPane state={state} /> : <Pane state={state} />}
            />
          )}
        </div>

        <DecisionCapture
          labId={LAB_ID}
          labTitle="A sleeker itinerary pane"
          options={options.map(({ id, label }) => ({ id, label }))}
          activeOption={option.id}
          onChoose={(id) => setOptionId(id as OptionId)}
        />
      </div>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<App />);
