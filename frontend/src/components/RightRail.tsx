import type { ReactNode } from "react";
import ItineraryPanel from "./ItineraryPanel";
import MapPanel from "./MapPanel";
import TripSwitcher from "./TripSwitcher";
import type { TripView } from "../types";

interface Props {
  /** The Photos / overview content (the existing TripPanel). */
  photos: ReactNode;
  /** Bumped when the trip changes so map + itinerary refetch. */
  reloadToken: number;
  /** Name of the stop to highlight (drives both itinerary + map). */
  focusName: string | null;
  onStopFocus: (kind: string, name: string) => void;
  onStopMap: (kind: string, name: string) => void;
  onSelect?: (kind: string, name: string) => void;
  onDeselect?: (kind: string, name: string) => void;
  /** Persistent saved-trips switcher (always visible). */
  tripVersion: number;
  onSwitched: (tripId?: string, view?: TripView | null) => void;
  /** Map is lazy (Google Maps JS bills per load) — opt-in, stays mounted. */
  mapOpen: boolean;
  onToggleMap: (open: boolean) => void;
}

export default function RightRail({
  photos,
  reloadToken,
  focusName,
  onStopFocus,
  onStopMap,
  onSelect,
  onDeselect,
  tripVersion,
  onSwitched,
  mapOpen,
  onToggleMap,
}: Props) {
  return (
    <div className="flex h-full min-h-0 w-full flex-col bg-surface">
      {/* Persistent header: saved-trips switcher + map toggle. Always shown. */}
      <div className="flex items-center gap-2 border-b border-slate-100 bg-white/70 px-3 py-2 backdrop-blur">
        <TripSwitcher version={tripVersion} onSwitched={onSwitched} />
        <button
          type="button"
          onClick={() => onToggleMap(!mapOpen)}
          aria-pressed={mapOpen}
          className={`ml-auto flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium transition ${
            mapOpen
              ? "bg-ink text-white shadow-sm"
              : "text-slate-600 ring-1 ring-slate-200 hover:bg-slate-100"
          }`}
          title={mapOpen ? "Hide map" : "Show map"}
        >
          <span aria-hidden>{"\u{1F5FA}\uFE0F"}</span>
          <span>{mapOpen ? "Hide map" : "Map"}</span>
        </button>
      </div>

      {/* Stacked panels — all visible at once (no tab switching). Each keeps
          its own scroll so long lists don't fight for space. */}
      <div className="flex min-h-0 flex-1 flex-col">
        {/* Itinerary — top region. */}
        <section className="flex min-h-0 basis-2/5 flex-col border-b border-slate-100">
          <div className="min-h-0 w-full flex-1">
            <ItineraryPanel
              reloadToken={reloadToken}
              focusName={focusName}
              onStopFocus={onStopFocus}
              onStopMap={onStopMap}
            />
          </div>
        </section>

        {/* Map — lazy: only mounts once the user opens it, then stays mounted. */}
        {mapOpen && (
          <section className="flex h-72 min-h-0 flex-col border-b border-slate-100">
            <div className="min-h-0 w-full flex-1">
              <MapPanel
                reloadToken={reloadToken}
                focusName={focusName}
                onPinFocus={onStopFocus}
                onSelect={onSelect}
                onDeselect={onDeselect}
              />
            </div>
          </section>
        )}

        {/* Photos / overview — bottom region, takes remaining space. */}
        <section className="flex min-h-0 flex-1 flex-col">
          <div className="min-h-0 w-full flex-1">{photos}</div>
        </section>
      </div>
    </div>
  );
}
