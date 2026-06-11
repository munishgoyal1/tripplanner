import type { ReactNode } from "react";
import ItineraryPanel from "./ItineraryPanel";
import MapPanel from "./MapPanel";

export type RailTab = "itinerary" | "map" | "photos";

interface Props {
  activeTab: RailTab;
  onTab: (t: RailTab) => void;
  /** The Photos tab content (the existing TripPanel). */
  photos: ReactNode;
  /** Bumped when the trip changes so map + itinerary refetch. */
  reloadToken: number;
  /** Name of the stop to highlight (drives both itinerary + map). */
  focusName: string | null;
  onStopFocus: (kind: string, name: string) => void;
  onStopMap: (name: string) => void;
}

const TABS: { id: RailTab; label: string; icon: string }[] = [
  { id: "itinerary", label: "Itinerary", icon: "\u{1F5D2}\uFE0F" },
  { id: "map", label: "Map", icon: "\u{1F5FA}\uFE0F" },
  { id: "photos", label: "Photos", icon: "\u{1F4F8}" },
];

export default function RightRail({
  activeTab,
  onTab,
  photos,
  reloadToken,
  focusName,
  onStopFocus,
  onStopMap,
}: Props) {
  return (
    <div className="flex h-full min-h-0 w-full flex-col bg-surface">
      <div
        role="tablist"
        aria-label="Trip views"
        className="flex items-center gap-1 border-b border-slate-100 bg-white/70 px-3 py-2 backdrop-blur"
      >
        {TABS.map((t) => {
          const active = activeTab === t.id;
          return (
            <button
              key={t.id}
              role="tab"
              aria-selected={active}
              type="button"
              onClick={() => onTab(t.id)}
              className={`flex flex-1 items-center justify-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium transition ${
                active
                  ? "bg-ink text-white shadow-sm"
                  : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              <span aria-hidden>{t.icon}</span>
              <span>{t.label}</span>
            </button>
          );
        })}
      </div>

      <div className="flex min-h-0 flex-1 flex-col">
        {/* Itinerary: always mounted (cheap) so its booked state stays warm. */}
        <div className={activeTab === "itinerary" ? "flex min-h-0 flex-1" : "hidden"}>
          <div className="min-h-0 w-full flex-1">
            <ItineraryPanel
              reloadToken={reloadToken}
              focusName={focusName}
              onStopFocus={onStopFocus}
              onStopMap={onStopMap}
            />
          </div>
        </div>

        {/* Map: lazy — Google Maps JS bills per load, so only mount on demand. */}
        {activeTab === "map" && (
          <div className="flex min-h-0 flex-1">
            <div className="min-h-0 w-full flex-1">
              <MapPanel reloadToken={reloadToken} focusName={focusName} />
            </div>
          </div>
        )}

        {/* Photos: always mounted to preserve scroll + overview cache. */}
        <div className={activeTab === "photos" ? "flex min-h-0 flex-1" : "hidden"}>
          <div className="min-h-0 w-full flex-1">{photos}</div>
        </div>
      </div>
    </div>
  );
}
