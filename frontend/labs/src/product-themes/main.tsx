import React, { useState } from "react";
import ReactDOM from "react-dom/client";
import { ArrowLeft, ArrowRight, CalendarDays, Compass, Map, MessageCircle, Sparkles, WalletCards } from "lucide-react";
import { DecisionCapture } from "../shared/DecisionCapture";
import { LabNavigation } from "../shared/LabNavigation";
import { LabScope } from "../shared/LabScope";
import { OptionContrast } from "../shared/OptionContrast";
import PublicEntry from "../../../src/publicEntry/PublicEntry";
import "../../../src/index.css";
import "./styles.css";
import "./landing-themes.css";

type ThemeId = "postcard" | "midnight" | "mineral" | "citrus";
type Surface = "landing" | "workspace" | "mobile";

const themes = [
  {
    id: "postcard" as const,
    label: "A · Postcard editorial",
    short: "Warm paper + coral",
    summary: "A daylight travel magazine system: soft paper, ink, coral action, and blue-green evidence surfaces.",
    bestFor: "The strongest bridge between public inspiration and serious planning.",
    fonts: "Newsreader + DM Sans",
    colors: ["#f7f2e9", "#e14d5f", "#176f72", "#1e2b31"],
  },
  {
    id: "midnight" as const,
    label: "B · Midnight atlas",
    short: "Ink + saffron",
    summary: "A cinematic atlas language that keeps the landing page memorable, then brings the workspace into the same dark family.",
    bestFor: "A confident, premium identity with strong evening browsing energy.",
    fonts: "Fraunces + Manrope",
    colors: ["#111a25", "#e8a44b", "#79c4bd", "#f5efe5"],
  },
  {
    id: "mineral" as const,
    label: "C · Coastal mineral",
    short: "Mist + terracotta",
    summary: "A calm, highly legible system built from sea-glass neutrals, mineral blue, and a grounded terracotta action color.",
    bestFor: "A quiet planner that feels dependable across dense itinerary work.",
    fonts: "Space Grotesk + Newsreader",
    colors: ["#e9f0ec", "#c95c45", "#1e6671", "#203238"],
  },
  {
    id: "citrus" as const,
    label: "D · Citrus modernist",
    short: "Chalk + cobalt",
    summary: "Bright chalk surfaces, cobalt navigation, and citrus signals give the product a more contemporary, energetic edge.",
    bestFor: "A sharper, more distinctive identity when the product wants more momentum.",
    fonts: "Manrope + Fraunces",
    colors: ["#f4f1e8", "#e36b37", "#2354a6", "#18243d"],
  },
];

const destinations = [
  { city: "Lisbon", dates: "6 days · Oct 12–17", color: "#e14d5f" },
  { city: "Porto", dates: "2 nights · wine country", color: "#176f72" },
];

function ThemeFrame({ theme, surface }: { theme: typeof themes[number]; surface: Surface }) {
  const isMobile = surface === "mobile";
  const [activeDay, setActiveDay] = useState(2);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [saved, setSaved] = useState(false);
  const accent = theme.colors[1];
  const ink = theme.colors[3];
  const secondary = theme.colors[2];

  if (surface === "landing") {
    return (
      <div className={`lab23-public-entry theme-${theme.id}`}>
        <PublicEntry onPlan={() => undefined} onSkip={() => undefined} />
      </div>
    );
  }

  return (
    <div className={`theme-frame theme-${theme.id} ${isMobile ? "theme-mobile" : ""}`} style={{ "--theme-accent": accent, "--theme-ink": ink, "--theme-secondary": secondary } as React.CSSProperties}>
      <header className="theme-nav">
        <div className="brand-lockup"><span className="brand-mark"><Compass size={16} /></span><span>tripplanner</span></div>
        <nav className="theme-nav-links" aria-label="Public navigation"><span>How it works</span><span>Saved trips</span><span>Sign in</span></nav>
        <button type="button" className="theme-nav-action" onClick={() => setAssistantOpen(true)}>Plan a trip <ArrowRight size={14} /></button>
      </header>

      {surface === "workspace" && <main className="workspace-surface">
        <div className="workspace-toolbar"><button type="button" className="trip-switcher"><span className="trip-dot" /> Lisbon + Porto <CalendarDays size={14} /></button><div className="workspace-status">Saved · 4 of 7 booking-ready</div><div className="workspace-controls"><button type="button" className="selected-control"><CalendarDays size={14} /> Itinerary</button><button type="button"><Map size={14} /> Map</button><button type="button" onClick={() => setAssistantOpen(true)}><MessageCircle size={14} /> Assistant</button></div><button type="button" className="icon-button" aria-label="Budget"><WalletCards size={16} /></button></div>
        <div className="workspace-grid"><aside className="itinerary-pane"><div className="pane-intro"><span className="section-kicker">Eight days, well spent</span><h2>Lisbon + Porto</h2><p>Oct 12–19 · 2 travelers · relaxed pace</p></div>{destinations.map((destination, index) => <button key={destination.city} type="button" onClick={() => setActiveDay(index + 1)} className={`day-row ${activeDay === index + 1 ? "active" : ""}`}><span className="day-number" style={{ background: destination.color }}>{index + 1}</span><span><strong>{destination.city}</strong><small>{destination.dates}</small></span><ArrowRight size={14} /></button>)}<div className="day-row active"><span className="day-number" style={{ background: accent }}>3</span><span><strong>Alfama slowly</strong><small>Miradouro · lunch · fado</small></span><ArrowRight size={14} /></div></aside><section className="map-pane"><div className="map-texture" /><div className="map-label map-label-one">Lisbon</div><div className="map-label map-label-two">Porto</div><div className="route-line" /><div className="map-pin pin-one">1</div><div className="map-pin pin-two">2</div><div className="map-card"><span className="section-kicker">Day {activeDay} focus</span><strong>Alfama to the river</strong><span>4.6 km · 52 min on foot</span></div></section><aside className="details-pane"><div className="detail-image" /><div className="detail-content"><span className="section-kicker">A considered morning</span><h2>Miradouro da Graça</h2><p>Start high, walk downhill, and keep lunch flexible around the light and the queue.</p><div className="detail-rule"><span>Planned time</span><strong>09:30 · 1h 20m</strong></div><div className="detail-rule"><span>Booking</span><strong className="needs-confirmation">No booking needed</strong></div><button type="button" className="secondary-button" onClick={() => setSaved(!saved)}>{saved ? "Saved to trip" : "Keep this stop"}</button></div></aside></div>
      </main>}

      {surface === "mobile" && <main className="mobile-surface"><div className="mobile-cover"><div className="mobile-cover-art"><div className="sun-disc" /></div><div className="mobile-cover-content"><span className="section-kicker">Your trip is taking shape</span><h1>Lisbon, at a human pace.</h1><p>6 days · 2 travelers · boutique stay</p><button type="button" className="primary-button" onClick={() => setAssistantOpen(true)}>Ask the planner <MessageCircle size={15} /></button></div></div><div className="mobile-tabs"><span className="active-tab">Overview</span><span>Map</span><span>Assistant</span></div><div className="mobile-list"><div className="mobile-list-heading"><span className="section-kicker">The good bits</span><span>6 days</span></div>{["Alfama morning", "A table in Mouraria", "Train to Porto"].map((item, index) => <div className="mobile-stop" key={item}><span className="mobile-stop-number">{index + 1}</span><span><strong>{item}</strong><small>{index === 0 ? "Day 2 · 09:30" : index === 1 ? "Day 2 · 13:00" : "Day 4 · 10:45"}</small></span><ArrowRight size={14} /></div>)}</div></main>}

      {assistantOpen && <div className="theme-modal"><button type="button" className="modal-backdrop" onClick={() => setAssistantOpen(false)} aria-label="Close planner" /><section className="theme-dialog" role="dialog" aria-modal="true"><span className="section-kicker">Trip assistant</span><h2>Where should we take you?</h2><p>Tell me a place, a feeling, or a constraint. I’ll turn it into a complete first plan.</p><div className="fake-input">Lisbon, six days in October <ArrowRight size={16} /></div><div className="suggestion-row"><span>quiet mornings</span><span>good food</span><span>no rushed transfers</span></div></section></div>}
    </div>
  );
}

function ProductThemesLab() {
  const params = new URLSearchParams(window.location.search);
  const requested = themes.find((theme) => theme.id === params.get("preview"));
  const [themeId, setThemeId] = useState<ThemeId>(requested?.id || "postcard");
  const [surface, setSurface] = useState<Surface>(params.get("surface") === "workspace" || params.get("surface") === "mobile" ? params.get("surface") as Surface : "landing");
  const theme = themes.find((item) => item.id === themeId) || themes[0];

  if (requested) return <main className="full-preview"><ThemeFrame theme={requested} surface={surface} /><a className="exit-preview" href="./lab-23-product-themes.html"><ArrowLeft size={14} /> Exit full-size preview</a></main>;

  return <main className="lab-page"><div className="lab-wrap"><LabNavigation detail labId="product-themes" /><header className="lab-header"><div><div className="lab-eyebrow"><Sparkles size={16} /> Product-wide visual language</div><h1>One product, four ways to feel it.</h1><p>Today the landing page is dark and the planner is light. This Lab tests four complete systems across the public edge, the spatial workspace, and mobile so the handoff feels intentional instead of accidental.</p></div></header><LabScope labId="product-themes" /><OptionContrast labId="product-themes" /><section className="decision-rules"><div><strong>Every option shares</strong><span>the same trip, hierarchy, copy, and interactions.</span></div><div><strong>The choice changes</strong><span>surface temperature, type pairing, contrast, and signal colors.</span></div><div><strong>Recommendation</strong><span>Start with A unless the product deliberately wants a darker identity everywhere.</span></div></section><div className="theme-options" role="tablist" aria-label="Product-wide visual themes">{themes.map((item) => <button key={item.id} type="button" role="tab" aria-selected={themeId === item.id} onClick={() => setThemeId(item.id)} className={`theme-option ${themeId === item.id ? "selected" : ""}`}><span className="swatches">{item.colors.map((color) => <i key={color} style={{ background: color }} />)}</span><strong>{item.label}</strong><span>{item.summary}</span><small>{item.bestFor}</small></button>)}</div><div className="preview-toolbar"><div><span className="section-kicker">Live comparison</span><strong>{theme.label}</strong></div><div className="surface-tabs" role="tablist" aria-label="Preview surface">{(["landing", "workspace", "mobile"] as Surface[]).map((item) => <button key={item} type="button" className={surface === item ? "active" : ""} onClick={() => setSurface(item)}>{item === "landing" ? "Landing" : item === "workspace" ? "Workspace" : "Mobile"}</button>)}</div><a className="preview-link" href={`?preview=${theme.id}&surface=${surface}`}>Open full size <ArrowRight size={14} /></a></div><section className="theme-preview" aria-label={`${theme.label} preview`}><ThemeFrame theme={theme} surface={surface} /></section><div className="theme-notes"><article><span className="note-index">01</span><strong>Continuity over contrast</strong><p>The landing page can be expressive, but its paper, type, and action colors must be recognizable when the user enters the dense planner.</p></article><article><span className="note-index">02</span><strong>One accent does the work</strong><p>Primary actions, active itinerary state, and saved outcomes share one signal. Secondary evidence gets a cooler supporting color.</p></article><article><span className="note-index">03</span><strong>Dark is a decision, not a default</strong><p>Option B is viable only if the workspace also accepts dark map chrome, dark inspector surfaces, and more demanding contrast testing.</p></article></div><DecisionCapture labId="product-themes" labTitle="Product-wide visual themes" options={themes} activeOption={themeId} onChoose={(id) => setThemeId(id as ThemeId)} /></div></main>;
}

ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><ProductThemesLab /></React.StrictMode>);
