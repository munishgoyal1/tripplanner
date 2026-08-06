import React, { useCallback, useState } from "react";
import ReactDOM from "react-dom/client";
import { ArrowLeft, FileText, Lock, Maximize2 } from "lucide-react";
import "../../../src/index.css";
import { DecisionCapture } from "../shared/DecisionCapture";
import { LabNavigation } from "../shared/LabNavigation";
import { LabScope } from "../shared/LabScope";
import { OptionContrast } from "../shared/OptionContrast";
import "../shared/experiment-layout.css";
import { DocumentsWorkspace } from "./DocumentsWorkspace";
import type { DocumentsOption } from "./DocumentsWorkspace";
import { readinessChecks } from "./fixture";

const LAB_ID = "travel-documents";

const variants: Array<{ id: DocumentsOption; label: string; summary: string; delta: string }> = [
  {
    id: "vault",
    label: "B · Account vault, trip shows gaps",
    summary:
      "Traveller details live permanently in Account, because they outlive any trip. The trip carries one honest badge — two documents to fix — that opens the vault focused on this trip's gaps. Details stays where it was.",
    delta:
      "Two homes matched to two lifetimes: a passport is yours, a booking reference is the trip's. The trip never turns into a document manager, but the answer is one click away instead of already on screen.",
  },
  {
    id: "readiness",
    label: "A · Trip readiness rail",
    summary:
      "The trip's third pane becomes Readiness. Blockers first, then every traveller with what is on file, then the checks that already pass. You add a document from the row that is missing it, and review it in place without leaving the trip.",
    delta:
      "The trip owns the whole subject. One place to look, nothing to manage elsewhere — at the cost of the Details pane, which is where you decide about the place you are looking at.",
  },
  {
    id: "inbox",
    label: "C · Document inbox",
    summary:
      "One dock at the bottom takes anything you drop — boarding pass, hotel mail, passport photo. Items land as Needs review, get read in the background, and route themselves: bookings to their stop, identity to the traveller.",
    delta:
      "You can empty your inbox of six attachments in one gesture and triage later. The cost is a second queue that can grow stale, and a trip that looks ready while three unreviewed items sit in the dock.",
  },
];

const kept = [
  {
    field: "Issuing country",
    why: "Decides whether a visa is needed at all.",
    keep: "Kept",
  },
  {
    field: "Expiry date",
    why: "Drives the validity rule for the destination and the renewal warning.",
    keep: "Kept",
  },
  {
    field: "Date of birth",
    why: "Child fares, age limits, minor-consent rules.",
    keep: "Kept",
  },
  {
    field: "Visa type, window, entries",
    why: "Decides whether this trip fits inside the visa you already hold.",
    keep: "Kept",
  },
  {
    field: "Insurance cover and assistance line",
    why: "Checks the destination minimum and gives you a number to call.",
    keep: "Kept",
  },
  {
    field: "Identity document number",
    why: "Needed by no check. The last four are enough to tell two passports apart.",
    keep: "Last four only",
  },
  {
    field: "Provider references",
    why: "Booking, policy and loyalty numbers exist to be quoted, so they are kept whole.",
    keep: "Kept",
  },
  {
    field: "The photo, scan or PDF",
    why: "Answers nothing once the fields are read, and is the only part worth stealing.",
    keep: "Never stored",
  },
];

const lifetimes = [
  {
    title: "Yours, and permanent",
    body: "Passport, visa, insurance, vaccination. Captured once, reused by every future trip. Asking for the same passport again next year is the failure this feature exists to prevent.",
    tone: "accent",
  },
  {
    title: "The trip's, and disposable",
    body: "Flight confirmations, hotel references, timed-entry codes. They attach to one stop on one day, and they stop mattering the moment the trip ends.",
    tone: "brand",
  },
];

const requirements = [
  "The original file is read once and discarded. Only the extracted fields persist, and an identity number persists as its last four digits.",
  "Extraction never writes to the trip on its own. Every field is shown for confirmation first, with the confidence that produced it.",
  "Details captured once are reused on the next trip without asking again, and the reuse is visible — 'Reused from Kyoto, Mar 2026'.",
  "Deterministic checks — validity windows, cover amounts, date arithmetic — are computed in code, never inferred by the model.",
  "Eligibility claims are grounded in a live source and carry the source and the date they were checked.",
  "A booking document attaches to the exact day and stop it belongs to, and marks that stop booked.",
  "Every stored detail can be viewed, corrected and deleted from one place, and delete means gone.",
  "Nothing from this feature ever enters a share link, whatever the export settings say.",
];

const criteria = [
  { title: "Second-trip cost", detail: "On the next trip, how much is the owner asked for again? The correct answer is nothing." },
  { title: "Blocker legibility", detail: "Does the owner understand why Priya's passport fails, without reading a rule number?" },
  { title: "Time to first value", detail: "From landing on the trip, how long until the real problem — two people cannot travel — is visible?" },
  { title: "Clutter cost", detail: "What does the surface cost when everything is already in order, which is the common case?" },
  { title: "Trust in extraction", detail: "Is it obvious what was read, how sure it was, and that the file itself is gone?" },
  { title: "Recovery", detail: "A wrong expiry was saved. How many steps to find and fix it?" },
];

const guardrails = [
  "No original document is written to storage, so there is nothing to leak, expire or rotate.",
  "Only the last four digits of an identity number are stored, so no export, reveal or breach can produce the rest. Provider references stay whole, because quoting them is their purpose.",
  "sanitize_plan stays an allowlist. No document field is ever added to it, so share links cannot regress into leaking identity data.",
  "Account privacy deletion must remove these records too; a privacy wipe that reports success while details survive is worse than no wipe.",
  "Guests cannot store identity details. A capability credential is not an identity.",
  "Insurance, vaccination and licence details follow the same rule as passports: fields in, file out.",
];

const outOfScope = [
  "Storing or rendering the original scan, photo or PDF.",
  "Word documents in v1 — PDF, JPEG, PNG, HEIC and pasted text cover every real case.",
  "Payment instruments of any kind. Card numbers have no planning value and unbounded downside.",
  "Filling or submitting a visa application on the owner's behalf.",
];

function useQueryPreview(): DocumentsOption | null {
  const requested = new URLSearchParams(window.location.search).get("preview");
  const match = variants.find((variant) => variant.id === requested);
  return match ? match.id : null;
}

function Lab() {
  const previewOption = useQueryPreview();
  const [option, setOption] = useState<DocumentsOption>("vault");
  const handleChoose = useCallback((next: string) => {
    const match = variants.find((variant) => variant.id === next);
    if (match) setOption(match.id);
  }, []);

  if (previewOption) {
    return (
      <div className="h-[100dvh] w-full">
        <a
          href="./lab-20-travel-documents.html"
          className="fixed bottom-4 right-4 z-[100] inline-flex items-center gap-1.5 rounded-full bg-ink px-3 py-2 text-xs font-semibold text-white shadow-pop"
        >
          <ArrowLeft size={13} aria-hidden /> Exit full-size preview
        </a>
        <DocumentsWorkspace option={previewOption} />
      </div>
    );
  }

  return (
    <main className="min-h-full bg-[linear-gradient(180deg,#f8fafc_0,#fafaf9_24rem)] px-4 py-6 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-[92rem]">
        <LabNavigation detail labId={LAB_ID} />

        <header className="mt-5 border-b border-slate-200 pb-6">
          <div className="flex items-center gap-2 text-brand">
            <FileText size={18} aria-hidden />
            <p className="text-xs font-bold uppercase">Travel documents</p>
          </div>
          <h1 className="display mt-2 text-3xl font-semibold text-ink sm:text-4xl">
            Where travel documents live, and what we refuse to keep
          </h1>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-600">
            Bookings, passports, visas and insurance all arrive as files, and today none of them have a home. The
            planner cannot tell you that one passport expires too soon, cannot put your confirmation number in the
            export, and asks for the same documents again on the next trip. This lab is about where that lives — and
            it is deliberately not about becoming a document locker.
          </p>
          <p className="mt-3 flex max-w-3xl items-start gap-2 rounded-2xl bg-white p-3.5 text-sm leading-relaxed text-ink shadow-card ring-1 ring-slate-200">
            <Lock size={15} className="mt-0.5 shrink-0 text-brand" aria-hidden />
            <span>
              <span className="font-semibold">Decided: we never store the document.</span> A passport photo is read
              once, the fields we can actually use are kept, and the file is deleted. Those fields are what get reused
              next year, so you are never asked to upload the same passport twice — and a breach of this app leaks four
              digits and an expiry date, not a scan of your identity.
            </span>
          </p>
        </header>

        <LabScope labId={LAB_ID} />
        <OptionContrast labId={LAB_ID} />

        <section className="mt-8">
          <p className="text-[10px] font-bold uppercase text-brand">The retention rule</p>
          <h2 className="mt-1 text-lg font-semibold text-ink">Every field earns its place, or it is not kept</h2>
          <div className="mt-3 overflow-hidden rounded-2xl bg-white shadow-card ring-1 ring-slate-200">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-[10px] font-bold uppercase text-slate-500">
                <tr>
                  <th className="px-3 py-2">What we read</th>
                  <th className="px-3 py-2">What it answers</th>
                  <th className="px-3 py-2">Retention</th>
                </tr>
              </thead>
              <tbody>
                {kept.map((row) => (
                  <tr key={row.field} className="border-t border-slate-100">
                    <td className="px-3 py-2 font-semibold text-ink">{row.field}</td>
                    <td className="px-3 py-2 text-slate-600">{row.why}</td>
                    <td className="px-3 py-2">
                      <span
                        className={`pill ${
                          row.keep === "Never stored"
                            ? "bg-rose-50 text-rose-700"
                            : row.keep === "Last four only"
                              ? "bg-amber-50 text-amber-800"
                              : "bg-emerald-50 text-emerald-700"
                        }`}
                      >
                        {row.keep}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="mt-8">
          <p className="text-[10px] font-bold uppercase text-brand">Two things, not one</p>
          <h2 className="mt-1 text-lg font-semibold text-ink">The word "document" hides two different lifetimes</h2>
          <div className="mt-3 grid gap-3 lg:grid-cols-2">
            {lifetimes.map((item) => (
              <article key={item.title} className="rounded-2xl bg-white p-4 shadow-card ring-1 ring-slate-200">
                <p className={`text-sm font-semibold ${item.tone === "accent" ? "text-accent" : "text-brand"}`}>
                  {item.title}
                </p>
                <p className="mt-1.5 text-xs leading-relaxed text-slate-600">{item.body}</p>
              </article>
            ))}
          </div>
          <p className="mt-2 max-w-3xl text-xs leading-relaxed text-slate-500">
            The three options below disagree about exactly one thing: whether those two lifetimes deserve two homes,
            one home, or one door.
          </p>
        </section>

        <section className="mt-8">
          <p className="text-[10px] font-bold uppercase text-brand">The checks this unlocks</p>
          <h2 className="mt-1 text-lg font-semibold text-ink">Real answers on the Lisbon trip in the preview</h2>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {readinessChecks.map((check) => (
              <div key={check.id} className="flex gap-2.5 rounded-2xl bg-white p-3 shadow-card ring-1 ring-slate-200">
                <span
                  className={`mt-1 h-2 w-2 shrink-0 rounded-full ${
                    check.severity === "blocker" ? "bg-rose-500" : check.severity === "warning" ? "bg-amber-500" : "bg-emerald-500"
                  }`}
                  aria-hidden
                />
                <div className="min-w-0">
                  <p className="text-xs font-semibold text-ink">{check.title}</p>
                  <p className="mt-0.5 text-[11px] leading-relaxed text-slate-600">{check.detail}</p>
                  <p className="mt-1 text-[10px] font-medium text-slate-500">
                    {check.origin === "computed" ? "Computed in code · " : "Grounded · "}
                    <span className="font-mono">{check.origin === "computed" ? check.rule : check.source}</span>
                  </p>
                </div>
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
          <div className="lab-variant-grid" role="tablist" aria-label="Travel document placement options">
            {variants.map((variant) => (
              <button
                key={variant.id}
                type="button"
                role="tab"
                aria-selected={option === variant.id}
                onClick={() => setOption(variant.id)}
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
                {variants.find((variant) => variant.id === option)?.label}
              </h2>
              <p className="mt-1 max-w-2xl text-xs text-slate-500">
                {variants.find((variant) => variant.id === option)?.delta}
              </p>
              <p className="mt-1.5 max-w-2xl text-xs text-slate-500">
                Add Aarav's passport to watch the capture run end to end — read, extract, confirm each field, save,
                discard the file. Then open Export to see how documents behave when they leave the app.
              </p>
            </div>
            <a
              href={`./lab-20-travel-documents.html?preview=${option}`}
              className="inline-flex h-9 items-center gap-1.5 rounded-full bg-white px-3 text-xs font-semibold text-slate-600 ring-1 ring-slate-200 transition hover:ring-slate-300"
            >
              <Maximize2 size={13} aria-hidden /> Full-size preview
            </a>
          </div>
          <div className="mt-3 h-[46rem] overflow-hidden rounded-2xl shadow-pop ring-1 ring-slate-200">
            <DocumentsWorkspace key={option} option={option} />
          </div>
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

        <section className="mt-9 grid gap-6 lg:grid-cols-2">
          <div>
            <p className="text-[10px] font-bold uppercase text-brand">Guardrails</p>
            <ul className="mt-3 space-y-1.5">
              {guardrails.map((guardrail) => (
                <li key={guardrail} className="flex gap-2 text-sm leading-relaxed text-slate-600">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-brand" aria-hidden />
                  {guardrail}
                </li>
              ))}
            </ul>
          </div>
          <div>
            <p className="text-[10px] font-bold uppercase text-brand">Out of scope</p>
            <ul className="mt-3 space-y-1.5">
              {outOfScope.map((item) => (
                <li key={item} className="flex gap-2 text-sm leading-relaxed text-slate-600">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-slate-300" aria-hidden />
                  {item}
                </li>
              ))}
            </ul>
          </div>
        </section>

        <div className="mt-10">
          <DecisionCapture
            labId={LAB_ID}
            labTitle="Where travel documents live, and what we refuse to keep"
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
