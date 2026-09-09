import { useState } from "react";
import ReactDOM from "react-dom/client";
import {
  Bell, BookOpen, CalendarDays, Check, ChevronDown, ChevronRight,
  Compass, Download, EyeOff, Layers3, List,
  LocateFixed, MapPin, Maximize2, MessageCircle, Minimize2,
  Navigation, PanelLeftClose, PanelRightClose, Plus, RotateCcw, Search, Send,
  Settings, Sparkles, Star, ThumbsDown, ThumbsUp, UserRound, WandSparkles, X,
} from "lucide-react";
import { DecisionCapture } from "../shared/DecisionCapture";
import { LabNavigation } from "../shared/LabNavigation";
import { LabScope } from "../shared/LabScope";
import { OptionContrast } from "../shared/OptionContrast";
import { options, type OptionId } from "./options";
import "../../../src/index.css";
import "./styles.css";

const days = [
  { day: 1, date: "Mon, 14 Apr", title: "Arrival & east Kyoto", tone: "Arrival", stops: [
    ["10:30", "Arrive at Kyoto Station", "Transfer · confirmed"], ["13:00", "Kiyomizu-dera", "Temple · 2 hr"], ["16:15", "Gion lanes", "Walk · 1 hr 20"],
  ]},
  { day: 2, date: "Tue, 15 Apr", title: "Arashiyama & gardens", tone: "Nature", stops: [
    ["08:00", "Bamboo Grove", "Sight · quiet hour"], ["10:15", "Tenryu-ji", "Garden · 1 hr"], ["14:30", "Okochi Sanso", "Garden · tea included"],
  ]},
  { day: 3, date: "Wed, 16 Apr", title: "Northern temples", tone: "Culture", stops: [
    ["09:00", "Kinkaku-ji", "Temple · 1 hr"], ["11:15", "Ryoan-ji", "Garden · 1 hr"], ["15:30", "Nishiki Market", "Market · 1 hr 30"],
  ]},
  { day: 4, date: "Thu, 17 Apr", title: "Fushimi & farewell", tone: "Flexible", stops: [
    ["07:30", "Fushimi Inari", "Shrine · 2 hr"], ["12:00", "Sake district", "Walk · 1 hr 30"], ["16:00", "Kyoto Station", "Departure"],
  ]},
] as const;

function Brand() {
  return <div className="pl-brand"><span><Navigation size={15} /></span><b>AI Trip Planner</b></div>;
}

function Feedback() {
  return <div className="pl-feedback" aria-label="Rate this trip"><button title="Helpful"><ThumbsUp size={13}/></button><button title="Not helpful"><ThumbsDown size={13}/></button><button><Star size={13}/> Rate</button></div>;
}

function TripActions({ minimal = false }: { minimal?: boolean }) {
  return <div className="pl-actions">
    <button title="Export itinerary"><Download size={14}/>{!minimal && <span>Export</span>}</button>
    <button title="Start a new trip"><Plus size={14}/>{!minimal && <span>New trip</span>}</button>
    <button title="Reset this trip"><RotateCcw size={13}/>{!minimal && <span>Reset</span>}</button>
  </div>;
}

function AccountActions() {
  return <div className="pl-account"><button aria-label="Settings" title="Settings"><Settings size={16}/></button><button className="signin"><UserRound size={14}/> Sign in</button></div>;
}

function Notice() {
  return <div className="pl-notice"><span><Bell size={13}/> No meal stop on Torii sunrise & north temples.</span><div><button>+1 more</button><button className="fix">Add food stops <ChevronRight size={13}/></button><button aria-label="Dismiss"><X size={13}/></button></div></div>;
}

function PinMap({ soft = false }: { soft?: boolean }) {
  return <div className={`pl-map ${soft ? "soft" : ""}`}>
    <div className="map-roads"/><span className="river"/><span className="district d1">HIGASHIYAMA</span><span className="district d2">GION</span>
    <div className="route-line"/><button className="pin p1">1</button><button className="pin p2">2</button><button className="pin p3">3</button><button className="pin p4">4</button>
    <div className="map-tools"><button title="Find me"><LocateFixed size={15}/></button><button title="Map layers"><Layers3 size={15}/></button></div>
  </div>;
}

function PlaceCard({ floating = false }: { floating?: boolean }) {
  return <aside className={`pl-place ${floating ? "floating" : ""}`}>
    <div className="place-image"><span>Sight</span><div className="temple">⌂</div></div>
    <div className="place-copy"><small>Kiyomizu-dera · 13:00</small><h3>Temple above the city</h3><div className="rating"><b>★ 4.7</b><span>44,120 reviews · ¥¥</span></div><p>A cedar stage stretches over the hillside, with wide views across spring Kyoto.</p><div className="place-meta"><span><MapPin size={12}/> 18 min from Gion</span><span><CalendarDays size={12}/> Open until 18:00</span></div><button className="primary">View stop details</button></div>
  </aside>;
}

function AssistantDock({ expanded, onToggle, label = "Ask for a change" }: { expanded: boolean; onToggle: () => void; label?: string }) {
  return <section className={`pl-assistant ${expanded ? "expanded" : ""}`}>
    <div className="assistant-head"><span><Sparkles size={14}/> Trip assistant</span><div><button onClick={onToggle} aria-label={expanded ? "Minimize assistant" : "Maximize assistant"}>{expanded ? <Minimize2 size={14}/> : <Maximize2 size={14}/>}</button><button aria-label="Hide assistant"><EyeOff size={14}/></button></div></div>
    {expanded && <div className="assistant-thread"><span className="ai">AI</span><p>I can make day 3 lighter while keeping the northern temples. Shall I move Nishiki Market to your flexible final afternoon?</p></div>}
    <div className="assistant-row"><div className="suggestions"><button>Make day 3 lighter</button><button>Add food stops</button><button>Rain plan for day 2</button></div><label><MessageCircle size={15}/><input aria-label={label} placeholder={`${label}…`}/><button className="send" aria-label="Send"><Send size={15}/></button></label></div>
  </section>;
}

function UtilityBar({ mode }: { mode: "journey" | "story" | "current" }) {
  return <><header className="pl-top"><Brand/><button className="trip-switch"><MapPin size={14}/><b>Kyoto in cherry season</b><span>(3)</span><ChevronDown size={14}/></button>
    {mode === "current" && <nav><button className="active">Workspace</button><button>Itinerary</button><button><MapPin size={13}/> Map</button><button>Guide</button></nav>}
    {mode === "journey" && <nav><button className="active">Journey</button><button>Bookings</button><button>Guide</button></nav>}
    {mode === "story" && <nav><button className="active">Plan</button><button>Map</button><button>Travel book</button></nav>}
    <span className="saved"><Check size={13}/> All changes saved</span><Feedback/><TripActions minimal/><AccountActions/>
  </header><Notice/></>;
}

function DayRail({ activeDay, onDay }: { activeDay: number; onDay: (day: number) => void }) {
  return <div className="journey-rail">{days.map((day) => <button key={day.day} className={activeDay === day.day ? "active" : ""} onClick={() => onDay(day.day)}><span>{day.day}</span><small>{day.date.replace(/,.*$/, "")}</small><b>{day.title}</b><em>{day.stops.length} stops</em></button>)}</div>;
}

function JourneyCanvas() {
  const [day, setDay] = useState(1); const [assistant, setAssistant] = useState(false); const current = days[day - 1];
  return <div className="pl-app journey"><UtilityBar mode="journey"/><div className="journey-summary"><div><small>Your trip at a glance</small><b>4 days · 10 stops · 60% ready</b></div><div className="readiness"><span style={{width:"60%"}}/></div><button><CalendarDays size={14}/> 14–18 Apr</button><button><UserRound size={14}/> 2 travellers</button></div>
    <main><PinMap/><DayRail activeDay={day} onDay={setDay}/><div className="focus-card" data-lab-change="Journey rail and focus card"><div><span className="day-number">0{day}</span><small>{current.date}</small><h2>{current.title}</h2></div><div className="focus-stops">{current.stops.map((stop, index) => <button key={stop[1]} className={index === 1 ? "selected" : ""}><time>{stop[0]}</time><span><b>{stop[1]}</b><small>{stop[2]}</small></span><ChevronRight size={14}/></button>)}</div></div><PlaceCard floating/>
    </main><AssistantDock expanded={assistant} onToggle={() => setAssistant(!assistant)} label="Change this journey"/></div>;
}

function Storyboard() {
  const [day, setDay] = useState(1); const [assistant, setAssistant] = useState(false); const current = days[day - 1];
  return <div className="pl-app story"><UtilityBar mode="story"/><div className="story-shell">
    <aside className="chapter-rail" data-lab-change="Chapter navigation"><div><small>KYOTO · 14–18 APR</small><h2>Cherry season,<br/>at your pace.</h2><div className="story-progress"><span/></div><p>4 days · 10 stops<br/>2 travellers</p></div><nav>{days.map((entry) => <button key={entry.day} onClick={() => setDay(entry.day)} className={day === entry.day ? "active" : ""}><span>0{entry.day}</span><div><b>{entry.title}</b><small>{entry.tone} · {entry.stops.length} stops</small></div></button>)}</nav><TripActions/></aside>
    <main className="story-page" data-lab-change="Editorial itinerary"><header><div><span>DAY {day} · {current.date.toUpperCase()}</span><h1>{current.title}</h1><p>A considered route through Kyoto, with enough room to notice where you are.</p></div><button><WandSparkles size={15}/> Refine this day</button></header><div className="story-list">{current.stops.map((stop, index) => <article key={stop[1]}><time>{stop[0]}</time><div className="story-dot">{index + 1}</div><div><span>{stop[2]}</span><h3>{stop[1]}</h3><p>{index === 1 ? "Allow time for the hillside approach. The quietest view is from the southern edge of the stage." : "Timing and route checked against the rest of your day."}</p><button>Open stop <ChevronRight size={13}/></button></div></article>)}</div></main>
    <aside className="evidence-rail"><div className="mini-map"><PinMap soft/></div><section><small>Why this order</small><h3>Shorter transfers, quieter hours</h3><p>This sequence saves 34 minutes and reaches the busiest sight before its afternoon peak.</p></section><section className="ready-card"><b><Check size={13}/> Day is route-ready</b><span>3 stops · 4.8 km · ¥7,400</span></section></aside>
  </div><AssistantDock expanded={assistant} onToggle={() => setAssistant(!assistant)} label="Ask about this day"/></div>;
}

function ItineraryPane({ polish = false, onHide }: { polish?: boolean; onHide: () => void }) {
  return <aside className="itinerary-pane"><header><div><small>14–18 APR · KYOTO</small><h2>Kyoto in cherry season</h2></div><div><button title="Expand itinerary"><Maximize2 size={14}/></button><button title="Hide itinerary" onClick={onHide}><PanelLeftClose size={15}/></button></div></header><div className="trip-stats"><span><b>4</b><small>DAYS</small></span><span><b>10</b><small>STOPS</small></span><span><b>60%</b><small>READY</small></span></div><div className="checkline"><span><Check/> Dates set</span><span><Check/> Every day planned</span></div>{days.slice(0,3).map((entry) => <section className="compact-day" key={entry.day}><header><span>{entry.day}</span><div><b>{entry.title}</b><small>{entry.date}</small></div><ChevronDown size={14}/></header>{entry.day === 1 && entry.stops.map(stop => <button key={stop[1]}><time>{stop[0]}</time><MapPin size={13}/><span>{stop[1]}</span></button>)}</section>)}{polish && <button className="add-day"><Plus size={14}/> Add a day</button>}</aside>;
}

function CurrentWorkspace({ polish = false }: { polish?: boolean }) {
  const [assistant, setAssistant] = useState(false); const [left, setLeft] = useState(true); const [right, setRight] = useState(true); const [max, setMax] = useState(false);
  return <div className={`pl-app current ${polish ? "polish" : "refined"}`}><UtilityBar mode="current"/><div className="day-tabs"><button><Plus size={15}/></button>{days.map(day => <button key={day.day} className={day.day === 1 ? "active" : ""}>Day {day.day}</button>)}<span/><button><Search size={14}/> Find a place</button></div>
    <main className={`workspace-grid ${!left ? "no-left" : ""} ${!right ? "no-right" : ""} ${max ? "map-max" : ""}`} data-lab-change={polish ? "Professional pane controls and finish" : "Refined three-pane workspace"}>{left && <ItineraryPane polish={polish} onHide={() => setLeft(false)}/>}<section className="map-pane"><PinMap/><header><span><MapPin size={14}/> Day 1 route</span><div>{!left && <button onClick={() => setLeft(true)}><List size={14}/> Show itinerary</button>}<button onClick={() => setMax(!max)} title={max ? "Restore map" : "Maximize map"}>{max ? <Minimize2 size={14}/> : <Maximize2 size={14}/>}</button>{right && <button onClick={() => setRight(false)} title="Hide details"><PanelRightClose size={15}/></button>}</div></header><div className="map-footer"><button><Compass size={14}/> Fit to day</button><button><Layers3 size={14}/> 4 stops</button></div></section>{right && !max && <PlaceCard/>}{!right && !max && <button className="restore-right" onClick={() => setRight(true)}><BookOpen size={14}/> Show details</button>}</main>
    <AssistantDock expanded={assistant} onToggle={() => setAssistant(!assistant)}/></div>;
}

function Preview({ option }: { option: OptionId }) {
  if (option === "journey") return <JourneyCanvas/>;
  if (option === "storyboard") return <Storyboard/>;
  return <CurrentWorkspace polish={option === "polish"}/>;
}

function App() {
  const [option, setOption] = useState<OptionId>("journey"); const active = options.find(item => item.id === option)!;
  return <main className="lab-page"><div className="lab-wrap"><LabNavigation detail labId="planner-layout-directions"/>
    <header className="lab-header"><div><p className="lab-kicker"><Compass size={16}/> Planner workspace architecture</p><h1>Four ways to<br/>inhabit a trip.</h1><p>The sbx4 planner has the right ingredients. This Lab asks whether they belong in a new spatial model, a calmer reading model, a stronger version of today's workspace, or the exact current structure with its rough edges carefully removed.</p></div><div className="principle-card"><span>The design test</span><strong>More trip.<br/>Less interface.</strong><small>Same fixture · same capability · four levels of change</small></div></header>
    <LabScope labId="planner-layout-directions"/><OptionContrast labId="planner-layout-directions"/>
    <section className="option-picker"><p className="section-kicker">Four coherent directions</p><div className="option-grid">{options.map(item => <button key={item.id} className={option === item.id ? "selected" : ""} onClick={() => setOption(item.id)}><span className="option-top"><i>{item.label}</i><em>{item.score}/100</em></span><small>{item.eyebrow}</small><strong>{item.summary}</strong><p>{item.delta}</p></button>)}</div></section>
    <section className="preview-intro"><div><p className="section-kicker">Production-scale preview</p><h2>{active.label}</h2><p><b>Exact delta:</b> {active.delta} The Kyoto content and available actions are identical in all four options.</p></div><span>Interactive · switch days, panes, and assistant</span></section>
    <div className="preview-stage"><Preview option={option}/></div>
    <DecisionCapture labId="planner-layout-directions" labTitle="Four ways to inhabit a trip" options={options.map(({id,label}) => ({id,label}))} activeOption={option} onChoose={(id) => setOption(id as OptionId)}/>
  </div></main>;
}

ReactDOM.createRoot(document.getElementById("root")!).render(<App/>);
