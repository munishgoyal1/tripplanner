import { useState } from "react";
import ReactDOM from "react-dom/client";
import {
  BarChart3,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleUserRound,
  FileText,
  Maximize2,
  Plus,
  Ruler,
  ShieldCheck,
  SlidersHorizontal,
  UsersRound,
  X,
} from "lucide-react";
import { DecisionCapture } from "../shared/DecisionCapture";
import { LabNavigation } from "../shared/LabNavigation";
import { LabScope } from "../shared/LabScope";
import { OptionContrast } from "../shared/OptionContrast";
import "../../../src/index.css";
import "./styles.css";

type OptionId = "wide-drawer" | "full-page" | "workspace-modal" | "two-pane" | "expandable";
type SectionId = "identity" | "travel" | "family" | "documents" | "privacy";
type Device = "desktop" | "mobile";

/** Today's Account settings drawer is max-w-sm, so every option is measured against it. */
const TODAY_WIDTH = 384;

const options = [
  {
    id: "wide-drawer" as const,
    label: "A · Wider drawer",
    summary: "The same right-side drawer, widened to a two-column editing surface.",
    cost: "Familiar and cheap, but a drawer still overlays the trip you were reading.",
    width: 960,
  },
  {
    id: "full-page" as const,
    label: "B · Full profile page",
    summary: "A dedicated page with a section rail and a genuinely wide canvas.",
    cost: "The most room by far; it leaves the workspace instead of floating over it.",
    width: 1240,
  },
  {
    id: "workspace-modal" as const,
    label: "C · Centered workspace",
    summary: "A large centered dialog with its own rail, floating above the trip.",
    cost: "Roomy without losing your place, but modal focus traps still fight long forms.",
    width: 1100,
  },
  {
    id: "two-pane" as const,
    label: "D · People-first two pane",
    summary: "A category rail plus a detail pane, with travellers as the primary object.",
    cost: "Best for families; slightly indirect for a single traveller editing one field.",
    width: 1080,
  },
  {
    id: "expandable" as const,
    label: "E · Expand on demand",
    summary: "The compact drawer stays for quick edits and expands to full width when needed.",
    cost: "No new destination to learn, but two states of the same screen to design and test.",
    width: 384,
  },
];

const sections: { id: SectionId; label: string; detail: string; icon: typeof CircleUserRound }[] = [
  { id: "identity", label: "Profile and sign-in", detail: "Identity and account access", icon: CircleUserRound },
  { id: "travel", label: "Travel preferences", detail: "Pace, budget, food, stays, flights", icon: SlidersHorizontal },
  { id: "family", label: "Travellers", detail: "Family members and their needs", icon: UsersRound },
  { id: "documents", label: "Travel documents", detail: "Passports, visas, reused details", icon: FileText },
  { id: "privacy", label: "Privacy and data", detail: "Analytics, erasure, deletion", icon: ShieldCheck },
];

const travellers = [
  { name: "Munish", role: "You", initials: "MG", tags: ["Balanced pace", "Local food", "Aisle seat"] },
  { name: "Rhea", role: "Partner", initials: "R", tags: ["Relaxed mornings", "Vegetarian", "Quiet room"] },
  { name: "Kabir", role: "Child · 8", initials: "K", tags: ["Earlier dinner", "Shorter walks", "Pool time"] },
];

const preferenceGroups = [
  { title: "Pace and style", fields: ["Trip style", "Daily pace", "Free time", "Trip length"] },
  { title: "Budget", fields: ["Budget level", "Currency", "Per-day ceiling", "Splurge on"] },
  { title: "Food", fields: ["Dietary", "Cuisines", "Dinner time", "Avoid"] },
  { title: "Stays and flights", fields: ["Star floor", "Room type", "Cabin class", "Direct only"] },
];

function Field({ label }: { label: string }) {
  return (
    <label className="pw-field">
      <span>{label}</span>
      <span className="pw-input" />
    </label>
  );
}

function TravellerCard({ traveller, compact }: { traveller: typeof travellers[number]; compact: boolean }) {
  return (
    <article className={`pw-person ${compact ? "compact" : ""}`}>
      <span className="pw-avatar">{traveller.initials}</span>
      <div>
        <strong>{traveller.name}</strong>
        <small>{traveller.role}</small>
        {!compact && (
          <div className="pw-tags">
            {traveller.tags.map((tag) => <span key={tag}>{tag}</span>)}
          </div>
        )}
      </div>
      <ChevronRight size={14} />
    </article>
  );
}

function SectionRail({ active, onSelect, compact }: {
  active: SectionId;
  onSelect: (id: SectionId) => void;
  compact: boolean;
}) {
  return (
    <nav className={`pw-rail ${compact ? "compact" : ""}`} aria-label="Profile sections">
      {sections.map(({ id, label, detail, icon: Icon }) => (
        <button key={id} type="button" className={active === id ? "active" : ""} onClick={() => onSelect(id)}>
          <i><Icon size={15} /></i>
          <span>
            <strong>{label}</strong>
            {!compact && <small>{detail}</small>}
          </span>
        </button>
      ))}
    </nav>
  );
}

function FamilyPane({ columns }: { columns: boolean }) {
  return (
    <div className="pw-pane">
      <header className="pw-pane-head">
        <div>
          <p className="section-kicker">Travellers</p>
          <h3>Who is usually travelling</h3>
          <p className="pw-hint">Shared defaults sit here. Anything personal is an exception on one person.</p>
        </div>
        <button type="button" className="pw-add"><Plus size={13} /> Add traveller</button>
      </header>
      <div className={`pw-people ${columns ? "columns" : ""}`}>
        {travellers.map((traveller) => <TravellerCard key={traveller.name} traveller={traveller} compact={!columns} />)}
      </div>
      <div className="pw-shared">
        <strong>Shared by everyone</strong>
        <div className="pw-grid two">
          <Field label="Home airport" />
          <Field label="Emergency contact" />
          <Field label="Usual room setup" />
          <Field label="Family food pattern" />
        </div>
      </div>
    </div>
  );
}

function TravelPane({ columns }: { columns: boolean }) {
  return (
    <div className="pw-pane">
      <header className="pw-pane-head">
        <div>
          <p className="section-kicker">Travel preferences</p>
          <h3>How you like to travel</h3>
          <p className="pw-hint">These are durable defaults. A single trip can still override any of them.</p>
        </div>
        <span className="pw-saved"><Check size={13} /> Saved</span>
      </header>
      <div className={`pw-groups ${columns ? "columns" : ""}`}>
        {preferenceGroups.map((group) => (
          <section key={group.title} className="pw-group">
            <strong>{group.title}</strong>
            <div className="pw-grid two">
              {group.fields.map((field) => <Field key={field} label={field} />)}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}

function PaneFor({ section, columns }: { section: SectionId; columns: boolean }) {
  if (section === "family") return <FamilyPane columns={columns} />;
  if (section === "travel") return <TravelPane columns={columns} />;
  const meta = sections.find((item) => item.id === section)!;
  return (
    <div className="pw-pane">
      <header className="pw-pane-head">
        <div>
          <p className="section-kicker">{meta.label}</p>
          <h3>{meta.detail}</h3>
          <p className="pw-hint">Unchanged in this Lab; shown so the rail is realistic.</p>
        </div>
      </header>
      <div className="pw-grid two">
        <Field label="Field" />
        <Field label="Field" />
        <Field label="Field" />
        <Field label="Field" />
      </div>
      {section === "privacy" && <p className="pw-hint">Analytics and erasure keep their existing confirmations.</p>}
      {section === "documents" && <p className="pw-hint">Document capture keeps its existing vault behavior.</p>}
    </div>
  );
}

function WorkspaceBackdrop() {
  return (
    <div className="pw-backdrop" aria-hidden>
      <div className="pw-backdrop-bar" />
      <div className="pw-backdrop-body">
        <div className="pw-backdrop-list" />
        <div className="pw-backdrop-map" />
      </div>
    </div>
  );
}

function Preview({ option, section, onSection, device, expanded, onExpand }: {
  option: OptionId;
  section: SectionId;
  onSection: (id: SectionId) => void;
  device: Device;
  expanded: boolean;
  onExpand: (next: boolean) => void;
}) {
  const mobile = device === "mobile";
  const active = options.find((item) => item.id === option)!;
  const width = option === "expandable" && expanded ? 1100 : active.width;
  const columns = !mobile && width >= 900;
  const railCompact = mobile || width < 900;

  const shell = (
    <section
      className={`pw-shell mode-${option} ${mobile ? "mobile" : ""}`}
      style={{ ["--pw-width" as string]: `${width}px` }}
      aria-label="Profile surface preview"
    >
      <header className="pw-shell-head">
        <div>
          <p className="section-kicker">Account</p>
          <h2>Your profile</h2>
        </div>
        <div className="pw-head-actions">
          {option === "expandable" && (
            <button type="button" className="pw-expand" onClick={() => onExpand(!expanded)}>
              <Maximize2 size={13} /> {expanded ? "Shrink" : "Open full profile"}
            </button>
          )}
          <span className="pw-width-tag"><Ruler size={12} /> {mobile ? "full width" : `${width}px`}</span>
          <button type="button" className="pw-close" aria-label="Close"><X size={15} /></button>
        </div>
      </header>
      <div className={`pw-body ${railCompact ? "stacked" : ""}`}>
        <SectionRail active={section} onSelect={onSection} compact={railCompact} />
        <div className="pw-canvas">
          {mobile && <button type="button" className="pw-back"><ChevronLeft size={13} /> All sections</button>}
          <PaneFor section={section} columns={columns} />
        </div>
      </div>
    </section>
  );

  const floats = option === "wide-drawer" || option === "workspace-modal" || option === "expandable";
  return (
    <div className={`pw-stage ${floats ? "floating" : "page"} ${mobile ? "mobile" : ""}`}>
      {floats && !mobile && <WorkspaceBackdrop />}
      {shell}
    </div>
  );
}

function App() {
  const [option, setOption] = useState<OptionId>("full-page");
  const [section, setSection] = useState<SectionId>("travel");
  const [device, setDevice] = useState<Device>("desktop");
  const [expanded, setExpanded] = useState(false);
  const active = options.find((item) => item.id === option)!;
  const shownWidth = option === "expandable" && expanded ? 1100 : active.width;

  return (
    <main className="lab-page"><div className="lab-wrap">
      <LabNavigation detail labId="profile-workspace" />
      <header className="lab-header">
        <div>
          <p className="lab-kicker"><SlidersHorizontal size={16} /> Profile editing surface</p>
          <h1>Room to actually<br />edit your profile.</h1>
          <p>Today every profile section lives in one 384px drawer: travel preferences, travellers, documents, and privacy all compete for the same narrow column. This Lab compares five roomier homes for the same content, and treats travellers as a destination of their own rather than a subsection.</p>
        </div>
        <div className="principle-card">
          <span>The measurement</span>
          <strong>384px today.<br />Not enough.</strong>
          <small>Two-column forms · family cards · document lists</small>
        </div>
      </header>
      <LabScope labId="profile-workspace" />
      <OptionContrast labId="profile-workspace" />

      <section className="option-picker">
        <div className="section-kicker">Five roomier homes</div>
        <div className="option-grid">
          {options.map((item) => (
            <button key={item.id} className={option === item.id ? "selected" : ""} onClick={() => { setOption(item.id); setExpanded(false); }}>
              <span className="option-label">{item.label}</span>
              <strong>{item.summary}</strong>
              <small>{item.cost}</small>
            </button>
          ))}
        </div>
      </section>

      <div className="pw-toolbar">
        <div>
          <p className="section-kicker">Live comparison</p>
          <strong>{active.label}</strong>
        </div>
        <div className="pw-ruler" aria-label="Width against today">
          <span className="pw-ruler-today" style={{ width: `${(TODAY_WIDTH / 1240) * 100}%` }}>today 384px</span>
          <span className="pw-ruler-new" style={{ width: `${(shownWidth / 1240) * 100}%` }}>
            {device === "mobile" ? "mobile full width" : `${shownWidth}px`}
          </span>
        </div>
        <div className="pw-devices">
          {(["desktop", "mobile"] as Device[]).map((item) => (
            <button key={item} type="button" className={device === item ? "active" : ""} onClick={() => setDevice(item)}>
              {item === "desktop" ? "Desktop" : "Mobile"}
            </button>
          ))}
        </div>
      </div>

      <Preview
        option={option}
        section={section}
        onSection={setSection}
        device={device}
        expanded={expanded}
        onExpand={setExpanded}
      />

      <section className="pw-notes">
        <div><BarChart3 size={15} /><span><strong>Same content in every option.</strong> Identity, travel preferences, travellers, documents, and privacy are the same five sections with the same fields.</span></div>
        <div><UsersRound size={15} /><span><strong>Travellers is its own destination.</strong> Family stops being a nested block inside travel preferences in all five.</span></div>
      </section>

      <DecisionCapture
        labId="profile-workspace"
        labTitle="Room to edit your profile"
        options={options.map(({ id, label }) => ({ id, label }))}
        activeOption={option}
        onChoose={(id) => setOption(id as OptionId)}
      />
    </div></main>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<App />);
