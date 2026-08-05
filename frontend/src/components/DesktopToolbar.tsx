import { List, Map, MessageCircle, PanelRight, Plus, UserRound } from "lucide-react";
import type { TripWorkspaceView } from "../types";
import type { AssistantTurnStatus } from "./ChatPanel";
import TripActionsMenu from "./TripActionsMenu";
import TripSwitcher from "./TripSwitcher";

type Pane = "itinerary" | "map" | "details" | "assistant";

interface Props {
  tripVersion: number;
  onTripSwitched: (tripId?: string, workspace?: TripWorkspaceView | null) => void;
  visibleStatus?: string;
  statusPhase?: AssistantTurnStatus["phase"];
  reviewPending: boolean;
  loading: boolean;
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
}

export default function DesktopToolbar({
  tripVersion,
  onTripSwitched,
  visibleStatus,
  statusPhase,
  reviewPending,
  loading,
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
}: Props) {
  return (
    <header className="relative z-50 flex h-12 shrink-0 items-center gap-2 overflow-visible border-b border-[#dce2df] bg-[#fbfcfb]/95 px-3 shadow-[0_1px_4px_rgba(23,36,51,.06)] backdrop-blur">
      <TripSwitcher version={tripVersion} onSwitched={onTripSwitched} />
      <div className="mr-auto flex min-w-32 flex-1 items-center gap-2 pl-2">
        <div className="min-w-0 flex-1" aria-live="polite" role="status">
        {visibleStatus ? (
          <p className={`line-clamp-2 whitespace-normal text-xs font-medium leading-tight ${
            reviewPending
              ? "text-amber-800"
              : statusPhase === "working" || statusPhase === "loading"
                ? "text-brand"
                : statusPhase === "error"
                  ? "text-rose-700"
                  : "text-emerald-700"
          }`} title={visibleStatus}>
            {visibleStatus}
          </p>
        ) : loading ? (
          <p className="text-xs text-slate-400">Refreshing trip…</p>
        ) : null}
        </div>
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
        <div className="flex items-center gap-1" aria-label="Pane visibility">
          <button
            type="button"
            onClick={() => onTogglePane("itinerary")}
            className={`inline-flex h-8 items-center justify-center gap-1.5 rounded-md px-2.5 text-xs font-semibold transition ${paneVisibility.itinerary ? "bg-slate-100 text-slate-600" : "text-slate-400 hover:bg-slate-50 hover:text-slate-600"}`}
            aria-pressed={paneVisibility.itinerary}
            title="Show or hide itinerary"
          >
            <List size={15} aria-hidden /> <span className="hidden xl:inline">Itinerary</span>
          </button>
          <button
            type="button"
            onClick={() => onTogglePane("map")}
            className={`inline-flex h-8 items-center justify-center gap-1.5 rounded-md px-2.5 text-xs font-semibold transition ${paneVisibility.map ? "bg-slate-100 text-slate-600" : "text-slate-400 hover:bg-slate-50 hover:text-slate-600"}`}
            aria-pressed={paneVisibility.map}
            title="Show or hide map"
          >
            <Map size={15} aria-hidden /> <span className="hidden xl:inline">Map</span>
          </button>
          <button
            type="button"
            onClick={() => onTogglePane("details")}
            className={`inline-flex h-8 items-center justify-center gap-1.5 rounded-md px-2.5 text-xs font-semibold transition ${paneVisibility.details ? "bg-slate-100 text-slate-600" : "text-slate-400 hover:bg-slate-50 hover:text-slate-600"}`}
            aria-pressed={paneVisibility.details}
            title="Show or hide trip details"
          >
            <PanelRight size={15} aria-hidden /> <span className="hidden xl:inline">Details</span>
          </button>
          <button
            type="button"
            onClick={() => onTogglePane("assistant")}
            className={`inline-flex h-8 items-center justify-center gap-1.5 rounded-md px-2.5 text-xs font-semibold transition ${paneVisibility.assistant ? "bg-slate-100 text-slate-600" : "text-slate-400 hover:bg-slate-50 hover:text-slate-600"}`}
            aria-pressed={paneVisibility.assistant}
            title="Show or hide the trip assistant"
          >
            <MessageCircle size={15} aria-hidden /> <span className="hidden xl:inline">Assistant</span>
          </button>
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