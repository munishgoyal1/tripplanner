import React from "react";
import ReactDOM from "react-dom/client";
import { Archive, CheckCircle2 } from "lucide-react";
import "../../../src/index.css";
import { LabNavigation } from "../shared/LabNavigation";
import { LabRecordCard } from "../shared/LabRecordCard";
import { completedLabs } from "../shared/labRecords";

function CompletedLabs() {
  return (
    <main className="min-h-full bg-[linear-gradient(180deg,#f0fdf4_0,#fafaf9_22rem)] px-4 py-8 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-5xl">
        <header className="flex flex-wrap items-end justify-between gap-5 border-b border-emerald-200 pb-6">
          <div>
            <div className="flex items-center gap-2 text-emerald-700"><Archive size={18} aria-hidden /><p className="text-xs font-bold uppercase">Preserved design decisions</p></div>
            <h1 className="display mt-2 text-3xl font-semibold text-ink sm:text-4xl">Completed UX Labs</h1>
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-600">Implemented and decided experiments remain browsable with their original alternatives and rationale.</p>
          </div>
          <LabNavigation current="completed" />
        </header>

        <section className="mt-7" aria-labelledby="completed-labs-title">
          <div className="flex items-end justify-between gap-4">
            <div>
              <p className="flex items-center gap-1 text-[10px] font-bold uppercase text-emerald-700"><CheckCircle2 size={12} aria-hidden /> Decision recorded</p>
              <h2 id="completed-labs-title" className="mt-0.5 text-lg font-semibold text-ink">Shipped and preserved</h2>
            </div>
            <span className="text-xs text-slate-400">{completedLabs.length} completed</span>
          </div>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            {completedLabs.map((lab) => <LabRecordCard key={lab.title} lab={lab} completed />)}
          </div>
          <p className="mt-4 text-xs leading-relaxed text-slate-400">The workspace-shell comparison predates standalone Lab pages, so its page reconstructs the preserved branch decision. Newer completed experiments retain their original interactive comparisons.</p>
        </section>
      </div>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><CompletedLabs /></React.StrictMode>);