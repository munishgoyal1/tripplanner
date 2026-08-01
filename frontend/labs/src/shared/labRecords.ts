import { BookOpen, LayoutPanelTop, ListChecks, Map, MessageCircle, SlidersHorizontal } from "lucide-react";

export interface LabRecord {
  id: string;
  title: string;
  category: string;
  description: string;
  date: string;
  status: string;
  href: string;
  decision: string;
  icon: typeof ListChecks;
}

export interface LabSelectionState {
  disposition?: "ready" | "parked" | "completed" | "discarded";
  selectionLabel?: string;
}

export function locallyCompletedLabs(selections: Record<string, LabSelectionState>): LabRecord[] {
  return activeLabs
    .filter((lab) => selections[lab.id]?.disposition === "completed")
    .map((lab) => ({
      ...lab,
      status: "Completed",
      decision: selections[lab.id]?.selectionLabel || "Decision recorded",
    }));
}

export const activeLabs: LabRecord[] = [
  {
    id: "account-settings",
    title: "Account and settings ownership",
    category: "Account controls",
    description: "Compare one unified account menu, a strict profile/settings split, and a sectioned account hub with working analytics preferences.",
    date: "1 Aug 2026",
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
    date: "30 Jul 2026",
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
    date: "1 Aug 2026",
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
    date: "1 Aug 2026",
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
    date: "31 Jul 2026",
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
    date: "31 Jul 2026",
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
    date: "31 Jul 2026",
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
    date: "31 Jul 2026",
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
    date: "30 Jul 2026",
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
    date: "29 Jul 2026",
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
    date: "29 Jul 2026",
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
    date: "23 Jul 2026",
    status: "Decided",
    decision: "Layout C: map-first canvas, details-first rail, and compact lower-right Assistant.",
    href: "./workspace-shell.html",
    icon: LayoutPanelTop,
  },
];