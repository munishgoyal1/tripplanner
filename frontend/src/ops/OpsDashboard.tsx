import { useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Bot,
  Clock3,
  Database,
  Gauge,
  PlaneTakeoff,
  RefreshCw,
  Server,
  Workflow,
} from "lucide-react";
import { fetchOpsOverview, type OpsOverview } from "../api";

const number = new Intl.NumberFormat("en-US");
const compact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });

function duration(value: number): string {
  if (value < 1000) return `${Math.round(value)} ms`;
  return `${(value / 1000).toFixed(1)} s`;
}

function Metric({ label, value, detail, icon: Icon }: {
  label: string;
  value: string;
  detail: string;
  icon: typeof Activity;
}) {
  return (
    <div className="border-l border-stone-200 px-4 first:border-l-0">
      <div className="flex items-center gap-2 text-xs font-semibold uppercase text-stone-500">
        <Icon size={14} aria-hidden /> {label}
      </div>
      <div className="mt-2 font-display text-3xl text-stone-950">{value}</div>
      <div className="mt-1 text-xs text-stone-500">{detail}</div>
    </div>
  );
}

function StatusDot({ active }: { active: boolean }) {
  return <span className={`inline-block size-2 rounded-full ${active ? "bg-emerald-500" : "bg-amber-500"}`} />;
}

export default function OpsDashboard() {
  const [overview, setOverview] = useState<OpsOverview | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const load = async (signal?: AbortSignal) => {
    setRefreshing(true);
    try {
      setOverview(await fetchOpsOverview(signal));
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
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, []);

  if (notFound) {
    return (
      <main className="grid min-h-full place-items-center bg-stone-100 px-6 text-center">
        <div><p className="font-display text-7xl text-stone-900">404</p><p className="mt-3 text-sm text-stone-500">Page not found.</p></div>
      </main>
    );
  }
  if (!overview) {
    return <main className="grid min-h-full place-items-center bg-stone-100 text-sm text-stone-500">Loading</main>;
  }

  const routes = Object.entries(overview.requests.by_route).sort(([, a], [, b]) => b.p95_ms - a.p95_ms);
  const tools = Object.entries(overview.tools).sort(([, a], [, b]) => b.calls - a.calls);
  const errorRate = overview.requests.calls ? (overview.requests.errors / overview.requests.calls) * 100 : 0;

  return (
    <main className="min-h-full bg-[#f4f3ef] text-stone-900">
      <header className="border-b border-stone-300 bg-[#1f2926] px-5 py-4 text-stone-50 sm:px-8">
        <div className="mx-auto flex max-w-[1500px] items-center justify-between gap-4">
          <div><p className="text-xs font-semibold uppercase text-emerald-300">Tripplanner operations</p><h1 className="font-display text-2xl">System pulse</h1></div>
          <div className="flex items-center gap-4 text-xs text-stone-300">
            <span className="hidden sm:inline">Updated {new Date(overview.generated_at).toLocaleTimeString()}</span>
            <button type="button" className="grid size-9 place-items-center border border-stone-600 hover:bg-stone-700" onClick={() => void load()} title="Refresh metrics" aria-label="Refresh metrics">
              <RefreshCw size={16} className={refreshing ? "animate-spin" : ""} />
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-[1500px] px-5 py-6 sm:px-8">
        <section className="grid gap-y-6 border-y border-stone-300 bg-white py-5 sm:grid-cols-2 lg:grid-cols-5">
          <Metric label="New trips" value={number.format(overview.business.new_trips["7d"])} detail={`${overview.business.new_trips.today} today · ${overview.business.new_trips["30d"]} in 30d`} icon={PlaneTakeoff} />
          <Metric label="Active trips" value={number.format(overview.business.active_trips["7d"])} detail={`${overview.business.active_trips.today} touched today`} icon={Workflow} />
          <Metric label="API calls" value={compact.format(overview.requests.calls)} detail={`${errorRate.toFixed(1)}% error rate`} icon={Activity} />
          <Metric label="Model calls" value={compact.format(overview.usage.model_calls)} detail={`$${Number(overview.usage.cost_usd).toFixed(2)} this month`} icon={Bot} />
          <Metric label="p95 latency" value={duration(overview.requests.p95_ms)} detail={`${duration(overview.requests.p50_ms)} median`} icon={Gauge} />
        </section>

        <div className="mt-6 grid min-w-0 gap-6 lg:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)]">
          <section className="min-w-0 border border-stone-300 bg-white">
            <div className="flex items-center justify-between border-b border-stone-200 px-5 py-4"><h2 className="font-display text-lg">Request performance</h2><span className="text-xs text-stone-500">Last {overview.requests.calls} calls</span></div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[620px] text-left text-sm">
                <thead className="bg-stone-50 text-xs uppercase text-stone-500"><tr><th className="px-5 py-3">Endpoint</th><th>Calls</th><th>Errors</th><th>p50</th><th>p95</th></tr></thead>
                <tbody>{routes.map(([route, row]) => <tr key={route} className="border-t border-stone-100"><td className="px-5 py-3 font-mono text-xs">{route}</td><td>{row.calls}</td><td className={row.errors ? "text-rose-700" : "text-stone-500"}>{row.errors}</td><td>{duration(row.p50_ms)}</td><td className="font-semibold">{duration(row.p95_ms)}</td></tr>)}</tbody>
              </table>
            </div>
          </section>

          <section className="min-w-0 border border-stone-300 bg-white">
            <div className="border-b border-stone-200 px-5 py-4"><h2 className="font-display text-lg">Runtime health</h2></div>
            <div className="divide-y divide-stone-200">
              <div className="flex items-center justify-between px-5 py-4"><div className="flex items-center gap-3"><Database size={18} /><div><p className="text-sm font-semibold">Provider cache</p><p className="text-xs text-stone-500">{overview.cache.memory_entries} local entries</p></div></div><span className="flex items-center gap-2 text-xs font-semibold uppercase"><StatusDot active={!overview.cache.fallback_active} />{overview.cache.backend}</span></div>
              <div className="flex items-center justify-between px-5 py-4"><div className="flex items-center gap-3"><Server size={18} /><div><p className="text-sm font-semibold">Redis</p><p className="text-xs text-stone-500">{overview.cache.configured ? "Configured" : "Not configured"}</p></div></div><span className="flex items-center gap-2 text-xs font-semibold uppercase"><StatusDot active={overview.cache.redis_connected || !overview.cache.configured} />{overview.cache.redis_connected ? "Connected" : overview.cache.fallback_active ? "Fallback" : "Off"}</span></div>
              <div className="flex items-center justify-between px-5 py-4"><div className="flex items-center gap-3"><Clock3 size={18} /><div><p className="text-sm font-semibold">Process uptime</p><p className="text-xs text-stone-500">Current container</p></div></div><span className="font-mono text-sm">{Math.floor(overview.uptime_seconds / 3600)}h {Math.floor((overview.uptime_seconds % 3600) / 60)}m</span></div>
            </div>
          </section>
        </div>

        <div className="mt-6 grid min-w-0 gap-6 lg:grid-cols-2">
          <section className="min-w-0 border border-stone-300 bg-white"><div className="border-b border-stone-200 px-5 py-4"><h2 className="font-display text-lg">Model activity</h2></div><div className="grid grid-cols-3 border-b border-stone-200 py-4 text-center"><div><p className="font-display text-2xl">{overview.models.calls}</p><p className="text-xs text-stone-500">live calls</p></div><div><p className="font-display text-2xl">{duration(overview.models.p95_ms)}</p><p className="text-xs text-stone-500">p95</p></div><div><p className="font-display text-2xl">{compact.format(overview.usage.prompt_tokens + overview.usage.completion_tokens)}</p><p className="text-xs text-stone-500">monthly tokens</p></div></div><div className="divide-y divide-stone-100">{overview.models.recent.slice(0, 6).map((call) => <div key={`${call.at}-${call.model}`} className="flex items-center justify-between px-5 py-3 text-sm"><span className="flex items-center gap-2"><StatusDot active={call.status === "ok"} />{call.model}</span><span className="font-mono text-xs">{duration(call.duration_ms)}</span></div>)}</div></section>
          <section className="min-w-0 border border-stone-300 bg-white"><div className="flex items-center justify-between border-b border-stone-200 px-5 py-4"><h2 className="font-display text-lg">Tool calls</h2><span className="text-xs text-stone-500">Cache and latency</span></div><div className="divide-y divide-stone-100">{tools.slice(0, 8).map(([name, row]) => <div key={name} className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-3 px-5 py-3 text-sm"><span className="truncate font-mono text-xs" title={name}>{name}</span><span className="text-xs text-stone-500">{row.calls} calls · {Math.round(row.hit_rate * 100)}% hit</span><span className="font-mono text-xs">{duration(row.p95_ms)}</span></div>)}{tools.length === 0 && <p className="px-5 py-8 text-center text-sm text-stone-500">No tool calls in this process yet.</p>}</div></section>
        </div>

        {overview.requests.errors > 0 && <section className="mt-6 flex items-start gap-3 border border-rose-300 bg-rose-50 px-5 py-4 text-sm text-rose-900"><AlertTriangle size={18} /><div><p className="font-semibold">Recent request errors</p><p className="mt-1 text-xs">{Object.entries(overview.requests.error_statuses).map(([status, count]) => `${status}: ${count}`).join(" · ")}</p></div></section>}
      </div>
    </main>
  );
}