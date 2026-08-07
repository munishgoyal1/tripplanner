import { AlertTriangle, List, Map, MessageCircle, PanelRight, Plus, UserRound } from "lucide-react";
import type { TripWorkspaceView } from "../types";
import StatusBar from "./StatusBar";
import TripActionsMenu from "./TripActionsMenu";
import TripSwitcher from "./TripSwitcher";

type Pane = "itinerary" | "map" | "details" | "assistant";

const PANES: { pane: Pane; label: string; Icon: typeof List; title: string }[] = [
  { pane: "assistant", label: "Chat", Icon: MessageCircle, title: "Show or hide chat" },
  { pane: "itinerary", label: "Itinerary", Icon: List, title: "Show or hide itinerary" },
  { pane: "map", label: "Map", Icon: Map, title: "Show or hide map" },
  { pane: "details", label: "Details", Icon: PanelRight, title: "Show or hide trip details" },
];

interface Props {
  tripVersion: number;
  onTripSwitched: (tripId?: string, workspace?: TripWorkspaceView | null) => void;
  reviewPending: boolean;
  onReviewWithPlanner: () => void;
  onKeepReview: () => void;
  onStartNewTrip: () => void;
  paneVisibility: Record<Pane, boolean>;
  onTogglePane: (pane: Pane) => void;
  tripActionsDisabled: boolean;
  onExport: () => void;
  signedIn: boolean;
  accountLabel: string;
  onOpenAccount: () => void;
  documentBadge: string;
  documentBadgeTone: "blocker" | "warning";
  onOpenDocuments: () => void;
}

export default function DesktopToolbar({
  tripVersion,
  onTripSwitched,
  reviewPending,
  onReviewWithPlanner,
  onKeepReview,
  onStartNewTrip,
  paneVisibility,
  onTogglePane,
  tripActionsDisabled,
  onExport,
  signedIn,
  accountLabel,
  onOpenAccount,
  documentBadge,
  documentBadgeTone,
  onOpenDocuments,
}: Props) {
  return (
    <header className="relative z-50 flex h-12 shrink-0 items-center gap-2 overflow-visible border-b border-[#dce2df] bg-[#fbfcfb]/95 px-3 shadow-[0_1px_4px_rgba(23,36,51,.06)] backdrop-blur">
      <TripSwitcher version={tripVersion} onSwitched={onTripSwitched} />
      <div className="ml-3 h-5 w-px shrink-0 bg-slate-200" aria-hidden />
      <div className="mr-auto flex min-w-32 flex-1 items-center gap-2 pl-3">
        <StatusBar />
        {documentBadge && (
          <button
            type="button"
            onClick={onOpenDocuments}
            className={`inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md px-2.5 text-xs font-semibold ring-1 ${
              documentBadgeTone === "blocker"
                ? "bg-rose-50 text-rose-700 ring-rose-200 hover:bg-rose-100"
                : "bg-amber-50 text-amber-800 ring-amber-200 hover:bg-amber-100"
            }`}
            title="Open your travel documents for this trip"
          >
            <AlertTriangle size={13} aria-hidden /> {documentBadge}
          </button>
        )}
        {reviewPending && (
          <div className="flex shrink-0 items-center gap-1" aria-label="Planner review choices">
            <button type="button" onClick={onReviewWithPlanner} className="rounded-md bg-amber-100 px-2 py-1 text-xs font-semibold text-amber-900 hover:bg-amber-200">
              Review with planner
            </button>
            <button type="button" onClick={onKeepReview} className="rounded-md px-2 py-1 text-xs font-medium text-slate-600 hover:bg-slate-100">
              Keep as is
            </button>
          </div>
        )}
      </div>
      <nav className="flex shrink-0 items-center gap-1" aria-label="Workspace controls">
        <button
          type="button"
          onClick={onStartNewTrip}
          className="inline-flex h-8 items-center gap-1.5 rounded-md bg-brand/10 px-3 text-xs font-semibold text-brand transition hover:bg-brand/15"
          title="Start a new trip"
          aria-label="New trip"
        >
          <Plus size={14} aria-hidden />
          <span>New trip</span>
        </button>
        <div className="mx-1 h-5 w-px bg-slate-200" aria-hidden />
        <div
          className="flex items-center gap-0.5 rounded-lg bg-slate-100/80 p-0.5 ring-1 ring-slate-200/80"
          aria-label="Pane visibility"
        >
          {PANES.map(({ pane, label, Icon, title }) => (
            <button
              key={pane}
              type="button"
              onClick={() => onTogglePane(pane)}
              className={`inline-flex h-7 items-center justify-center gap-1.5 rounded-md px-2 text-xs font-semibold transition ${
                paneVisibility[pane]
                  ? "bg-white text-slate-700 shadow-sm ring-1 ring-slate-200/70"
                  : "text-slate-400 hover:text-slate-600"
              }`}
              aria-pressed={paneVisibility[pane]}
              title={title}
            >
              <Icon size={15} aria-hidden /> <span className="hidden xl:inline">{label}</span>
            </button>
          ))}
        </div>
        <TripActionsMenu disabled={tripActionsDisabled} onExport={onExport} compactTrigger />
        <button
          type="button"
          onClick={onOpenAccount}
          className="inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-xs font-semibold text-slate-600 transition hover:bg-slate-50"
          title="Account settings"
          aria-label="Account settings"
        >
          <span className="relative">
            <UserRound size={15} aria-hidden />
            <span className={`absolute -bottom-1 -right-1 h-2 w-2 rounded-full ring-2 ring-white ${signedIn ? "bg-emerald-500" : "bg-slate-400"}`} aria-hidden />
          </span>
          <span>{accountLabel}</span>
        </button>
      </nav>
    </header>
  );
}