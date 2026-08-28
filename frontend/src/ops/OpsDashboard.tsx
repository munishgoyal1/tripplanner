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

function estimatedCost(cost: number, unknown: number): string {
  const value = `$${cost.toFixed(cost < 0.01 ? 4 : 2)}`;
  return unknown ? `${value} + ${unknown} unknown` : value;
}

function CostView({ overview }: { overview: OpsOverview }) {
  const usage = overview.provider_usage;
  const interactions = usage.by_interaction.filter((row) => row.interaction_id);
  const trips = usage.by_trip;
  const userCalls = usage.by_initiator
    .filter((row) => row.initiator === "user_trip" || row.initiator === "user_action")
    .reduce((total, row) => total + row.calls, 0);
  const backgroundCalls = usage.totals.calls - userCalls;

  return (
    <>
      <section className="grid gap-y-6 border-y border-stone-300 bg-white py-5 sm:grid-cols-2 xl:grid-cols-5">
        <Metric label="Measured calls" value={number.format(usage.totals.calls)} detail={`${usage.totals.failures} failed · ${usage.totals.avoided_calls} avoided`} icon={Boxes} />
        <Metric label="Estimated cost" value={`$${usage.totals.estimated_cost_usd.toFixed(2)}`} detail="Known catalog prices only" icon={DollarSign} />
        <Metric label="Unknown price" value={number.format(usage.totals.unknown_cost_calls)} detail="Measured calls, cost unavailable" icon={AlertTriangle} />
        <Metric label="User initiated" value={number.format(userCalls)} detail={`${usage.totals.calls ? Math.round(userCalls / usage.totals.calls * 100) : 0}% of measured calls`} icon={Users} />
        <Metric label="Non-user initiated" value={number.format(backgroundCalls)} detail={`${interactions.length} attributed interactions`} icon={Workflow} />
      </section>

      <section className="mt-6 border border-amber-300 bg-amber-50 px-5 py-4 text-sm text-amber-950">
        <p className="font-semibold">Cost is an estimate, not a billing statement.</p>
        <p className="mt-1 text-xs">{usage.pricing.basis} Catalog {usage.pricing.catalog_version}. Unknown-price calls remain visible and are excluded from the dollar total.</p>
      </section>

      <div className="mt-6 grid min-w-0 gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)]">
        <Panel title="Activity source" note="Environment → initiator">
          {usage.by_initiator.length ? <div className="divide-y divide-stone-100">{usage.by_initiator.map((row) => (
            <div key={`${row.environment}-${row.initiator}`} className="grid grid-cols-[minmax(0,1fr)_auto] gap-4 px-5 py-4 text-sm">
              <div><p className="font-semibold">{initiatorLabels[row.initiator || ""] || row.initiator}</p><p className="mt-1 text-xs uppercase text-stone-500">{row.environment}</p></div>
              <div className="text-right"><p className="font-semibold">{number.format(row.calls)} calls</p><p className="mt-1 text-xs text-stone-500">{estimatedCost(row.estimated_cost_usd, row.unknown_cost_calls)}</p></div>
            </div>
          ))}</div> : <Empty>No provider or model calls recorded in this period.</Empty>}
        </Panel>

        <Panel title="Trip and provider hierarchy" note="Expand a trip for operation detail">
          {trips.length ? <div className="divide-y divide-stone-200">{trips.map((trip) => {
            const providers = usage.by_provider.filter((row) => row.environment === trip.environment && row.initiator === trip.initiator && row.trip_id === trip.trip_id);
            return <details key={`${trip.environment}-${trip.initiator}-${trip.trip_id}`} className="group">
              <summary className="grid cursor-pointer list-none grid-cols-[minmax(0,1fr)_auto] gap-4 px-5 py-4 text-sm hover:bg-stone-50">
                <div className="min-w-0"><p className="truncate font-semibold">{trip.trip_id && trip.trip_id !== "unattributed" ? trip.trip_id : "Not tied to a saved trip"}</p><p className="mt-1 text-xs text-stone-500">{trip.environment} · {initiatorLabels[trip.initiator || ""] || trip.initiator}</p></div>
                <div className="text-right"><p>{trip.calls} calls</p><p className="mt-1 text-xs text-stone-500">{estimatedCost(trip.estimated_cost_usd, trip.unknown_cost_calls)}</p></div>
              </summary>
              <div className="border-t border-stone-100 bg-stone-50 px-5 py-3">{providers.map((provider) => {
                const operations = usage.by_operation.filter((row) => row.environment === provider.environment && row.initiator === provider.initiator && row.trip_id === provider.trip_id && row.provider === provider.provider);
                return <div key={provider.provider} className="border-b border-stone-200 py-3 last:border-b-0">
                  <div className="flex justify-between gap-4 text-sm"><strong>{provider.provider}</strong><span>{provider.calls} calls · {estimatedCost(provider.estimated_cost_usd, provider.unknown_cost_calls)}</span></div>
                  <div className="mt-2 space-y-1">{operations.map((operation) => <div key={`${operation.operation}-${operation.sku_class}`} className="grid grid-cols-[minmax(0,1fr)_auto] gap-3 font-mono text-xs text-stone-600"><span className="truncate">{operation.operation} · {operation.sku_class}</span><span>{operation.calls} · {estimatedCost(operation.estimated_cost_usd, operation.unknown_cost_calls)}</span></div>)}</div>
                </div>;
              })}</div>
            </details>;
          })}</div> : <Empty>No trip-attributed calls recorded in this period.</Empty>}
        </Panel>
      </div>

      <div className="mt-6"><Panel title="Initiated interactions" note="One request or audit run, content-free">
        {interactions.length ? <div className="overflow-x-auto"><table className="w-full min-w-[720px] text-left text-sm"><thead className="bg-stone-50 text-xs uppercase text-stone-500"><tr><th className="px-5 py-3">Interaction</th><th>Source</th><th>Trip</th><th>Calls</th><th>Failures</th><th>Estimated cost</th></tr></thead><tbody>{interactions.map((row) => <tr key={`${row.environment}-${row.interaction_id}`} className="border-t border-stone-100"><td className="max-w-64 truncate px-5 py-3 font-mono text-xs">{row.interaction_id}</td><td>{initiatorLabels[row.initiator || ""] || row.initiator}</td><td className="font-mono text-xs">{row.trip_id === "unattributed" ? "—" : row.trip_id}</td><td>{row.calls}</td><td className={row.failures ? "text-rose-700" : "text-stone-500"}>{row.failures}</td><td>{estimatedCost(row.estimated_cost_usd, row.unknown_cost_calls)}</td></tr>)}</tbody></table></div> : <Empty>No interaction IDs recorded in this period.</Empty>}
      </Panel></div>
    </>
  );
}

function BusinessView({ overview }: { overview: OpsOverview }) {
  const activities = Object.entries(overview.product.activities).sort(([, a], [, b]) => b - a);
  const countries = Object.entries(overview.product.countries).sort(([, a], [, b]) => b - a);
  const sources = Object.entries(overview.product.sources).sort(([, a], [, b]) => b - a);
  const dropOffs = Object.entries(overview.product.drop_offs).sort(([, a], [, b]) => b - a);
  const funnel = Object.entries(overview.product.funnel);
  const funnelBase = Math.max(overview.product.funnel.page_view, 1);

  return (
    <>
      <section className="grid gap-y-6 border-y border-stone-300 bg-white py-5 sm:grid-cols-2 xl:grid-cols-5">
        <Metric label="Users" value={number.format(overview.product.users)} detail={`${overview.product.sessions} consented sessions`} icon={Users} />
        <Metric label="Engagement" value={elapsed(overview.product.engagement_seconds)} detail="Active time between events" icon={Clock3} />
        <Metric label="New trips" value={number.format(overview.business.new_trips["7d"])} detail={`${overview.business.new_trips.today} today · ${overview.business.new_trips["30d"]} in 30d`} icon={PlaneTakeoff} />
        <Metric label="Itineraries" value={number.format(overview.product.funnel.planning_completed)} detail="Completed consented sessions" icon={Workflow} />
        <Metric label="Exports" value={number.format((overview.product.activities.itinerary_exported || 0) + (overview.product.activities.calendar_exported || 0))} detail={`${overview.product.activities.trip_shared || 0} trips shared`} icon={Activity} />
      </section>

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

function SystemView({ overview }: { overview: OpsOverview }) {
  const routes = Object.entries(overview.requests.by_route).sort(([, a], [, b]) => b.p95_ms - a.p95_ms);
  const tools = Object.entries(overview.tools).sort(([, a], [, b]) => b.calls - a.calls);
  const providers = Object.entries(overview.providers).sort(([, a], [, b]) => b.failure_rate - a.failure_rate || b.calls - a.calls);
  const toolErrors = tools.flatMap(([tool, row]) => Object.entries(row.error_types).map(([error, count]) => ({ tool, error, count }))).sort((a, b) => b.count - a.count);
  const errorRate = overview.requests.calls ? (overview.requests.errors / overview.requests.calls) * 100 : 0;
  const chatErrorRate = overview.chat_turns.calls ? (overview.chat_turns.errors / overview.chat_turns.calls) * 100 : 0;

  return (
    <>
      <section className="grid gap-y-6 border-y border-stone-300 bg-white py-5 sm:grid-cols-2 xl:grid-cols-5">
        <Metric label="Chat p95" value={duration(overview.chat_turns.p95_ms)} detail={`${duration(overview.chat_turns.p50_ms)} median end-to-end`} icon={Bot} />
        <Metric label="Model p95" value={duration(overview.models.p95_ms)} detail={`${overview.models.calls} live model calls`} icon={Gauge} />
        <Metric label="Tools / turn" value={overview.chat_turns.avg_tools_per_turn.toFixed(1)} detail={`${overview.chat_turns.tool_calls} calls across ${overview.chat_turns.calls} turns`} icon={Wrench} />
        <Metric label="Chat failures" value={`${chatErrorRate.toFixed(1)}%`} detail={`${overview.chat_turns.errors} failed turns`} icon={AlertTriangle} />
        <Metric label="API errors" value={`${errorRate.toFixed(1)}%`} detail={`${overview.requests.errors} of ${overview.requests.calls} calls`} icon={Activity} />
      </section>

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
  const [view, setView] = useState<"business" | "cost" | "system">("business");
  const [days, setDays] = useState(30);
  const [notFound, setNotFound] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const load = async (signal?: AbortSignal) => {
    setRefreshing(true);
    try {
      setOverview(await fetchOpsOverview(days, signal));
      setNotFound(false);
    } catch {
      if (!signal?.aborted) setNotFound(true);
    } finally {
      if (!signal?.aborted) setRefreshing(false);
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    const timer = window.setInterval(() => void load(controller.signal), 30_000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [days]);

  if (notFound) return <main className="grid min-h-full place-items-center bg-stone-100 px-6 text-center"><div><p className="font-display text-7xl text-stone-900">404</p><p className="mt-3 text-sm text-stone-500">Page not found.</p></div></main>;
  if (!overview) return <main className="grid min-h-full place-items-center bg-stone-100 text-sm text-stone-500">Loading</main>;

  return (
    <main className="min-h-full bg-[#f4f3ef] text-stone-900">
      <header className="border-b border-stone-700 bg-[#1f2926] px-5 py-4 text-stone-50 sm:px-8">
        <div className="mx-auto flex max-w-[1500px] flex-wrap items-center justify-between gap-4">
          <div><p className="text-xs font-semibold uppercase text-emerald-300">Tripplanner operations</p><h1 className="font-display text-2xl">Owner insight console</h1></div>
          <div className="flex items-center gap-4 text-xs text-stone-300"><span className="hidden sm:inline">Updated {new Date(overview.generated_at).toLocaleTimeString()}</span>{view === "cost" && <div className="flex border border-stone-600" aria-label="Cost reporting period">{[7, 30, 90].map((period) => <button key={period} type="button" className={`px-3 py-2 ${days === period ? "bg-stone-100 text-stone-950" : "hover:bg-stone-700"}`} onClick={() => setDays(period)}>{period}d</button>)}</div>}<button type="button" className="grid size-9 place-items-center border border-stone-600 hover:bg-stone-700" onClick={() => void load()} title="Refresh metrics" aria-label="Refresh metrics"><RefreshCw size={16} className={refreshing ? "animate-spin" : ""} /></button></div>
        </div>
        <div className="mx-auto mt-4 flex max-w-[1500px] gap-1" role="tablist" aria-label="Operations views">
          <button type="button" role="tab" aria-selected={view === "business"} onClick={() => setView("business")} className={`px-4 py-2 text-sm font-semibold ${view === "business" ? "bg-emerald-500 text-stone-950" : "text-stone-300 hover:bg-stone-700"}`}><span className="flex items-center gap-2"><Users size={15} />Business</span></button>
          <button type="button" role="tab" aria-selected={view === "cost"} onClick={() => setView("cost")} className={`px-4 py-2 text-sm font-semibold ${view === "cost" ? "bg-emerald-500 text-stone-950" : "text-stone-300 hover:bg-stone-700"}`}><span className="flex items-center gap-2"><Split size={15} />API &amp; cost</span></button>
          <button type="button" role="tab" aria-selected={view === "system"} onClick={() => setView("system")} className={`px-4 py-2 text-sm font-semibold ${view === "system" ? "bg-emerald-500 text-stone-950" : "text-stone-300 hover:bg-stone-700"}`}><span className="flex items-center gap-2"><Server size={15} />System health</span></button>
        </div>
      </header>
      <div className="mx-auto max-w-[1500px] px-5 py-6 sm:px-8">{view === "business" ? <BusinessView overview={overview} /> : view === "cost" ? <CostView overview={overview} /> : <SystemView overview={overview} />}</div>
    </main>
  );
}
