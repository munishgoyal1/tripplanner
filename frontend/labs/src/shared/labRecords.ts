import { BookOpen, LayoutPanelTop, ListChecks, Map, MessageCircle } from "lucide-react";

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

export const activeLabs: LabRecord[] = [
  {
    id: "shell-visual-refresh",
    title: "Workspace visual refresh",
    category: "Visual system",
    description: "Compare semantic icon-and-text, compact icon, and text-led controls inside a realistic full planner shell.",
    date: "30 Jul 2026",
    status: "In evaluation",
    decision: "Open · Production control styling remains unchanged until selection.",
    href: "./shell-visual-refresh.html",
    icon: LayoutPanelTop,
  },
  {
    id: "workspace-command-bar",
    title: "Workspace command bar controls",
    category: "Workspace controls",
    description: "Compare direct pane toggles, a segmented view group, and a compact Layout popover with local Hide and Maximize controls.",
    date: "31 Jul 2026",
    status: "In evaluation",
    decision: "Open · Recommended starting point: B · Segmented view group.",
    href: "./workspace-command-bar.html",
    icon: LayoutPanelTop,
  },
  {
    id: "trip-snapshot-hierarchy",
    title: "Trip snapshot hierarchy",
    category: "Trip overview",
    description: "Compare scan-ledger, decision-brief, and progressive whole-trip summaries above the itinerary agenda.",
    date: "31 Jul 2026",
    status: "In evaluation",
    decision: "Open · Recommended starting point: B · Decision brief.",
    href: "./trip-snapshot.html",
    icon: ListChecks,
  },
  {
    id: "map-controls",
    title: "Map command and day context",
    category: "Map interaction",
    description: "Compare route ribbons, a compact command deck, and a schedule-first map for add-stop, day focus, and route summaries.",
    date: "31 Jul 2026",
    status: "In evaluation",
    decision: "Open · Recommended starting point: A · Unified route ribbon.",
    href: "./map-controls.html",
    icon: Map,
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
  {
    id: "itinerary-density",
    title: "Compact itinerary density",
    category: "Itinerary layout",
    description: "Compare one-line, circuit-header, and progressive-focus agendas inside a 320 px day frame.",
    date: "30 Jul 2026",
    status: "In evaluation",
    decision: "Open experiment · B starts as the recommended direction.",
    href: "./itinerary-density.html",
    icon: ListChecks,
  },
];

export const completedLabs: LabRecord[] = [
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