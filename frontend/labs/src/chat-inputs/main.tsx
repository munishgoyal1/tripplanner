import { useState } from "react";
import ReactDOM from "react-dom/client";
import { CalendarRange, Check, CircleSlash, Compass, MapPin, MessageCircle, Minus, Plus, Send, ShieldCheck, Sparkles, Undo2, Wallet } from "lucide-react";
import { DecisionCapture } from "../shared/DecisionCapture";
import { LabNavigation } from "../shared/LabNavigation";
import { LabScope } from "../shared/LabScope";
import { OptionContrast } from "../shared/OptionContrast";
import "../../../src/index.css";
import "./styles.css";

type OptionId = "chips" | "card" | "assumed" | "queue" | "bar";
type AskId = "origin" | "travellers" | "dates" | "budget" | "pace" | "interests";
/** "none" is a real, saved answer: a destination-only trip the traveller arrives at on their own. */
type Origin = { kind: "unset" } | { kind: "city"; city: string } | { kind: "none" };

const options = [
  { id: "chips" as const, label: "A · Inline chips", summary: "The ask is a row of tap targets under the agent's line.", cost: "Fastest for short answers; long value sets need a second surface." },
  { id: "card" as const, label: "B · Compact ask card", summary: "One small card carries the right control for that fact.", cost: "Handles any value type, but takes more vertical room in the thread." },
  { id: "assumed" as const, label: "C · Stated assumption", summary: "The agent commits to a value inline and invites a correction.", cost: "Zero taps when right; a wrong guess must be obvious and cheap to undo." },
  { id: "queue" as const, label: "D · One at a time", summary: "A tiny stack asks the next useful thing, always skippable.", cost: "Calm and finite, but it feels like a sequence rather than a chat." },
  { id: "bar" as const, label: "E · Context bar", summary: "Unresolved facts sit above the composer until answered.", cost: "Never blocks the conversation; easier to ignore indefinitely." },
];

const asks: { id: AskId; control: string; question: string; hint: string; icon: typeof MapPin }[] = [
  { id: "origin", control: "Chips + explicit opt-out", question: "Where are you starting from?", hint: "It changes flights, transfers, and day one pacing.", icon: MapPin },
  { id: "travellers", control: "Stepper", question: "How many travellers?", hint: "Rooms, tickets, and table sizes follow from this.", icon: Plus },
  { id: "dates", control: "Date range + flexible toggle", question: "When are you going?", hint: "Flexible is a real answer; I will pick good windows.", icon: CalendarRange },
  { id: "budget", control: "Slider", question: "Roughly what budget per person?", hint: "A range is enough. I will stay inside it.", icon: Wallet },
  { id: "pace", control: "Segmented control", question: "What pace suits you?", hint: "This decides how many stops fit in a day.", icon: Compass },
  { id: "interests", control: "Multi-select tags", question: "Anything you would hate to miss?", hint: "Pick a few. I will build days around them.", icon: Sparkles },
];

const cities = ["Delhi", "Mumbai", "Bengaluru"];
const paces = ["Relaxed", "Balanced", "See it all"];
const interestTags = ["Forts", "Local food", "Markets", "Sunset views", "Craft workshops"];

function originLabel(origin: Origin) {
  if (origin.kind === "city") return origin.city;
  if (origin.kind === "none") return "Destination-only trip";
  return "Not answered yet";
}

function OriginControl({ origin, onChange }: { origin: Origin; onChange: (next: Origin) => void }) {
  return (
    <div className="control-row" role="group" aria-label="Starting city">
      {cities.map((city) => (
        <button key={city} className={`chip ${origin.kind === "city" && origin.city === city ? "on" : ""}`} onClick={() => onChange({ kind: "city", city })}>
          <MapPin size={13} /> {city}
        </button>
      ))}
      <button className={`chip opt-out ${origin.kind === "none" ? "on" : ""}`} onClick={() => onChange({ kind: "none" })}>
        <CircleSlash size={13} /> I will get there myself
      </button>
    </div>
  );
}

function AskBody({ ask, state }: { ask: AskId; state: ReturnType<typeof useTripDraft> }) {
  if (ask === "origin") return <OriginControl origin={state.origin} onChange={state.setOrigin} />;
  if (ask === "travellers") return (
    <div className="control-row stepper" role="group" aria-label="Travellers">
      <button onClick={() => state.setTravellers(Math.max(1, state.travellers - 1))} aria-label="Fewer travellers"><Minus size={14} /></button>
      <strong>{state.travellers} {state.travellers === 1 ? "traveller" : "travellers"}</strong>
      <button onClick={() => state.setTravellers(state.travellers + 1)} aria-label="More travellers"><Plus size={14} /></button>
    </div>
  );
  if (ask === "dates") return (
    <div className="control-row" role="group" aria-label="Dates">
      {["12–20 Nov", "5–13 Dec", "Flexible"].map((window) => (
        <button key={window} className={`chip ${state.dates === window ? "on" : ""}`} onClick={() => state.setDates(window)}>
          <CalendarRange size={13} /> {window}
        </button>
      ))}
    </div>
  );
  if (ask === "budget") return (
    <div className="control-row slider-row">
      <input type="range" min={20} max={200} step={10} value={state.budget} onChange={(event) => state.setBudget(Number(event.target.value))} aria-label="Budget per person per day" />
      <strong>₹{(state.budget * 100).toLocaleString("en-IN")} <small>per person / day</small></strong>
    </div>
  );
  if (ask === "pace") return (
    <div className="segmented" role="group" aria-label="Trip pace">
      {paces.map((pace) => <button key={pace} className={state.pace === pace ? "on" : ""} onClick={() => state.setPace(pace)}>{pace}</button>)}
    </div>
  );
  return (
    <div className="control-row" role="group" aria-label="Interests">
      {interestTags.map((tag) => (
        <button key={tag} className={`chip ${state.interests.includes(tag) ? "on" : ""}`} onClick={() => state.toggleInterest(tag)}>
          {state.interests.includes(tag) && <Check size={12} />} {tag}
        </button>
      ))}
    </div>
  );
}

function useTripDraft() {
  const [origin, setOrigin] = useState<Origin>({ kind: "unset" });
  const [travellers, setTravellers] = useState(2);
  const [dates, setDates] = useState("");
  const [budget, setBudget] = useState(60);
  const [pace, setPace] = useState("");
  const [interests, setInterests] = useState<string[]>([]);
  const toggleInterest = (tag: string) => setInterests((current) => current.includes(tag) ? current.filter((item) => item !== tag) : [...current, tag]);
  return { origin, setOrigin, travellers, setTravellers, dates, setDates, budget, setBudget, pace, setPace, interests, toggleInterest };
}

function AskBlock({ option, ask, state }: { option: OptionId; ask: typeof asks[number]; state: ReturnType<typeof useTripDraft> }) {
  const Icon = ask.icon;
  if (option === "assumed" && ask.id === "origin") {
    return (
      <div className="assumed-line">
        <p>Planning from <button className="assumed-value" onClick={() => state.setOrigin({ kind: "unset" })}>{state.origin.kind === "unset" ? "Delhi" : originLabel(state.origin)}</button>. Say the word if that is wrong.</p>
        <OriginControl origin={state.origin} onChange={state.setOrigin} />
      </div>
    );
  }
  if (option === "chips") return <div className="ask-inline"><AskBody ask={ask.id} state={state} /></div>;
  return (
    <div className={`ask-card ${option}`}>
      <div className="ask-head"><span className="ask-icon"><Icon size={14} /></span><div><strong>{ask.question}</strong><small>{ask.hint}</small></div><span className="control-tag">{ask.control}</span></div>
      <AskBody ask={ask.id} state={state} />
    </div>
  );
}

function LearnedRail({ state }: { state: ReturnType<typeof useTripDraft> }) {
  const rows: { label: string; value: string; answered: boolean }[] = [
    { label: "Starting from", value: originLabel(state.origin), answered: state.origin.kind !== "unset" },
    { label: "Travellers", value: `${state.travellers}`, answered: true },
    { label: "Dates", value: state.dates || "Not answered yet", answered: Boolean(state.dates) },
    { label: "Pace", value: state.pace || "Not answered yet", answered: Boolean(state.pace) },
    { label: "Must-sees", value: state.interests.join(", ") || "Not answered yet", answered: state.interests.length > 0 },
  ];

  return (
    <aside className="learned-rail" aria-label="What the trip knows so far">
      <div className="rail-brand"><span><Compass size={17} /></span><strong>What the trip knows</strong></div>
      <p className="rail-caption">Every value here came from one tap in the conversation. Nothing was guessed and saved.</p>
      <div className="learned-list">
        {rows.map((row) => (
          <div key={row.label} className={`learned-row ${row.answered ? "" : "empty"}`}>
            <small>{row.label}</small>
            <strong>{row.value}</strong>
          </div>
        ))}
      </div>
      <div className="origin-actions">
        {state.origin.kind === "none" ? (
          <button className="rail-action" onClick={() => state.setOrigin({ kind: "unset" })}><Plus size={13} /> Add a starting city</button>
        ) : (
          <button className="rail-action" onClick={() => state.setOrigin({ kind: "none" })}><CircleSlash size={13} /> Remove the starting city</button>
        )}
        {state.origin.kind !== "unset" && (
          <button className="rail-action ghost" onClick={() => state.setOrigin({ kind: "unset" })}><Undo2 size={13} /> Unset</button>
        )}
      </div>
      <div className="honesty-note">
        <ShieldCheck size={15} />
        <span><strong>A destination-only trip is a real answer.</strong> An unanswered origin stays unanswered; existing trips are never back-filled with a guessed home city.</span>
      </div>
    </aside>
  );
}

function ChatPreview({ option }: { option: OptionId }) {
  const state = useTripDraft();
  const [step, setStep] = useState(0);
  const visible = option === "queue" ? [asks[step]] : option === "bar" ? asks.slice(0, 1) : asks.slice(0, 3);
  const unresolved = asks.filter((ask) => (ask.id === "origin" && state.origin.kind === "unset") || (ask.id === "dates" && !state.dates) || (ask.id === "pace" && !state.pace));

  return (
    <section className={`chat-preview mode-${option}`} aria-label="Chat input preview">
      <div className="chat-column">
        <header className="chat-head">
          <div><p className="section-kicker">Assistant</p><h2>Rajasthan, nine days</h2></div>
          <span className="soft-badge">{option === "assumed" ? "Assumes, then checks" : "Asks, never assumes"}</span>
        </header>

        <div className="thread">
          <div className="bubble user"><span className="bubble-avatar">MG</span><p>Plan me a Rajasthan trip around Diwali.</p></div>
          <div className="bubble agent">
            <span className="bubble-avatar agent"><Sparkles size={13} /></span>
            <div className="bubble-body">
              <p>I can build this now. {option === "queue" ? `One quick thing at a time will make it materially better — ${step + 1} of ${asks.length}` : "Three quick things will make it materially better"}.</p>
              {visible.map((ask) => (
                <div key={ask.id} className="ask-slot">
                  {option === "chips" && <p className="ask-question">{ask.question} <small>{ask.hint}</small></p>}
                  <AskBlock option={option} ask={ask} state={state} />
                </div>
              ))}
              {option === "queue" && (
                <div className="queue-actions">
                  <button className="ghost-action" onClick={() => setStep((current) => Math.min(asks.length - 1, current + 1))}>Skip this</button>
                  <button className="primary-action" onClick={() => setStep((current) => Math.min(asks.length - 1, current + 1))}>Next <Check size={13} /></button>
                </div>
              )}
            </div>
          </div>
          {state.origin.kind !== "unset" && (
            <div className="bubble agent">
              <span className="bubble-avatar agent"><Sparkles size={13} /></span>
              <div className="bubble-body"><p>{state.origin.kind === "none" ? "Got it — I will plan the destination only and leave getting there to you." : `Good — I will price flights and transfers from ${state.origin.city}.`}</p></div>
            </div>
          )}
        </div>

        {option === "bar" && (
          <div className="context-bar" aria-label="Unresolved details">
            <span className="bar-label"><MessageCircle size={13} /> Still useful</span>
            <div className="bar-pills">{unresolved.map((ask) => <button key={ask.id} className="bar-pill">{ask.question}</button>)}</div>
            {unresolved.length === 0 && <span className="bar-clear"><Check size={13} /> Nothing pending</span>}
          </div>
        )}

        <div className="composer"><input placeholder="Or just tell me in your own words" aria-label="Message the planner" /><button aria-label="Send"><Send size={15} /></button></div>
      </div>
      <LearnedRail state={state} />
    </section>
  );
}

function App() {
  const [option, setOption] = useState<OptionId>("chips");
  return (
    <main className="lab-page"><div className="lab-wrap">
      <LabNavigation detail labId="chat-inputs" />
      <header className="lab-header">
        <div>
          <p className="lab-kicker"><MessageCircle size={16} /> Lab #27 · Agent-requested inputs</p>
          <h1>The agent asks.<br />You tap.</h1>
          <p>When one missing fact would visibly improve the plan, the planner should ask for it in the conversation, using the smallest control that fits the answer. Typing stays available; it is never the only way in.</p>
        </div>
        <div className="principle-card">
          <span>Product principle</span>
          <strong>Ask in chat.<br />Never invent.</strong>
          <small>Tap-sized answers · explicit opt-outs · no back-filled data</small>
        </div>
      </header>
      <LabScope labId="chat-inputs" />
      <OptionContrast labId="chat-inputs" />
      <section className="option-picker">
        <div className="section-kicker">Five ways to ask</div>
        <div className="option-grid">
          {options.map((item) => (
            <button key={item.id} className={option === item.id ? "selected" : ""} onClick={() => setOption(item.id)}>
              <span className="option-label">{item.label}</span>
              <strong>{item.summary}</strong>
              <small>{item.cost}</small>
            </button>
          ))}
        </div>
      </section>
      <ChatPreview key={option} option={option} />
      <DecisionCapture labId="chat-inputs" labTitle="The agent asks, you tap" options={options.map(({ id, label }) => ({ id, label }))} activeOption={option} onChoose={(id) => setOption(id as OptionId)} />
    </div></main>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<App />);
