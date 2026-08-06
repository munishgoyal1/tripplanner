import React from "react";
import ReactDOM from "react-dom/client";
import { FlaskConical } from "lucide-react";
import "../../../src/index.css";
import { LabNavigation } from "../shared/LabNavigation";
import { LabRecordCard } from "../shared/LabRecordCard";
import { allLabs, effectiveLabDisposition, resolvedLabRecord, type LabDisposition } from "../shared/labRecords";
import { useLabSelections } from "../shared/useLabSelections";

function LabCatalog() {
  const requestedView = new URLSearchParams(window.location.search).get("view");
  const currentView = requestedView === "active" || requestedView === "implemented-review" || requestedView === "parked" ? requestedView : "catalog";
  const showActive = currentView === "catalog" || currentView === "active";
  const showReview = currentView === "catalog" || currentView === "implemented-review";
  const showParked = currentView === "catalog" || currentView === "parked";
  const { selections, status } = useLabSelections();

  const labsFor = (dispositions: LabDisposition[]) => status === "loaded"
    ? allLabs
        .filter((lab) => dispositions.includes(effectiveLabDisposition(lab, selections[lab.id])))
        .sort((first, second) => second.labNumber - first.labNumber)
    : [];
  const visibleLabs = labsFor(["ready"]);
  const reviewLabs = labsFor(["implemented-review"]);
  const parkedLabs = labsFor(["parked"]);
  const title = currentView === "active" ? "UX Labs in progress" : currentView === "implemented-review" ? "Implemented UX Labs for review" : currentView === "parked" ? "Parked UX Labs" : "All Open UX Labs";
  const subtitle = currentView === "active" ? "Open evaluations and approved handoffs still in progress." : currentView === "implemented-review" ? "Production implementations waiting for owner review and sign-off." : currentView === "parked" ? "Saved evaluations waiting for a later decision, with their handoff intact." : "Every Lab not yet completed, grouped by its authoritative lifecycle state.";
  return (
    <main className="min-h-full bg-[linear-gradient(180deg,#f8fafc_0,#fafaf9_20rem)] px-4 py-8 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-5xl">
        <header className="flex flex-wrap items-end justify-between gap-5 border-b border-slate-200 pb-6">
          <div>
            <div className="flex items-center gap-2 text-brand"><FlaskConical size={18} aria-hidden /><p className="text-xs font-bold uppercase">Internal design workshop</p></div>
            <h1 className="display mt-2 text-3xl font-semibold text-ink sm:text-4xl">{title}</h1>
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-600">{subtitle}</p>
          </div>
          <LabNavigation current={currentView} />
        </header>

        {status !== "loaded" && <p role={status === "error" ? "alert" : "status"} className={`mt-7 rounded-md px-4 py-3 text-sm ring-1 ${status === "error" ? "bg-rose-50 text-rose-800 ring-rose-200" : "bg-white text-slate-500 ring-slate-200"}`}>{status === "error" ? "Lab decisions are unavailable. No lifecycle state has been inferred; restart the Labs server and reload." : "Loading saved Lab decisions…"}</p>}

        {showActive && status === "loaded" && <section className="mt-7" aria-labelledby="active-labs">
          <div className="flex items-end justify-between gap-4">
            <div>
              <p className="text-[10px] font-bold uppercase text-brand">Open work</p>
              <h2 id="active-labs" className="mt-0.5 text-lg font-semibold text-ink">In-progress experiments</h2>
            </div>
            <span className="text-xs text-slate-400">{status === "loaded" ? visibleLabs.length : "—"} open</span>
          </div>
          <div className="mt-3 overflow-hidden rounded-md ring-1 ring-slate-200">
            {visibleLabs.map((lab) => {
              const disposition = effectiveLabDisposition(lab, selections[lab.id]);
              return <LabRecordCard key={lab.id} lab={resolvedLabRecord(lab, selections[lab.id])} compact state={disposition} selection={selections[lab.id]} />;
            })}
          </div>
        </section>}

        {showReview && status === "loaded" && (currentView === "implemented-review" || reviewLabs.length > 0) && <section className={currentView === "implemented-review" ? "mt-7" : "mt-10"} aria-labelledby="review-labs-title">
          <div className="flex items-end justify-between gap-4">
            <div><p className="text-[10px] font-bold uppercase text-sky-700">Owner validation</p><h2 id="review-labs-title" className="mt-0.5 text-lg font-semibold text-ink">Implemented - To be reviewed</h2></div>
            <span className="text-xs text-slate-400">{reviewLabs.length} awaiting review</span>
          </div>
          <div className="mt-3 overflow-hidden rounded-md ring-1 ring-slate-200">
            {reviewLabs.map((lab) => <LabRecordCard key={lab.id} lab={resolvedLabRecord(lab, selections[lab.id])} compact state="implemented-review" selection={selections[lab.id]} />)}
          </div>
        </section>}

        {showParked && status === "loaded" && (currentView === "parked" || parkedLabs.length > 0) && <section className={currentView === "parked" ? "mt-7" : "mt-10"} aria-labelledby="parked-labs-title">
            <div className="flex items-end justify-between gap-4">
              <div><p className="text-[10px] font-bold uppercase text-amber-700">Saved for later</p><h2 id="parked-labs-title" className="mt-0.5 text-lg font-semibold text-ink">Parked experiments</h2></div>
              <span className="text-xs text-slate-400">{parkedLabs.length} parked</span>
            </div>
            <div className="mt-3 overflow-hidden rounded-md ring-1 ring-slate-200">
              {parkedLabs.map((lab) => <LabRecordCard key={lab.id} lab={resolvedLabRecord(lab, selections[lab.id])} compact state="parked" selection={selections[lab.id]} />)}
            </div>
          </section>}
      </div>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><LabCatalog /></React.StrictMode>);