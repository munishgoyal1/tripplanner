import { useState } from "react";
import { CarFront, EyeOff, Map, MessageSquare, PanelsTopLeft, Plane, Route, SlidersHorizontal, TrainFront } from "lucide-react";
import { JourneyMap } from "./JourneyMap";
import { legsWithin, type Scenario, type VariantId } from "./scenarios";

const modeIcon = { road: CarFront, rail: TrainFront, flight: Plane, local: Route } as const;

function CommandBar({ scenario }: { scenario: Scenario }) {
  return (
    <header className="flex h-11 shrink-0 items-center gap-2 border-b border-slate-200 bg-white px-3">
      <span className="text-[10px] font-bold uppercase text-brand">Rajasthan · 8 days</span>
      <span className="h-5 border-l border-slate-200" />
      <span className="text-xs font-semibold text-ink">{scenario.day}</span>
      <span className="truncate text-[11px] text-slate-500">{scenario.route}</span>
      <div className="ml-auto flex items-center gap-1">
        {[
          { label: "Itinerary", icon: PanelsTopLeft },
          { label: "Map", icon: Map },
          { label: "Details", icon: SlidersHorizontal },
          { label: "Assistant", icon: MessageSquare },
        ].map(({ label, icon: Icon }) => (
          <span
            key={label}
            className={`inline-flex h-7 items-center gap-1.5 rounded-sm px-2 text-[11px] font-semibold ${
              label === "Map" ? "bg-slate-100 text-ink" : "text-slate-500"
            }`}
          >
            <Icon size={12} aria-hidden />
            {label}
          </span>
        ))}
      </div>
    </header>
  );
}

function ItineraryRail({ scenario, visibleIds }: { scenario: Scenario; visibleIds: string[] }) {
  return (
    <aside className="hidden min-h-0 overflow-y-auto border-r border-slate-200 bg-white lg:block">
      <div className="border-b border-slate-100 px-3 py-2.5">
        <p className="text-[9px] font-bold uppercase text-slate-400">Itinerary · persisted order</p>
        <h3 className="mt-0.5 text-sm font-semibold text-ink">{scenario.day}</h3>
        <p className="mt-1 text-[10px] leading-relaxed text-slate-500">{scenario.summary}</p>
      </div>
      <ul>
        {scenario.nodes.map((node) => {
          const onMap = visibleIds.includes(node.id);
          return (
            <li key={node.id} className={`border-b border-slate-100 px-3 py-2 ${onMap ? "" : "bg-rose-50/40"}`}>
              <div className="flex items-start gap-2">
                <span
                  className={`mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full text-[9px] font-bold ${
                    node.kind === "hotel"
                      ? "bg-brand text-white"
                      : node.kind === "terminal"
                        ? "bg-sky-100 text-sky-700"
                        : "bg-slate-100 text-slate-600"
                  }`}
                >
                  {node.marker}
                </span>
                <div className="min-w-0">
                  <p className="text-[11px] font-semibold leading-tight text-ink">{node.name}</p>
                  <p className="text-[10px] leading-tight text-slate-500">
                    {node.time} · {node.detail}
                  </p>
                  {!onMap && (
                    <p className="mt-1 inline-flex items-center gap-1 rounded-sm bg-rose-100 px-1.5 py-0.5 text-[9px] font-bold text-rose-700">
                      <EyeOff size={9} aria-hidden /> Not on the map
                    </p>
                  )}
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}

function RouteRail({ scenario, visibleIds, visibleLegCount, note }: { scenario: Scenario; visibleIds: string[]; visibleLegCount: number; note: string }) {
  return (
    <aside className="hidden min-h-0 overflow-y-auto border-l border-slate-200 bg-white xl:block">
      <div className="border-b border-slate-100 px-3 py-2.5">
        <p className="text-[9px] font-bold uppercase text-slate-400">Selected day route</p>
        <h3 className="mt-0.5 text-sm font-semibold text-ink">{scenario.travel.label}</h3>
      </div>
      <dl className="divide-y divide-slate-100">
        {[
          ["Duration", scenario.travel.duration],
          ["Distance", scenario.travel.distance],
          ["Stops on map", `${visibleIds.length} of ${scenario.nodes.length}`],
          ["Legs drawn", `${visibleLegCount} of ${scenario.legs.length}`],
        ].map(([label, value]) => (
          <div key={label} className="flex items-baseline justify-between gap-2 px-3 py-2">
            <dt className="text-[10px] font-semibold uppercase text-slate-400">{label}</dt>
            <dd className="text-[11px] font-semibold text-ink">{value}</dd>
          </div>
        ))}
      </dl>
      <div className="border-t border-slate-100 px-3 py-2.5">
        <p className="text-[10px] leading-relaxed text-slate-600">{scenario.travel.detail}</p>
        <p className="mt-2 rounded-sm bg-slate-50 px-2 py-1.5 text-[10px] leading-relaxed text-slate-600">{note}</p>
      </div>
    </aside>
  );
}

function JourneyStrip({ scenario }: { scenario: Scenario }) {
  const first = scenario.nodes[0];
  const last = scenario.nodes[scenario.nodes.length - 1];
  const Icon = modeIcon[scenario.legs.find((leg) => leg.mode !== "local")?.mode ?? "local"];
  return (
    <div
      data-lab-change="Pinned inter-city journey strip"
      className="grid shrink-0 grid-cols-[1fr_auto_1fr] items-center gap-2 border-b border-slate-200 bg-white px-3 py-2"
    >
      <div className="min-w-0">
        <p className="text-[9px] font-bold uppercase text-slate-400">{first.time} · depart</p>
        <p className="truncate text-[11px] font-semibold text-ink">{first.name}</p>
      </div>
      <div className="min-w-36 text-center">
        <Icon size={14} className="mx-auto text-brand" aria-hidden />
        <p className="mt-0.5 text-[9px] font-bold text-ink">
          {scenario.travel.duration} · {scenario.travel.distance}
        </p>
        <div className="mt-1 h-px bg-brand" />
      </div>
      <div className="min-w-0 text-right">
        <p className="text-[9px] font-bold uppercase text-slate-400">{last.time} · arrive</p>
        <p className="truncate text-[11px] font-semibold text-ink">{last.name}</p>
      </div>
    </div>
  );
}

interface WorkspaceProps {
  scenario: Scenario;
  variant: VariantId;
  view: "baseline" | "option";
  height?: string;
}

export function IntercityWorkspace({ scenario, variant, view, height = "h-[34rem]" }: WorkspaceProps) {
  const [localVisible, setLocalVisible] = useState(true);
  const [intercityVisible, setIntercityVisible] = useState(true);

  const baseline = view === "baseline";
  // The ordinary-day guard has no inter-city leg: every option must leave it exactly as it is today.
  const inert = !scenario.legs.some((leg) => leg.mode !== "local");
  const layered = !baseline && !inert && variant === "layer-toggle";
  const strip = !baseline && !inert && variant === "journey-strip";

  let visibleIds: string[];
  if (baseline || inert) {
    visibleIds = scenario.baselineNodeIds;
  } else if (strip) {
    visibleIds = scenario.nodes.filter((node) => node.side === "destination").map((node) => node.id);
  } else if (layered) {
    const activeLegs = scenario.legs.filter((leg) =>
      leg.mode === "local" ? localVisible : intercityVisible,
    );
    const fromLegs = new Set(activeLegs.flatMap((leg) => [leg.from, leg.to]));
    visibleIds = scenario.nodes
      .filter((node) => {
        // Terminals belong to the inter-city journey, so they follow that layer rather than staying behind.
        if (node.kind === "terminal") return intercityVisible;
        return node.kind === "hotel" || fromLegs.has(node.id);
      })
      .map((node) => node.id);
  } else {
    visibleIds = scenario.nodes.map((node) => node.id);
  }

  const nodes = scenario.nodes.filter((node) => visibleIds.includes(node.id));
  const legs = legsWithin(scenario, visibleIds).filter((leg) =>
    layered ? (leg.mode === "local" ? localVisible : intercityVisible) : true,
  );

  const caption = inert
    ? "Ordinary sightseeing day · identical before and after this Lab"
    : baseline
      ? "Today in production · transfer geometry removed"
      : `${variant === "full-journey" ? "Complete connected day journey" : variant === "journey-strip" ? "Destination-local map" : "Dual-scale map with route layers"} · mock geometry, production focus semantics`;

  const note = baseline ? scenario.baselineNote : scenario.afterNote;

  return (
    <div className={`flex ${height} min-h-0 flex-col overflow-hidden bg-white`}>
      <CommandBar scenario={scenario} />
      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[15rem_minmax(0,1fr)] xl:grid-cols-[15rem_minmax(0,1fr)_14rem]">
        <ItineraryRail scenario={scenario} visibleIds={visibleIds} />
        <section className="flex min-h-0 min-w-0 flex-col">
          {strip && <JourneyStrip scenario={scenario} />}
          {layered && (
            <div
              data-lab-change="Independent route-layer controls"
              className="flex shrink-0 items-center gap-3 border-b border-slate-200 bg-white px-3 py-2"
            >
              <p className="mr-auto text-[11px] font-semibold text-ink">Route layers</p>
              <label className="inline-flex items-center gap-1.5 text-[10px] font-semibold text-slate-600">
                <input type="checkbox" checked={localVisible} onChange={(event) => setLocalVisible(event.target.checked)} /> Local plans
              </label>
              <label className="inline-flex items-center gap-1.5 text-[10px] font-semibold text-slate-600">
                <input type="checkbox" checked={intercityVisible} onChange={(event) => setIntercityVisible(event.target.checked)} /> Inter-city travel
              </label>
            </div>
          )}
          <div className="min-h-0 flex-1" data-lab-change={baseline || inert ? undefined : "Transfer-day map geometry and framing"}>
            <JourneyMap
              nodes={nodes}
              legs={legs}
              height="h-full"
              fit={baseline || inert || variant === "full-journey" ? scenario.fit : undefined}
              fitLabel={baseline && !inert ? "Today's fit" : "Selected-day fit"}
              caption={caption}
              muted={baseline && !inert}
            />
          </div>
        </section>
        <RouteRail scenario={scenario} visibleIds={visibleIds} visibleLegCount={legs.length} note={note} />
      </div>
    </div>
  );
}
