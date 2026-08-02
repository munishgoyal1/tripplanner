import { BookOpen, Compass, LayoutPanelTop, ListChecks, Map, MessageCircle, Route, SlidersHorizontal } from "lucide-react";

export interface LabRecord {
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

export function effectiveLabDisposition(lab: LabRecord, selection?: LabSelectionState): LabDisposition | undefined {
  return selection?.disposition ?? lab.defaultDisposition;
}

export function resolvedLabRecord(lab: LabRecord, selection?: LabSelectionState): LabRecord {
  const disposition = effectiveLabDisposition(lab, selection);
  const status = disposition === "completed" ? "Completed"
    : disposition === "implemented-review" ? "Implemented - To be reviewed"
    : disposition === "ready" ? "Under implementation"
    : disposition === "parked" ? "Parked"
    : lab.status;
  const decision = selection?.disposition && selection.selectionLabel ? selection.selectionLabel : lab.decision;
  return { ...lab, status, decision };
}

export const activeLabs: LabRecord[] = [
  {
    id: "intercity-map",
    title: "Inter-city travel on the day map",
    category: "Map completeness",
    description: "Compare a connected day journey, a journey strip, and optional route layers for road, rail, and flight transfer days.",
    createdAt: "2026-08-01",
    status: "In evaluation",
    decision: "Open · Recommended starting point: A · Connected day journey.",
    href: "./intercity-map.html",
    icon: Map,
  },
  {
    id: "multi-city-itinerary",
    title: "Transition-day itinerary design",
    category: "Multi-city itinerary",
    description: "Compare three ways to show old-stay checkout, inter-city travel, new-stay check-in, and the remaining day.",
    createdAt: "2026-08-01",
    status: "In evaluation",
    decision: "Open · Recommended starting point: A · Transition spine.",
    href: "./multi-city-itinerary.html",
    icon: Route,
  },
  {
    id: "destination-guide",
    title: "Destination guide depth and context",
    category: "Place discovery",
    description: "Compare contextual alternatives, city chapters, and a filtered directory for browsing beyond the current ten-place shortlist.",
    createdAt: "2026-08-01",
    status: "In evaluation",
    decision: "Open · Recommended starting point: A · Contextual explorer.",
    href: "./destination-guide.html",
    icon: Compass,
  },
  {
    id: "account-settings",
    title: "Account and settings ownership",
    category: "Account controls",
    description: "Compare one unified account menu, a strict profile/settings split, and a sectioned account hub with complete profile, analytics, and privacy destinations.",
    createdAt: "2026-08-01",
    status: "In evaluation",
    decision: "Open · Recommended starting point: A · Unified account menu.",
    href: "./account-settings.html",
    icon: SlidersHorizontal,
  },
  {
    id: "itinerary-trip-book",
    title: "Execution-ready Trip Book",
    category: "Trip export",
    description: "Compare compact, layered, and visual structures for one printable itinerary with confirmations and personal context.",
    createdAt: "2026-07-30",
    status: "In evaluation",
    decision: "Open · Recommended starting point: B · Layered Trip Book.",
    href: "./itinerary-trip-book.html",
    icon: BookOpen,
  },
];

export const completedLabs: LabRecord[] = [
  {
    id: "itinerary-density",
    title: "Compact itinerary density",
    category: "Itinerary layout",
    description: "Consolidated identical hotel endpoints while retaining the detailed Compact Agenda and distinct stay transitions.",
    createdAt: "2026-08-01",
    defaultDisposition: "completed",
    defaultStateChangedAt: "2026-08-01",
    status: "Implemented",
    decision: "B · Circuit header, adapted to preserve production detail and exact endpoint behavior.",
    href: "./itinerary-density.html",
    icon: ListChecks,
  },
  {
    id: "pane-control-polish",
    title: "Pane control polish",
    category: "Enhancements and polish",
    description: "Compared clearer pane-local presentations for Hide and Maximize without changing independent ownership or behavior.",
    createdAt: "2026-08-01",
    defaultDisposition: "completed",
    defaultStateChangedAt: "2026-08-01",
    status: "Implemented",
    decision: "B · Restrained icon pair, applied only to Itinerary, Map, and Details pane-local controls.",
    href: "./pane-controls.html",
    icon: LayoutPanelTop,
  },
  {
    id: "map-controls",
    title: "Map command and day context",
    category: "Map interaction",
    description: "Compared route ribbons, a compact command deck, and a schedule-first map for add-stop, day focus, and route summaries.",
    createdAt: "2026-07-31",
    defaultDisposition: "completed",
    defaultStateChangedAt: "2026-07-31",
    status: "Implemented",
    decision: "A · Unified route ribbon, changing only the Map command hierarchy.",
    href: "./map-controls.html",
    icon: Map,
  },
  {
    id: "trip-snapshot-hierarchy",
    title: "Trip snapshot hierarchy",
    category: "Trip overview",
    description: "Compared scan-ledger, decision-brief, and progressive whole-trip summaries above the itinerary agenda.",
    createdAt: "2026-07-31",
    defaultDisposition: "completed",
    defaultStateChangedAt: "2026-07-31",
    status: "Implemented",
    decision: "B · Decision brief, with compact facts and no repeated Trip fit block below Budget.",
    href: "./trip-snapshot.html",
    icon: ListChecks,
  },
  {
    id: "workspace-command-bar",
    title: "Workspace command bar controls",
    category: "Workspace controls",
    description: "Compared direct pane toggles, a segmented view group, and a compact Layout popover with local Hide and Maximize controls.",
    createdAt: "2026-07-31",
    defaultDisposition: "completed",
    defaultStateChangedAt: "2026-07-31",
    status: "Implemented",
    decision: "A · Direct pane toggles, with labeled New trip and unchanged pane-local controls.",
    href: "./workspace-command-bar.html",
    icon: LayoutPanelTop,
  },
  {
    id: "shell-visual-refresh",
    title: "Workspace visual refresh",
    category: "Visual system",
    description: "Compared semantic icon-and-text, compact icon, and text-led controls inside a realistic full planner shell.",
    createdAt: "2026-07-31",
    defaultDisposition: "completed",
    defaultStateChangedAt: "2026-07-31",
    status: "Implemented",
    decision: "A · Semantic icon + text, applied only to the desktop top command bar.",
    href: "./shell-visual-refresh.html",
    icon: LayoutPanelTop,
  },
  {
    id: "chat-assistant-overlay",
    title: "Assistant-led trip kickoff",
    category: "Assistant layout",
    description: "Compared a collapsible edge drawer, corner conversation sheet, and prompt popover using the same pre-filled trip brief.",
    createdAt: "2026-07-30",
    defaultDisposition: "completed",
    defaultStateChangedAt: "2026-07-30",
    status: "Implemented",
    decision: "B · Corner conversation sheet, preserving the mounted conversation and usable workspace.",
    href: "./chat-assistant.html",
    icon: MessageCircle,
  },
  {
    id: "itinerary-row-design",
    title: "Itinerary row design",
    category: "Itinerary layout",
    description: "Compared Journey Timeline, Compact Agenda, and Guided Place Cards for each scheduled stop.",
    createdAt: "2026-07-29",
    defaultDisposition: "completed",
    defaultStateChangedAt: "2026-07-29",
    status: "Implemented",
    decision: "B · Compact Agenda, paired with C · Compact Brief.",
    href: "./itinerary-information.html",
    icon: ListChecks,
  },
  {
    id: "itinerary-summary-design",
    title: "Itinerary summary design",
    category: "Trip overview",
    description: "Compared Editorial, Balanced, and Compact modifications of Narrative Brief above Compact Agenda.",
    createdAt: "2026-07-29",
    defaultDisposition: "completed",
    defaultStateChangedAt: "2026-07-29",
    status: "Implemented",
    decision: "C · Compact Brief with explicit travel rhythm, day plan, and booking readiness.",
    href: "./itinerary-summary.html",
    icon: LayoutPanelTop,
  },
  {
    id: "workspace-shell",
    title: "Workspace shell layout",
    category: "Workspace layout",
    description: "Compared map-first, story-first, and compact-mobile workspace structures on experiment branches.",
    createdAt: "2026-07-23",
    defaultDisposition: "completed",
    defaultStateChangedAt: "2026-07-23",
    status: "Decided",
    decision: "Layout C: map-first canvas, details-first rail, and compact lower-right Assistant.",
    href: "./workspace-shell.html",
    icon: LayoutPanelTop,
  },
];

export const allLabs = [...activeLabs, ...completedLabs];