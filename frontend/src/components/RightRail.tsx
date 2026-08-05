import type { ReactNode } from "react";
import ItineraryPanel from "./ItineraryPanel";
import MapPanel from "./MapPanel";
import TripSwitcher from "./TripSwitcher";
import type { DeselectItemOptions, SelectItemOptions } from "../api";
import type { Itinerary, MapView, TripView, TripWorkspaceView } from "../types";
import type { ItineraryJump } from "../workspaceState";
import type { ItineraryFilter } from "../lib/itineraryFilters";

interface Props {
  filters: readonly ItineraryFilter[];
  onFilterToggle: (filter: ItineraryFilter) => void;
  overview: TripView["overview"];
  /** The Photos / overview content (the existing TripPanel). */
  photos: ReactNode;
  /** Bumped when the trip changes so map + itinerary refetch. */
  reloadToken: number;
  tripId?: string | null;
  /** View-models handed over by a trip switch, so the panels skip a refetch. */
  mapSeed?: MapView | null;
  itinerarySeed?: Itinerary | null;
  /** Name of the stop to highlight (drives both itinerary + map). */
  focusName: string | null;
  /** Exact itinerary day when the focused place occurs more than once. */
  focusDay?: number;
  focusStop?: number;
  focusToken?: number;
  circuitFocusDay?: number;
  circuitFocusToken?: number;
  routeFocusDay?: number;
  routeFocusToken?: number;
  itineraryJump: ItineraryJump | null;
  onStopFocus: (kind: string, name: string, day?: number, stop?: number) => void;
  onStopMap: (kind: string, name: string, day?: number, stop?: number) => void;
  onDayMap: (day: number) => void;
  onMapDayFocus: (day: number) => void;
  onMapAllDaysFocus: () => void;
  onSelect?: (
    kind: string,
    name: string,
    options?: SelectItemOptions,
  ) => void | Promise<boolean>;
  onDeselect?: (
    kind: string,
    name: string,
    options?: DeselectItemOptions,
  ) => void | Promise<boolean>;
  /** Persistent saved-trips switcher (always visible). */
  tripVersion: number;
  onSwitched: (tripId?: string, workspace?: TripWorkspaceView | null) => void;
  /** Map is lazy (Google Maps JS bills per load) — opt-in, stays mounted. */
  mapOpen: boolean;
  onToggleMap: (open: boolean) => void;
}

export default function RightRail({
  filters,
  onFilterToggle,
  overview,
  photos,
  reloadToken,
  tripId,
  mapSeed,
  itinerarySeed,
  focusName,
  focusDay,
  focusStop,
  focusToken,
  circuitFocusDay,
  circuitFocusToken,
  routeFocusDay,
  routeFocusToken,
  itineraryJump,
  onStopFocus,
  onStopMap,
  onDayMap,
  onMapDayFocus,
  onMapAllDaysFocus,
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
              filters={filters}
              onFilterToggle={onFilterToggle}
              overview={overview}
              reloadToken={reloadToken}
              tripId={tripId}
              seed={itinerarySeed}
              focusName={focusName}
              focusDay={focusDay}
              focusStop={focusStop}
              focusToken={focusToken}
              circuitFocusDay={circuitFocusDay}
              circuitFocusToken={circuitFocusToken}
              jumpTo={itineraryJump}
              onStopFocus={onStopFocus}
              onStopMap={onStopMap}
              onDayMap={onDayMap}
              onAllDaysMap={onMapAllDaysFocus}
              onStopRemove={onDeselect
                ? async (kind, name, day, stop) => { await onDeselect(kind, name, {
                    day,
                    stop,
                    all_occurrences: false,
                  }); }
                : undefined}
            />
          </div>
        </section>

        {/* Map — lazy: only mounts once the user opens it, then stays mounted. */}
        {mapOpen && (
          <section className="flex h-72 min-h-0 flex-col border-b border-slate-100">
            <div className="min-h-0 w-full flex-1">
              <MapPanel
                filters={filters}
                reloadToken={reloadToken}
                tripId={tripId}
                seed={mapSeed}
                focusName={focusName}
                focusDay={focusDay}
                focusStop={focusStop}
                focusToken={focusToken}
                circuitFocusDay={circuitFocusDay}
                circuitFocusToken={circuitFocusToken}
                routeFocusDay={routeFocusDay}
                routeFocusToken={routeFocusToken}
                onPinFocus={onStopFocus}
                onDayFocus={onMapDayFocus}
                onAllDaysFocus={onMapAllDaysFocus}
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
