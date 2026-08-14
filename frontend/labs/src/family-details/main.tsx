import { useMemo, useState } from "react";
import ReactDOM from "react-dom/client";
import { Check, ChevronRight, CircleHelp, Clock3, Heart, MessageCircle, ShieldCheck, Sparkles, UsersRound } from "lucide-react";
import { DecisionCapture } from "../shared/DecisionCapture";
import { LabNavigation } from "../shared/LabNavigation";
import { LabScope } from "../shared/LabScope";
import { OptionContrast } from "../shared/OptionContrast";
import "../../../src/index.css";
import "./styles.css";

type OptionId = "roster" | "questions" | "defaults" | "chat" | "matrix";
type MemberId = "family" | "munish" | "rhea" | "kabir";

interface Member { id: MemberId; name: string; role: string; initials: string; color: string; note: string; tags: string[]; }
const members: Member[] = [
  { id: "family", name: "Everyone", role: "Shared family defaults", initials: "∴", color: "olive", note: "The things that are true for most trips together", tags: ["Balanced days", "Vegetarian-friendly", "One central base"] },
  { id: "munish", name: "Munish", role: "You", initials: "MG", color: "coral", note: "Primary planner and decision maker", tags: ["See the context", "Local food", "Comfortable room"] },
  { id: "rhea", name: "Rhea", role: "Partner", initials: "R", color: "plum", note: "Added from a planning conversation", tags: ["Relaxed mornings", "Vegetarian", "Quiet room"] },
  { id: "kabir", name: "Kabir", role: "Child · 8", initials: "K", color: "blue", note: "Age is useful for activities and pacing", tags: ["Earlier dinner", "Shorter walks", "Pool time"] },
];

const options = [
  { id: "roster" as const, label: "A · Family roster", summary: "Start with people cards, then add only what matters.", cost: "A clear review home, if empty fields stay quiet." },
  { id: "questions" as const, label: "B · Trip questions", summary: "Ask only what this next trip needs.", cost: "Durable facts may wait until they matter." },
  { id: "defaults" as const, label: "C · Shared defaults", summary: "Set the family norm, then add exceptions.", cost: "Individual overrides need strong visibility." },
  { id: "chat" as const, label: "D · Chat-led profile", summary: "Notice, suggest, and confirm tiny facts in context.", cost: "The later review surface must make growth visible." },
  { id: "matrix" as const, label: "E · Profile matrix", summary: "Compare everyone across a few travel dimensions.", cost: "Powerful review, but it can feel like admin." },
];

function PersonCard({ member, selected, onSelect }: { member: Member; selected: boolean; onSelect: () => void }) {
  return <button className={`person-card ${selected ? "selected" : ""}`} onClick={onSelect}><span className={`person-avatar ${member.color}`}>{member.initials}</span><span><strong>{member.name}</strong><small>{member.role}</small></span>{selected && <Check size={16} />}</button>;
}

function CapturePanel({ option }: { option: OptionId }) {
  const [selected, setSelected] = useState<MemberId>(option === "defaults" ? "family" : "rhea");
  const [suggestion, setSuggestion] = useState<"new" | "saved" | "dismissed">("new");
  const [tripNeed, setTripNeed] = useState("room and pace");
  const active = members.find((member) => member.id === selected) || members[0];
  const dimensions = useMemo(() => ["Pace", "Food", "Mobility", "Sleep"], []);
  const chooseSuggestion = (choice: "saved" | "dismissed") => setSuggestion(choice);

  return <section className={`family-preview mode-${option}`} aria-label="Family details capture preview">
    <aside className="family-rail"><div className="family-brand"><span><UsersRound size={18} /></span><strong>Our travel profile</strong></div><p className="rail-caption">A little context, remembered only to make the next trip easier.</p><div className="people-list">{members.map((member) => <PersonCard key={member.id} member={member} selected={selected === member.id} onSelect={() => setSelected(member.id)} />)}</div><button className="add-person"><span>+</span> Add someone</button><div className="privacy-note"><ShieldCheck size={15} /><span>You decide what is saved. Change or remove it anytime.</span></div></aside>
    <div className="family-main"><header className="family-header"><div><p className="section-kicker">Family details</p><h2>{option === "chat" ? "We can learn this as you plan" : option === "questions" ? "Just enough for this trip" : "Make the next trip easier"}</h2><p>Shared context first. Individual needs where they make a difference.</p></div><div className="completion"><strong>{option === "chat" ? "Growing naturally" : "3 of 6 useful"}</strong><span>{option === "chat" ? "2 facts learned this week" : "You can stop here"}</span></div></header>
      {option === "chat" ? <div className="chat-capture"><div className="chat-line assistant"><span className="chat-icon"><Sparkles size={14} /></span><p>Rhea mentioned she likes relaxed mornings. Should I remember that for future trips?</p></div>{suggestion === "new" ? <div className="suggestion-card"><div><span className="learned-label"><Clock3 size={13} /> Not saved yet</span><strong>Rhea · Morning rhythm</strong><small>Suggested from your planning conversation</small></div><div className="suggestion-actions"><button onClick={() => chooseSuggestion("saved")}><Check size={14} /> Remember</button><button onClick={() => chooseSuggestion("dismissed")}>Not now</button></div></div> : <div className={`result-card ${suggestion}`}><Check size={15} />{suggestion === "saved" ? "Remembered: Rhea prefers relaxed mornings." : "Nothing saved. We will not ask again for this fact."}</div>}<div className="chat-line user"><span className="chat-icon">MG</span><p>For this Rajasthan trip, keep the mornings easy for everyone.</p></div><div className="trip-inference"><MessageCircle size={15} /><div><strong>Trip-only suggestion</strong><span>Relaxed mornings · Rajasthan · only this trip</span></div><button onClick={() => setTripNeed("easy mornings")}>Use for trip</button></div></div> : option === "matrix" ? <div className="matrix-wrap"><div className="matrix-heading"><div><h3>Compare the family</h3><p>See differences before they become surprises.</p></div><span className="soft-badge">4 travellers</span></div><div className="matrix"><div className="matrix-cell matrix-label">Needs</div>{members.slice(1).map((member) => <div className="matrix-cell matrix-person" key={member.id}><span className={`mini-avatar ${member.color}`}>{member.initials}</span>{member.name}</div>)}{dimensions.map((dimension, index) => <div className="matrix-row" key={dimension}><span>{dimension}</span>{members.slice(1).map((member) => <button key={member.id} className="matrix-value" onClick={() => setSelected(member.id)}>{member.tags[index % member.tags.length]}</button>)}</div>)}</div></div> : <div className="capture-layout"><div className="people-column">{option === "questions" && <div className="trip-question"><span className="question-number">01</span><div><strong>For this Rajasthan trip</strong><p>What would make the days work better for your family?</p></div><button onClick={() => setTripNeed(tripNeed === "room and pace" ? "easy mornings" : "room and pace")}><Heart size={14} /> {tripNeed}</button></div>}{option === "defaults" && <div className="shared-first"><span><UsersRound size={15} /></span><div><strong>Start with the family norm</strong><p>Set once, then add a person-specific exception only when needed.</p></div></div>}{members.map((member) => <PersonCard key={member.id} member={member} selected={selected === member.id} onSelect={() => setSelected(member.id)} />)}</div><div className="detail-card"><div className="detail-heading"><span className={`person-avatar ${active.color}`}>{active.initials}</span><div><h3>{active.name}</h3><p>{active.note}</p></div></div><p className="detail-label">Quick details</p><div className="quick-tags">{active.tags.map((tag) => <button key={tag} onClick={() => setSuggestion("saved")} className="quick-tag">{tag}<span>+</span></button>)}</div><div className="empty-prompt"><CircleHelp size={16} /><span>Only add what helps the planner make a better choice. You can tell us the rest naturally in chat.</span></div></div></div>}
    </div>
  </section>;
}

function App() {
  const [option, setOption] = useState<OptionId>("chat");
  return <main className="lab-page"><div className="lab-wrap"><LabNavigation current="catalog" /><header className="lab-header"><div><p className="lab-kicker"><UsersRound size={16} /> Lab #26 · Family and traveler details</p><h1>A family profile that grows with the trip.</h1><p>Capture shared context and individual needs without turning family life into a form. Start small, learn naturally from chat, and make every saved fact visible and reversible.</p></div><div className="principle-card"><span>Product principle</span><strong>Ask less.<br />Remember helpfully.</strong><small>Explicitly saved · passively suggested · trip-only context</small></div></header><LabScope labId="family-details" /><OptionContrast labId="family-details" /><section className="option-picker"><div className="section-kicker">Five ways in</div><div className="option-grid">{options.map((item) => <button key={item.id} className={option === item.id ? "selected" : ""} onClick={() => setOption(item.id)}><span className="option-label">{item.label}</span><strong>{item.summary}</strong><small>{item.cost}</small></button>)}</div></section><CapturePanel option={option} /><DecisionCapture labId="family-details" labTitle="A family profile that grows with the trip" options={options.map(({ id, label }) => ({ id, label }))} activeOption={option} onChoose={(id) => setOption(id as OptionId)} /></div></main>;
}

ReactDOM.createRoot(document.getElementById("root")!).render(<App />);
