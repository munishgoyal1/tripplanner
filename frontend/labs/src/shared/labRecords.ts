import { BookOpen, Compass, DoorOpen, FileText, Globe2, LayoutPanelTop, ListChecks, Map, MessageCircle, Palette, Radio, Route, SlidersHorizontal, UsersRound, Workflow } from "lucide-react";

export interface LabRecord {
  labNumber: number;
  id: string;
  title: string;
  category: string;
  description: string;
  createdAt: string;
  defaultDisposition: LabDisposition;
  defaultStateChangedAt?: string;
  href: string;
  decision: string;
  icon: typeof ListChecks;
}

export interface ResolvedLabRecord extends LabRecord {
  status: string;
}

export interface LabSelectionState {
  disposition?: LabDisposition;
  selectionLabel?: string;
  stateChangedAt?: string;
  updatedAt?: string;
}

export type LabDisposition = "ready" | "implemented-review" | "parked" | "completed" | "discarded";

export const LAB_STATUS_LABELS: Record<LabDisposition, string> = {
  ready: "In progress",
  "implemented-review": "Implemented - To be reviewed",
  parked: "Parked",
  completed: "Completed",
  discarded: "Discarded",
};

export const LAST_ASSIGNED_LAB_NUMBER = 26;

export function effectiveLabDisposition(lab: LabRecord, selection?: LabSelectionState): LabDisposition {
  return selection?.disposition ?? lab.defaultDisposition;
}

export function resolvedLabRecord(lab: LabRecord, selection?: LabSelectionState): ResolvedLabRecord {
  const disposition = effectiveLabDisposition(lab, selection);
  return {
    ...lab,
    status: LAB_STATUS_LABELS[disposition],
    decision: selection?.disposition && selection.selectionLabel ? selection.selectionLabel : lab.decision,
  };
}

// Committed defaults are the fallback only. The tracked canonical selection store
// in docs/ux-experiments overrides them at runtime and merges any newer local draft.
export const allLabs: LabRecord[] = [
  {
    labNumber: 26,
    id: "family-details",
    title: "A family profile that grows with the trip",
    category: "Family and traveler details",
    description: "Compare five low-pressure ways to capture shared family context and individual traveler details, while letting chat and future trip interactions fill the profile naturally over time.",
    createdAt: "2026-08-14",
    defaultDisposition: "ready",
    defaultStateChangedAt: "2026-08-14",
    decision: "Open · Recommended starting point: D · Chat-led profile",
    href: "./lab-26-family-details.html",
    icon: UsersRound,
  },
  {
    labNumber: 24,
    id: "localization",
    title: "One planner, local ways of reading it",
    category: "Regional content and currency",
    description: "Compare five homes for country, language, display currency, and regional formats across Home, Workspace, and Profile, using localized Rajasthan, US Pacific Coast, Scotland, and continental Europe trips.",
    createdAt: "2026-08-09",
    defaultDisposition: "ready",
    defaultStateChangedAt: "2026-08-09",
    decision: "Open · Recommended starting point: C · Profile-first",
    href: "./lab-24-localization.html",
    icon: Globe2,
  },
  {
    labNumber: 23,
    id: "product-themes",
    title: "One product, six ways to feel it",
    category: "Product-wide visual language",
    description: "Compare four coherent visual systems across the public landing page, spatial planner workspace, and mobile trip view so the dark-to-light handoff becomes an intentional product decision.",
    createdAt: "2026-08-09",
    defaultDisposition: "ready",
    defaultStateChangedAt: "2026-08-09",
    decision: "Open · Recommended starting point: A · Postcard editorial",
    href: "./lab-23-product-themes.html",
    icon: Palette,
  },
  {
    labNumber: 22,
    id: "live-plan",
    title: "The live plan, and what the visitor is meant to do while it runs",
    category: "Public entry",
    description: "Lab 21's live agent stage, taken as the base and pushed four ways: the same screen in daylight, the same screen said plainly, a hero that plans your destination from the first keystroke, and a decision replay you can overrule. The demo trip is now six days across Lisbon and Porto with two hotels, a flight, a train, a hire car and a tram, so the plan argues for itself. All four cover landing, first plan and shared trip.",
    createdAt: "2026-08-07",
    defaultDisposition: "completed",
    defaultStateChangedAt: "2026-08-09",
    decision: "E · Dark stage, argued during the run.",
    href: "./lab-22-live-plan.html",
    icon: Radio,
  },
  {
    labNumber: 21,
    id: "first-visit",
    title: "The first visit, from stranger to a trip they own",
    category: "Public entry",
    description: "The root URL currently boots an empty workspace: no explanation, no proof, no public trip page, no guest-to-account moment. Four options rebuild the whole public edge - a prompt-first hero, a proof-first magazine, a guided intake, and a dark live agent stage that plans a trip in front of you - each across landing, first plan and shared trip.",
    createdAt: "2026-08-06",
    defaultDisposition: "completed",
    defaultStateChangedAt: "2026-08-09",
    decision: "Completed · Last recorded direction: B · Proof-first magazine, with D's live stage as the proof block.",
    href: "./lab-21-first-visit.html",
    icon: DoorOpen,
  },
  {
    labNumber: 20,
    id: "travel-documents",
    title: "Where travel documents live, and what we refuse to keep",
    category: "Trip data",
    description: "Bookings, passports, visas and insurance get a home: fields are extracted once, the original file is never stored, and details are reused on the next trip. Compare a trip readiness rail, an account vault the trip only reports gaps against, and a drop-anything inbox that routes items later.",
    createdAt: "2026-08-06",
    defaultDisposition: "completed",
    defaultStateChangedAt: "2026-08-09",
    decision: "B · Account vault, trip shows gaps.",
    href: "./lab-20-travel-documents.html",
    icon: FileText,
  },
  {
    labNumber: 19,
    id: "agentic-planning",
    title: "An itinerary that cannot be edited into nonsense",
    category: "Agent behaviour",
    description: "A deterministic plan engine between intent and the trip: envelope, presence, anchors, blast radius and receipts, so a change from chat, map, itinerary or details can never place a stop after the flight home or silently delete a booked leg.",
    createdAt: "2026-08-05",
    defaultDisposition: "completed",
    defaultStateChangedAt: "2026-08-09",
    decision: "B · Guarded autonomy.",
    href: "./lab-19-agentic-planning.html",
    icon: Workflow,
  },
  {
    labNumber: 18,
    id: "map-canvas",
    title: "Map canvas, reimagined",
    category: "Map interaction",
    description: "Compare a floating control deck, a bottom route dock with the day's stop timeline, and a single command ribbon for how much of the map pane is actually geography.",
    createdAt: "2026-08-05",
    defaultDisposition: "completed",
    defaultStateChangedAt: "2026-08-09",
    decision: "Completed · Last recorded direction: D · Search-first dock.",
    href: "./lab-18-map-canvas.html",
    icon: Map,
  },
  {
    labNumber: 17,
    id: "itinerary-canvas",
    title: "Itinerary canvas, reimagined",
    category: "Itinerary layout",
    description: "Compare a continuous journey spine, layered stop cards with in-place notes, and an editorial agenda for reading a five-day plan quickly without losing a single production fact.",
    createdAt: "2026-08-05",
    defaultDisposition: "completed",
    defaultStateChangedAt: "2026-08-09",
    decision: "Completed · Last recorded direction: B · Layered stop cards.",
    href: "./lab-17-itinerary-canvas.html",
    icon: ListChecks,
  },
  {
    labNumber: 16,
    id: "chat-agent-workspace",
    title: "Reimagining the chat agent",
    category: "Assistant and workspace layout",
    description: "Compare a resident conversation column, a full-width focus composer, and a right-rail turn thread for where the Assistant lives and how a turn, its time, and its effects are read.",
    createdAt: "2026-08-05",
    defaultDisposition: "completed",
    defaultStateChangedAt: "2026-08-06",
    decision: "B · Focus composer.",
    href: "./lab-16-chat-agent-workspace.html",
    icon: MessageCircle,
  },
  {
    labNumber: 14,
    id: "intercity-map",
    title: "Inter-city travel on the day map",
    category: "Map completeness",
    description: "Compare a connected day journey, a journey strip, and optional route layers for road, rail, and flight transfer days.",
    createdAt: "2026-08-01",
    defaultDisposition: "completed",
    defaultStateChangedAt: "2026-08-06",
    decision: "C · Optional inter-city layer.",
    href: "./lab-14-intercity-map.html",
    icon: Map,
  },
  {
    labNumber: 15,
    id: "multi-city-itinerary",
    title: "Transition-day itinerary design",
    category: "Multi-city itinerary",
    description: "Compare three ways to show old-stay checkout, inter-city travel, new-stay check-in, and the remaining day.",
    createdAt: "2026-08-01",
    defaultDisposition: "completed",
    defaultStateChangedAt: "2026-08-06",
    decision: "A · Transition spine.",
    href: "./lab-15-multi-city-itinerary.html",
    icon: Route,
  },
  {
    labNumber: 13,
    id: "destination-guide",
    title: "Destination guide depth and context",
    category: "Place discovery",
    description: "Compare contextual alternatives, city chapters, and a filtered directory for browsing beyond the current ten-place shortlist.",
    createdAt: "2026-08-01",
    defaultDisposition: "completed",
    defaultStateChangedAt: "2026-08-06",
    decision: "A · Contextual explorer (with search).",
    href: "./lab-13-destination-guide.html",
    icon: Compass,
  },
  {
    labNumber: 12,
    id: "account-settings",
    title: "Account and settings ownership",
    category: "Account controls",
    description: "Compare one unified account menu, a strict profile/settings split, and a sectioned account hub with complete profile, analytics, and privacy destinations.",
    createdAt: "2026-08-01",
    defaultDisposition: "completed",
    defaultStateChangedAt: "2026-08-06",
    decision: "C · Account settings hub.",
    href: "./lab-12-account-settings.html",
    icon: SlidersHorizontal,
  },
  {
    labNumber: 5,
    id: "itinerary-trip-book",
    title: "Execution-ready Trip Book",
    category: "Trip export",
    description: "Compare compact, layered, and visual structures for one printable itinerary with confirmations and personal context.",
    createdAt: "2026-07-30",
    defaultDisposition: "parked",
    defaultStateChangedAt: "2026-08-06",
    decision: "B · Layered Trip Book.",
    href: "./lab-5-itinerary-trip-book.html",
    icon: BookOpen,
  },
  {
    labNumber: 11,
    id: "itinerary-density",
    title: "Compact itinerary density",
    category: "Itinerary layout",
    description: "Consolidated identical hotel endpoints while retaining the detailed Compact Agenda and distinct stay transitions.",
    createdAt: "2026-08-01",
    defaultDisposition: "completed",
    defaultStateChangedAt: "2026-08-01",
    decision: "B · Circuit header, adapted to preserve production detail and exact endpoint behavior.",
    href: "./lab-11-itinerary-density.html",
    icon: ListChecks,
  },
  {
    labNumber: 10,
    id: "pane-control-polish",
    title: "Pane control polish",
    category: "Enhancements and polish",
    description: "Compared clearer pane-local presentations for Hide and Maximize without changing independent ownership or behavior.",
    createdAt: "2026-08-01",
    defaultDisposition: "completed",
    defaultStateChangedAt: "2026-08-01",
    decision: "B · Restrained icon pair, applied only to Itinerary, Map, and Details pane-local controls.",
    href: "./lab-10-pane-controls.html",
    icon: LayoutPanelTop,
  },
  {
    labNumber: 8,
    id: "map-controls",
    title: "Map command and day context",
    category: "Map interaction",
    description: "Compared route ribbons, a compact command deck, and a schedule-first map for add-stop, day focus, and route summaries.",
    createdAt: "2026-07-31",
    defaultDisposition: "completed",
    defaultStateChangedAt: "2026-07-31",
    decision: "A · Unified route ribbon, changing only the Map command hierarchy.",
    href: "./lab-8-map-controls.html",
    icon: Map,
  },
  {
    labNumber: 6,
    id: "trip-snapshot-hierarchy",
    title: "Trip snapshot hierarchy",
    category: "Trip overview",
    description: "Compared scan-ledger, decision-brief, and progressive whole-trip summaries above the itinerary agenda.",
    createdAt: "2026-07-31",
    defaultDisposition: "completed",
    defaultStateChangedAt: "2026-07-31",
    decision: "B · Decision brief, with compact facts and no repeated Trip fit block below Budget.",
    href: "./lab-6-trip-snapshot.html",
    icon: ListChecks,
  },
  {
    labNumber: 7,
    id: "workspace-command-bar",
    title: "Workspace command bar controls",
    category: "Workspace controls",
    description: "Compared direct pane toggles, a segmented view group, and a compact Layout popover with local Hide and Maximize controls.",
    createdAt: "2026-07-31",
    defaultDisposition: "completed",
    defaultStateChangedAt: "2026-07-31",
    decision: "A · Direct pane toggles, with labeled New trip and unchanged pane-local controls.",
    href: "./lab-7-workspace-command-bar.html",
    icon: LayoutPanelTop,
  },
  {
    labNumber: 9,
    id: "shell-visual-refresh",
    title: "Workspace visual refresh",
    category: "Visual system",
    description: "Compared semantic icon-and-text, compact icon, and text-led controls inside a realistic full planner shell.",
    createdAt: "2026-07-31",
    defaultDisposition: "completed",
    defaultStateChangedAt: "2026-07-31",
    decision: "A · Semantic icon + text, applied only to the desktop top command bar.",
    href: "./lab-9-shell-visual-refresh.html",
    icon: LayoutPanelTop,
  },
  {
    labNumber: 4,
    id: "chat-assistant-overlay",
    title: "Assistant-led trip kickoff",
    category: "Assistant layout",
    description: "Compared a collapsible edge drawer, corner conversation sheet, and prompt popover using the same pre-filled trip brief.",
    createdAt: "2026-07-30",
    defaultDisposition: "completed",
    defaultStateChangedAt: "2026-07-30",
    decision: "B · Corner conversation sheet, preserving the mounted conversation and usable workspace.",
    href: "./lab-4-chat-assistant.html",
    icon: MessageCircle,
  },
  {
    labNumber: 2,
    id: "itinerary-row-design",
    title: "Itinerary row design",
    category: "Itinerary layout",
    description: "Compared Journey Timeline, Compact Agenda, and Guided Place Cards for each scheduled stop.",
    createdAt: "2026-07-29",
    defaultDisposition: "completed",
    defaultStateChangedAt: "2026-07-29",
    decision: "B · Compact Agenda, paired with C · Compact Brief.",
    href: "./lab-2-itinerary-information.html",
    icon: ListChecks,
  },
  {
    labNumber: 3,
    id: "itinerary-summary-design",
    title: "Itinerary summary design",
    category: "Trip overview",
    description: "Compared Editorial, Balanced, and Compact modifications of Narrative Brief above Compact Agenda.",
    createdAt: "2026-07-29",
    defaultDisposition: "completed",
    defaultStateChangedAt: "2026-07-29",
    decision: "C · Compact Brief with explicit travel rhythm, day plan, and booking readiness.",
    href: "./lab-3-itinerary-summary.html",
    icon: LayoutPanelTop,
  },
  {
    labNumber: 1,
    id: "workspace-shell",
    title: "Workspace shell layout",
    category: "Workspace layout",
    description: "Compared map-first, story-first, and compact-mobile workspace structures on experiment branches.",
    createdAt: "2026-07-23",
    defaultDisposition: "completed",
    defaultStateChangedAt: "2026-07-23",
    decision: "Layout C: map-first canvas, details-first rail, and compact lower-right Assistant.",
    href: "./lab-1-workspace-shell.html",
    icon: LayoutPanelTop,
  },
];

const assignedLabNumbers = allLabs.map((lab) => lab.labNumber);
const labNumbersAreValid = assignedLabNumbers.every((number) => Number.isInteger(number) && number > 0)
  && new Set(assignedLabNumbers).size === allLabs.length
  && Math.max(...assignedLabNumbers) === LAST_ASSIGNED_LAB_NUMBER
  && allLabs.length === LAST_ASSIGNED_LAB_NUMBER;
if (!labNumbersAreValid) throw new Error("Lab numbers must be unique, contiguous, and never reused");