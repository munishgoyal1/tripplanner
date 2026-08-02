import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { CircleDot, Eye, EyeOff, LockKeyhole } from "lucide-react";

interface ScopeDefinition {
  changes: string[];
  context: string[];
}

const scopes: Record<string, ScopeDefinition> = {
  "intercity-map": {
    changes: [
      "Whether and how an inter-city transfer appears with local route circuits on the selected day's Map",
      "Road, rail, and flight geometry, terminals, labels, framing, and optional route layers",
    ],
    context: ["Itinerary timing, hotel endpoints, route facts, and place order", "Google Maps implementation, provider routing, geocoding, and mutation behavior"],
  },
  "multi-city-itinerary": {
    changes: [
      "The visual hierarchy of checkout, inter-city travel, arrival, check-in, and remaining destination plans",
      "How road, rail, and flight transition days separate their origin and destination context",
    ],
    context: ["Persisted stop order, timing, booking state, and hotel identity", "Map rendering, route providers, itinerary mutation, and trip planning logic"],
  },
  "destination-guide": {
    changes: [
      "How whole-trip places are scoped by destination and place type, ordered, and progressively revealed",
      "How a focused hotel, attraction, or restaurant leads to relevant alternatives",
    ],
    context: ["Itinerary, Map, trip route, and selected-place mutation behavior", "Provider ranking, place data, photos, reviews, and API pagination implementation"],
  },
  "account-settings": {
    changes: [
      "Ownership and grouping of Account, Settings, travel profile, analytics, privacy, and sign-out controls",
      "The command-bar trigger or triggers and the complete Travel Profile, Analytics, and Privacy and Data destinations",
    ],
    context: ["Trip selection, pane visibility, and workspace content", "Authentication, analytics collection, preference storage, and privacy API behavior"],
  },
  "shell-visual-refresh": {
    changes: [
      "The visual language of pane visibility controls and related workspace chrome",
      "Whether those controls use icon-and-text, compact icons, or text-led commands",
    ],
    context: ["Pane arrangement and resizing behavior", "Itinerary, Map, Details, Assistant, and trip content"],
  },
  "workspace-command-bar": {
    changes: [
      "How the command bar groups and presents pane visibility controls",
      "Whether visibility uses direct toggles, a segmented group, or a Layout menu",
    ],
    context: ["Pane layout, sizes, and content", "Each pane's existing Hide and Maximize behavior"],
  },
  "trip-snapshot-hierarchy": {
    changes: [
      "The information hierarchy and density of the whole-trip snapshot above the itinerary",
      "How trip facts, readiness, budget, and constraints are grouped and emphasized",
    ],
    context: ["Day briefs and itinerary stop rows", "Map, Details, Assistant, and the fixture's trip facts"],
  },
  "map-controls": {
    changes: [
      "The Map control hierarchy for All days/day scope, Add stop, and route summaries",
      "Where full-schedule and route-only timing appear while inspecting the Map",
    ],
    context: ["Map geography, pins, routes, and fixture data", "Itinerary sidebar, trip structure, and mutation semantics"],
  },
  "pane-control-polish": {
    changes: [
      "The visual presentation of each pane's existing Hide and Maximize or Restore actions",
      "Whether those pane-local actions use compact labels, a restrained icon pair, or a local action menu",
    ],
    context: ["Independent pane ownership, handlers, disabled states, and recovery", "Pane layout, resizing, content, command bar, and responsive behavior"],
  },
  "itinerary-trip-book": {
    changes: [
      "The exported Trip Book's structure, navigation, information layering, and visual emphasis",
      "How itinerary, confirmations, documents, and personal context are organized for print and phone PDF",
    ],
    context: ["The underlying London trip facts and booking states", "Live workspace UI, document ingestion, storage, and PDF merge behavior"],
  },
  "itinerary-density": {
    changes: [
      "The density and progressive disclosure of itinerary stop rows inside a 320 px day frame",
      "Which timing, travel, duration, and booking details remain visible at a glance",
    ],
    context: ["Stop order, names, times, travel estimates, and booking facts", "Trip snapshot, day brief, Map, Details, and Assistant"],
  },
  "chat-assistant-overlay": {
    changes: [
      "The Assistant surface's placement, footprint, open/close behavior, and relationship to the workspace",
      "How the structured trip kickoff appears inside that Assistant surface",
    ],
    context: ["Itinerary, Map, Details, command bar, and trip fixture", "Planning logic, saved preferences, tools, and generated itinerary content"],
  },
  "itinerary-row-design": {
    changes: [
      "The visual structure and information hierarchy of each itinerary stop row",
      "How time, travel, duration, place identity, notes, and booking state are scanned",
    ],
    context: ["Trip snapshot and day-summary design", "Stop sequence, trip facts, Map, Details, and Assistant behavior"],
  },
  "itinerary-summary-design": {
    changes: [
      "The day brief above each itinerary agenda: wording, hierarchy, density, and booking-readiness summary",
      "How schedule span, planned stops, travel rhythm, and guidance are communicated",
    ],
    context: ["The Compact Agenda stop-row design below it", "Trip snapshot, stop facts, Map, Details, and Assistant behavior"],
  },
  "workspace-shell": {
    changes: [
      "The overall workspace pane arrangement, relative priority, and responsive composition",
      "Where Itinerary, Map, Details, and Assistant live across desktop and compact layouts",
    ],
    context: ["The detailed visual design inside each pane", "Trip data, planning logic, map behavior, and itinerary content"],
  },
};

interface MarkerRect {
  label: string;
  top: number;
  left: number;
  width: number;
  height: number;
}

const MARKERS_KEY = "tripplanner_lab_change_markers";

function ChangeMarkerOverlay({ enabled }: { enabled: boolean }) {
  const [markers, setMarkers] = useState<MarkerRect[]>([]);

  useEffect(() => {
    if (!enabled) {
      setMarkers([]);
      return;
    }

    let frame = 0;
    let targets: HTMLElement[] = [];
    const update = () => {
      setMarkers(targets.map((target) => {
        const rect = target.getBoundingClientRect();
        return {
          label: target.dataset.labChange || "Changes in this Lab",
          top: rect.top,
          left: rect.left,
          width: rect.width,
          height: rect.height,
        };
      }).filter((marker) => marker.width > 0 && marker.height > 0));
    };
    const schedule = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(update);
    };
    const resizeObserver = new ResizeObserver(schedule);
    const refreshTargets = () => {
      targets = Array.from(document.querySelectorAll<HTMLElement>("[data-lab-change]"));
      resizeObserver.disconnect();
      targets.forEach((target) => resizeObserver.observe(target));
      schedule();
    };
    const root = document.getElementById("root");
    const mutationObserver = new MutationObserver(refreshTargets);
    if (root) mutationObserver.observe(root, { childList: true, subtree: true });
    window.addEventListener("resize", schedule);
    window.addEventListener("scroll", schedule, true);
    refreshTargets();

    return () => {
      cancelAnimationFrame(frame);
      mutationObserver.disconnect();
      resizeObserver.disconnect();
      window.removeEventListener("resize", schedule);
      window.removeEventListener("scroll", schedule, true);
    };
  }, [enabled]);

  if (!enabled || markers.length === 0) return null;
  return createPortal(
    <div className="pointer-events-none fixed inset-0 z-[90]" aria-hidden="true">
      {markers.map((marker, index) => (
        <div key={`${marker.label}-${index}`}>
          <div
            className="fixed rounded-md ring-2 ring-emerald-500 ring-offset-2 ring-offset-transparent"
            style={{ top: marker.top, left: marker.left, width: marker.width, height: marker.height }}
          />
          <span
            className="fixed max-w-56 truncate rounded-sm bg-emerald-700 px-2 py-1 text-[10px] font-bold uppercase text-white shadow-pop"
            style={{ top: Math.max(4, marker.top - 25), left: Math.max(4, marker.left) }}
          >
            Change · {marker.label}
          </span>
        </div>
      ))}
    </div>,
    document.body,
  );
}

export function LabScope({ labId }: { labId: string }) {
  const scope = scopes[labId];
  const [markersVisible, setMarkersVisible] = useState(() => localStorage.getItem(MARKERS_KEY) !== "hidden");
  if (!scope) return null;

  const toggleMarkers = () => {
    setMarkersVisible((visible) => {
      localStorage.setItem(MARKERS_KEY, visible ? "hidden" : "visible");
      return !visible;
    });
  };

  return (
    <>
      <section className="mt-5 overflow-hidden rounded-md bg-white shadow-card ring-1 ring-slate-200" aria-labelledby={`${labId}-scope-title`}>
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-4 py-3">
          <div>
            <p className="text-[10px] font-bold uppercase text-brand">Change scope</p>
            <h2 id={`${labId}-scope-title`} className="mt-0.5 text-sm font-semibold text-ink">What this Lab is deciding</h2>
            <p className="mt-1 text-xs leading-relaxed text-slate-500">Only the items under Changes vary between options. The rest of the preview is fixed context and is not part of this decision.</p>
          </div>
          <button type="button" aria-pressed={markersVisible} onClick={toggleMarkers} className="btn-ghost shrink-0">
            {markersVisible ? <EyeOff size={14} aria-hidden /> : <Eye size={14} aria-hidden />}
            {markersVisible ? "Hide change markers" : "Show change markers"}
          </button>
        </div>
        <div className="grid md:grid-cols-2">
          <div className="px-4 py-3 md:border-r md:border-slate-100">
            <p className="flex items-center gap-1.5 text-[10px] font-bold uppercase text-emerald-700"><CircleDot size={12} aria-hidden /> Changes in this Lab</p>
            <ul className="mt-2 space-y-1.5 text-xs leading-relaxed text-slate-700">
              {scope.changes.map((item) => <li key={item} className="flex gap-2"><span className="text-emerald-600">•</span><span>{item}</span></li>)}
            </ul>
          </div>
          <div className="border-t border-slate-100 bg-slate-50/60 px-4 py-3 md:border-t-0">
            <p className="flex items-center gap-1.5 text-[10px] font-bold uppercase text-slate-500"><LockKeyhole size={12} aria-hidden /> Context only, not changing</p>
            <ul className="mt-2 space-y-1.5 text-xs leading-relaxed text-slate-600">
              {scope.context.map((item) => <li key={item} className="flex gap-2"><span className="text-slate-400">•</span><span>{item}</span></li>)}
            </ul>
          </div>
        </div>
      </section>
      <ChangeMarkerOverlay enabled={markersVisible} />
    </>
  );
}