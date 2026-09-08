import { useEffect, useMemo, useState } from "react";
import {
  AUDIT_COMMAND,
  type Group,
  type Report,
  type Rule,
  type TripRecord,
  howLongAgo,
  loadReport,
  openUrl,
} from "./report";

type Tab = "findings" | "rules" | "trips";

function OpenLink({ record }: { record: TripRecord | undefined }) {
  if (!record) return <span className="no-open">record gone</span>;
  // Debug-store revisions are historical states that were never in a database.
  if (!record.openable) return <span className="no-open">past revision</span>;
  return (
    <a className="open" href={openUrl(record)} target="_blank" rel="noreferrer">
      Open
    </a>
  );
}

function Findings({ report }: { report: Report }) {
  const [rule, setRule] = useState("");
  const [provenance, setProvenance] = useState("");
  const [newOnly, setNewOnly] = useState(false);
  const [text, setText] = useState("");
  const [open, setOpen] = useState<string | null>(null);

  const records = useMemo(
    () => new Map(report.records.map((item) => [item.id, item])),
    [report.records]
  );
  const provenances = useMemo(
    () => [...new Set(report.groups.flatMap((item) => Object.keys(item.provenances)))].sort(),
    [report.groups]
  );

  const shown = report.groups.filter(
    (group) =>
      (!rule || group.rule === rule) &&
      (!provenance || provenance in group.provenances) &&
      (!newOnly || group.new) &&
      (!text || group.symptom.toLowerCase().includes(text.toLowerCase()))
  );
  const total = shown.reduce((sum, group) => sum + group.count, 0);

  return (
    <>
      <div className="filters">
        <select value={rule} onChange={(event) => setRule(event.target.value)}>
          <option value="">All rules</option>
          {report.rules
            .filter((item) => item.hits)
            .map((item) => (
              <option key={item.code} value={item.code}>
                {item.code} ({item.hits})
              </option>
            ))}
        </select>
        <select value={provenance} onChange={(event) => setProvenance(event.target.value)}>
          <option value="">Any provenance</option>
          {provenances.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
        <input
          placeholder="Search symptom..."
          value={text}
          onChange={(event) => setText(event.target.value)}
        />
        <label>
          <input
            type="checkbox"
            checked={newOnly}
            onChange={(event) => setNewOnly(event.target.checked)}
          />
          Not yet accepted
        </label>
        <span className="meta">
          {shown.length} group(s), {total} occurrence(s)
        </span>
      </div>

      {shown.map((group: Group) => (
        <div className="card" key={group.key}>
          <button
            className="group-head"
            onClick={() => setOpen(open === group.key ? null : group.key)}
            aria-expanded={open === group.key}
          >
            <span className="mono">{group.rule}</span>
            <span className="count">{group.count}</span>
            <span className="symptom">
              {group.symptom}
              <br />
              <span className="meta">
                {Object.entries(group.provenances)
                  .map(([name, hits]) => `${name} ${hits}`)
                  .join(", ")}
              </span>
            </span>
            <span className={`chip ${group.new ? "new" : "known"}`}>
              {group.new ? "open" : `accepted ${group.accepted_on}`}
            </span>
          </button>

          {open === group.key && (
            <div className="findings">
              {group.findings.map((finding, index) => (
                <div className="finding" key={`${finding.record_id}-${index}`}>
                  <span className="msg">
                    {finding.day !== null && <b>Day {finding.day} · </b>}
                    {finding.message}
                    <br />
                    <span className="meta mono">{finding.record_id}</span>
                  </span>
                  <OpenLink record={records.get(finding.record_id)} />
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </>
  );
}

function Movement({ rule }: { rule: Rule }) {
  if (rule.first_seen) {
    return <span className="move new">new rule</span>;
  }
  const delta = rule.trips - rule.was_trips;
  if (delta === 0) {
    return <span className="move flat">no change</span>;
  }
  return (
    <span className={`move ${delta < 0 ? "better" : "worse"}`}>
      {delta < 0 ? "\u2193" : "\u2191"} {Math.abs(delta)} trip
      {Math.abs(delta) === 1 ? "" : "s"}
      <span className="meta"> (was {rule.was_trips})</span>
    </span>
  );
}

function Rules({ report }: { report: Report }) {
  return (
    <>
      {report.compared_with ? (
        <p className="meta">
          Movement is against the audit of {report.compared_with}.
        </p>
      ) : (
        <p className="meta">
          No earlier report was on disk, so nothing can be compared yet.
        </p>
      )}
      <table>
        <thead>
          <tr>
            <th>Code</th>
            <th>Rule</th>
            <th>What it asserts</th>
            <th>Severity</th>
            <th>Trips</th>
            <th>Hits</th>
            <th>Since last audit</th>
          </tr>
        </thead>
        <tbody>
          {report.rules.map((rule) => (
            <tr key={rule.code} className={rule.hits ? "" : "silent"}>
              <td className="mono">{rule.code}</td>
              <td>{rule.title}</td>
              <td>
                {rule.statement}
                <br />
                <span className="meta mono">{rule.evaluated_in}</span>
              </td>
              <td>
                <span className={`chip ${rule.severity}`}>{rule.severity}</span>
              </td>
              <td>{rule.trips || "\u2014"}</td>
              <td>{rule.hits || "never fired"}</td>
              <td>
                <Movement rule={rule} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function Trips({ report }: { report: Report }) {
  const [openableOnly, setOpenableOnly] = useState(true);
  const shown = report.records.filter((item) => !openableOnly || item.openable);
  return (
    <>
      <div className="filters">
        <label>
          <input
            type="checkbox"
            checked={openableOnly}
            onChange={(event) => setOpenableOnly(event.target.checked)}
          />
          Only trips I can open
        </label>
        <span className="meta">
          {shown.length} of {report.records.length}
        </span>
      </div>
      <table>
        <thead>
          <tr>
            <th>Destination</th>
            <th>Dates</th>
            <th>Days</th>
            <th>Provenance</th>
            <th>Findings</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {shown.map((record) => (
            <tr key={record.id}>
              <td>
                {record.destination || <span className="meta">no destination</span>}
                <br />
                <span className="meta mono">{record.id}</span>
              </td>
              <td className="meta">
                {record.departure_date} → {record.return_date}
              </td>
              <td>{record.days}</td>
              <td className="meta">{record.provenance}</td>
              <td>{record.findings}</td>
              <td>
                <OpenLink record={record} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function Observations({ report }: { report: Report }) {
  return (
    <div className="obs">
      {report.observations.map((item) => (
        <div className="card" key={item.label}>
          <div className="label">{item.label}</div>
          <div className="value">{item.value}</div>
          {item.detail && <div className="detail">{item.detail}</div>}
        </div>
      ))}
    </div>
  );
}

export default function App() {
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<Tab>("findings");

  useEffect(() => {
    loadReport()
      .then(setReport)
      .catch(() => setReport(null))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="wrap">Loading…</div>;

  if (!report) {
    return (
      <div className="wrap">
        <div className="empty">
          No audit report yet. Run the audit and reload.
          <code>{AUDIT_COMMAND}</code>
        </div>
      </div>
    );
  }

  return (
    <div className="wrap">
      <header>
        <h1>Quality Inspector</h1>
        <div className="sub">
          {report.corpus.size} trips · {report.groups.length} finding groups ·{" "}
          {report.groups.filter((group) => group.new).length} not yet accepted · report generated{" "}
          {howLongAgo(report.generated_at)}
        </div>
        <div className="sub mono">{report.corpus.sources.join("  ·  ")}</div>
        {report.retired.length > 0 && (
          <div className="sub">
            {report.retired.length} accepted finding(s) no longer occur — a fix retired them.
          </div>
        )}
      </header>

      <nav className="tabs">
        {(["findings", "rules", "trips"] as Tab[]).map((name) => (
          <button key={name} aria-selected={tab === name} onClick={() => setTab(name)}>
            {name[0].toUpperCase() + name.slice(1)}
          </button>
        ))}
      </nav>

      {tab === "findings" && <Findings report={report} />}
      {tab === "rules" && <Rules report={report} />}
      {tab === "trips" && (
        <>
          <Trips report={report} />
          <h2 style={{ fontSize: 15, marginTop: 28 }}>What these trips actually look like</h2>
          <Observations report={report} />
        </>
      )}
    </div>
  );
}
