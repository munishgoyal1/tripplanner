import React from "react";
import ReactDOM from "react-dom/client";
import { FlaskConical } from "lucide-react";
import "../../../src/index.css";
import { LabNavigation } from "../shared/LabNavigation";
import { LabRecordCard } from "../shared/LabRecordCard";
import { activeLabs } from "../shared/labRecords";

function LabCatalog() {
  return (
    <main className="min-h-full bg-[linear-gradient(180deg,#f8fafc_0,#fafaf9_20rem)] px-4 py-8 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-5xl">
        <header className="flex flex-wrap items-end justify-between gap-5 border-b border-slate-200 pb-6">
          <div>
            <div className="flex items-center gap-2 text-brand"><FlaskConical size={18} aria-hidden /><p className="text-xs font-bold uppercase">Internal design workshop</p></div>
            <h1 className="display mt-2 text-3xl font-semibold text-ink sm:text-4xl">UX Labs in progress</h1>
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-600">Current choices that still need evaluation. Completed decisions now live in their own preserved archive.</p>
          </div>
          <LabNavigation current="catalog" />
        </header>

        <section className="mt-7" aria-labelledby="active-labs">
          <div className="flex items-end justify-between gap-4">
            <div>
              <p className="text-[10px] font-bold uppercase text-brand">In evaluation</p>
              <h2 id="active-labs" className="mt-0.5 text-lg font-semibold text-ink">Active experiments</h2>
            </div>
            <span className="text-xs text-slate-400">{activeLabs.length} open</span>
          </div>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            {activeLabs.map((lab) => <LabRecordCard key={lab.title} lab={lab} />)}
          </div>
        </section>
      </div>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><LabCatalog /></React.StrictMode>);