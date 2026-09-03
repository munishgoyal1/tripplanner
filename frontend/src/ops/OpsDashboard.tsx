import { useEffect, useState, type ReactNode } from "react";
import {
  Activity,
  AlertTriangle,
  Bot,
  Boxes,
  Clock3,
  Database,
  DollarSign,
  Gauge,
  Globe2,
  MapPin,
  MessageSquare,
  PlaneTakeoff,
  RefreshCw,
  Server,
  Split,
  Users,
  Workflow,
  Wrench,
} from "lucide-react";
import { fetchOpsOverview, type OpsOverview } from "../api";

const number = new Intl.NumberFormat("en-US");
const compact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });
const labels: Record<string, string> = {
  page_view: "Visits",
  planning_started: "Planning started",
  trip_created: "Trips created",
  planning_completed: "Itineraries completed",
  new_trip_started: "New trip started",
  trip_reset: "Trip reset",
  login: "Sign-ins",
  place_added: "Places added",
  place_removed: "Places removed",
  trip_shared: "Trips shared",
  itinerary_exported: "Itineraries exported",
  calendar_exported: "Calendar exports",
  shared_trip_imported: "Shared trips imported",
  planning_failed: "Planning failed",
  planning_abandoned: "Planning started, not completed",
  page_only: "Visit only",
};

function duration(value: number): string {
  if (value < 1000) return `${Math.round(value)} ms`;
  return `${(value / 1000).toFixed(1)} s`;
}

function elapsed(value: number): string {
  if (value < 60) return `${Math.round(value)} sec`;
  if (value < 3600) return `${Math.round(value / 60)} min`;
  return `${(value / 3600).toFixed(1)} hr`;
}

function bytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function Metric({ label, value, detail, icon: Icon }: {
  label: string;
  value: string;
  detail: string;
  icon: typeof Activity;
}) {
  return (
    <div className="min-w-0 border-l border-stone-200 px-4 first:border-l-0">
      <div className="flex items-center gap-2 text-xs font-semibold uppercase text-stone-500">
        <Icon size={14} aria-hidden /> {label}
      </div>
      <div className="mt-2 font-display text-3xl text-stone-950">{value}</div>
      <div className="mt-1 text-xs text-stone-500">{detail}</div>
    </div>
  );
}

function Panel({ title, note, children }: { title: string; note?: string; children: ReactNode }) {
  return (
    <section className="min-w-0 border border-stone-300 bg-white">
      <div className="flex items-center justify-between gap-4 border-b border-stone-200 px-5 py-4">
        <h2 className="font-display text-lg">{title}</h2>
        {note && <span className="text-right text-xs text-stone-500">{note}</span>}
      </div>
      {children}
    </section>
  );
}

function Empty({ children }: { children: ReactNode }) {
  return <p className="px-5 py-8 text-center text-sm text-stone-500">{children}</p>;
}

const initiatorLabels: Record<string, string> = {
  user_trip: "User trip building",
  user_action: "User action outside planning",
  audit: "Audit and validation",
  agent_background: "Agent background work",
  automation: "Automation",
  unattributed: "Unattributed",
};

const serviceLabels: Record<string, string> = {
  azure_openai: "Azure OpenAI",
  google_places: "Google Places",
  google_routes: "Google Routes",
  google_maps: "Google Maps",
};

const datasetLabels: Record<string, string> = {
  places_search: "Places search and discovery",
  places_details_reviews_hours: "Place details, reviews, and hours",
  places_photos: "Place photos",
  routes: "Routes",
  static_maps: "Static maps",
  llm_completion: "LLM completions",
};

function estimatedCost(cost: number, unknown: number): string {
  const value = `$${cost.toFixed(cost < 0.01 ? 4 : 2)}`;
  return unknown ? `${value} + ${unknown} unknown` : value;
}

function DateRangeControl({ overview, days, startDate, endDate, onPreset, onStartDate, onEndDate }: {
  overview: OpsOverview;
  days: number;
  startDate: string;
  endDate: string;
  onPreset: (days: number) => void;
  onStartDate: (value: string) => void;
  onEndDate: (value: string) => void;
}) {
  const today = new Date().toISOString().slice(0, 10);
  const startMax = endDate && endDate < today ? endDate : today;
  return <section className="mb-6 flex flex-wrap items-end justify-between gap-4 border border-stone-300 bg-white px-5 py-4" aria-label="Reporting period">
    <div><p className="text-xs font-semibold uppercase text-stone-500">Reporting period</p><p className="mt-1 text-sm font-semibold">{overview.reporting_period.start_date} to {overview.reporting_period.end_date}</p></div>
    <div className="flex flex-wrap items-end gap-3">
      <div className="flex border border-stone-300">{[7, 30, 90].map((period) => <button key={period} type="button" className={`px-3 py-2 text-sm ${!startDate && !endDate && days === period ? "bg-stone-900 text-white" : "hover:bg-stone-100"}`} onClick={() => onPreset(period)}>{period}d</button>)}</div>
      <label className="text-xs font-semibold text-stone-600">From<input type="date" value={startDate} max={startMax} onChange={(event) => onStartDate(event.target.value)} className="mt-1 block border border-stone-300 bg-white px-2 py-1.5 font-normal" /></label>
      <label className="text-xs font-semibold text-stone-600">To<input type="date" value={endDate} min={startDate || undefined} max={today} onChange={(event) => onEndDate(event.target.value)} className="mt-1 block border border-stone-300 bg-white px-2 py-1.5 font-normal" /></label>
    </div>
  </section>;
}

function TripCostSection({ overview, kind, title, note }: {
  overview: OpsOverview;
  kind: "new_trip" | "trip_update";
  title: string;
  note: string;
}) {
  const usage = overview.provider_usage;
  const category = usage.trip_costs[kind];
  const trips = usage.by_trip.filter((row) => row.interaction_kind === kind);

  return <section className="mt-8">
    <div className="mb-3 flex flex-wrap items-end justify-between gap-3 border-b border-stone-300 pb-3">
      <div><h2 className="font-serif text-2xl text-stone-950">{title}</h2><p className="mt-1 text-sm text-stone-500">{note}</p></div>
      <div className="flex gap-6 text-right text-sm">
        <div><p className="text-xs uppercase text-stone-500">Average per {kind === "new_trip" ? "trip" : "update"}</p><p className="mt-1 font-semibold">{estimatedCost(category.average_estimated_cost_usd, 0)}</p><p className="mt-1 text-xs text-stone-500">{category.unknown_cost_interactions} include unknown prices</p></div>
        <div><p className="text-xs uppercase text-stone-500">Cumulative</p><p className="mt-1 font-semibold">{estimatedCost(category.estimated_cost_usd, category.unknown_cost_interactions)}</p></div>
      </div>
    </div>
    <Panel title={`${title} by trip`} note={`${category.interactions} measured ${category.interactions === 1 ? "interaction" : "interactions"} across ${category.trips} trips`}>
      {trips.length ? <div className="divide-y divide-stone-200">{trips.map((trip) => {
        const interactions = usage.by_interaction.filter((row) => row.interaction_kind === kind && row.trip_id === trip.trip_id && row.environment === trip.environment && row.initiator === trip.initiator);
        const tripLabel = trip.trip_name || (trip.trip_id !== "unattributed" ? trip.trip_id : "Trip not yet saved");
        return <details key={`${kind}-${trip.environment}-${trip.initiator}-${trip.trip_id}`} className="group">
          <summary className="grid cursor-pointer list-none grid-cols-[minmax(0,1fr)_auto] gap-4 px-5 py-4 text-sm hover:bg-stone-50">
            <div className="min-w-0"><p className="truncate font-semibold">{tripLabel}</p><p className="mt-1 truncate font-mono text-xs text-stone-500">{trip.trip_id === "unattributed" ? "Not tied to a saved trip" : trip.trip_id}</p></div>
            <div className="text-right"><p>{estimatedCost(trip.estimated_cost_usd, trip.unknown_cost_calls)}</p><p className="mt-1 text-xs text-stone-500">{trip.calls} provider · {trip.cache_hits ?? 0} cache · ${trip.estimated_savings_usd.toFixed(4)} saved</p></div>
          </summary>
          <div className="border-t border-stone-100 bg-stone-50 px-5 py-3">
            {interactions.map((interaction, index) => {
              const providers = usage.by_provider.filter((row) => row.interaction_id === interaction.interaction_id && row.interaction_kind === kind && row.trip_id === interaction.trip_id && row.environment === interaction.environment && row.initiator === interaction.initiator);
              return <details key={`${interaction.environment}-${interaction.initiator}-${interaction.trip_id}-${interaction.interaction_id}`} className="border-b border-stone-200 last:border-b-0">
                <summary className="grid cursor-pointer list-none grid-cols-[minmax(0,1fr)_auto] gap-3 py-3 text-sm">
                  <span className="font-semibold">{kind === "new_trip" ? "Creation request" : `Update ${index + 1}`}</span>
                  <span>{interaction.calls} provider · {interaction.cache_hits ?? 0} cache · {estimatedCost(interaction.estimated_cost_usd, interaction.unknown_cost_calls)}</span>
                </summary>
                <div className="pb-4 pl-3">
                  {providers.map((provider) => {
                    const operations = usage.by_operation.filter((row) => row.interaction_id === interaction.interaction_id && row.provider === provider.provider && row.trip_id === interaction.trip_id && row.environment === interaction.environment && row.initiator === interaction.initiator && row.interaction_kind === kind);
                    return <div key={`${provider.environment}-${provider.initiator}-${provider.trip_id}-${provider.interaction_id}-${provider.provider}`} className="border-t border-stone-200 py-3 first:border-t-0">
                      <div className="flex justify-between gap-4 text-sm"><strong>{provider.provider}</strong><span>{estimatedCost(provider.estimated_cost_usd, provider.unknown_cost_calls)}</span></div>
                      {operations.map((operation) => <div key={`${operation.operation}-${operation.sku_class}`} className="mt-1 grid grid-cols-[minmax(0,1fr)_auto] gap-3 font-mono text-xs text-stone-600"><span className="truncate">{operation.operation} · {operation.sku_class}</span><span>{operation.calls} · {estimatedCost(operation.estimated_cost_usd, operation.unknown_cost_calls)}</span></div>)}
                    </div>;
                  })}
                  <div className="flex justify-between gap-4 border-t border-stone-200 pt-3 text-xs text-stone-500"><span>Shared Azure infrastructure</span><span>Not allocated</span></div>
                </div>
              </details>;
            })}
          </div>
        </details>;
      })}</div> : <Empty>No measured {kind === "new_trip" ? "new-trip creations" : "existing-trip updates"} in this period.</Empty>}
    </Panel>
  </section>;
}

function CostView({ overview, days, startDate, endDate, onPreset, onStartDate, onEndDate }: {
  overview: OpsOverview;
  days: number;
  startDate: string;
  endDate: string;
  onPreset: (days: number) => void;
  onStartDate: (value: string) => void;
  onEndDate: (value: string) => void;
}) {
  const usage = overview.provider_usage;
  const cache = usage.cache_effectiveness;

  return (
    <>
      <DateRangeControl {...{ overview, days, startDate, endDate, onPreset, onStartDate, onEndDate }} />

      <section className="grid gap-y-6 border-y border-stone-300 bg-white py-5 sm:grid-cols-2 xl:grid-cols-5">
        <Metric label="Measured calls" value={number.format(usage.totals.calls)} detail={`${usage.totals.failures} failed · ${usage.totals.avoided_calls} avoided`} icon={Boxes} />
        <Metric label="Cumulative provider cost" value={`$${usage.totals.estimated_cost_usd.toFixed(2)}`} detail="Known catalog prices only" icon={DollarSign} />
        <Metric label="Average new trip" value={estimatedCost(usage.trip_costs.new_trip.average_estimated_cost_usd, 0)} detail={`${usage.trip_costs.new_trip.interactions} measured creations`} icon={PlaneTakeoff} />
        <Metric label="Average trip update" value={estimatedCost(usage.trip_costs.trip_update.average_estimated_cost_usd, 0)} detail={`${usage.trip_costs.trip_update.interactions} measured updates`} icon={Workflow} />
        <Metric label="Unknown price" value={number.format(usage.totals.unknown_cost_calls)} detail="Measured calls, cost unavailable" icon={AlertTriangle} />
      </section>

      <section className="mt-6 border border-amber-300 bg-amber-50 px-5 py-4 text-sm text-amber-950">
        <p className="font-semibold">Cost is an estimate, not a billing statement.</p>
        <p className="mt-1 text-xs">{usage.pricing.basis} Catalog {usage.pricing.catalog_version}. Unknown-price calls remain visible and are excluded from the dollar total.</p>
      </section>

      <div className="mt-6 grid min-w-0 gap-6 xl:grid-cols-2">
        <Panel title="Activity source" note="Environment → initiator">
          {usage.by_initiator.length ? <div className="divide-y divide-stone-100">{usage.by_initiator.map((row) => (
            <div key={`${row.environment}-${row.initiator}`} className="grid grid-cols-[minmax(0,1fr)_auto] gap-4 px-5 py-4 text-sm">
              <div><p className="font-semibold">{initiatorLabels[row.initiator || ""] || row.initiator}</p><p className="mt-1 text-xs uppercase text-stone-500">{row.environment}</p></div>
              <div className="text-right"><p className="font-semibold">{number.format(row.calls)} calls</p><p className="mt-1 text-xs text-stone-500">{estimatedCost(row.estimated_cost_usd, row.unknown_cost_calls)}</p></div>
            </div>
          ))}</div> : <Empty>No provider or model calls recorded in this period.</Empty>}
        </Panel>

        <Panel title="Cumulative provider cost" note="All measured work in this period">
          {usage.by_provider_total.length ? <div className="divide-y divide-stone-100">{usage.by_provider_total.map((row) => <div key={`${row.environment}-${row.provider}`} className="grid grid-cols-[minmax(0,1fr)_auto] gap-4 px-5 py-4 text-sm"><div><p className="font-semibold">{row.provider}</p><p className="mt-1 text-xs uppercase text-stone-500">{row.environment}</p></div><div className="text-right"><p className="font-semibold">{estimatedCost(row.estimated_cost_usd, row.unknown_cost_calls)}</p><p className="mt-1 text-xs text-stone-500">{row.calls} calls</p></div></div>)}</div> : <Empty>No provider costs recorded in this period.</Empty>}
        </Panel>
      </div>
      <div className="mt-6 grid min-w-0 gap-6 xl:grid-cols-2">
        <Panel title="Cumulative cost by service" note="Provider service · selected period">
          {usage.by_service.length ? <div className="divide-y divide-stone-100">{usage.by_service.map((row) => <div key={`${row.environment}-${row.service}`} className="grid grid-cols-[minmax(0,1fr)_auto] gap-4 px-5 py-4 text-sm"><div><p className="font-semibold">{serviceLabels[row.service || ""] || row.service?.replaceAll("_", " ")}</p><p className="mt-1 text-xs uppercase text-stone-500">{row.environment} · {row.calls} provider calls</p></div><div className="text-right"><p className="font-semibold">{estimatedCost(row.estimated_cost_usd, row.unknown_cost_calls)}</p><p className="mt-1 text-xs text-emerald-700">${row.estimated_savings_usd.toFixed(4)} cache savings</p></div></div>)}</div> : <Empty>No service costs recorded in this period.</Empty>}
        </Panel>
        <Panel title="Provider calls vs cache" note={`${cache.requests} measured requests`}>
          <div className="p-5">
            <div className="flex h-4 overflow-hidden bg-stone-100" aria-label={`${Math.round(cache.provider_call_rate * 100)}% provider calls and ${Math.round(cache.cache_hit_rate * 100)}% cache hits`}><div className="bg-amber-500" style={{ width: `${cache.provider_call_rate * 100}%` }} /><div className="bg-emerald-600" style={{ width: `${cache.cache_hit_rate * 100}%` }} /></div>
            <div className="mt-4 grid grid-cols-2 gap-6 text-sm"><div><p className="text-xs uppercase text-stone-500">Provider calls</p><p className="mt-1 font-display text-2xl">{Math.round(cache.provider_call_rate * 100)}%</p><p className="text-xs text-stone-500">{cache.provider_calls} requests reached providers</p></div><div><p className="text-xs uppercase text-stone-500">Cache served</p><p className="mt-1 font-display text-2xl">{Math.round(cache.cache_hit_rate * 100)}%</p><p className="text-xs text-stone-500">{cache.cache_hits} requests · ${cache.estimated_savings_usd.toFixed(4)} estimated saved</p></div></div>
          </div>
        </Panel>
      </div>
      <TripCostSection overview={overview} kind="new_trip" title="New trip creation" note="Cost of producing the first saved itinerary" />
      <TripCostSection overview={overview} kind="trip_update" title="Existing trip updates" note="Cost of each later planning request" />
      <p className="mt-6 text-xs text-stone-500">{usage.trip_costs.infrastructure.basis} Provider estimates above exclude that shared cost.</p>
    </>
  );
}

function BusinessView({ overview, rangeProps }: { overview: OpsOverview; rangeProps: Omit<Parameters<typeof DateRangeControl>[0], "overview"> }) {
  const activities = Object.entries(overview.product.activities).sort(([, a], [, b]) => b - a);
  const countries = Object.entries(overview.product.countries).sort(([, a], [, b]) => b - a);
  const sources = Object.entries(overview.product.sources).sort(([, a], [, b]) => b - a);
  const dropOffs = Object.entries(overview.product.drop_offs).sort(([, a], [, b]) => b - a);
  const funnel = Object.entries(overview.product.funnel);
  const funnelBase = Math.max(overview.product.funnel.page_view, 1);

  return (
    <>
      <DateRangeControl overview={overview} {...rangeProps} />
      <section className="grid gap-y-6 border-y border-stone-300 bg-white py-5 sm:grid-cols-2 xl:grid-cols-5">
        <Metric label="Visitors" value={number.format(overview.business_activity.visitors)} detail="Consented unique visitors" icon={Users} />
        <Metric label="New trips" value={number.format(overview.business_activity.new_trips)} detail="Created in this period" icon={PlaneTakeoff} />
        <Metric label="Trip updates" value={number.format(overview.business_activity.existing_trip_updates)} detail="Turns after first build" icon={Workflow} />
        <Metric label="Chat turns" value={number.format(overview.business_activity.chat_turns)} detail="User turns on saved trips" icon={MessageSquare} />
        <Metric label="Engagement" value={elapsed(overview.product.engagement_seconds)} detail="Current-process active time" icon={Clock3} />
      </section>

      <div className="mt-6">
        <Panel title="Page visits" note="Consented views · selected period">
          {Object.keys(overview.business_activity.page_counts).length ? <div className="grid divide-y divide-stone-100 sm:grid-cols-3 sm:divide-x sm:divide-y-0">{Object.entries(overview.business_activity.page_counts).map(([page, count]) => <div key={page} className="px-5 py-4"><p className="text-xs font-semibold uppercase text-stone-500">{page}</p><p className="mt-2 font-display text-3xl">{number.format(count)}</p></div>)}</div> : <Empty>No consented page views in this period.</Empty>}
        </Panel>
      </div>

      <div className="mt-6 grid min-w-0 gap-6 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <Panel title="Activation funnel" note="Consented sessions · current process">
          <div className="space-y-5 p-5">
            {funnel.map(([stage, count], index) => {
              const conversion = index === 0 ? 100 : (count / funnelBase) * 100;
              return (
                <div key={stage}>
                  <div className="mb-2 flex items-end justify-between gap-3 text-sm">
                    <span className="font-semibold">{labels[stage] || stage}</span>
                    <span className="font-mono text-xs text-stone-600">{count} · {conversion.toFixed(0)}%</span>
                  </div>
                  <div className="h-3 bg-stone-100"><div className="h-full bg-emerald-600" style={{ width: `${Math.max(count ? 3 : 0, conversion)}%` }} /></div>
                </div>
              );
            })}
          </div>
        </Panel>

        <Panel title="Observed drop-off" note="Stage, not inferred intent">
          {dropOffs.length ? <div className="divide-y divide-stone-100">{dropOffs.map(([name, count]) => (
            <div key={name} className="flex items-center justify-between px-5 py-4 text-sm"><span>{labels[name] || name}</span><strong>{count}</strong></div>
          ))}</div> : <Empty>No incomplete consented sessions in this process.</Empty>}
        </Panel>
      </div>

      <div className="mt-6 grid min-w-0 gap-6 xl:grid-cols-3">
        <Panel title="Key interactions" note={`${overview.product.events} events`}>
          {activities.length ? <div className="divide-y divide-stone-100">{activities.map(([name, count]) => (
            <div key={name} className="flex items-center justify-between px-5 py-3 text-sm"><span>{labels[name] || name.replaceAll("_", " ")}</span><strong>{count}</strong></div>
          ))}</div> : <Empty>Product events appear after analytics consent.</Empty>}
        </Panel>
        <Panel title="Acquisition source" note="Category only">
          {sources.length ? <div className="divide-y divide-stone-100">{sources.map(([source, count]) => (
            <div key={source} className="flex items-center justify-between px-5 py-3 text-sm"><span className="capitalize">{source}</span><strong>{count}</strong></div>
          ))}</div> : <Empty>GA4 remains the long-horizon source authority.</Empty>}
        </Panel>
        <Panel title="Country" note="GA4 is authoritative">
          {countries.length ? <div className="divide-y divide-stone-100">{countries.map(([country, count]) => (
            <div key={country} className="flex items-center justify-between px-5 py-3 text-sm"><span className="flex items-center gap-2"><Globe2 size={14} />{country}</span><strong>{count}</strong></div>
          ))}</div> : <Empty>No trusted first-party geo dimension is available.</Empty>}
        </Panel>
      </div>
    </>
  );
}

function TripsView({ overview }: { overview: OpsOverview }) {
  return <>
    <section className="grid gap-y-6 border-y border-stone-300 bg-white py-5 sm:grid-cols-3">
      <Metric label="Trips shown" value={number.format(overview.trip_insights.length)} detail="All persisted user trips" icon={PlaneTakeoff} />
      <Metric label="Iterations" value={number.format(overview.business_activity.existing_trip_updates)} detail="Follow-up user turns" icon={Workflow} />
      <Metric label="Chat turns" value={number.format(overview.business_activity.chat_turns)} detail="Across persisted trip chats" icon={MessageSquare} />
    </section>
    <div className="mt-6">
      <Panel title="Trip interactions" note="One row per persisted user trip">
        <div className="overflow-x-auto"><table className="w-full min-w-[1180px] text-left text-sm"><thead className="bg-stone-50 text-xs uppercase text-stone-500"><tr><th className="px-5 py-3">User ID</th><th>Itinerary</th><th>Places requested</th><th>First build</th><th>Iterations</th><th>Chat turns</th><th>Feedback</th><th>Updated</th></tr></thead><tbody>{overview.trip_insights.map((trip) => <tr key={`${trip.user_id}-${trip.trip_id}`} className="border-t border-stone-100 align-top"><td className="max-w-48 break-all px-5 py-3 font-mono text-xs">{trip.user_id}</td><td className="py-3 pr-4"><p className="font-semibold">{trip.title}</p><p className="mt-1 font-mono text-xs text-stone-500">{trip.trip_id}</p></td><td className="py-3 pr-4"><span className="flex items-center gap-2"><MapPin size={14} />{trip.places_requested || "Not recorded"}</span></td><td className="py-3 pr-4">{trip.first_build_seconds === null ? "Not recorded" : elapsed(trip.first_build_seconds)}</td><td className="py-3 pr-4">{trip.iterations}</td><td className="py-3 pr-4">{trip.chat_turns}</td><td className="max-w-80 whitespace-normal py-3 pr-4">{trip.feedback || "No feedback"}</td><td className="whitespace-nowrap py-3 pr-5 text-xs text-stone-500">{trip.updated_at ? new Date(trip.updated_at).toLocaleString() : "Unknown"}</td></tr>)}</tbody></table>{!overview.trip_insights.length && <Empty>No saved trips were created or updated in this period.</Empty>}</div>
      </Panel>
    </div>
  </>;
}

function InfraView({ overview }: { overview: OpsOverview }) {
  const cosmos = overview.infra.cosmos;
  return <>
    <section className="grid gap-y-6 border-y border-stone-300 bg-white py-5 sm:grid-cols-3">
      <Metric label="Data store" value={cosmos.enabled ? "Cosmos DB" : "Local"} detail={cosmos.database || "JSON persistence"} icon={Database} />
      <Metric label="Collections" value={number.format(cosmos.containers.length)} detail="Counted during this refresh" icon={Boxes} />
      <Metric label="Records" value={number.format(cosmos.containers.reduce((total, row) => total + row.records, 0))} detail="Snapshot, not real-time" icon={Activity} />
    </section>
    <div className="mt-6 grid min-w-0 gap-6 xl:grid-cols-2">
      <Panel title="Cosmos collections" note="Latest count at page refresh">
        {cosmos.containers.length ? <div className="overflow-x-auto"><table className="w-full min-w-[480px] text-left text-sm"><thead className="bg-stone-50 text-xs uppercase text-stone-500"><tr><th className="px-5 py-3">Collection</th><th>Records</th><th>Retention</th></tr></thead><tbody>{cosmos.containers.map((row) => <tr key={row.name} className="border-t border-stone-100"><td className="px-5 py-3 font-mono text-xs">{row.name}</td><td>{number.format(row.records)}</td><td>{row.default_ttl == null ? "Retained" : `${number.format(row.default_ttl / 86400)} days`}</td></tr>)}</tbody></table></div> : <Empty>Cosmos DB is not configured for this runtime.</Empty>}
      </Panel>
      <Panel title="Infrastructure configuration" note="Allowlisted values only · no secrets">
        <div className="divide-y divide-stone-100">{overview.infra.configuration.map((row) => <div key={`${row.category}-${row.name}`} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-4 px-5 py-3 text-sm"><div><p className="font-semibold">{row.name}</p><p className="mt-1 text-xs uppercase text-stone-500">{row.category}</p></div><p className="break-words text-right font-mono text-xs">{row.value}</p></div>)}</div>
      </Panel>
    </div>
  </>;
}

function SystemView({ overview }: { overview: OpsOverview }) {
  const routes = Object.entries(overview.requests.by_route).sort(([, a], [, b]) => b.p95_ms - a.p95_ms);
  const tools = Object.entries(overview.tools).sort(([, a], [, b]) => b.calls - a.calls);
  const providers = Object.entries(overview.providers).sort(([, a], [, b]) => b.failure_rate - a.failure_rate || b.calls - a.calls);
  const toolErrors = tools.flatMap(([tool, row]) => Object.entries(row.error_types).map(([error, count]) => ({ tool, error, count }))).sort((a, b) => b.count - a.count);
  const errorRate = overview.requests.calls ? (overview.requests.errors / overview.requests.calls) * 100 : 0;
  const chatErrorRate = overview.chat_turns.calls ? (overview.chat_turns.errors / overview.chat_turns.calls) * 100 : 0;
  const conversationWindows = (["daily", "weekly", "lifetime"] as const).map((window) => ({
    window,
    ...overview.conversation_limits[window],
  }));
  const cacheDatasets = overview.provider_usage.cache_effectiveness.by_dataset;

  return (
    <>
      <section className="grid gap-y-6 border-y border-stone-300 bg-white py-5 sm:grid-cols-2 xl:grid-cols-5">
        <Metric label="Chat p95" value={duration(overview.chat_turns.p95_ms)} detail={`${duration(overview.chat_turns.p50_ms)} median end-to-end`} icon={Bot} />
        <Metric label="Model p95" value={duration(overview.models.p95_ms)} detail={`${overview.models.calls} live model calls`} icon={Gauge} />
        <Metric label="Tools / turn" value={overview.chat_turns.avg_tools_per_turn.toFixed(1)} detail={`${overview.chat_turns.tool_calls} calls across ${overview.chat_turns.calls} turns`} icon={Wrench} />
        <Metric label="Chat failures" value={`${chatErrorRate.toFixed(1)}%`} detail={`${overview.chat_turns.errors} failed turns`} icon={AlertTriangle} />
        <Metric label="API errors" value={`${errorRate.toFixed(1)}%`} detail={`${overview.requests.errors} of ${overview.requests.calls} calls`} icon={Activity} />
      </section>

      <div className="mt-6">
        <Panel title="Conversation capacity" note="Environment-wide cost guardrail">
          <div className="grid divide-y divide-stone-100 sm:grid-cols-3 sm:divide-x sm:divide-y-0">
            {conversationWindows.map(({ window, categories, resets_at: resetsAt }) => (
              <div key={window} className="px-5 py-4 text-sm">
                <div className="mb-3 font-semibold capitalize text-stone-900">{window}</div>
                <div className="flex justify-between gap-4 py-1"><span>New trips</span><strong>{categories.new_trip.used} / {categories.new_trip.limit || "Off"}</strong></div>
                <div className="flex justify-between gap-4 py-1"><span>Trip updates</span><strong>{categories.existing_trip_turn.used} / {categories.existing_trip_turn.limit || "Off"}</strong></div>
                {resetsAt && <div className="mt-2 text-xs text-stone-500">Resets {new Date(resetsAt).toLocaleString()}</div>}
              </div>
            ))}
          </div>
        </Panel>
      </div>

      <div className="mt-6 grid min-w-0 gap-6 xl:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)]">
        <Panel title="Tool performance" note="Volume · failures · cache · p95">
          <div className="overflow-x-auto"><table className="w-full min-w-[650px] text-left text-sm"><thead className="bg-stone-50 text-xs uppercase text-stone-500"><tr><th className="px-5 py-3">Tool</th><th>Calls</th><th>Failure</th><th>Cache hit</th><th>p95</th></tr></thead><tbody>{tools.map(([name, row]) => <tr key={name} className="border-t border-stone-100"><td className="px-5 py-3 font-mono text-xs">{name}</td><td>{row.calls}</td><td className={row.errors ? "text-rose-700" : "text-stone-500"}>{Math.round((row.errors / Math.max(row.calls, 1)) * 100)}%</td><td>{Math.round(row.hit_rate * 100)}%</td><td className="font-mono text-xs">{duration(row.p95_ms)}</td></tr>)}</tbody></table>{!tools.length && <Empty>No tool calls in this process yet.</Empty>}</div>
        </Panel>
        <Panel title="Cache capacity" note="Provider namespace only">
          <div className="divide-y divide-stone-100 text-sm">
            <div className="flex items-center justify-between px-5 py-4"><span className="flex items-center gap-2"><Database size={16} />Backend</span><strong className="uppercase">{overview.cache.backend}</strong></div>
            <div className="flex items-center justify-between px-5 py-4"><span>Redis connectivity</span><strong className={overview.cache.redis_connected ? "text-emerald-700" : "text-amber-700"}>{overview.cache.redis_connected ? "Connected" : overview.cache.fallback_active ? "Memory fallback" : "Off"}</strong></div>
            <div className="flex items-center justify-between px-5 py-4"><span>Redis entries</span><strong>{number.format(overview.cache.redis_entries)}{overview.cache.redis_stats_truncated ? "+" : ""}</strong></div>
            <div className="flex items-center justify-between px-5 py-4"><span>Redis memory</span><strong>{bytes(overview.cache.redis_bytes)}</strong></div>
            <div className="flex items-center justify-between px-5 py-4"><span>Local fallback entries</span><strong>{number.format(overview.cache.memory_entries)}</strong></div>
          </div>
        </Panel>
      </div>

      <div className="mt-6">
        <Panel title="Cache health by dataset" note={`${overview.provider_usage.start_date} to ${overview.provider_usage.end_date} · durable provider boundary`}>
          <div className="overflow-x-auto"><table className="w-full min-w-[700px] text-left text-sm"><thead className="bg-stone-50 text-xs uppercase text-stone-500"><tr><th className="px-5 py-3">Dataset</th><th>Requests</th><th>Cache hits</th><th>Provider calls</th><th>Hit rate</th><th>Estimated saved</th></tr></thead><tbody>{cacheDatasets.map((row) => <tr key={row.dataset} className="border-t border-stone-100"><td className="px-5 py-3 font-semibold">{datasetLabels[row.dataset] || row.dataset.replaceAll("_", " ")}</td><td>{row.requests}</td><td>{row.cache_hits}</td><td>{row.provider_calls}</td><td className={row.hit_rate >= 0.5 ? "text-emerald-700" : "text-amber-700"}>{Math.round(row.hit_rate * 100)}%</td><td>${row.estimated_savings_usd.toFixed(4)}</td></tr>)}</tbody></table>{!cacheDatasets.length && <Empty>No durable cache activity in this period.</Empty>}</div>
        </Panel>
      </div>

      <div className="mt-6 grid min-w-0 gap-6 xl:grid-cols-2">
        <Panel title="Provider reliability" note="Fare providers · current process">
          <div className="overflow-x-auto"><table className="w-full min-w-[520px] text-left text-sm"><thead className="bg-stone-50 text-xs uppercase text-stone-500"><tr><th className="px-5 py-3">Provider</th><th>Calls</th><th>Failures</th><th>Failure rate</th><th>Avg</th></tr></thead><tbody>{providers.map(([name, row]) => <tr key={name} className="border-t border-stone-100"><td className="px-5 py-3 font-semibold">{name}</td><td>{row.calls}</td><td className={row.failures ? "text-rose-700" : "text-stone-500"}>{row.failures}</td><td>{Math.round(row.failure_rate * 100)}%</td><td className="font-mono text-xs">{duration(row.avg_ms)}</td></tr>)}</tbody></table>{!providers.length && <Empty>No fare-provider calls in this process yet.</Empty>}</div>
        </Panel>
        <Panel title="Request performance" note="Slowest routes by p95">
          <div className="overflow-x-auto"><table className="w-full min-w-[540px] text-left text-sm"><thead className="bg-stone-50 text-xs uppercase text-stone-500"><tr><th className="px-5 py-3">Endpoint</th><th>Calls</th><th>Errors</th><th>p50</th><th>p95</th></tr></thead><tbody>{routes.slice(0, 10).map(([route, row]) => <tr key={route} className="border-t border-stone-100"><td className="px-5 py-3 font-mono text-xs">{route}</td><td>{row.calls}</td><td className={row.errors ? "text-rose-700" : "text-stone-500"}>{row.errors}</td><td>{duration(row.p50_ms)}</td><td className="font-semibold">{duration(row.p95_ms)}</td></tr>)}</tbody></table></div>
        </Panel>
      </div>

      <div className="mt-6 grid min-w-0 gap-6 xl:grid-cols-2">
        <Panel title="Top tool failures" note="Exception class only">
          {toolErrors.length ? <div className="divide-y divide-stone-100">{toolErrors.slice(0, 8).map((item) => <div key={`${item.tool}-${item.error}`} className="grid grid-cols-[minmax(0,1fr)_auto] gap-4 px-5 py-3 text-sm"><div className="min-w-0"><p className="truncate font-mono text-xs">{item.tool}</p><p className="mt-1 text-xs text-rose-700">{item.error}</p></div><strong>{item.count}</strong></div>)}</div> : <Empty>No tool exceptions in this process.</Empty>}
        </Panel>
        <Panel title="Top cache hits" note="Tool category, never raw keys">
          {tools.some(([, row]) => row.cache_hits > 0) ? <div className="divide-y divide-stone-100">{tools.filter(([, row]) => row.cache_hits > 0).sort(([, a], [, b]) => b.cache_hits - a.cache_hits).slice(0, 8).map(([name, row]) => <div key={name} className="flex items-center justify-between gap-4 px-5 py-3 text-sm"><span className="truncate font-mono text-xs">{name}</span><strong>{row.cache_hits}</strong></div>)}</div> : <Empty>No cache hits in this process.</Empty>}
        </Panel>
      </div>

      <div className="mt-6 grid min-w-0 gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)]">
        <Panel title="Persisted inventory" note="Current owner scope">
          <div className="grid grid-cols-2 divide-x divide-y divide-stone-200 text-center sm:grid-cols-4 sm:divide-y-0"><div className="py-5"><p className="font-display text-3xl">{overview.business.inventory.trips}</p><p className="text-xs text-stone-500">trips</p></div><div className="py-5"><p className="font-display text-3xl">{overview.business.inventory.flights}</p><p className="text-xs text-stone-500">selected flights</p></div><div className="py-5"><p className="font-display text-3xl">{overview.business.inventory.hotels}</p><p className="text-xs text-stone-500">selected stays</p></div><div className="py-5"><p className="font-display text-3xl">{overview.business.inventory.activities}</p><p className="text-xs text-stone-500">selected places</p></div></div>
        </Panel>
        <Panel title="Model activity" note={`${overview.usage.month} · persisted usage`}>
          <div className="grid grid-cols-3 border-b border-stone-200 py-4 text-center"><div><p className="font-display text-2xl">{compact.format(overview.usage.model_calls)}</p><p className="text-xs text-stone-500">calls</p></div><div><p className="font-display text-2xl">{compact.format(overview.usage.prompt_tokens + overview.usage.completion_tokens)}</p><p className="text-xs text-stone-500">tokens</p></div><div><p className="font-display text-2xl">${Number(overview.usage.cost_usd).toFixed(2)}</p><p className="text-xs text-stone-500">cost</p></div></div>
          <div className="divide-y divide-stone-100">{overview.models.recent.slice(0, 5).map((call) => <div key={`${call.at}-${call.model}`} className="flex items-center justify-between px-5 py-3 text-sm"><span>{call.model}</span><span className={`font-mono text-xs ${call.status === "ok" ? "text-stone-600" : "text-rose-700"}`}>{call.status} · {duration(call.duration_ms)}</span></div>)}</div>
        </Panel>
      </div>

      {overview.requests.errors > 0 && <section className="mt-6 flex items-start gap-3 border border-rose-300 bg-rose-50 px-5 py-4 text-sm text-rose-900"><AlertTriangle size={18} /><div><p className="font-semibold">Recent HTTP error categories</p><p className="mt-1 text-xs">{Object.entries(overview.requests.error_statuses).map(([status, count]) => `${status}: ${count}`).join(" · ")}</p></div></section>}
    </>
  );
}

export default function OpsDashboard() {
  const [overview, setOverview] = useState<OpsOverview | null>(null);
  const [view, setView] = useState<"business" | "trips" | "cost" | "infra" | "system">("business");
  const [days, setDays] = useState(30);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [notFound, setNotFound] = useState(false);
  const [rangeError, setRangeError] = useState("");
  const [refreshing, setRefreshing] = useState(false);

  const load = async (signal?: AbortSignal) => {
    setRefreshing(true);
    try {
      setOverview(await fetchOpsOverview(days, signal, startDate || undefined, endDate || undefined));
      setNotFound(false);
      setRangeError("");
    } catch (error) {
      if (!signal?.aborted) {
        const status = (error as { status?: number }).status;
        setNotFound(status === 404);
        setRangeError(status === 422 ? "Choose a valid reporting range ending today or earlier." : "");
      }
    } finally {
      if (!signal?.aborted) setRefreshing(false);
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    const timer = window.setInterval(() => void load(controller.signal), 30_000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [days, startDate, endDate]);

  if (notFound) return <main className="grid min-h-full place-items-center bg-stone-100 px-6 text-center"><div><p className="font-display text-7xl text-stone-900">404</p><p className="mt-3 text-sm text-stone-500">Page not found.</p></div></main>;
  if (!overview) return <main className="grid min-h-full place-items-center bg-stone-100 text-sm text-stone-500">Loading</main>;
  const rangeProps = { days, startDate, endDate, onPreset: (period: number) => { setDays(period); setStartDate(""); setEndDate(""); }, onStartDate: setStartDate, onEndDate: setEndDate };

  return (
    <main className="min-h-full bg-[#f4f3ef] text-stone-900">
      <header className="border-b border-stone-700 bg-[#1f2926] px-5 py-4 text-stone-50 sm:px-8">
        <div className="mx-auto flex max-w-[1500px] flex-wrap items-center justify-between gap-4">
          <div><p className="text-xs font-semibold uppercase text-emerald-300">Tripplanner operations</p><h1 className="font-display text-2xl">Owner insight console</h1></div>
          <div className="flex items-center gap-4 text-xs text-stone-300"><span className="hidden sm:inline">Updated {new Date(overview.generated_at).toLocaleTimeString()}</span><button type="button" className="grid size-9 place-items-center border border-stone-600 hover:bg-stone-700" onClick={() => void load()} title="Refresh metrics" aria-label="Refresh metrics"><RefreshCw size={16} className={refreshing ? "animate-spin" : ""} /></button></div>
        </div>
        <div className="mx-auto mt-4 flex w-full max-w-[1500px] gap-1 overflow-x-auto" role="tablist" aria-label="Operations views">
          <button type="button" role="tab" aria-selected={view === "business"} onClick={() => setView("business")} className={`shrink-0 px-4 py-2 text-sm font-semibold ${view === "business" ? "bg-emerald-500 text-stone-950" : "text-stone-300 hover:bg-stone-700"}`}><span className="flex items-center gap-2"><Users size={15} />Business</span></button>
          <button type="button" role="tab" aria-selected={view === "trips"} onClick={() => setView("trips")} className={`shrink-0 px-4 py-2 text-sm font-semibold ${view === "trips" ? "bg-emerald-500 text-stone-950" : "text-stone-300 hover:bg-stone-700"}`}><span className="flex items-center gap-2"><PlaneTakeoff size={15} />Trips</span></button>
          <button type="button" role="tab" aria-selected={view === "cost"} onClick={() => setView("cost")} className={`shrink-0 px-4 py-2 text-sm font-semibold ${view === "cost" ? "bg-emerald-500 text-stone-950" : "text-stone-300 hover:bg-stone-700"}`}><span className="flex items-center gap-2"><Split size={15} />API &amp; cost</span></button>
          <button type="button" role="tab" aria-selected={view === "infra"} onClick={() => setView("infra")} className={`shrink-0 px-4 py-2 text-sm font-semibold ${view === "infra" ? "bg-emerald-500 text-stone-950" : "text-stone-300 hover:bg-stone-700"}`}><span className="flex items-center gap-2"><Database size={15} />Infra</span></button>
          <button type="button" role="tab" aria-selected={view === "system"} onClick={() => setView("system")} className={`shrink-0 px-4 py-2 text-sm font-semibold ${view === "system" ? "bg-emerald-500 text-stone-950" : "text-stone-300 hover:bg-stone-700"}`}><span className="flex items-center gap-2"><Server size={15} />System health</span></button>
        </div>
      </header>

      {rangeError && <div role="alert" className="border-b border-amber-300 bg-amber-50 px-5 py-3 text-sm text-amber-950 sm:px-8">{rangeError}</div>}
      <div className="mx-auto max-w-[1500px] px-5 py-6 sm:px-8">{view === "business" ? <BusinessView overview={overview} rangeProps={rangeProps} /> : view === "trips" ? <TripsView overview={overview} /> : view === "cost" ? <CostView overview={overview} {...rangeProps} /> : view === "infra" ? <InfraView overview={overview} /> : <SystemView overview={overview} />}</div>
    </main>
  );
}
