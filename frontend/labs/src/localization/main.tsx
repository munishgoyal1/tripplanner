import React, { useEffect, useState } from "react";
import ReactDOM from "react-dom/client";
import {
  ArrowLeft,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleUserRound,
  ExternalLink,
  FileText,
  Globe2,
  Languages,
  List,
  Map,
  MessageCircle,
  MoreHorizontal,
  Navigation,
  PanelRight,
  Plane,
  Plus,
  ReceiptText,
  RotateCcw,
  Settings2,
  SlidersHorizontal,
  TrainFront,
  UserRound,
  WalletCards,
  X,
} from "lucide-react";
import PublicEntry from "../../../src/publicEntry/PublicEntry";
import "../../../src/index.css";
import { DecisionCapture } from "../shared/DecisionCapture";
import { LabNavigation } from "../shared/LabNavigation";
import { LabScope } from "../shared/LabScope";
import { OptionContrast } from "../shared/OptionContrast";
import "./styles.css";
import "./mobile.css";
import "./realistic.css";

type VariantId = "welcome" | "confirm" | "profile" | "quick" | "trip-lens";
type Surface = "home" | "workspace" | "profile";
type FixtureId = "rajasthan" | "pacific" | "highlands" | "eurostar";
type LocaleId = "india" | "us" | "uk" | "euro";

interface LocalePreset {
  id: LocaleId;
  flag: string;
  region: string;
  language: string;
  locale: string;
  currency: "INR" | "USD" | "GBP" | "EUR";
  rateFromUsd: number;
  weekStart: string;
  units: string;
  temperature: string;
  feeRule: string;
  phoneRule: string;
}

interface Fixture {
  id: FixtureId;
  localeId: LocaleId;
  title: string;
  route: string;
  start: string;
  end: string;
  totalUsd: number;
  distanceKm: number;
  temperatureC: number;
  sourceAmount: string;
  sourceCurrency: string;
  destinationContext: string;
  stops: { day: string; city: string; detail: string; mode: "plane" | "train" | "road" }[];
}

const variants = [
  {
    id: "welcome" as const,
    label: "A · Welcome setup",
    summary: "Country, language, and display currency appear over the real first visit before planning begins.",
    cost: "Explicit, but interrupts the production landing experience before its proof of value.",
  },
  {
    id: "confirm" as const,
    label: "B · Detect, then confirm",
    summary: "A one-time confirmation sits below the real masthead and disappears after one answer.",
    cost: "Fast when inference is right; travelers, VPNs, and shared devices still need correction.",
  },
  {
    id: "profile" as const,
    label: "C · Profile-first",
    summary: "The real landing stays quiet; Region and language lives in the current Account settings drawer.",
    cost: "Best durable home, but the inferred first-use default needs B's one-time confirmation.",
  },
  {
    id: "quick" as const,
    label: "D · Workspace quick switch",
    summary: "A compact locale control joins the real toolbar beside trip actions and Account settings.",
    cost: "Very visible, but competes with pane controls and dynamic workspace status every day.",
  },
  {
    id: "trip-lens" as const,
    label: "E · Profile + trip lens",
    summary: "Profile owns the default; the workspace can temporarily change display currency per trip.",
    cost: "Strongest cross-border price honesty, with an extra display-versus-source concept to teach.",
  },
];

const localePresets: LocalePreset[] = [
  {
    id: "india",
    flag: "IN",
    region: "India",
    language: "English (India)",
    locale: "en-IN",
    currency: "INR",
    rateFromUsd: 83,
    weekStart: "Monday week start",
    units: "km",
    temperature: "C",
    feeRule: "GST and mandatory fees separated",
    phoneRule: "Indian address and +91 phone formats",
  },
  {
    id: "us",
    flag: "US",
    region: "United States",
    language: "English (US)",
    locale: "en-US",
    currency: "USD",
    rateFromUsd: 1,
    weekStart: "Sunday week start",
    units: "mi",
    temperature: "F",
    feeRule: "Sales tax, resort fees, and tips itemized",
    phoneRule: "US address and +1 phone formats",
  },
  {
    id: "uk",
    flag: "GB",
    region: "United Kingdom",
    language: "English (UK)",
    locale: "en-GB",
    currency: "GBP",
    rateFromUsd: 0.78,
    weekStart: "Monday week start",
    units: "mi",
    temperature: "C",
    feeRule: "VAT and discretionary service marked",
    phoneRule: "UK postcode and +44 phone formats",
  },
  {
    id: "euro",
    flag: "EU",
    region: "Euro area",
    language: "English (Europe)",
    locale: "en-IE",
    currency: "EUR",
    rateFromUsd: 0.92,
    weekStart: "Monday week start",
    units: "km",
    temperature: "C",
    feeRule: "VAT-inclusive prices and city taxes separated",
    phoneRule: "Country-specific address and phone formats",
  },
];

const fixtures: Fixture[] = [
  {
    id: "rajasthan",
    localeId: "india",
    title: "Rajasthan heritage circuit",
    route: "Delhi → Jaipur → Jodhpur → Udaipur",
    start: "2026-11-12T12:00:00Z",
    end: "2026-11-20T12:00:00Z",
    totalUsd: 184600 / 83,
    distanceKm: 287,
    temperatureC: 29,
    sourceAmount: "$620",
    sourceCurrency: "USD · flight · checked 12 min ago",
    destinationContext: "Left-hand traffic · vegetarian and Jain confidence · Diwali closure checks",
    stops: [
      { day: "Days 1–2", city: "Delhi", detail: "Arrival buffer · Old Delhi food walk · Humayun's Tomb", mode: "plane" },
      { day: "Days 3–4", city: "Jaipur", detail: "Shatabdi rail · Amber Fort · block-print workshop", mode: "train" },
      { day: "Days 5–6", city: "Jodhpur", detail: "Private transfer · Mehrangarh · stepwell evening", mode: "road" },
      { day: "Days 7–9", city: "Udaipur", detail: "Ranakpur en route · lake hotel · departure flight", mode: "road" },
    ],
  },
  {
    id: "pacific",
    localeId: "us",
    title: "Pacific coast and parks",
    route: "San Francisco → Yosemite → Big Sur → Los Angeles",
    start: "2027-05-16T12:00:00Z",
    end: "2027-05-24T12:00:00Z",
    totalUsd: 4280,
    distanceKm: 286,
    temperatureC: 25,
    sourceAmount: "$1,248",
    sourceCurrency: "USD · hotel · checked 8 min ago",
    destinationContext: "Park reservations · holiday traffic · tipping and resort-fee expectations",
    stops: [
      { day: "Days 1–2", city: "San Francisco", detail: "Neighborhood stay · ferry market · no rental car", mode: "plane" },
      { day: "Days 3–4", city: "Yosemite", detail: "Rental pickup · timed park entry · valley shuttle", mode: "road" },
      { day: "Days 5–6", city: "Big Sur", detail: "Highway conditions · coastal lodge · flexible overlooks", mode: "road" },
      { day: "Days 7–9", city: "Los Angeles", detail: "Return car · museum day · evening departure", mode: "road" },
    ],
  },
  {
    id: "highlands",
    localeId: "uk",
    title: "Scotland by rail and road",
    route: "Edinburgh → Inverness → Isle of Skye → Glasgow",
    start: "2027-09-14T12:00:00Z",
    end: "2027-09-22T12:00:00Z",
    totalUsd: 3260 / 0.78,
    distanceKm: 180,
    temperatureC: 16,
    sourceAmount: "€486",
    sourceCurrency: "EUR · air · checked 18 min ago",
    destinationContext: "Left-hand driving · ferry cut-offs · rail disruption and weather buffers",
    stops: [
      { day: "Days 1–2", city: "Edinburgh", detail: "Old Town walk · rail-friendly hotel · castle slot", mode: "plane" },
      { day: "Days 3–4", city: "Inverness", detail: "Highland rail · Culloden · loch cruise", mode: "train" },
      { day: "Days 5–7", city: "Isle of Skye", detail: "Left-side rental · weather buffer · ferry fallback", mode: "road" },
      { day: "Days 8–9", city: "Glasgow", detail: "Car return · architecture trail · onward rail", mode: "road" },
    ],
  },
  {
    id: "eurostar",
    localeId: "euro",
    title: "Three capitals by rail",
    route: "Amsterdam → Brussels → Paris",
    start: "2027-04-03T12:00:00Z",
    end: "2027-04-10T12:00:00Z",
    totalUsd: 3780 / 0.92,
    distanceKm: 316,
    temperatureC: 17,
    sourceAmount: "£238",
    sourceCurrency: "GBP · rail · checked 6 min ago",
    destinationContext: "Cross-border rail · city taxes · strikes and local public holidays",
    stops: [
      { day: "Days 1–3", city: "Amsterdam", detail: "Canal district · museum entry · bicycle caution", mode: "plane" },
      { day: "Days 4–5", city: "Brussels", detail: "Eurostar · Art Nouveau walk · day-trip decision", mode: "train" },
      { day: "Days 6–8", city: "Paris", detail: "Direct rail · Left Bank stay · airport transfer", mode: "train" },
    ],
  },
];

const modeIcons = { plane: Plane, train: TrainFront, road: Navigation };

function presetFor(id: LocaleId) {
  return localePresets.find((preset) => preset.id === id) ?? localePresets[0];
}

function fixtureFor(id: FixtureId) {
  return fixtures.find((fixture) => fixture.id === id) ?? fixtures[0];
}

function money(fixture: Fixture, preset: LocalePreset) {
  return new Intl.NumberFormat(preset.locale, {
    style: "currency",
    currency: preset.currency,
    maximumFractionDigits: 0,
  }).format(fixture.totalUsd * preset.rateFromUsd);
}

function dates(fixture: Fixture, preset: LocalePreset) {
  const formatter = new Intl.DateTimeFormat(preset.locale, {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
  return formatter.formatRange(new Date(fixture.start), new Date(fixture.end));
}

function distance(fixture: Fixture, preset: LocalePreset) {
  const value = preset.units === "mi" ? fixture.distanceKm * 0.621371 : fixture.distanceKm;
  return `${new Intl.NumberFormat(preset.locale, { maximumFractionDigits: 0 }).format(value)} ${preset.units}`;
}

function temperature(fixture: Fixture, preset: LocalePreset) {
  const value = preset.temperature === "F" ? (fixture.temperatureC * 9) / 5 + 32 : fixture.temperatureC;
  return `${Math.round(value)}°${preset.temperature}`;
}

function time(preset: LocalePreset) {
  return new Intl.DateTimeFormat(preset.locale, {
    hour: "numeric",
    minute: "2-digit",
    timeZone: "UTC",
  }).format(new Date("2026-01-01T19:30:00Z"));
}

function LocaleFields({ localeId, onLocaleChange, compact = false }: {
  localeId: LocaleId;
  onLocaleChange: (id: LocaleId) => void;
  compact?: boolean;
}) {
  const preset = presetFor(localeId);
  return (
    <div className={`real-locale-fields ${compact ? "two-column" : ""}`}>
      <label>
        Country or region
        <select value={localeId} onChange={(event) => onLocaleChange(event.target.value as LocaleId)}>
          {localePresets.map((item) => <option key={item.id} value={item.id}>{item.region}</option>)}
        </select>
      </label>
      <label>
        Language
        <select value={preset.language} onChange={() => undefined}>
          <option>{preset.language}</option>
          <option disabled>More languages coming later</option>
        </select>
      </label>
      <label>
        Display currency
        <select value={preset.currency} onChange={() => undefined}>
          <option>{preset.currency}</option>
        </select>
      </label>
    </div>
  );
}

function LocaleNote() {
  return (
    <div className="locale-language-note">
      <Languages size={13} />
      <span>Interface language remains English in this Lab. The selector establishes the future contract without pretending translations exist.</span>
    </div>
  );
}

function HomeSurface({ variant, fixture, preset, localeId, onLocaleChange }: {
  variant: VariantId;
  fixture: Fixture;
  preset: LocalePreset;
  localeId: LocaleId;
  onLocaleChange: (id: LocaleId) => void;
}) {
  const [popoverOpen, setPopoverOpen] = useState(variant === "profile");
  useEffect(() => setPopoverOpen(variant === "profile"), [variant]);

  return (
    <section className="real-home" aria-label="Production landing page with localization option">
      <div className="real-home-overlay">
        {variant !== "welcome" && variant !== "confirm" && (
          <button type="button" className="locale-chip" onClick={() => setPopoverOpen(!popoverOpen)}>
            <Globe2 size={14} /> {preset.flag} · {preset.currency}
            {variant === "trip-lens" && <small>Default</small>}
          </button>
        )}
      </div>
      <div className="product-theme-aegean min-h-full">
        <PublicEntry onPlan={() => undefined} onSkip={() => undefined} />
      </div>
      {variant === "welcome" && (
        <aside className="locale-welcome" aria-label="Welcome localization setup">
          <header><Globe2 size={20} /><span><h3>Make Tripplanner feel local</h3><p>Choose how dates, prices, distance, weather, and practical guidance should read.</p></span></header>
          <LocaleFields localeId={localeId} onLocaleChange={onLocaleChange} compact />
          <LocaleNote />
          <button type="button" className="locale-primary" style={{ marginTop: 14 }}>Continue to Tripplanner</button>
        </aside>
      )}
      {variant === "confirm" && (
        <div className="locale-confirm">
          <Globe2 size={17} />
          <span><strong>Use {preset.language}?</strong> Show {preset.currency}, {preset.units}, °{preset.temperature}, and local date conventions.</span>
          <button type="button" className="locale-primary">Yes, use this</button>
          <button type="button" className="locale-secondary">Change</button>
        </div>
      )}
      {popoverOpen && variant === "profile" && (
        <aside className="locale-popover">
          <header><Settings2 size={18} /><span><h3>Region and language</h3><p>This shortcut opens the durable preference in Account settings.</p></span></header>
          <LocaleFields localeId={localeId} onLocaleChange={onLocaleChange} compact />
          <LocaleNote />
        </aside>
      )}
      {variant === "trip-lens" && popoverOpen && (
        <aside className="locale-popover">
          <header><WalletCards size={18} /><span><h3>Account display default</h3><p>{preset.region} · {preset.currency}. A trip may temporarily use another display currency without changing this default.</p></span></header>
          <LocaleFields localeId={localeId} onLocaleChange={onLocaleChange} compact />
          <LocaleNote />
        </aside>
      )}
      <span hidden>{fixture.title}</span>
    </section>
  );
}

function WorkspaceSurface({ variant, fixture, preset, localeId, onLocaleChange }: {
  variant: VariantId;
  fixture: Fixture;
  preset: LocalePreset;
  localeId: LocaleId;
  onLocaleChange: (id: LocaleId) => void;
}) {
  return (
    <section className="real-workspace" aria-label="Production-faithful localized workspace">
      <header className="real-toolbar">
        <button type="button" className="real-trip-switcher"><i /> {fixture.title}<ChevronDown size={13} /></button>
        <span className="real-status">Saved · 4 of 7 choices booking-ready</span>
        <nav className="real-toolbar-group" aria-label="Workspace controls">
          <button type="button" title="Start a new trip"><Plus size={14} /><span className="control-label">New trip</span></button>
          <button type="button" title="Reset trip"><RotateCcw size={14} /></button>
          <div className="real-toolbar-group real-pane-controls">
            <button type="button" className="active"><MessageCircle size={14} /><span className="control-label">Chat</span></button>
            <button type="button" className="active"><List size={14} /><span className="control-label">Itinerary</span></button>
            <button type="button" className="active"><Map size={14} /><span className="control-label">Map</span></button>
            <button type="button" className="active"><PanelRight size={14} /><span className="control-label">Details</span></button>
          </div>
          {variant === "quick" && (
            <label className="workspace-locale-button">
              <Globe2 size={13} />
              <select aria-label="Workspace locale" value={localeId} onChange={(event) => onLocaleChange(event.target.value as LocaleId)}>
                {localePresets.map((item) => <option key={item.id} value={item.id}>{item.flag} · {item.currency}</option>)}
              </select>
            </label>
          )}
          {variant === "trip-lens" && (
            <label className="workspace-locale-button">
              <WalletCards size={13} />
              <select aria-label="Trip display currency" value={localeId} onChange={(event) => onLocaleChange(event.target.value as LocaleId)}>
                {localePresets.map((item) => <option key={item.id} value={item.id}>Display {item.currency}</option>)}
              </select>
            </label>
          )}
          <button type="button" className="real-export-button" title="Trip actions"><MoreHorizontal size={15} /></button>
          <button type="button" className="real-account-button" title="Account settings"><UserRound size={15} /><span className="real-account-label">Munish</span></button>
        </nav>
      </header>

      <div className="real-workspace-grid">
        <aside className="real-itinerary">
          <header className="real-pane-head">
            <p className="eyebrow">{fixture.route}</p>
            <h2>{fixture.title}</h2>
            <p>{dates(fixture, preset)} · 2 travelers · balanced pace</p>
            <div className="real-local-summary">
              <span><small>Indicative display total</small><strong>{money(fixture, preset)}</strong><small>{preset.region} conventions</small></span>
              <span className="real-source-quote"><small>Provider source quote</small><strong>{fixture.sourceAmount}</strong><small>{fixture.sourceCurrency}</small></span>
            </div>
          </header>
          <div className="real-day">
            <header><span className="real-day-number">1–9</span><span><strong>A complete route, localized</strong><small>{distance(fixture, preset)} · {temperature(fixture, preset)} · dinner {time(preset)}</small></span></header>
            {fixture.stops.map((stop) => {
              const Icon = modeIcons[stop.mode];
              return (
                <article className="real-stop" key={stop.city}>
                  <span className="real-stop-icon"><Icon size={13} /></span>
                  <span><strong>{stop.city}</strong><small>{stop.day} · {stop.detail}</small></span>
                  <ChevronRight size={13} />
                </article>
              );
            })}
          </div>
        </aside>

        <section className="real-map" aria-label="Trip route map">
          <div className="real-route" />
          {fixture.stops.map((stop, index) => <span className={`real-map-pin pin-${index + 1}`} key={stop.city}>{index + 1}</span>)}
          <div className="real-map-card"><small>Selected route</small><strong>{fixture.stops[1].city} to {fixture.stops[2].city}</strong><small>{distance(fixture, preset)} · local driving and rail conventions applied</small></div>
        </section>

        <aside className="real-details">
          <div className="real-detail-image" aria-label={`${fixture.stops[1].city} destination image treatment`} />
          <div className="real-detail-copy">
            <p className="eyebrow">Day 3 · grounded choice</p>
            <h2>{fixture.stops[1].city}, without rushing</h2>
            <p>{fixture.stops[1].detail}. The same production detail hierarchy now shows local formats and destination conventions together.</p>
            <div className="real-detail-rule"><span>Planned time</span><strong>{time(preset)} · 1 h 20 min</strong></div>
            <div className="real-detail-rule"><span>Distance</span><strong>{distance(fixture, preset)}</strong></div>
            <div className="real-detail-rule"><span>Price display</span><strong>{money(fixture, preset)}</strong></div>
            <section className="real-local-context">
              <h3>Regional context applied</h3>
              {[preset.feeRule, preset.weekStart, preset.phoneRule, fixture.destinationContext].map((item) => <div key={item}><Check size={12} /><span>{item}</span></div>)}
              {variant === "trip-lens" && <div><ReceiptText size={12} /><span>Converted display values retain source currency, provider, rate source, and checked time.</span></div>}
            </section>
          </div>
        </aside>
      </div>

      <footer className="real-assistant-dock"><span><MessageCircle size={14} /></span><p>Ask the planner to change this trip. Locale changes presentation, never the trip or provider quote.</p><button type="button">Open Assistant</button></footer>
    </section>
  );
}

function SettingsMenu({ onOpenRegion, preset }: { onOpenRegion: () => void; preset: LocalePreset }) {
  const rows = [
    { icon: CircleUserRound, label: "Profile and sign-in", detail: "Identity and account access" },
    { icon: SlidersHorizontal, label: "Travel profile", detail: "Preferences, travel style, and accessibility" },
    { icon: Globe2, label: "Region and language", detail: `${preset.region} · ${preset.language} · ${preset.currency}`, action: onOpenRegion },
    { icon: FileText, label: "Travel documents", detail: "Passports, visas, and details reused by every trip" },
  ];
  return (
    <>
      <div className="real-identity"><span className="real-avatar">MG</span><span><strong>Munish Goyal</strong><small>Used on web and mobile</small></span></div>
      <nav className="real-settings-menu" aria-label="Account settings sections">
        {rows.map(({ icon: Icon, label, detail, action }) => <button type="button" key={label} onClick={action}><i><Icon size={15} /></i><span><strong>{label}</strong><small>{detail}</small></span><ChevronRight size={13} /></button>)}
      </nav>
    </>
  );
}

function RegionForm({ variant, fixture, preset, localeId, onLocaleChange, onBack }: {
  variant: VariantId;
  fixture: Fixture;
  preset: LocalePreset;
  localeId: LocaleId;
  onLocaleChange: (id: LocaleId) => void;
  onBack: () => void;
}) {
  return (
    <div className="real-region-form">
      <button type="button" className="real-back" onClick={onBack}><ChevronLeft size={13} /> Back to settings</button>
      <div className="real-settings-title"><span><Globe2 size={17} /></span><div><p>Reusable defaults</p><h3>Region and language</h3><small>Choose how dates, prices, distance, temperature, addresses, and practical guidance read across web and mobile.</small></div></div>
      <LocaleFields localeId={localeId} onLocaleChange={onLocaleChange} />
      <div className="real-format-preview"><span>Live preview for this trip</span><strong>{money(fixture, preset)} · {dates(fixture, preset)}</strong><small>{distance(fixture, preset)} · {temperature(fixture, preset)} · {time(preset)} · {preset.weekStart}</small></div>
      <label className="real-toggle"><span><strong>Show provider source currency</strong><small>Keep original quotes beside converted display values.</small></span><input type="checkbox" defaultChecked /></label>
      {variant === "trip-lens" && <label className="real-toggle"><span><strong>Allow a per-trip display currency</strong><small>Temporary trip lens does not change this account default.</small></span><input type="checkbox" defaultChecked /></label>}
      <LocaleNote />
      <button type="button" className="locale-primary" style={{ width: "100%", marginTop: 14 }}>Save regional preferences</button>
    </div>
  );
}

function ProfileSurface({ variant, fixture, preset, localeId, onLocaleChange }: {
  variant: VariantId;
  fixture: Fixture;
  preset: LocalePreset;
  localeId: LocaleId;
  onLocaleChange: (id: LocaleId) => void;
}) {
  const [regionOpen, setRegionOpen] = useState(variant === "profile" || variant === "trip-lens");
  useEffect(() => setRegionOpen(variant === "profile" || variant === "trip-lens"), [variant]);
  return (
    <section className="real-settings-scene" aria-label="Production-faithful account settings">
      <div className="real-settings-backdrop"><WorkspaceSurface variant={variant} fixture={fixture} preset={preset} localeId={localeId} onLocaleChange={onLocaleChange} /></div>
      <aside className="real-account-drawer" aria-label="Account settings">
        <header><h2>Account settings</h2><button type="button" aria-label="Close account settings"><X size={16} /></button></header>
        <div className="real-account-body">
          {regionOpen
            ? <RegionForm variant={variant} fixture={fixture} preset={preset} localeId={localeId} onLocaleChange={onLocaleChange} onBack={() => setRegionOpen(false)} />
            : <SettingsMenu onOpenRegion={() => setRegionOpen(true)} preset={preset} />}
        </div>
      </aside>
    </section>
  );
}

function Preview({ surface, variant, fixture, preset, localeId, onLocaleChange, fullSize = false }: {
  surface: Surface;
  variant: VariantId;
  fixture: Fixture;
  preset: LocalePreset;
  localeId: LocaleId;
  onLocaleChange: (id: LocaleId) => void;
  fullSize?: boolean;
}) {
  return (
    <div className={`real-preview-stage localization-real ${fullSize ? "full-size" : ""}`}>
      {surface === "home" && <HomeSurface variant={variant} fixture={fixture} preset={preset} localeId={localeId} onLocaleChange={onLocaleChange} />}
      {surface === "workspace" && <WorkspaceSurface variant={variant} fixture={fixture} preset={preset} localeId={localeId} onLocaleChange={onLocaleChange} />}
      {surface === "profile" && <ProfileSurface variant={variant} fixture={fixture} preset={preset} localeId={localeId} onLocaleChange={onLocaleChange} />}
    </div>
  );
}

function LocalizationLab() {
  const params = new URLSearchParams(window.location.search);
  const requestedVariant = variants.find((variant) => variant.id === params.get("preview"));
  const requestedSurface = (["home", "workspace", "profile"] as Surface[]).find((item) => item === params.get("surface"));
  const requestedFixture = fixtures.find((fixture) => fixture.id === params.get("fixture"));
  const [variantId, setVariantId] = useState<VariantId>(requestedVariant?.id ?? "profile");
  const [surface, setSurface] = useState<Surface>(requestedSurface ?? "home");
  const [fixtureId, setFixtureId] = useState<FixtureId>(requestedFixture?.id ?? "rajasthan");
  const [localeId, setLocaleId] = useState<LocaleId>((requestedFixture ?? fixtures[0]).localeId);
  const variant = variants.find((item) => item.id === variantId) ?? variants[0];
  const fixture = fixtureFor(fixtureId);
  const preset = presetFor(localeId);

  const chooseFixture = (id: FixtureId) => {
    const next = fixtureFor(id);
    setFixtureId(id);
    setLocaleId(next.localeId);
  };

  if (requestedVariant) {
    return (
      <main className="localization-real">
        <Preview surface={surface} variant={variantId} fixture={fixture} preset={preset} localeId={localeId} onLocaleChange={setLocaleId} fullSize />
        <a className="exit-preview" href="./lab-24-localization.html"><ArrowLeft size={14} /> Exit full-size preview</a>
      </main>
    );
  }

  return (
    <main className="lab-page localization-real"><div className="lab-wrap">
      <LabNavigation detail labId="localization" />
      <header className="lab-header"><div><p className="lab-kicker"><Globe2 size={16} /> Regional content and currency</p><h1>The real product.<br />Four local ways to read it.</h1><p>Every option now uses the promoted Aegean landing page and the current production workspace and settings geometry. Only localization placement and display conventions vary.</p></div><div className="locale-manifest"><span>Actual promoted landing</span><span>Current workspace shell</span><span>4 regional stress cases</span></div></header>
      <LabScope labId="localization" />
      <OptionContrast labId="localization" />
      <section className="variant-grid" aria-label="Localization UX options">{variants.map((item) => <button key={item.id} type="button" className={variantId === item.id ? "selected" : ""} onClick={() => setVariantId(item.id)}><span>{item.label}</span><p>{item.summary}</p><small>{item.cost}</small></button>)}</section>
      <div className="review-toolbar"><div><p className="eyebrow">Production-backed comparison</p><strong>{variant.label}</strong></div><div className="surface-tabs">{(["home", "workspace", "profile"] as Surface[]).map((item) => <button key={item} type="button" className={surface === item ? "active" : ""} onClick={() => setSurface(item)}>{item === "profile" ? "Account settings" : item[0].toUpperCase() + item.slice(1)}</button>)}</div><div className="fixture-tabs">{fixtures.map((item) => <button key={item.id} type="button" className={fixtureId === item.id ? "active" : ""} onClick={() => chooseFixture(item.id)}>{presetFor(item.localeId).flag}</button>)}</div></div>
      <Preview surface={surface} variant={variantId} fixture={fixture} preset={preset} localeId={localeId} onLocaleChange={setLocaleId} />
      <div className="real-preview-caption"><strong>{fixture.title}</strong><span>Trip fixture stays fixed while locale controls change presentation.</span><span>{preset.region} · {money(fixture, preset)} · {dates(fixture, preset)}</span><a className="real-full-link" href={`?preview=${variantId}&surface=${surface}&fixture=${fixtureId}`}><ExternalLink size={13} /> Inspect full-size</a></div>
      <section className="fixture-ledger"><div><p className="eyebrow">Same four stress cases in every option</p><h2>Compare the whole page, not a localization card.</h2></div>{fixtures.map((item) => { const itemPreset = presetFor(item.localeId); return <button type="button" key={item.id} onClick={() => { chooseFixture(item.id); setSurface("workspace"); }}><span className="flag">{itemPreset.flag}</span><span><strong>{item.title}</strong><small>{item.route}</small></span><span><strong>{money(item, itemPreset)}</strong><small>{distance(item, itemPreset)} · {temperature(item, itemPreset)}</small></span></button>; })}</section>
      <DecisionCapture labId="localization" labTitle="Regional content and currency" options={variants.map(({ id, label }) => ({ id, label }))} activeOption={variantId} onChoose={(id) => setVariantId(id as VariantId)} />
    </div></main>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><LocalizationLab /></React.StrictMode>);
