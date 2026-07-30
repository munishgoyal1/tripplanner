import React from "react";
import ReactDOM from "react-dom/client";
import {
  ArrowRight,
  Check,
  Clock3,
  FlaskConical,
  LayoutPanelTop,
  ListChecks,
  MessageCircle,
} from "lucide-react";
import "../../../src/index.css";

interface LabRecord {
  title: string;
  description: string;
  date: string;
  status: string;
  href?: string;
  decision?: string;
  icon: typeof ListChecks;
}

const activeLabs: LabRecord[] = [
  {
    title: "Assistant-led trip kickoff",
    description: "Compare overlay footprints and test preference-aware, pre-filled inputs before the first itinerary build.",
    date: "30 Jul 2026",
    status: "In evaluation",
    decision: "Open · Recommended starting point: B · Focus overlay.",
    href: "/labs/chat-assistant.html",
    icon: MessageCircle,
  },
  {
    title: "Compact itinerary density",
    description: "Compare one-line, circuit-header, and progressive-focus agendas inside a 320 px day frame.",
    date: "30 Jul 2026",
    status: "In evaluation",
    decision: "Open experiment · B starts as the recommended direction.",
    href: "/labs/itinerary-density.html",
    icon: ListChecks,
  },
];

const decidedLabs: LabRecord[] = [
  {
    title: "Itinerary row design",
    description: "Compare Journey Timeline, Compact Agenda, and Guided Place Cards for each scheduled stop.",
    date: "29 Jul 2026",
    status: "Implemented",
    decision: "B · Compact Agenda, paired with C · Compact Brief.",
    href: "/labs/itinerary-information.html",
    icon: ListChecks,
  },
  {
    title: "Itinerary summary design",
    description: "Compare Editorial, Balanced, and Compact modifications of Narrative Brief above Compact Agenda.",
    date: "29 Jul 2026",
    status: "Implemented",
    decision: "C · Compact Brief with explicit travel rhythm, day plan, and booking readiness.",
    href: "/labs/itinerary-summary.html",
    icon: LayoutPanelTop,
  },
  {
    title: "Workspace shell layout",
    description: "Compared map-first, story-first, and compact-mobile workspace structures on experiment branches.",
    date: "23 Jul 2026",
    status: "Decided",
    decision: "Layout C: map-first canvas, details-first rail, and compact lower-right Assistant.",
    href: "/labs/workspace-shell.html",
    icon: LayoutPanelTop,
  },
];

function LabCard({ lab, archived = false }: { lab: LabRecord; archived?: boolean }) {
  const Icon = lab.icon;
  const content = (
    <>
      <div className="flex items-start gap-3">
        <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-md ${archived ? "bg-emerald-50 text-emerald-700" : "bg-brand-50 text-brand"}`}>
          <Icon size={17} aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold text-ink">{lab.title}</h3>
            <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ring-1 ${archived ? "bg-emerald-50 text-emerald-700 ring-emerald-200" : "bg-amber-50 text-amber-700 ring-amber-200"}`}>{lab.status}</span>
          </div>
          <p className="mt-1 text-xs leading-relaxed text-slate-500">{lab.description}</p>
        </div>
        {lab.href && <ArrowRight size={16} className="mt-1 shrink-0 text-slate-400" aria-hidden />}
      </div>
      <div className="mt-4 border-t border-slate-100 pt-3">
        <p className="text-xs font-medium text-slate-700">{lab.decision}</p>
        <p className="mt-1 flex items-center gap-1 text-[11px] text-slate-400"><Clock3 size={11} aria-hidden /> {lab.date}</p>
      </div>
    </>
  );

  const className = "block rounded-md bg-white p-4 shadow-card ring-1 ring-slate-200 transition";
  return lab.href ? (
    <a href={lab.href} className={`${className} hover:-translate-y-0.5 hover:shadow-pop hover:ring-brand/30`}>{content}</a>
  ) : (
    <article className={className}>{content}</article>
  );
}

function LabCatalog() {
  return (
    <main className="min-h-full bg-[linear-gradient(180deg,#f8fafc_0,#fafaf9_20rem)] px-4 py-8 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-5xl">
        <header className="border-b border-slate-200 pb-6">
          <div className="flex items-center gap-2 text-brand">
            <FlaskConical size={18} aria-hidden />
            <p className="text-xs font-bold uppercase">Internal design archive</p>
          </div>
          <h1 className="display mt-2 text-3xl font-semibold text-ink sm:text-4xl">UX Labs</h1>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-600">One catalog for current design choices and the experiments that shaped the product.</p>
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
            {activeLabs.map((lab) => <LabCard key={lab.title} lab={lab} />)}
          </div>
        </section>

        <section className="mt-10" aria-labelledby="decided-labs">
          <div className="flex items-end justify-between gap-4">
            <div>
              <p className="flex items-center gap-1 text-[10px] font-bold uppercase text-emerald-700"><Check size={11} aria-hidden /> Preserved decisions</p>
              <h2 id="decided-labs" className="mt-0.5 text-lg font-semibold text-ink">Already decided</h2>
            </div>
            <span className="text-xs text-slate-400">{decidedLabs.length} recorded</span>
          </div>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            {decidedLabs.map((lab) => <LabCard key={lab.title} lab={lab} archived />)}
          </div>
          <p className="mt-3 text-xs text-slate-400">The workspace-shell comparison predates standalone lab pages, so its linked page is a reconstructed read-only record based on preserved branches. Newer decided experiments retain their original interactive pages.</p>
        </section>
      </div>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><LabCatalog /></React.StrictMode>);