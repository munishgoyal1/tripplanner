import {
  Bus,
  Building2,
  Camera,
  ChevronDown,
  CircleUserRound,
  Download,
  List,
  Map as MapIcon,
  MessageCircle,
  PanelRight,
  Plane,
  Plus,
  Settings2,
  Sparkles,
  UtensilsCrossed,
} from "lucide-react";
import type { ReactNode } from "react";
import type { StopKind } from "./tripFixture";
import { bookingTotals, trip } from "./tripFixture";

export const kindMeta: Record<StopKind, { Icon: typeof Camera; label: string }> = {
  hotel: { Icon: Building2, label: "Stay" },
  attraction: { Icon: Camera, label: "Place" },
  meal: { Icon: UtensilsCrossed, label: "Food" },
  transport: { Icon: Bus, label: "Transfer" },
  flight: { Icon: Plane, label: "Flight" },
  airport: { Icon: Plane, label: "Airport" },
};

const panes = [
  { id: "itinerary", label: "Itinerary", Icon: List },
  { id: "map", label: "Map", Icon: MapIcon },
  { id: "details", label: "Details", Icon: PanelRight },
  { id: "assistant", label: "Assistant", Icon: MessageCircle },
];

function DetailsRail() {
  return (
    <aside
      className="flex min-h-0 flex-col overflow-y-auto border-l border-[#dce2df] bg-white max-lg:hidden"
      aria-label="Details"
    >
      <div className="border-b border-slate-200 px-4 py-2.5">
        <p className="text-[10px] font-bold uppercase text-slate-500">Details</p>
      </div>
      <div className="p-4">
        <div
          className="h-28 w-full rounded-2xl"
          style={{ background: "linear-gradient(135deg,#fde7ea 0%,#f7d7c6 45%,#cfe6e2 100%)" }}
          aria-hidden
        />
        <h3 className="display mt-3 text-lg font-semibold text-ink">Jerónimos Monastery</h3>
        <p className="mt-0.5 text-xs text-slate-500">Praça do Império 1400-206 Lisboa</p>
        <div className="mt-2 flex flex-wrap gap-1">
          <span className="chip">★ 4.7 · 61.3K reviews</span>
          <span className="chip">€12</span>
          <span className="chip">10:00 – 17:30</span>
        </div>
        <p className="mt-3 text-xs leading-relaxed text-slate-600">
          The cloister queue is shortest before 10:30 and worst after 12:00. Entry is included in
          the Lisboa Card you already hold.
        </p>
        <div className="mt-3 flex flex-wrap gap-1.5">
          <button type="button" className="btn-primary h-8 px-3 text-xs">Confirm booking</button>
          <button type="button" className="btn-ghost h-8 px-3 text-xs">Move day</button>
        </div>
      </div>
    </aside>
  );
}

interface WorkspaceFrameProps {
  itinerary: ReactNode;
  map: ReactNode;
  /** Widen the pane under evaluation so the option is judged at a real working size. */
  emphasis?: "itinerary" | "map";
  showDetails?: boolean;
  className?: string;
}

/**
 * Production-scale planner shell. Both canvas Labs render their option inside this
 * frame so an option is judged next to the toolbar, sibling panes, and Assistant it
 * will actually ship with.
 */
export function WorkspaceFrame({
  itinerary,
  map,
  emphasis = "itinerary",
  showDetails = true,
  className = "",
}: WorkspaceFrameProps) {
  const columns = showDetails
    ? emphasis === "itinerary"
      ? "lg:grid-cols-[minmax(20rem,32%)_minmax(0,1fr)_minmax(15rem,22%)]"
      : "lg:grid-cols-[minmax(16rem,22%)_minmax(0,1fr)_minmax(15rem,22%)]"
    : emphasis === "itinerary"
      ? "lg:grid-cols-[minmax(20rem,36%)_minmax(0,1fr)]"
      : "lg:grid-cols-[minmax(16rem,24%)_minmax(0,1fr)]";

  return (
    <div className={`relative flex h-full min-h-0 flex-col overflow-hidden bg-[#eef1ef] ${className}`}>
      <header className="relative z-30 flex h-12 shrink-0 items-center gap-2 border-b border-[#dce2df] bg-[#fbfcfb]/95 px-3 shadow-[0_1px_4px_rgba(23,36,51,.06)] backdrop-blur">
        <button
          type="button"
          className="inline-flex h-8 shrink-0 items-center gap-2 rounded-md border border-[#d6ddda] bg-white px-2.5 text-xs font-semibold text-ink shadow-sm"
        >
          {trip.destination} · 8–13 Oct
          <ChevronDown size={13} aria-hidden />
        </button>
        <span className="mx-1 hidden h-5 w-px shrink-0 bg-slate-200 sm:block" aria-hidden />
        <span className="hidden truncate text-[11px] font-medium text-accent lg:inline">
          Saved · {bookingTotals.booked} of {bookingTotals.stops} bookings ready
        </span>
        <nav className="ml-auto flex shrink-0 items-center gap-1" aria-label="Workspace controls">
          <button
            type="button"
            className="inline-flex h-8 items-center gap-1.5 rounded-md bg-brand/10 px-3 text-xs font-semibold text-brand"
          >
            <Plus size={14} aria-hidden />
            <span className="hidden sm:inline">New trip</span>
          </button>
          <span className="mx-1 h-5 w-px bg-slate-200" aria-hidden />
          {panes.map(({ id, label, Icon }) => (
            <button
              key={id}
              type="button"
              aria-pressed={id !== "assistant"}
              title={label}
              className={`inline-flex h-8 items-center justify-center gap-1.5 rounded-md px-2.5 text-xs font-semibold transition ${
                id === "assistant"
                  ? "text-slate-400 hover:bg-slate-50 hover:text-slate-600"
                  : "bg-slate-100 text-slate-600"
              }`}
            >
              <Icon size={15} aria-hidden />
              <span className="hidden xl:inline">{label}</span>
            </button>
          ))}
          <span className="mx-1 h-5 w-px bg-slate-200" aria-hidden />
          <button type="button" title="Export" className="grid h-8 w-8 place-items-center rounded-md text-slate-400 hover:bg-slate-50 hover:text-slate-600">
            <Download size={15} aria-hidden />
          </button>
          <button type="button" title="Preferences" className="grid h-8 w-8 place-items-center rounded-md text-slate-400 hover:bg-slate-50 hover:text-slate-600">
            <Settings2 size={15} aria-hidden />
          </button>
          <button type="button" title="Account" className="grid h-8 w-8 place-items-center rounded-md text-slate-400 hover:bg-slate-50 hover:text-slate-600">
            <CircleUserRound size={16} aria-hidden />
          </button>
        </nav>
      </header>

      <div className={`grid min-h-0 flex-1 grid-cols-1 ${columns}`}>
        <section className="min-h-0 overflow-hidden border-r border-[#dce2df] bg-white" aria-label="Itinerary">
          {itinerary}
        </section>
        <section className="relative min-h-0 overflow-hidden max-lg:hidden" aria-label="Map">
          {map}
        </section>
        {showDetails && <DetailsRail />}
      </div>

      <button
        type="button"
        className="absolute bottom-4 right-4 z-40 inline-flex h-10 items-center gap-2 rounded-full bg-ink px-4 text-xs font-semibold text-white shadow-pop"
      >
        <Sparkles size={14} aria-hidden />
        Ask the planner
      </button>
    </div>
  );
}
