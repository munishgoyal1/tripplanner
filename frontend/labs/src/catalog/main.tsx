import React, { useEffect, useState } from "react";
import ReactDOM from "react-dom/client";
import { Archive, FlaskConical } from "lucide-react";
import "../../../src/index.css";
import { LabNavigation } from "../shared/LabNavigation";
import { LabRecordCard } from "../shared/LabRecordCard";
import { activeLabs, completedLabs, locallyCompletedLabs, type LabSelectionState } from "../shared/labRecords";

function LabCatalog() {
  const activeOnly = new URLSearchParams(window.location.search).get("view") === "active";
  const [selections, setSelections] = useState<Record<string, LabSelectionState>>({});

  useEffect(() => {
    fetch("/__labs/selections")
      .then((response) => response.ok ? response.json() : {})
      .then((saved: Record<string, LabSelectionState>) => setSelections(saved))
      .catch(() => undefined);
  }, []);

  const visibleLabs = activeLabs.filter((lab) => !["parked", "completed", "discarded"].includes(selections[lab.id]?.disposition || ""));
  const parkedLabs = activeLabs.filter((lab) => selections[lab.id]?.disposition === "parked");
  const allCompletedLabs = [...locallyCompletedLabs(selections), ...completedLabs];
  return (
    <main className="min-h-full bg-[linear-gradient(180deg,#f8fafc_0,#fafaf9_20rem)] px-4 py-8 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-5xl">
        <header className="flex flex-wrap items-end justify-between gap-5 border-b border-slate-200 pb-6">
          <div>
            <div className="flex items-center gap-2 text-brand"><FlaskConical size={18} aria-hidden /><p className="text-xs font-bold uppercase">Internal design workshop</p></div>
            <h1 className="display mt-2 text-3xl font-semibold text-ink sm:text-4xl">{activeOnly ? "UX Labs in progress" : "Tripplanner UX Labs"}</h1>
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-600">{activeOnly ? "Current choices that still need evaluation, organized for quick comparison." : "Current experiments and preserved decisions in one concise index."}</p>
          </div>
          <LabNavigation current={activeOnly ? "active" : "catalog"} />
        </header>

        <section className="mt-7" aria-labelledby="active-labs">
          <div className="flex items-end justify-between gap-4">
            <div>
              <p className="text-[10px] font-bold uppercase text-brand">In evaluation</p>
              <h2 id="active-labs" className="mt-0.5 text-lg font-semibold text-ink">Active experiments</h2>
            </div>
            <span className="text-xs text-slate-400">{visibleLabs.length} open</span>
          </div>
          <div className="mt-3 overflow-hidden rounded-md ring-1 ring-slate-200">
            {visibleLabs.map((lab, index) => <LabRecordCard key={lab.id} lab={lab} index={index + 1} compact state={selections[lab.id]?.disposition === "ready" ? "ready" : undefined} />)}
          </div>
        </section>

        {!activeOnly && (
          <>
          {parkedLabs.length > 0 && <section className="mt-10" aria-labelledby="parked-labs-title">
            <div className="flex items-end justify-between gap-4">
              <div><p className="text-[10px] font-bold uppercase text-amber-700">Saved for later</p><h2 id="parked-labs-title" className="mt-0.5 text-lg font-semibold text-ink">Parked experiments</h2></div>
              <span className="text-xs text-slate-400">{parkedLabs.length} parked</span>
            </div>
            <div className="mt-3 overflow-hidden rounded-md ring-1 ring-slate-200">
              {parkedLabs.map((lab, index) => <LabRecordCard key={lab.id} lab={lab} index={index + 1} compact state="parked" />)}
            </div>
          </section>}
          <section className="mt-10" aria-labelledby="completed-labs-title">
            <div className="flex items-end justify-between gap-4">
              <div>
                <p className="flex items-center gap-1 text-[10px] font-bold uppercase text-emerald-700"><Archive size={12} aria-hidden /> Decision recorded</p>
                <h2 id="completed-labs-title" className="mt-0.5 text-lg font-semibold text-ink">Completed experiments</h2>
              </div>
              <a href="./completed-labs.html" className="text-xs font-semibold text-emerald-700 hover:text-emerald-900">Open archive</a>
            </div>
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              {allCompletedLabs.map((lab) => <LabRecordCard key={lab.id} lab={lab} completed />)}
            </div>
          </section>
          </>
        )}
      </div>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><LabCatalog /></React.StrictMode>);