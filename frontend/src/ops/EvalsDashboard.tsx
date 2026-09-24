import { Fragment, useEffect, useState, type ReactNode } from "react";
import { Bug, ChevronDown, ChevronRight, Gauge, Gavel, ListChecks, RefreshCw, Zap } from "lucide-react";
import { fetchOpsEvals, type EvalFinding, type EvalJudgedTrip, type EvalsReport } from "../api";

type View = "findings" | "judge" | "audit" | "efficiency";

const SEVERITY_ORDER: EvalFinding["severity"][] = ["critical", "high", "medium", "low"];
const SEVERITY_STYLE: Record<EvalFinding["severity"], string> = {
  critical: "bg-rose-600 text-white",
  high: "bg-orange-500 text-stone-950",
  medium: "bg-amber-300 text-stone-950",
  low: "bg-stone-300 text-stone-900",
};
const STATUS_STYLE: Record<NonNullable<EvalFinding["status"]>, string> = {
  open: "border border-stone-400 text-stone-700",
  fixed: "bg-emerald-600 text-white",
  deferred: "border border-dashed border-stone-400 text-stone-500",
};
const SCORE_STYLE: Record<number, string> = {
  1: "bg-rose-200 text-rose-950",
  2: "bg-orange-200 text-orange-950",
  3: "bg-amber-100 text-amber-950",
  4: "bg-emerald-100 text-emerald-950",
  5: "bg-emerald-300 text-emerald-950",
};
const DIMENSION_LABELS: Record<string, string> = {
  scenario_preference_fidelity: "Fidelity",
  budget_evidence_completeness: "Budget",
  destination_specificity: "Specificity",
  memorable_moments: "Moments",
  narrative_coherence: "Coherence",
  meal_quality: "Meals",
  intentional_free_time: "Free time",
  repetition: "Repetition",
};

function Panel({ title, children, aside }: { title: string; children: ReactNode; aside?: ReactNode }) {
  return (
    <section className="border border-stone-200 bg-white">
      <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-stone-200 px-4 py-3">
        <h2 className="font-display text-lg text-stone-900">{title}</h2>
        {aside && <div className="text-xs text-stone-500">{aside}</div>}
      </div>
      <div className="p-4">{children}</div>
    </section>
  );
}

function Tile({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="border border-stone-200 bg-white px-4 py-3">
      <p className="text-xs font-semibold uppercase text-stone-500">{label}</p>
      <p className="mt-1 font-display text-3xl text-stone-900">{value}</p>
      <p className="mt-1 text-xs text-stone-500">{detail}</p>
    </div>
  );
}

function Empty({ children }: { children: ReactNode }) {
  return <p className="text-sm text-stone-500">{children}</p>;
}

function ScoreCell({ trip, dimension }: { trip: EvalJudgedTrip; dimension: string }) {
  const item = trip.assessments.find((assessment) => assessment.dimension === dimension);
  if (!item || item.score === null) {
    return <td className="border border-white bg-stone-100 px-2 py-1 text-center text-xs text-stone-500" title={item?.rationale}>{item?.status === "not_applicable" ? "n/a" : "?"}</td>;
  }
  return <td className={`border border-white px-2 py-1 text-center font-mono text-sm font-semibold ${SCORE_STYLE[item.score]}`} title={item.rationale}>{item.score}</td>;
}

function FindingsView({ report }: { report: EvalsReport }) {
  const findings = [...report.findings].sort((a, b) => SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity));
  if (!findings.length) return <Panel title="Business-logic findings"><Empty>No findings are recorded in this report.</Empty></Panel>;
  return (
    <div className="grid gap-3">
      {findings.map((finding) => (
        <article key={finding.id} className="border border-stone-200 bg-white p-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`px-2 py-0.5 text-xs font-bold uppercase ${SEVERITY_STYLE[finding.severity]}`}>{finding.severity}</span>
            <span className="font-mono text-xs text-stone-500">{finding.id}</span>
            <span className="text-xs text-stone-500">· {finding.area}</span>
            {finding.prevalence && <span className="text-xs font-semibold text-stone-700">· {finding.prevalence}</span>}
            {finding.status && <span className={`ml-auto px-2 py-0.5 text-xs font-bold uppercase ${STATUS_STYLE[finding.status]}`}>{finding.status}</span>}
          </div>
          <h3 className="mt-2 font-display text-lg text-stone-900">{finding.title}</h3>
          <dl className="mt-2 grid gap-2 text-sm text-stone-700 md:grid-cols-3">
            <div><dt className="text-xs font-semibold uppercase text-stone-500">Evidence</dt><dd>{finding.evidence}</dd></div>
            <div><dt className="text-xs font-semibold uppercase text-stone-500">Impact</dt><dd>{finding.impact}</dd></div>
            <div><dt className="text-xs font-semibold uppercase text-stone-500">Proposed fix</dt><dd>{finding.fix}</dd></div>
          </dl>
          {finding.resolution && <p className="mt-2 border-l-2 border-stone-300 pl-3 text-sm text-stone-700"><span className="font-semibold">Resolution: </span>{finding.resolution}</p>}
          <p className="mt-2 text-xs text-stone-500">Found by {finding.source}</p>
        </article>
      ))}
    </div>
  );
}

function JudgeView({ report }: { report: EvalsReport }) {
  const [open, setOpen] = useState<string | null>(null);
  const judge = report.judge;
  if (!judge || !judge.trips.length) return <Panel title="Itinerary judge"><Empty>No judged trips are recorded in this report.</Empty></Panel>;
  const dimensions = judge.rubric.dimensions.map((dimension) => dimension.key);
  const trips = [...judge.trips].sort((a, b) => (a.overall_score ?? 0) - (b.overall_score ?? 0));
  return (
    <Panel title={`Rubric ${judge.rubric.version} · ${judge.trips.length} corpus trips`} aside={`Judge: ${judge.judge_model} · ${judge.method}`}>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[880px] border-collapse text-sm">
          <thead>
            <tr className="text-left text-xs uppercase text-stone-500">
              <th className="py-2 pr-3">Trip</th>
              {dimensions.map((key) => <th key={key} className="px-2 py-2 text-center" title={judge.rubric.dimensions.find((d) => d.key === key)?.criterion}>{DIMENSION_LABELS[key] ?? key}</th>)}
              <th className="px-2 py-2 text-center">Overall</th>
            </tr>
          </thead>
          <tbody>
            {trips.map((trip) => (
              <Fragment key={trip.slug}>
                <tr className="cursor-pointer hover:bg-stone-50" onClick={() => setOpen(open === trip.slug ? null : trip.slug)}>
                  <td className="py-1 pr-3"><span className="flex items-center gap-1">{open === trip.slug ? <ChevronDown size={14} /> : <ChevronRight size={14} />}<span className="font-medium text-stone-900">{trip.destination}</span><span className="text-xs text-stone-500">· {trip.days}d · {trip.slug}</span></span></td>
                  {dimensions.map((key) => <ScoreCell key={key} trip={trip} dimension={key} />)}
                  <td className="px-2 py-1 text-center font-mono font-semibold" title={trip.hard_gate_failed ? "Capped: a hard gate scored 2 or lower" : undefined}>{trip.overall_score?.toFixed(2) ?? "—"}{trip.hard_gate_failed ? " ⚑" : ""}</td>
                </tr>
                {open === trip.slug && (
                  <tr>
                    <td colSpan={dimensions.length + 2} className="bg-stone-50 px-4 py-3">
                      <p className="text-xs text-stone-600"><span className="font-semibold">Request:</span> {trip.request || "not recorded"}</p>
                      <ul className="mt-2 grid gap-2 md:grid-cols-2">
                        {trip.assessments.map((item) => (
                          <li key={item.dimension} className="border border-stone-200 bg-white p-2 text-xs">
                            <p className="font-semibold text-stone-800">{DIMENSION_LABELS[item.dimension] ?? item.dimension} · {item.score ?? item.status}</p>
                            <p className="mt-1 text-stone-700">{item.rationale}</p>
                            {item.evidence.map((ref) => <p key={`${ref.path}-${ref.quote}`} className="mt-1 truncate font-mono text-[11px] text-stone-500" title={`${ref.path}: ${ref.quote}`}>{ref.path} · “{ref.quote}”</p>)}
                          </li>
                        ))}
                      </ul>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
            <tr className="border-t-2 border-stone-300 text-xs">
              <td className="py-2 pr-3 font-semibold uppercase text-stone-500">Mean</td>
              {dimensions.map((key) => <td key={key} className="px-2 py-2 text-center font-mono font-semibold">{judge.dimension_means[key]?.toFixed(2) ?? "n/a"}</td>)}
              <td />
            </tr>
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-xs text-stone-500">Scores are advisory (1 = substantial failure, 5 = excellent) and every cited quote is validated against the trip evidence. Select a row for rationale and evidence.</p>
    </Panel>
  );
}

function ProbesPanel({ report }: { report: EvalsReport }) {
  const probes = report.probes;
  if (!probes) return null;
  const identity = probes.place_identity;
  return (
    <Panel title="Business-logic probes over every corpus trip" aside={`${probes.results[0]?.evaluated ?? 0} trips in ${probes.corpus}`}>
      <div className="grid gap-2">
        {probes.results.map((probe) => (
          <div key={probe.key} className="grid grid-cols-[minmax(0,1fr)_minmax(0,12rem)_5rem] items-start gap-3 text-sm">
            <span className="text-stone-800">{probe.title}{probe.examples[0] && <span className="block truncate text-xs text-stone-500" title={probe.examples.join("\n")}>e.g. {probe.examples[0]}</span>}</span>
            <span className="mt-1.5 h-2 bg-stone-100"><span className="block h-2 bg-orange-500" style={{ width: `${(100 * probe.trips) / Math.max(1, probe.evaluated)}%` }} /></span>
            <span className="text-right font-mono text-xs text-stone-700">{probe.trips}/{probe.evaluated}</span>
          </div>
        ))}
      </div>
      <p className="mt-4 text-sm text-stone-800"><span className="font-semibold">Place resolution:</span> {identity.mismatched} of {identity.resolved} cached Google place lookups ({((100 * identity.mismatched) / Math.max(1, identity.resolved)).toFixed(1)}%) resolved to a place sharing no word with the stop name.</p>
      <p className="mt-1 text-xs text-stone-500">Most repeated wrong targets: {identity.most_common.map(([name, count]) => `${name} ×${count}`).join(" · ")}</p>
    </Panel>
  );
}

function AuditView({ report }: { report: EvalsReport }) {
  const audit = report.audit;
  if (!audit) return <div className="grid gap-4"><ProbesPanel report={report} /><Panel title="Deterministic audit"><Empty>No audit run is recorded in this report.</Empty></Panel></div>;
  const maxTrips = Math.max(1, ...audit.rules.map((rule) => rule.trips));
  return (
    <div className="grid gap-4">
      <ProbesPanel report={report} />
      {audit.observations.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {audit.observations.slice(0, 8).map((item) => <Tile key={item.label} label={item.label} value={item.value} detail={item.detail} />)}
        </div>
      )}
      <Panel title="Rules by affected trips" aside={`${audit.corpus.size ?? "?"} trips · ${(audit.corpus.sources ?? []).join(", ")}`}>
        <div className="grid gap-1">
          {audit.rules.map((rule) => (
            <div key={rule.code} className="grid grid-cols-[3.5rem_minmax(0,1fr)_minmax(0,14rem)_4rem] items-center gap-3 text-sm" title={rule.statement}>
              <span className={`font-mono text-xs font-semibold ${rule.severity === "gate" ? "text-rose-700" : "text-stone-600"}`}>{rule.code}</span>
              <span className="truncate text-stone-800">{rule.title} <span className="text-xs text-stone-500">· {rule.statement}</span></span>
              <span className="h-2 bg-stone-100"><span className={`block h-2 ${rule.severity === "gate" ? "bg-rose-500" : "bg-stone-500"}`} style={{ width: `${(100 * rule.trips) / maxTrips}%` }} /></span>
              <span className="text-right font-mono text-xs text-stone-700">{rule.trips}</span>
            </div>
          ))}
        </div>
      </Panel>
      <Panel title="Largest finding groups">
        <ul className="grid gap-2 text-sm">
          {audit.top_groups.map((group) => (
            <li key={`${group.rule}-${group.symptom}`} className="grid grid-cols-[3.5rem_minmax(0,1fr)_4rem] gap-3">
              <span className="font-mono text-xs font-semibold text-stone-600">{group.rule}</span>
              <span className="text-stone-800">{group.symptom}<span className="block truncate text-xs text-stone-500">e.g. {group.example}</span></span>
              <span className="text-right font-mono text-xs">{group.count}{group.accepted ? " ✓" : ""}</span>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}

function EfficiencyView({ report }: { report: EvalsReport }) {
  if (!report.efficiencies.length) return <Panel title="Engineering efficiencies"><Empty>No efficiency items are recorded.</Empty></Panel>;
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      {report.efficiencies.map((item) => (
        <article key={item.id} className="border border-stone-200 bg-white p-4">
          <p className="font-mono text-xs text-stone-500">{item.id} · value {item.value} · effort {item.effort}</p>
          <h3 className="mt-1 font-display text-lg text-stone-900">{item.title}</h3>
          <p className="mt-2 text-sm text-stone-700"><span className="font-semibold">Evidence: </span>{item.evidence}</p>
          <p className="mt-1 text-sm text-stone-700"><span className="font-semibold">Plan: </span>{item.plan}</p>
        </article>
      ))}
    </div>
  );
}

export default function EvalsDashboard() {
  const [report, setReport] = useState<EvalsReport | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState("");
  const [view, setView] = useState<View>("findings");
  const [loading, setLoading] = useState(false);

  const load = async (signal?: AbortSignal) => {
    setLoading(true);
    try {
      const result = await fetchOpsEvals(signal);
      if (signal?.aborted) return;
      setReport(result);
      setError("");
    } catch (failure) {
      if (signal?.aborted) return;
      const status = (failure as { status?: number }).status;
      setNotFound(status === 404);
      setError("Evaluation report unavailable. Please retry.");
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, []);

  if (notFound) return <main className="grid min-h-full place-items-center bg-stone-100 px-6 text-center"><div><p className="font-display text-7xl text-stone-900">404</p><p className="mt-3 text-sm text-stone-500">Page not found.</p></div></main>;
  if (!report) return <main className="grid min-h-full place-items-center bg-stone-100 text-sm text-stone-500">{error ? <div role="alert" className="text-center"><p>{error}</p><button type="button" className="mt-3 underline" onClick={() => void load()}>Retry</button></div> : "Loading"}</main>;

  const open = report.findings.filter((finding) => finding.status !== "fixed").length;
  const fixed = report.findings.filter((finding) => finding.status === "fixed").length;
  const severe = report.findings.filter((finding) => finding.status !== "fixed" && (finding.severity === "critical" || finding.severity === "high")).length;
  const judged = report.judge?.trips ?? [];
  const scored = judged.map((trip) => trip.overall_score).filter((score): score is number => score !== null);
  const mean = scored.length ? (scored.reduce((sum, score) => sum + score, 0) / scored.length).toFixed(2) : "—";
  const gateTrips = report.audit?.rules.filter((rule) => rule.severity === "gate" && rule.trips > 0).length ?? 0;
  const tabs: { id: View; label: string; icon: typeof Bug }[] = [
    { id: "findings", label: "Findings", icon: Bug },
    { id: "judge", label: "LLM judge", icon: Gavel },
    { id: "audit", label: "Deterministic audit", icon: ListChecks },
    { id: "efficiency", label: "Efficiency", icon: Zap },
  ];

  return (
    <main className="min-h-full bg-[#f4f3ef] text-stone-900">
      <header className="border-b border-stone-700 bg-[#1f2926] px-5 py-4 text-stone-50 sm:px-8">
        <div className="mx-auto flex max-w-[1500px] flex-wrap items-center justify-between gap-4">
          <div><p className="text-xs font-semibold uppercase text-emerald-300">Tripplanner evaluations</p><h1 className="font-display text-2xl">Trip quality console</h1></div>
          <div className="flex items-center gap-4 text-xs text-stone-300">
            <a href="/operations" className="underline-offset-2 hover:underline">Operations</a>
            <span className="hidden sm:inline">Report {report.generated_at ? new Date(report.generated_at).toLocaleString() : "not generated"}</span>
            <button type="button" className="grid size-9 place-items-center border border-stone-600 hover:bg-stone-700" onClick={() => void load()} title="Reload report" aria-label="Reload report"><RefreshCw size={16} className={loading ? "animate-spin" : ""} /></button>
          </div>
        </div>
        <div className="mx-auto mt-4 flex w-full max-w-[1500px] gap-1 overflow-x-auto" role="tablist" aria-label="Evaluation views">
          {tabs.map(({ id, label, icon: Icon }) => (
            <button key={id} type="button" role="tab" aria-selected={view === id} onClick={() => setView(id)} className={`shrink-0 px-4 py-2 text-sm font-semibold ${view === id ? "bg-emerald-500 text-stone-950" : "text-stone-300 hover:bg-stone-700"}`}><span className="flex items-center gap-2"><Icon size={15} />{label}</span></button>
          ))}
        </div>
      </header>
      {error && <div role="alert" className="border-b border-amber-300 bg-amber-50 px-5 py-3 text-sm text-amber-950 sm:px-8">{error}</div>}
      <div className="mx-auto grid max-w-[1500px] gap-4 px-5 py-6 sm:px-8">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Tile label="Open findings" value={String(open)} detail={`${severe} critical or high open · ${fixed} fixed`} />
          <Tile label="Judged trips" value={String(judged.length)} detail={`mean overall ${mean} / 5`} />
          <Tile label="Audit corpus" value={String(report.audit?.corpus.size ?? "—")} detail={`${gateTrips} gate rules failing somewhere`} />
          <Tile label="Efficiency items" value={String(report.efficiencies.length)} detail="ranked by value" />
        </div>
        {view === "findings" ? <FindingsView report={report} /> : view === "judge" ? <JudgeView report={report} /> : view === "audit" ? <AuditView report={report} /> : <EfficiencyView report={report} />}
        <p className="flex items-center gap-2 text-xs text-stone-500"><Gauge size={14} />Offline report: built from committed corpus trips by scripts/dev/owner_evals.py. Opening this page never plans a trip or calls Google.</p>
      </div>
    </main>
  );
}
