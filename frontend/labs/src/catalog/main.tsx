import React from "react";
import ReactDOM from "react-dom/client";
import { FlaskConical } from "lucide-react";
import "../../../src/index.css";
import { LabNavigation } from "../shared/LabNavigation";
import { LabRecordCard } from "../shared/LabRecordCard";
import { activeLabs } from "../shared/labRecords";
import { useLabSelections } from "../shared/useLabSelections";

function LabCatalog() {
  const activeOnly = new URLSearchParams(window.location.search).get("view") === "active";
  const { selections, status } = useLabSelections();

  const visibleLabs = status === "loaded" ? activeLabs.filter((lab) => !["parked", "completed", "discarded"].includes(selections[lab.id]?.disposition || "")) : [];
  const parkedLabs = status === "loaded" ? activeLabs.filter((lab) => selections[lab.id]?.disposition === "parked") : [];
  return (
    <main className="min-h-full bg-[linear-gradient(180deg,#f8fafc_0,#fafaf9_20rem)] px-4 py-8 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-5xl">
        <header className="flex flex-wrap items-end justify-between gap-5 border-b border-slate-200 pb-6">
          <div>
            <div className="flex items-center gap-2 text-brand"><FlaskConical size={18} aria-hidden /><p className="text-xs font-bold uppercase">Internal design workshop</p></div>
            <h1 className="display mt-2 text-3xl font-semibold text-ink sm:text-4xl">{activeOnly ? "UX Labs in progress" : "Tripplanner UX Labs"}</h1>
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-600">Current choices that still need evaluation, organized for quick comparison.</p>
          </div>
          <LabNavigation current={activeOnly ? "active" : "catalog"} />
        </header>

        <section className="mt-7" aria-labelledby="active-labs">
          <div className="flex items-end justify-between gap-4">
            <div>
              <p className="text-[10px] font-bold uppercase text-brand">In evaluation</p>
              <h2 id="active-labs" className="mt-0.5 text-lg font-semibold text-ink">Active experiments</h2>
            </div>
            <span className="text-xs text-slate-400">{status === "loaded" ? visibleLabs.length : "—"} open</span>
          </div>
          {status !== "loaded" && <p role={status === "error" ? "alert" : "status"} className={`mt-3 rounded-md px-4 py-3 text-sm ring-1 ${status === "error" ? "bg-rose-50 text-rose-800 ring-rose-200" : "bg-white text-slate-500 ring-slate-200"}`}>{status === "error" ? "Lab decisions are unavailable. No lifecycle state has been inferred; restart the Labs server and reload." : "Loading saved Lab decisions…"}</p>}
          {status === "loaded" && <div className="mt-3 overflow-hidden rounded-md ring-1 ring-slate-200">
            {visibleLabs.map((lab, index) => <LabRecordCard key={lab.id} lab={lab} index={index + 1} compact state={selections[lab.id]?.disposition === "ready" ? "ready" : undefined} />)}
          </div>}
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
          </>
        )}
      </div>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><LabCatalog /></React.StrictMode>);