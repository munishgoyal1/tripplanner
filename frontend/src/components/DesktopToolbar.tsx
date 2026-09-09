import { AlertTriangle, Bell, Compass, House, LayoutDashboard, List, MapPin, MessageCircle, PanelRight, Plus, RotateCcw, Settings, UserRound } from "lucide-react";
import { useNotice } from "../lib/notices";
import type { TripWorkspaceView } from "../types";
import StatusBar from "./StatusBar";
import TripActionsMenu from "./TripActionsMenu";
import TripFeedbackControl from "./TripFeedbackControl";
import TripSwitcher from "./TripSwitcher";

type Pane = "itinerary" | "map" | "details" | "assistant";

const PANES: { pane: Pane; label: string; Icon: typeof List; title: string }[] = [
  { pane: "itinerary", label: "Itinerary", Icon: List, title: "Show or hide itinerary" },
  { pane: "map", label: "Map", Icon: MapPin, title: "Show or hide map" },
  { pane: "details", label: "Guide", Icon: PanelRight, title: "Show or hide trip details" },
  { pane: "assistant", label: "Assistant", Icon: MessageCircle, title: "Show or hide chat" },
];

interface Props {
  tripVersion: number;
  onTripSwitched: (tripId?: string, workspace?: TripWorkspaceView | null) => void;
  reviewPending: boolean;
  onReviewWithPlanner: () => void;
  onKeepReview: () => void;
  onStartNewTrip: () => void;
  onResetTrip: () => void;
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
  onOpenWelcome: () => void;
  feedback: { count: number; last_rating?: number | null; last_sentiment?: "up" | "down" | null };
}

export default function DesktopToolbar({
  tripVersion,
  onTripSwitched,
  reviewPending,
  onReviewWithPlanner,
  onKeepReview,
  onStartNewTrip,
  onResetTrip,
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
  onOpenWelcome,
  feedback,
}: Props) {
  const notice = useNotice();
  return (
    <>
      <header className="relative z-50 flex h-10 shrink-0 items-center gap-2 overflow-visible border-b border-border bg-paper px-3 lg:gap-2.5 lg:px-4">
        <span className="hidden shrink-0 items-center gap-2 xl:inline-flex">
          <Compass size={17} className="text-brand" aria-hidden />
          <span className="display text-lg text-ink">AI Tripplanner</span>
        </span>
        <TripSwitcher version={tripVersion} onSwitched={onTripSwitched} />
        <div className="h-6 w-px shrink-0 bg-border" aria-hidden />
        <nav className="ml-auto flex shrink-0 items-center gap-1.5 lg:gap-2" aria-label="Workspace controls">
          <span className="hidden items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted lg:inline-flex">
            <LayoutDashboard size={14} className="text-brand" aria-hidden /> Workspace
          </span>
          <div
            role="group" className="flex shrink-0 items-center gap-0.5 rounded-full border border-border bg-sand p-0.5"
            aria-label="Pane visibility"
          >
            {PANES.map(({ pane, label, Icon, title }) => (
              <button
                key={pane}
                type="button"
                onClick={() => onTogglePane(pane)}
                className={`inline-flex h-7 items-center justify-center gap-1 rounded-full px-2 text-xs font-semibold transition ${
                  paneVisibility[pane]
                    ? "bg-clay-soft text-ink shadow-sm ring-1 ring-clay/20"
                    : "text-muted hover:bg-paper hover:text-ink"
                }`}
                aria-pressed={paneVisibility[pane]}
                title={title}
              >
                <Icon size={15} aria-hidden /> <span>{label}</span>
              </button>
            ))}
          </div>
          <TripFeedbackControl disabled={tripActionsDisabled} initial={feedback} />
          <div role="group" className="flex items-center gap-0.5 rounded-full border border-border bg-paper p-0.5" aria-label="Trip actions">
            <TripActionsMenu disabled={tripActionsDisabled} onExport={onExport} compactTrigger />
            <span className="h-4 w-px shrink-0 bg-border" aria-hidden />
            <button
              type="button"
              onClick={onStartNewTrip}
              className="inline-flex h-7 items-center gap-1.5 rounded-full bg-paper px-2 text-xs font-semibold text-ink transition hover:bg-clay-soft"
              title="Start a new trip"
              aria-label="New trip"
            >
              <Plus size={14} className="text-clay" aria-hidden />
              <span className="hidden xl:inline">New trip</span>
            </button>
            <span className="h-4 w-px shrink-0 bg-border" aria-hidden />
            <button
              type="button"
              onClick={onResetTrip}
              className="inline-flex h-7 w-7 items-center justify-center rounded-full text-muted transition hover:bg-sand hover:text-ink"
              title="Clear this trip's plan and start over, keeping the destination, dates and travellers"
              aria-label="Reset trip"
            >
              <RotateCcw size={14} aria-hidden />
            </button>
          </div>
          <span className="h-5 w-px shrink-0 bg-border" aria-hidden />
          <button
            type="button"
            onClick={onOpenWelcome}
            className="inline-flex h-7 w-7 items-center justify-center rounded-full text-muted transition hover:bg-sand hover:text-ink"
            title="Home: About and support information"
            aria-label="Open home page"
          >
            <House size={15} aria-hidden />
          </button>
          <button
            type="button"
            onClick={onOpenAccount}
            className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-border text-muted transition hover:bg-sand hover:text-ink"
            title="Account settings"
            aria-label="Settings"
          >
            <Settings size={15} aria-hidden />
          </button>
          <button
            type="button"
            onClick={onOpenAccount}
            className={`inline-flex h-7 items-center gap-1.5 rounded-full px-3 text-xs font-semibold transition ${signedIn ? "border border-border text-ink hover:bg-sand" : "bg-brand text-white shadow-sm hover:bg-brand-600"}`}
            title="Account settings"
            aria-label="Account settings"
          >
            {signedIn && <UserRound size={14} className="shrink-0" aria-hidden />}
            <span className="max-w-24 truncate">{signedIn ? accountLabel : "Sign in"}</span>
            {!signedIn && <span className="sr-only">Guest</span>}
          </button>
        </nav>
      </header>
      <div aria-label="Workspace notifications" className="relative z-40 flex h-7 shrink-0 items-center gap-x-3 border-b border-ochre/20 bg-ochre/15 px-3">
        <div className="mr-auto min-w-0 flex-1">
          {notice ? <StatusBar compact /> : (
            <div className="flex items-center gap-2 text-xs font-medium text-muted" role="status">
              <Bell size={13} className="text-ochre" aria-hidden />
              {tripActionsDisabled ? "Start a trip to see planning updates here." : "All changes saved."}
            </div>
          )}
        </div>
        {documentBadge && (
          <button
            type="button"
            onClick={onOpenDocuments}
            className={`inline-flex h-7 shrink-0 items-center gap-1.5 rounded-full px-3 text-xs font-semibold ring-1 ${
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
            <button type="button" onClick={onReviewWithPlanner} className="rounded-full bg-brand px-2 py-1 text-xs font-semibold text-white hover:bg-brand-600">
              Review with planner
            </button>
            <button type="button" onClick={onKeepReview} className="rounded-full px-2 py-1 text-xs font-medium text-muted hover:bg-paper">
              Keep as is
            </button>
          </div>
        )}
      </div>
    </>
  );
}
