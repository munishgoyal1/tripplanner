import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { CircleDot, Eye, EyeOff, LockKeyhole } from "lucide-react";
import { allLabs, effectiveLabDisposition, type LabDisposition } from "./labRecords";
import { useLabSelections } from "./useLabSelections";

interface ScopeDefinition {
  changes: string[];
  context: string[];
}

const scopes: Record<string, ScopeDefinition> = {
  "profile-preferences": {
    changes: [
      "The complete Profile and About me information architecture, including durable preferences, personal context, and identity details",
      "Whether preference categories are edited as visible tags, a guided sequence, or a searchable command surface",
      "How each friendly tag maps to a stable internal key and value such as trip_pace: balanced, see_it_all, or relaxed",
      "The balance between quick selection, optional notes, confidence, and a clear saved state",
    ],
    context: [
      "The existing profile persistence contract, authenticated account boundary, and production settings route",
      "The planner's preference application and agent prompt assembly; this Lab visualizes the contract but does not change runtime behavior",
      "Travel documents, analytics, privacy controls, sign-in, trip selection, and the rest of the workspace",
    ],
  },
  "localization": {
    changes: [
      "Where country, interface language, display currency, date/time, week-start, distance, and temperature preferences are first confirmed and later changed",
      "Whether the workspace exposes a persistent locale control, keeps it in Account settings, or adds a per-trip display-currency lens",
      "How converted prices retain provider currency, exchange-rate source, and checked time instead of implying the provider will charge the display amount",
      "Regional practical content: Indian digit grouping, taxes and mandatory fees, tipping and service, driving side, address and phone formats, public holidays, transport conventions, and local booking cut-offs",
      "Four fixed stress cases: Rajasthan in INR, the US Pacific Coast in USD, Scotland in GBP, and Amsterdam–Brussels–Paris in EUR",
    ],
    context: [
      "English interface copy is the only implemented language in this Lab; the selector establishes a future contract and does not pretend translations exist",
      "The itinerary choices, provider quotes, stored source currency, and trip totals are fixed; formatting may change but source data never does",
      "Passport, visa, entry, and document rules depend on traveler citizenship/residency and destination, never on the selected interface country",
      "Live foreign-exchange services, translation infrastructure, provider checkout behavior, geolocation, and production preference persistence",
    ],
  },
  "product-themes": {
    changes: [
      "Colour tokens: page, surface, text, border, action, evidence, and signal colours",
      "Typography: the display and body families used to express each visual direction",
      "Surface treatment and contrast, applied consistently across the public entry, workspace, and mobile specimens",
    ],
    context: [
      "The exact production landing component, including its copy, hierarchy, replay, progress, inline decisions, totals, and evidence sections",
      "Plan mine, Skip to the app, reset, overrule, and undo behavior; every theme renders the same controls in the same places",
      "The Lisbon and Porto fixture, content order, responsive behavior, and the workspace and mobile product functionality",
    ],
  },
  "live-plan": {
    changes: [
      "What a first-time visitor is asked to do while the planner works: watch it, read it, replace it, or argue with it",
      "The primary call to action, which currently reads as a move in a game rather than an action on your own trip",
      "Whether the demo trip exists at all, or whether the hero is bound to a destination you choose",
      "Whether the stream shows activity or judgement — and whether a judgement can be overruled before you have an account",
      "How complete the demo plan has to be to convince: two cities, two hotels, and flight, rail, road and tram all compared",
      "How the run reports its own progress, so an unfinished plan is never mistaken for a broken one",
    ],
    context: [
      "The decision to prove the product by planning in front of the visitor, which Lab 21 settled and this Lab assumes",
      "The rest of the public edge — destination pages, pricing, legal — beyond the three surfaces shown here",
      "The workspace itself, which begins after this Lab ends",
      "Real authentication, provider search, live pricing, and the rate limiting that option C would genuinely require",
    ],
  },
  "first-visit": {
    changes: [
      "What the root URL is: an explanation and an entry point, instead of the empty workspace it boots today",
      "The order of the first screen — ask, prove, interview, or perform — and which of the product's two claims it makes visible first",
      "The forty seconds after Plan is pressed: a durable guest trip URL, streaming reasoning, and a stated expiry",
      "Where the account is asked for, what it adopts, and what a visitor loses by refusing",
      "The shared trip: a public read-only plan page and the link preview a message app renders for it",
    ],
    context: [
      "The Lisbon fixture plan, its prices, sources and savings, which are identical in all four options",
      "The workspace itself — itinerary, map, details, assistant — which begins after this Lab ends",
      "Real authentication, provider search, live pricing, SEO tooling, and server-side rendering mechanics",
      "Pricing and plan tiers beyond the one honest line that the beta is free",
    ],
  },
  "travel-documents": {
    changes: [
      "Where travel documents live: inside the trip, on the account, or in one intake queue that routes items afterwards",
      "How a document is captured — the read, extract, confirm-each-field, save sequence — and how plainly it says the original file is discarded",
      "How the trip reports paperwork readiness: the blockers it names, the rule it cites, and how much surface that costs when nothing is wrong",
      "How stored details are reused on the next trip, corrected, and deleted, and how they behave in an export",
    ],
    context: [
      "The retention rule itself: fields are kept, document numbers are kept masked, the original file is never stored. Every option obeys it",
      "The Lisbon fixture trip, its travellers, and the deterministic checks, which are identical across options",
      "Itinerary, Map, and Details pane design, extraction accuracy, provider search, and server-side persistence",
    ],
  },
  "agentic-planning": {
    changes: [
      "Where the authority to write the trip lives: a deterministic plan engine that owns placement, validation, and persistence, with the model reduced to intent in and explanation out",
      "What a change owes the owner before and after it lands: a chosen slot with its reasons, the slots ruled out, a declared blast radius, and a reversible receipt",
      "How much autonomy the agent keeps for safe edits versus where it must stop and ask",
      "That every channel — chat, map, itinerary, and details — issues the same typed operation and receives the same verdict",
    ],
    context: [
      "The trip data model, the LangGraph agent's phases and tool set, and the model's ability to converse and rank preferences",
      "Visual design of the itinerary, map, and details panes, which appear here only as production-scale context",
      "Provider search, geocoding, booking handoff, and server-side persistence",
    ],
  },
  "itinerary-canvas": {
    changes: [
      "The visual hierarchy of a stop row: which of its facts are loud, which are quiet chips, and which open in place",
      "How a day announces itself, and whether its schedule, route, weather, and readiness read as one header or a stack of lines",
      "How the trip header presents cost, readiness, weather, packing, constraints, and budget without owning half the pane",
    ],
    context: [
      "Every production fact on a stop, a day, and the trip; each option must retain all of them",
      "Map, Details, and Assistant panes, the toolbar, persisted stop order, booking state, and itinerary mutation logic",
    ],
  },
  "map-canvas": {
    changes: [
      "Where day scope, place search, stop type, target day, and Add live relative to the map surface",
      "How much of the pane is geography once controls, day facts, and the selected-pin card are placed",
      "Whether the map also carries the day's stop sequence, times, and travel legs",
    ],
    context: [
      "Route colour, marker numbering, and day identity, which must keep matching the itinerary pane",
      "Google Maps implementation, provider search, geocoding, place data, and trip mutation behavior",
    ],
  },
  "chat-agent-workspace": {
    changes: [
      "Where the Assistant lives in the workspace, what it costs the other panels at rest, and how it is opened or dismissed",
      "How one turn presents its question, its answer, the time that answer took, and the stops it changed",
      "How a whole planning session is navigated, grouped, and read without losing the reader's scroll position",
    ],
    context: [
      "Itinerary, Map, and Details content design, their fixture trip, and their independent Hide and Maximize behavior",
      "The trip agent, its tools and phases, the SSE contract, and server-side transcript persistence",
    ],
  },
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
      "The command-bar trigger or triggers and the complete Profile and Sign-in, Travel Profile, Analytics, and Privacy and Data destinations",
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

const statusPresentation: Record<LabDisposition, { label: string; className: string }> = {
  ready: { label: "In progress", className: "bg-orange-50 text-orange-800 ring-orange-200" },
  "implemented-review": { label: "Implemented - To be reviewed", className: "bg-sky-50 text-sky-800 ring-sky-200" },
  parked: { label: "Parked", className: "bg-amber-50 text-amber-800 ring-amber-200" },
  completed: { label: "Completed", className: "bg-emerald-50 text-emerald-800 ring-emerald-200" },
  discarded: { label: "Discarded", className: "bg-slate-100 text-slate-600 ring-slate-200" },
};

function formatStatusDate(value: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(value));
}

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
  const lab = allLabs.find((candidate) => candidate.id === labId);
  const { selections, status: selectionStatus } = useLabSelections();
  const selection = selections[labId];
  const disposition = lab ? effectiveLabDisposition(lab, selection) : undefined;
  const status = disposition ? statusPresentation[disposition] : undefined;
  const statusDate = selection?.stateChangedAt || selection?.updatedAt || lab?.defaultStateChangedAt;
  const [markersVisible, setMarkersVisible] = useState(() => localStorage.getItem(MARKERS_KEY) !== "hidden");
  if (!scope || !lab) return null;

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
            <p className="text-[10px] font-bold uppercase text-brand">Lab #{lab.labNumber} · Change scope</p>
            <h2 id={`${labId}-scope-title`} className="mt-0.5 text-sm font-semibold text-ink">What this Lab is deciding</h2>
            <p className="mt-1 text-xs leading-relaxed text-slate-500">Only the items under Changes vary between options. The rest of the preview is fixed context and is not part of this decision.</p>
          </div>
          <div className="flex shrink-0 flex-col items-end gap-2">
            <div className="text-right" aria-live="polite">
              <p className="text-[10px] font-bold uppercase text-slate-400">Lab status</p>
              {selectionStatus === "loading" && <span className="mt-1 inline-flex rounded-full bg-slate-50 px-2.5 py-1 text-xs font-bold text-slate-500 ring-1 ring-slate-200">Loading status...</span>}
              {selectionStatus === "error" && <span className="mt-1 inline-flex rounded-full bg-rose-50 px-2.5 py-1 text-xs font-bold text-rose-700 ring-1 ring-rose-200">Status unavailable</span>}
              {selectionStatus === "loaded" && (
                <>
                  <span className={`mt-1 inline-flex rounded-full px-2.5 py-1 text-xs font-bold ring-1 ${status?.className || "bg-slate-50 text-slate-600 ring-slate-200"}`}>{status?.label || "In evaluation"}</span>
                  {statusDate && <p className="mt-1 text-[10px] text-slate-400">Since {formatStatusDate(statusDate)}</p>}
                </>
              )}
            </div>
            <button type="button" aria-pressed={markersVisible} onClick={toggleMarkers} className="btn-ghost">
              {markersVisible ? <EyeOff size={14} aria-hidden /> : <Eye size={14} aria-hidden />}
              {markersVisible ? "Hide change markers" : "Show change markers"}
            </button>
          </div>
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