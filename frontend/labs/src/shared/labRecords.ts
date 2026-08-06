import { BookOpen, Compass, LayoutPanelTop, ListChecks, Map, MessageCircle, Route, SlidersHorizontal, Workflow } from "lucide-react";

export interface LabRecord {
  labNumber: number;
  id: string;
  title: string;
  category: string;
  description: string;
  createdAt: string;
  defaultDisposition?: LabDisposition;
  defaultStateChangedAt?: string;
  status: string;
  href: string;
  decision: string;
  icon: typeof ListChecks;
}

export interface LabSelectionState {
  disposition?: LabDisposition;
  selectionLabel?: string;
  stateChangedAt?: string;
  updatedAt?: string;
}

export type LabDisposition = "ready" | "implemented-review" | "parked" | "completed" | "discarded";

export const LAST_ASSIGNED_LAB_NUMBER = 19;

export function effectiveLabDisposition(lab: LabRecord, selection?: LabSelectionState): LabDisposition | undefined {
  return selection?.disposition ?? lab.defaultDisposition;
}

export function resolvedLabRecord(lab: LabRecord, selection?: LabSelectionState): LabRecord {
  const disposition = effectiveLabDisposition(lab, selection);
  const status = disposition === "completed" ? "Completed"
    : disposition === "implemented-review" ? "Implemented - To be reviewed"
    : disposition === "ready" ? "In progress"
    : disposition === "parked" ? "Parked"
    : lab.status;
  const decision = selection?.disposition && selection.selectionLabel ? selection.selectionLabel : lab.decision;
  return { ...lab, status, decision };
}

export const activeLabs: LabRecord[] = [
  {
    labNumber: 19,
    id: "agentic-planning",
    title: "An itinerary that cannot be edited into nonsense",
    category: "Agent behaviour",
    description: "A deterministic plan engine between intent and the trip: envelope, presence, anchors, blast radius and receipts, so a change from chat, map, itinerary or details can never place a stop after the flight home or silently delete a booked leg.",
    createdAt: "2026-08-05",
    status: "In evaluation",
    decision: "Open · Recommended starting point: B · Guarded autonomy.",
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
    status: "In evaluation",
    decision: "Open · Recommended starting point: B · Route dock.",
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
    status: "In evaluation",
    decision: "Open · Recommended starting point: B · Layered stop cards.",
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
    status: "In evaluation",
    decision: "Open · Recommended starting point: C · Turn thread.",
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
    status: "In evaluation",
    decision: "Open · Recommended starting point: A · Connected day journey.",
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
    defaultDisposition: "implemented-review",
    defaultStateChangedAt: "2026-08-02",
    status: "In evaluation",
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
    defaultDisposition: "implemented-review",
    defaultStateChangedAt: "2026-08-04",
    status: "In evaluation",
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
    defaultDisposition: "implemented-review",
    defaultStateChangedAt: "2026-08-02",
    status: "In evaluation",
    decision: "Open · Recommended starting point: A · Unified account menu.",
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
    status: "In evaluation",
    decision: "Open · Recommended starting point: B · Layered Trip Book.",
    href: "./lab-5-itinerary-trip-book.html",
    icon: BookOpen,
  },
];

export const completedLabs: LabRecord[] = [
  {
    labNumber: 11,
    id: "itinerary-density",
    title: "Compact itinerary density",
    category: "Itinerary layout",
    description: "Consolidated identical hotel endpoints while retaining the detailed Compact Agenda and distinct stay transitions.",
    createdAt: "2026-08-01",
    defaultDisposition: "completed",
    defaultStateChangedAt: "2026-08-01",
    status: "Implemented",
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
    status: "Implemented",
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
    status: "Implemented",
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
    status: "Implemented",
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
    status: "Implemented",
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
    status: "Implemented",
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
    status: "Implemented",
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
    status: "Implemented",
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
    status: "Implemented",
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
    status: "Decided",
    decision: "Layout C: map-first canvas, details-first rail, and compact lower-right Assistant.",
    href: "./lab-1-workspace-shell.html",
    icon: LayoutPanelTop,
  },
];

export const allLabs = [...activeLabs, ...completedLabs];

const assignedLabNumbers = allLabs.map((lab) => lab.labNumber);
const labNumbersAreValid = assignedLabNumbers.every((number) => Number.isInteger(number) && number > 0)
  && new Set(assignedLabNumbers).size === allLabs.length
  && Math.max(...assignedLabNumbers) === LAST_ASSIGNED_LAB_NUMBER
  && allLabs.length === LAST_ASSIGNED_LAB_NUMBER;
if (!labNumbersAreValid) throw new Error("Lab numbers must be unique, contiguous, and never reused");