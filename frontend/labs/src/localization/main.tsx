import React, { useState } from "react";
import ReactDOM from "react-dom/client";
import {
  ArrowRight,
  CalendarDays,
  Check,
  ChevronDown,
  CircleUserRound,
  Clock3,
  Download,
  Globe2,
  Languages,
  Map,
  MapPin,
  Plane,
  ReceiptText,
  Settings2,
  TrainFront,
  WalletCards,
} from "lucide-react";
import "../../../src/index.css";
import { DecisionCapture } from "../shared/DecisionCapture";
import { LabNavigation } from "../shared/LabNavigation";
import { LabScope } from "../shared/LabScope";
import { OptionContrast } from "../shared/OptionContrast";
import "./styles.css";
import "./mobile.css";

type VariantId = "welcome" | "confirm" | "profile" | "quick" | "trip-lens";
type Surface = "home" | "workspace" | "profile";
type FixtureId = "rajasthan" | "pacific" | "highlands" | "eurostar";

interface Fixture {
  id: FixtureId;
  flag: string;
  region: string;
  language: string;
  locale: string;
  currency: "INR" | "USD" | "GBP" | "EUR";
  title: string;
  route: string;
  dates: string;
  time: string;
  distance: string;
  temperature: string;
  total: number;
  sourceAmount: string;
  sourceCurrency: string;
  practical: string[];
  stops: { day: string; city: string; detail: string; mode: "plane" | "train" | "road" }[];
}

const variants = [
  {
    id: "welcome" as const,
    label: "A · Welcome setup",
    summary: "Country and language are a deliberate first-visit step before the planner begins.",
    cost: "Clear, but asks everyone to configure the product before seeing its value.",
  },
  {
    id: "confirm" as const,
    label: "B · Detect, then confirm",
    summary: "Browser region seeds a compact confirmation banner on Home and disappears after one answer.",
    cost: "Fast for most people, but detection can be wrong for travelers, VPNs, and shared devices.",
  },
  {
    id: "profile" as const,
    label: "C · Profile-first",
    summary: "A quiet Home chip opens Region and language inside Account settings, where the choice persists.",
    cost: "The cleanest long-term home, though a first-time visitor may not notice the inferred default.",
  },
  {
    id: "quick" as const,
    label: "D · Workspace quick switch",
    summary: "A compact locale control sits beside Export for people who compare formats often.",
    cost: "Immediate and visible, but spends scarce workspace chrome on an infrequent preference.",
  },
  {
    id: "trip-lens" as const,
    label: "E · Profile + trip lens",
    summary: "Profile owns the default; Trip actions can override display currency and reveal provider currency.",
    cost: "Most honest for cross-border prices, with the most concepts to explain and persist.",
  },
];

const fixtures: Fixture[] = [
  {
    id: "rajasthan",
    flag: "IN",
    region: "India",
    language: "English (India)",
    locale: "en-IN",
    currency: "INR",
    title: "Rajasthan heritage circuit",
    route: "Delhi → Jaipur → Jodhpur → Udaipur",
    dates: "12–20 November 2026",
    time: "19:30",
    distance: "287 km",
    temperature: "29°C",
    total: 184600,
    sourceAmount: "$620",
    sourceCurrency: "USD · flight",
    practical: ["GST and mandatory hotel fees separated", "Vegetarian and Jain meal confidence", "Left-hand traffic · driver recommended", "Indian address and +91 phone formats", "Diwali and local closure checks"],
    stops: [
      { day: "Days 1–2", city: "Delhi", detail: "Arrival buffer · Humayun’s Tomb · Old Delhi food walk", mode: "plane" },
      { day: "Days 3–4", city: "Jaipur", detail: "Shatabdi rail · Amber Fort · block-print workshop", mode: "train" },
      { day: "Days 5–6", city: "Jodhpur", detail: "Private road transfer · Mehrangarh · stepwell evening", mode: "road" },
      { day: "Days 7–9", city: "Udaipur", detail: "Ranakpur en route · lake hotel · departure flight", mode: "road" },
    ],
  },
  {
    id: "pacific",
    flag: "US",
    region: "United States",
    language: "English (US)",
    locale: "en-US",
    currency: "USD",
    title: "Pacific coast and parks",
    route: "San Francisco → Yosemite → Big Sur → Los Angeles",
    dates: "May 16–24, 2027",
    time: "7:30 PM",
    distance: "178 mi",
    temperature: "77°F",
    total: 4280,
    sourceAmount: "$1,248",
    sourceCurrency: "USD · hotel",
    practical: ["Sales tax, resort fees, and tips itemized", "12-hour time and Sunday week start", "Miles, °F, and US address and +1 phone formats", "Park reservations and holiday traffic"],
    stops: [
      { day: "Days 1–2", city: "San Francisco", detail: "Neighborhood stay · ferry market · no rental car", mode: "plane" },
      { day: "Days 3–4", city: "Yosemite", detail: "Rental pickup · timed park entry · valley shuttle", mode: "road" },
      { day: "Days 5–6", city: "Big Sur", detail: "Highway conditions · coastal lodge · flexible overlooks", mode: "road" },
      { day: "Days 7–9", city: "Los Angeles", detail: "Return car · museum day · evening departure", mode: "road" },
    ],
  },
  {
    id: "highlands",
    flag: "GB",
    region: "United Kingdom",
    language: "English (UK)",
    locale: "en-GB",
    currency: "GBP",
    title: "Scotland by rail and road",
    route: "Edinburgh → Inverness → Isle of Skye → Glasgow",
    dates: "14–22 September 2027",
    time: "19:30",
    distance: "112 mi",
    temperature: "16°C",
    total: 3260,
    sourceAmount: "€486",
    sourceCurrency: "EUR · air",
    practical: ["VAT and discretionary service marked", "24-hour rail times and Monday week start", "Miles on roads, °C for weather", "UK postcode and +44 phone formats", "Left-hand driving and ferry cut-offs"],
    stops: [
      { day: "Days 1–2", city: "Edinburgh", detail: "Old Town walk · rail-friendly hotel · castle slot", mode: "plane" },
      { day: "Days 3–4", city: "Inverness", detail: "Highland rail · Culloden · loch cruise", mode: "train" },
      { day: "Days 5–7", city: "Isle of Skye", detail: "Left-side rental · weather buffer · ferry fallback", mode: "road" },
      { day: "Days 8–9", city: "Glasgow", detail: "Car return · architecture trail · onward rail", mode: "road" },
    ],
  },
  {
    id: "eurostar",
    flag: "EU",
    region: "Euro area",
    language: "English (Europe)",
    locale: "en-IE",
    currency: "EUR",
    title: "Three capitals by rail",
    route: "Amsterdam → Brussels → Paris",
    dates: "3–10 April 2027",
    time: "19:30",
    distance: "316 km",
    temperature: "17°C",
    total: 3780,
    sourceAmount: "£238",
    sourceCurrency: "GBP · rail",
    practical: ["VAT-inclusive prices and city taxes separated", "24-hour times, Monday week start", "Metric distance and °C", "Country-specific address and phone formats", "Cross-border rail, strikes, and local holidays"],
    stops: [
      { day: "Days 1–3", city: "Amsterdam", detail: "Canal district · timed museum entry · bicycle caution", mode: "plane" },
      { day: "Days 4–5", city: "Brussels", detail: "Eurostar · Art Nouveau walk · day-trip decision", mode: "train" },
      { day: "Days 6–8", city: "Paris", detail: "Direct rail · Left Bank stay · airport transfer", mode: "train" },
    ],
  },
];

const modeIcons = { plane: Plane, train: TrainFront, road: MapPin };

function money(fixture: Fixture, value = fixture.total) {
  return new Intl.NumberFormat(fixture.locale, {
    style: "currency",
    currency: fixture.currency,
    maximumFractionDigits: 0,
  }).format(value);
}

function LocaleFields({ fixture }: { fixture: Fixture }) {
  return (
    <div className="locale-fields">
      <label><span>Country or region</span><select value={fixture.id} onChange={() => undefined}>{fixtures.map((item) => <option key={item.id} value={item.id}>{item.region}</option>)}</select></label>
      <label><span>Language</span><select value={fixture.language} onChange={() => undefined}><option>{fixture.language}</option><option disabled>More languages coming later</option></select></label>
      <label><span>Display currency</span><select value={fixture.currency} onChange={() => undefined}><option>{fixture.currency} · {money(fixture, 1).replace(/[\d.,\s]/g, "") || fixture.currency}</option></select></label>
    </div>
  );
}

function HomePreview({ variant, fixture }: { variant: VariantId; fixture: Fixture }) {
  return (
    <section className="preview-shell home-preview" aria-label="Localized Home preview">
      <header className="product-bar"><div className="brand"><span>T</span> Tripplanner</div><button className="profile-trigger" type="button"><Globe2 size={14} /> {fixture.flag} · {fixture.currency}</button></header>
      {variant === "confirm" && <div className="detect-banner"><Globe2 size={16} /><span><strong>Planning from {fixture.region}?</strong> Dates, prices, distance, and weather will use {fixture.language} conventions.</span><button type="button">Yes, use this</button><button type="button" className="text-button">Change</button></div>}
      <div className="home-hero"><p className="eyebrow">A complete trip, in your terms</p><h2>Plan globally.<br />Read it locally.</h2><p>Grounded routes, stays, and prices with the formats and practical details you expect at home.</p><div className="home-input">Where do you want to go?<button type="button"><ArrowRight size={16} /></button></div></div>
      {variant === "welcome" && <div className="welcome-panel"><div className="panel-title"><Globe2 size={18} /><span><strong>Make Tripplanner feel local</strong><small>You can change this later in Account settings.</small></span></div><LocaleFields fixture={fixture} /><button className="primary" type="button">Continue to Tripplanner</button></div>}
      {variant !== "welcome" && <div className="sample-strip"><span>Previewing</span><strong>{fixture.title}</strong><span>{money(fixture)} · {fixture.dates}</span></div>}
    </section>
  );
}

function WorkspacePreview({ variant, fixture }: { variant: VariantId; fixture: Fixture }) {
  return (
    <section className="preview-shell workspace-preview" aria-label="Localized workspace preview">
      <header className="workspace-bar"><button type="button" className="trip-name">{fixture.title}<ChevronDown size={13} /></button><div className="workspace-status">Saved · all prices checked</div><div className="workspace-actions">{variant === "quick" && <label className="quick-locale"><Globe2 size={13} /><select value={fixture.id} onChange={() => undefined}>{fixtures.map((item) => <option key={item.id} value={item.id}>{item.flag} · {item.currency}</option>)}</select></label>}{variant === "trip-lens" && <button type="button" className="lens-button"><WalletCards size={14} /> Display {fixture.currency}<ChevronDown size={12} /></button>}<button type="button"><Download size={14} /> Export</button><button type="button" aria-label="Account settings"><CircleUserRound size={15} /></button></div></header>
      <div className="workspace-summary"><div><p className="eyebrow">{fixture.route}</p><h2>{fixture.title}</h2><p>{fixture.dates} · 2 travellers</p></div><div className="total"><span>Indicative total</span><strong>{money(fixture)}</strong><small>Display estimate · source quote {fixture.sourceAmount} {fixture.sourceCurrency}</small></div></div>
      <div className="format-ribbon"><span><CalendarDays size={13} /> {fixture.dates}</span><span><Clock3 size={13} /> Dinner {fixture.time}</span><span><Map size={13} /> {fixture.distance}</span><span>{fixture.temperature}</span></div>
      <div className="workspace-body"><div className="itinerary-list">{fixture.stops.map((stop) => { const Icon = modeIcons[stop.mode]; return <article key={stop.city}><span className="route-icon"><Icon size={14} /></span><div><small>{stop.day}</small><strong>{stop.city}</strong><p>{stop.detail}</p></div></article>; })}</div><aside className="regional-panel"><p className="eyebrow">Local context applied</p><h3>What changes beyond the symbol</h3>{fixture.practical.map((item) => <div key={item}><Check size={13} /><span>{item}</span></div>)}{variant === "trip-lens" && <div className="rate-note"><ReceiptText size={14} /><span><strong>Conversion stays honest</strong>A production conversion must add its rate source and checked time.</span></div>}</aside></div>
    </section>
  );
}

function ProfilePreview({ variant, fixture }: { variant: VariantId; fixture: Fixture }) {
  return (
    <section className="preview-shell profile-preview" aria-label="Localized profile preview">
      <div className="profile-context"><div className="mini-workspace"><div className="brand"><span>T</span> Tripplanner</div><h2>{fixture.title}</h2><p>{fixture.route}</p><div className="ghost-lines"><i /><i /><i /></div></div></div>
      <aside className="settings-drawer"><header><div><p>Account settings</p><strong>Region and language</strong></div><Settings2 size={16} /></header><div className="identity"><span>MG</span><div><strong>Munish Goyal</strong><small>Used on web and mobile</small></div></div><p className="settings-copy">Your default display conventions. They never change provider quotes or passport and visa rules.</p><LocaleFields fixture={fixture} /><div className="format-preview"><span>Preview</span><strong>{money(fixture)} · {fixture.dates}</strong><small>{fixture.distance} · {fixture.temperature} · {fixture.time}</small></div>{variant === "trip-lens" && <label className="toggle-row"><span><strong>Show provider currency</strong><small>Keep the original quote beside converted prices.</small></span><input type="checkbox" defaultChecked /></label>}<button className="primary" type="button">Save regional preferences</button><p className="language-note"><Languages size={13} /> Interface language is English in this Lab. The selector establishes the future contract without pretending translations exist.</p></aside>
    </section>
  );
}

function Lab() {
  const [variantId, setVariantId] = useState<VariantId>("profile");
  const [surface, setSurface] = useState<Surface>("home");
  const [fixtureId, setFixtureId] = useState<FixtureId>("rajasthan");
  const variant = variants.find((item) => item.id === variantId)!;
  const fixture = fixtures.find((item) => item.id === fixtureId)!;

  return (
    <main className="lab-page"><div className="lab-wrap">
      <LabNavigation detail labId="localization" />
      <header className="lab-header"><div><p className="lab-kicker"><Globe2 size={16} /> Regional content and currency</p><h1>One trip planner.<br />Local ways of reading it.</h1><p>Five ways to place a durable locale preference without confusing display currency with the price a provider will actually charge.</p></div><div className="locale-manifest"><span>4 trip fixtures</span><span>5 UX options</span><span>English copy for now</span></div></header>
      <LabScope labId="localization" />
      <OptionContrast labId="localization" />
      <section className="variant-grid" aria-label="Localization UX options">{variants.map((item) => <button key={item.id} type="button" className={variantId === item.id ? "selected" : ""} onClick={() => setVariantId(item.id)}><span>{item.label}</span><p>{item.summary}</p><small>{item.cost}</small></button>)}</section>
      <div className="review-toolbar"><div><p className="eyebrow">Live comparison</p><strong>{variant.label}</strong></div><div className="surface-tabs">{(["home", "workspace", "profile"] as Surface[]).map((item) => <button key={item} type="button" className={surface === item ? "active" : ""} onClick={() => setSurface(item)}>{item === "home" ? "Home" : item === "workspace" ? "Workspace" : "Profile"}</button>)}</div><div className="fixture-tabs">{fixtures.map((item) => <button key={item.id} type="button" className={fixtureId === item.id ? "active" : ""} onClick={() => setFixtureId(item.id)}>{item.flag}</button>)}</div></div>
      <div className="preview-stage">{surface === "home" ? <HomePreview variant={variantId} fixture={fixture} /> : surface === "workspace" ? <WorkspacePreview variant={variantId} fixture={fixture} /> : <ProfilePreview variant={variantId} fixture={fixture} />}</div>
      <section className="fixture-ledger"><div><p className="eyebrow">Same four stress cases in every option</p><h2>Localization is more than changing `$` to `₹`.</h2></div>{fixtures.map((item) => <button type="button" key={item.id} onClick={() => { setFixtureId(item.id); setSurface("workspace"); }}><span className="flag">{item.flag}</span><span><strong>{item.title}</strong><small>{item.route}</small></span><span><strong>{money(item)}</strong><small>{item.distance} · {item.temperature}</small></span></button>)}</section>
      <DecisionCapture labId="localization" labTitle="Regional content and currency" options={variants.map(({ id, label }) => ({ id, label }))} activeOption={variantId} onChoose={(id) => setVariantId(id as VariantId)} />
    </div></main>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><Lab /></React.StrictMode>);
