import { useMemo, useState } from "react";
import ReactDOM from "react-dom/client";
import { Check, ChevronRight, CircleUserRound, Info, Search, Sparkles, Tag, UserRound } from "lucide-react";
import { DecisionCapture } from "../shared/DecisionCapture";
import { LabNavigation } from "../shared/LabNavigation";
import { LabScope } from "../shared/LabScope";
import { OptionContrast } from "../shared/OptionContrast";
import { useLabSelections } from "../shared/useLabSelections";
import "../../../src/index.css";
import "./styles.css";

type OptionId = "shelf" | "briefing" | "palette";
type PreferenceKey = "trip_pace" | "planning_style" | "stay_style" | "food";

interface PreferenceTag {
  label: string;
  value: string;
  detail: string;
}

interface PreferenceGroup {
  key: PreferenceKey;
  label: string;
  hint: string;
  tags: PreferenceTag[];
}

const preferenceGroups: PreferenceGroup[] = [
  {
    key: "trip_pace",
    label: "Trip rhythm",
    hint: "How full should a day feel?",
    tags: [
      { label: "Balanced", value: "balanced", detail: "A full day with room to breathe" },
      { label: "See it all", value: "see_it_all", detail: "More anchors, fewer empty windows" },
      { label: "Relaxed", value: "relaxed", detail: "Fewer stops and generous free time" },
    ],
  },
  {
    key: "planning_style",
    label: "Planning style",
    hint: "How should the planner make decisions?",
    tags: [
      { label: "Surprise me", value: "surprise_me", detail: "Let the planner choose the strongest fit" },
      { label: "Show me options", value: "show_options", detail: "Bring back a short list to compare" },
      { label: "Keep it flexible", value: "flexible", detail: "Protect open time for discoveries" },
    ],
  },
  {
    key: "stay_style",
    label: "Where you stay",
    hint: "What makes a base work?",
    tags: [
      { label: "Central and walkable", value: "central_walkable", detail: "Trade a little space for a better base" },
      { label: "Quiet retreat", value: "quiet_retreat", detail: "A calmer stay away from the busiest streets" },
      { label: "Best value", value: "best_value", detail: "Keep the total practical cost in view" },
    ],
  },
  {
    key: "food",
    label: "Food and flavour",
    hint: "What should the itinerary notice?",
    tags: [
      { label: "Local favourites", value: "local_favourites", detail: "Neighbourhood places worth the detour" },
      { label: "Vegetarian", value: "vegetarian", detail: "Vegetarian-first choices and clear menus" },
      { label: "Food is part of the trip", value: "food_centric", detail: "Build the day around memorable meals" },
    ],
  },
];

const defaultValues: Record<PreferenceKey, string> = {
  trip_pace: "balanced",
  planning_style: "show_options",
  stay_style: "central_walkable",
  food: "local_favourites",
};

const options = [
  { id: "shelf" as const, label: "A · Preference shelf", summary: "See the whole profile at a glance, then make quick edits with tags.", cost: "Needs a small amount of information architecture up front." },
  { id: "briefing" as const, label: "B · Trip briefing", summary: "Answer one friendly preference group at a time with smart defaults.", cost: "Beautiful for setup, slower for everyday corrections." },
  { id: "palette" as const, label: "C · Command palette", summary: "Search or jump directly to any preference without browsing sections.", cost: "Fast for experts, but the profile becomes less legible as a whole." },
];

function TagButton({ tag, selected, onClick }: { tag: PreferenceTag; selected: boolean; onClick: () => void }) {
  return (
    <button className={`tag-button ${selected ? "is-selected" : ""}`} onClick={onClick} aria-pressed={selected}>
      <span>{tag.label}</span>
      {selected ? <Check size={15} aria-hidden /> : <span className="tag-plus">+</span>}
    </button>
  );
}

function ProfilePreview({ option }: { option: OptionId }) {
  const [values, setValues] = useState(defaultValues);
  const [activeGroup, setActiveGroup] = useState<PreferenceKey>("trip_pace");
  const [saved, setSaved] = useState(true);
  const [query, setQuery] = useState("");
  const active = preferenceGroups.find((group) => group.key === activeGroup) || preferenceGroups[0];
  const selectedTags = useMemo(() => preferenceGroups.map((group) => ({ group, tag: group.tags.find((tag) => tag.value === values[group.key])! })), [values]);
  const visibleGroups = query
    ? preferenceGroups.filter((group) => `${group.label} ${group.hint} ${group.tags.map((tag) => tag.label).join(" ")}`.toLowerCase().includes(query.toLowerCase()))
    : preferenceGroups;
  const choose = (key: PreferenceKey, value: string) => {
    setValues((current) => ({ ...current, [key]: value }));
    setSaved(false);
  };

  return (
    <section className={`profile-preview option-${option}`} aria-label="Profile settings preview">
      <div className="profile-sidebar">
        <div className="profile-avatar"><CircleUserRound size={20} /></div>
        <div><strong>Munish Goyal</strong><span>Personal travel profile</span></div>
        <nav>
          <button className="nav-active"><Sparkles size={15} /> Preferences</button>
          <button><UserRound size={15} /> About me</button>
          <button><Info size={15} /> Travel details</button>
        </nav>
        <div className="sidebar-note"><Tag size={15} /><span>These choices shape every new trip. Change them anytime.</span></div>
      </div>
      <div className="profile-main">
        <header className="profile-title">
          <div><p className="section-kicker">Your travel profile</p><h2>{option === "briefing" ? "Let's tune your next trip" : option === "palette" ? "Profile command center" : "A better trip starts here"}</h2><p>Tell Tripplanner what feels like you. You can always change a choice for one trip later.</p></div>
          <button className={`save-button ${saved ? "saved" : ""}`} onClick={() => setSaved(true)}>{saved ? <Check size={15} /> : null}{saved ? "Saved" : "Save changes"}</button>
        </header>
        {option === "palette" && <label className="profile-search"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Find a preference" /><kbd>⌘ K</kbd></label>}
        <div className="profile-body">
          <div className="preference-content">
            {option === "briefing" ? (
              <div className="briefing-card"><span className="step-count">01 / 04</span><h3>What should a day feel like?</h3><p>We will use this to balance must-sees with time to wander.</p><div className="tag-stack">{active.tags.map((tag) => <TagButton key={tag.value} tag={tag} selected={values[active.key] === tag.value} onClick={() => choose(active.key, tag.value)} />)}</div><button className="next-button" onClick={() => setActiveGroup(preferenceGroups[(preferenceGroups.findIndex((group) => group.key === activeGroup) + 1) % preferenceGroups.length].key)}>Next preference <ChevronRight size={16} /></button></div>
            ) : (
              visibleGroups.map((group) => <div className="preference-group" key={group.key}><div className="group-heading"><div><h3>{group.label}</h3><p>{group.hint}</p></div><code>{group.key}</code></div><div className="tag-row">{group.tags.map((tag) => <TagButton key={tag.value} tag={tag} selected={values[group.key] === tag.value} onClick={() => choose(group.key, tag.value)} />)}</div></div>)
            )}
            <div className="about-section"><div className="about-heading"><div><h3>About me</h3><p>Optional context helps the planner make better calls.</p></div><span>Saved privately</span></div><textarea defaultValue="I like thoughtful days, good neighbourhood food, and a comfortable base. I am happy to trade a little time for a better experience." aria-label="About me" /></div>
          </div>
          <aside className="understanding-card"><div className="understanding-title"><span className="mapping-icon"><Sparkles size={15} /></span><div><strong>What Tripplanner understands</strong><p>Friendly choices, precise planning</p></div></div>{selectedTags.map(({ group, tag }) => <div className="mapping-row" key={group.key}><div><span>{group.label}</span><strong>{tag.label}</strong></div><code>{group.key}: {tag.value}</code></div>)}<p className="mapping-footnote">The words are human. The values stay stable for the planner and every future trip.</p></aside>
        </div>
      </div>
    </section>
  );
}

function App() {
  const [option, setOption] = useState<OptionId>("shelf");
  useLabSelections();
  const activeOption = option;
  return <main className="lab-page"><div className="lab-wrap"><LabNavigation current="catalog" /><header className="lab-header"><div><p className="lab-kicker"><Sparkles size={16} /> Lab #25 · Profile and preferences</p><h1>Profile, in choices you can see.</h1><p>Reimagine About me as a quick, calm place to tell the planner what matters. Choose tags instead of translating your travel life into form fields, while the profile keeps an exact internal vocabulary underneath.</p></div><div className="schema-badge"><span>Internal contract</span><code>trip_pace: balanced</code><code>trip_pace: see_it_all</code><code>trip_pace: relaxed</code></div></header><LabScope labId="profile-preferences" /><OptionContrast labId="profile-preferences" /><section className="option-picker"><div className="section-kicker">Three ways in</div><div className="option-grid">{options.map((item) => <button key={item.id} className={activeOption === item.id ? "selected" : ""} onClick={() => setOption(item.id)}><span className="option-label">{item.label}</span><strong>{item.summary}</strong><small>{item.cost}</small></button>)}</div></section><ProfilePreview option={activeOption} /><DecisionCapture labId="profile-preferences" labTitle="Profile, in choices you can see" options={options.map(({ id, label }) => ({ id, label }))} activeOption={activeOption} onChoose={(id) => setOption(id as OptionId)} /></div></main>;
}

ReactDOM.createRoot(document.getElementById("root")!).render(<App />);
