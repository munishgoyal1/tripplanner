import { useMemo, useState } from "react";
import ReactDOM from "react-dom/client";
import {
  BedDouble,
  Check,
  CircleDashed,
  Inbox,
  ListTodo,
  MapPinOff,
  MessageCircle,
  PenLine,
  Plane,
  Sparkles,
  TriangleAlert,
  Utensils,
} from "lucide-react";
import { DecisionCapture } from "../shared/DecisionCapture";
import { LabNavigation } from "../shared/LabNavigation";
import { LabScope } from "../shared/LabScope";
import { OptionContrast } from "../shared/OptionContrast";
import { days, gaps, improvements, trip, type Gap, type GapKind, type Stop } from "./fixture";
import { options, type OptionId } from "./options";
import "../../../src/index.css";
import "./styles.css";

type Device = "desktop" | "mobile";
type Resolved = Record<string, string>;

const KIND_ICON: Record<GapKind, typeof BedDouble> = { stay: BedDouble, meal: Utensils, journey: Plane, fare: TriangleAlert };
const KIND_LABEL: Record<GapKind, string> = { stay: "Stay", meal: "Meals", journey: "Journeys", fare: "Prices" };
const gapById = Object.fromEntries(gaps.map((gap) => [gap.id, gap])) as Record<string, Gap>;

interface Api {
  resolved: Resolved;
  resolve: (gapId: string, choice: string) => void;
}

function displayName(stop: Stop, resolved: Resolved, today: boolean): string {
  const choice = stop.gap && !today ? resolved[stop.gap] : undefined;
  if (!choice) return stop.name;
  if (stop.gap === "outbound") return `Flight: Bangalore to Goa · ${choice}`;
  if (stop.gap === "fare") return choice === "Find a bookable fare" ? "Flight: Goa to Bangalore · searching real fares" : "Flight: Goa to Bangalore · estimate only";
  return choice;
}

function Suggestions({ gap, api, compact = false }: { gap: Gap; api: Api; compact?: boolean }) {
  const chosen = api.resolved[gap.id];
  if (chosen) {
    return <span className="hg-done"><Check size={12} /> {chosen}</span>;
  }
  return (
    <span className={`hg-chips ${compact ? "compact" : ""}`}>
      {gap.suggestions.map((choice) => (
        <button key={choice} type="button" onClick={() => api.resolve(gap.id, choice)}><Sparkles size={11} />{choice}</button>
      ))}
      {gap.kind !== "fare" && <button type="button" className="ghost" onClick={() => api.resolve(gap.id, "Your choice (typed)")}><PenLine size={11} />Choose myself</button>}
    </span>
  );
}

function StopRow({ stop, option, api, today }: { stop: Stop; option: OptionId; api: Api; today: boolean }) {
  const gap = stop.gap ? gapById[stop.gap] : undefined;
  const open = Boolean(gap && !api.resolved[gap.id]);
  const marked = open && !today && option !== "assistant";
  const Icon = stop.kind === "hotel" ? BedDouble : stop.kind === "meal" ? Utensils : stop.kind === "flight" ? Plane : CircleDashed;
  const fare = gap?.kind === "fare" && open;
  return (
    <div className={`hg-stop ${marked && option !== "checklist" ? "open" : ""}`} data-lab-change={marked ? "gap-row" : undefined}>
      <span className="hg-time">{stop.time ?? "—"}</span>
      <span className="hg-icon"><Icon size={14} /></span>
      <span className="hg-main">
        <strong>{displayName(stop, api.resolved, today)}</strong>
        {stop.note && <small>{stop.note}</small>}
        {marked && option === "slots" && gap && (
          <span className="hg-slot" data-lab-change="inline-slot">
            <em>{gap.need}</em>
            <Suggestions gap={gap} api={api} compact />
          </span>
        )}
      </span>
      {marked && option === "inbox" && <span className="hg-flag">{fare ? "Not bookable" : "Open"}</span>}
      {marked && option === "slots" && fare && <span className="hg-flag">Not bookable</span>}
      {marked && option === "checklist" && <span className="hg-hollow" title="Open decision in Details" />}
      {open && !today && option !== "assistant" && <span className="hg-nopin" title="Not pinned on the map until decided"><MapPinOff size={13} /></span>}
    </div>
  );
}

function openGaps(resolved: Resolved) {
  return gaps.filter((gap) => !resolved[gap.id]);
}

function InboxBar({ api }: { api: Api }) {
  const [expanded, setExpanded] = useState(true);
  const [all, setAll] = useState(false);
  const remaining = openGaps(api.resolved);
  const shown = all ? remaining : remaining.slice(0, 3);
  const fares = remaining.filter((gap) => gap.kind === "fare").length;
  return (
    <section className="hg-inbox" data-lab-change="decision-inbox">
      <button type="button" className="hg-inbox-head" onClick={() => setExpanded(!expanded)} aria-expanded={expanded}>
        <Inbox size={15} />
        <strong>{remaining.length ? `${remaining.length} open decision${remaining.length === 1 ? "" : "s"}` : "Every decision made"}</strong>
        {fares > 0 && <span className="hg-warn">{fares} fare not bookable</span>}
        <span className="hg-progress"><span style={{ width: `${(100 * (gaps.length - remaining.length)) / gaps.length}%` }} /></span>
        <small>{expanded ? "Hide" : "Show"}</small>
      </button>
      {expanded && remaining.length > 0 && (
        <ul>
          {shown.map((gap) => {
            const Icon = KIND_ICON[gap.kind];
            return (
              <li key={gap.id}>
                <Icon size={14} />
                <div><strong>{gap.need}</strong><small>{gap.why}</small><Suggestions gap={gap} api={api} /></div>
              </li>
            );
          })}
          {remaining.length > shown.length && <li className="hg-more-row"><button type="button" onClick={() => setAll(true)}>Show all {remaining.length}</button></li>}
        </ul>
      )}
    </section>
  );
}

function Checklist({ api }: { api: Api }) {
  const groups = (Object.keys(KIND_LABEL) as GapKind[]).map((kind) => ({ kind, items: gaps.filter((gap) => gap.kind === kind) }));
  return (
    <aside className="hg-details" data-lab-change="readiness-checklist">
      <p className="section-kicker">Details</p>
      <h3>Plan readiness</h3>
      {groups.map(({ kind, items }) => {
        const done = items.filter((gap) => api.resolved[gap.id]).length;
        return (
          <div key={kind} className="hg-group">
            <p><strong>{KIND_LABEL[kind]}</strong><span>{done}/{items.length}</span></p>
            {items.map((gap) => (
              <div key={gap.id} className={`hg-check ${api.resolved[gap.id] ? "done" : ""}`}>
                {api.resolved[gap.id] ? <Check size={12} /> : <CircleDashed size={12} />}
                <div><span>{gap.need}</span>{!api.resolved[gap.id] && <Suggestions gap={gap} api={api} compact />}</div>
              </div>
            ))}
          </div>
        );
      })}
    </aside>
  );
}

function AssistantSheet({ api }: { api: Api }) {
  const remaining = openGaps(api.resolved);
  return (
    <aside className="hg-assistant" data-lab-change="assistant-follow-up">
      <p className="hg-assistant-head"><MessageCircle size={14} /> Assistant</p>
      <div className="hg-bubble user">{trip.request}</div>
      <div className="hg-bubble">Here is your relaxed Goa plan: four slow beach days from Baga to Palolem.</div>
      <div className="hg-bubble">
        {remaining.length ? `A few things are still open (${remaining.length}). Tap one and I'll fill it:` : "Everything is decided now."}
        <span className="hg-chips compact">
          {remaining.map((gap) => <button key={gap.id} type="button" onClick={() => api.resolve(gap.id, gap.suggestions[0])}><Sparkles size={11} />{gap.need}</button>)}
        </span>
      </div>
    </aside>
  );
}

function Preview({ option, device, today, api }: { option: OptionId; device: Device; today: boolean; api: Api }) {
  const mobile = device === "mobile";
  const side = today || option === "inbox" || option === "slots" ? "map" : option === "checklist" ? "details" : "assistant";
  return (
    <div className={`hg-stage ${mobile ? "mobile" : ""}`}>
      <section className={`hg-shell ${mobile ? "mobile" : ""}`} aria-label="Workspace preview">
        <header className="hg-bar">
          <div><strong>{trip.title}</strong><small>{trip.dates} · {trip.party}</small></div>
          <span className="hg-meter" title="Existing booking readiness meter (context only)">Booking readiness <b>0%</b></span>
        </header>
        <div className="hg-body">
          <div className="hg-plan">
            {!today && option === "inbox" && <InboxBar api={api} />}
            {days.map((day) => {
              const dayOpen = day.stops.filter((stop) => stop.gap && !api.resolved[stop.gap]).length;
              return (
                <article key={day.day} className="hg-day">
                  <header>
                    <div><strong>Day {day.day} · {day.title}</strong><small>{day.date}</small></div>
                    {!today && option === "slots" && dayOpen > 0 && <span className="hg-count" data-lab-change="day-count">{dayOpen} open</span>}
                  </header>
                  <p className="hg-summary">{day.summary}</p>
                  {day.stops.map((stop, index) => <StopRow key={`${day.day}-${index}`} stop={stop} option={option} api={api} today={today} />)}
                </article>
              );
            })}
          </div>
          {!mobile && side === "map" && (
            <div className="hg-map">
              <span className="hg-pin" style={{ left: "38%", top: "22%" }}>Baga</span>
              <span className="hg-pin" style={{ left: "30%", top: "30%" }}>Candolim</span>
              <span className="hg-pin" style={{ left: "26%", top: "36%" }}>Fort Aguada</span>
              <span className="hg-pin" style={{ left: "44%", top: "16%" }}>Anjuna</span>
              <span className="hg-pin" style={{ left: "62%", top: "82%" }}>Palolem</span>
              {today ? <span className="hg-pin wrong" style={{ left: "48%", top: "44%" }}>Tereza Beach House ← "Beachside dining (TBD)"</span> : <p className="hg-map-note"><MapPinOff size={13} /> {openGaps(api.resolved).length} undecided places are not pinned</p>}
            </div>
          )}
          {!mobile && !today && side === "details" && <Checklist api={api} />}
          {!mobile && !today && side === "assistant" && <AssistantSheet api={api} />}
        </div>
        {mobile && !today && option === "checklist" && <Checklist api={api} />}
        {mobile && !today && option === "assistant" && <AssistantSheet api={api} />}
      </section>
    </div>
  );
}

function App() {
  const [option, setOption] = useState<OptionId>(options[0]?.id ?? "inbox");
  const [device, setDevice] = useState<Device>("desktop");
  const [today, setToday] = useState(false);
  const [resolved, setResolved] = useState<Resolved>({});
  const active = options.find((item) => item.id === option) ?? options[0];
  const api = useMemo<Api>(() => ({ resolved, resolve: (gapId, choice) => setResolved((current) => ({ ...current, [gapId]: choice })) }), [resolved]);

  return (
    <main className="lab-page"><div className="lab-wrap">
      <LabNavigation detail labId="honest-gaps" />
      <header className="lab-header">
        <div>
          <p className="lab-kicker"><ListTodo size={16} /> Plan trust and completeness</p>
          <h1>Show what the<br />plan has not decided.</h1>
          <p>An offline review judged twelve real corpus trips. Every one of them still held something the planner had not decided — "Hotel (TBD)", "Lunch (TBD)", a flight with no time, a sample fare that cannot be booked — and the workspace draws each of those exactly like a chosen place, even pinning a guessed restaurant on the map. This Lab asks where those open decisions should gather and how a traveller closes each one in a tap. The fixture is the corpus trip <code>goa-relaxed</code>, placeholders unchanged.</p>
        </div>
        <div className="principle-card">
          <span>The rule</span>
          <strong>A guess never<br />looks like a choice.</strong>
          <small>Undecided stops are marked · never pinned · one tap to resolve</small>
        </div>
      </header>
      <LabScope labId="honest-gaps" />
      <OptionContrast labId="honest-gaps" />

      <section className="option-picker">
        <div className="section-kicker">Four homes for the same open decisions</div>
        <div className="hg-option-grid">
          {options.map((item) => (
            <button key={item.id} type="button" className={option === item.id ? "selected" : ""} onClick={() => setOption(item.id)}>
              <span className="option-label">{item.label}</span>
              <strong>{item.summary}</strong>
              <small>Exact delta: {item.delta}</small>
              <span className="option-rest"><span>Lives in: {item.home}</span></span>
            </button>
          ))}
        </div>
      </section>

      <div className="hg-toolbar">
        <div>
          <p className="section-kicker">Exact delta · live</p>
          <strong>{active.label}</strong>
          <p className="hg-delta">{active.delta} Resolve a few gaps below: the itinerary row, the count and the map note update in every option.</p>
        </div>
        <label className="hg-toggle"><input type="checkbox" checked={today} onChange={(event) => setToday(event.target.checked)} /> Compare with today</label>
        <button type="button" className="hg-reset" onClick={() => setResolved({})}>Reset gaps</button>
        <div className="hg-devices">
          {(["desktop", "mobile"] as Device[]).map((item) => (
            <button key={item} type="button" className={device === item ? "active" : ""} onClick={() => setDevice(item)}>{item === "desktop" ? "Desktop" : "Mobile"}</button>
          ))}
        </div>
      </div>

      <Preview option={option} device={device} today={today} api={api} />

      <section className="hg-more">
        <p className="section-kicker">More improvements from the same review · ranked by value</p>
        <h2>What else the evaluation says the workspace should show</h2>
        <ol>
          {improvements.map((item) => (
            <li key={item.rank}>
              <span className="hg-rank">{item.rank}</span>
              <div><strong>{item.title}</strong><p>{item.idea}</p><small>Evidence: {item.evidence}</small></div>
            </li>
          ))}
        </ol>
        <p className="hg-more-note">These are candidates, not options in this Lab. Name any of them in your handoff to open its own Lab or to fold it into this implementation.</p>
      </section>

      <DecisionCapture
        labId="honest-gaps"
        labTitle="Honest gaps: show what the plan has not decided"
        options={options.map(({ id, label }) => ({ id, label }))}
        activeOption={option}
        onChoose={(id) => setOption(id as OptionId)}
      />
    </div></main>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<App />);
