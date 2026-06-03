import type { TripItem, TripView } from "../types";

interface Props {
  view: TripView | null;
  loading: boolean;
  onFocus: (kind: string, name: string) => void;
  onClearFocus: () => void;
  onSelect: (kind: string, name: string) => void;
}

function Stars({ rating, count }: { rating: number | null; count: number | null }) {
  if (rating == null) return null;
  return (
    <span className="text-xs text-amber-500">
      ★ {rating.toFixed(1)}
      {count != null && <span className="text-slate-400"> ({count})</span>}
    </span>
  );
}

function ItemCard({
  item,
  onFocus,
  onSelect,
}: {
  item: TripItem;
  onFocus: (kind: string, name: string) => void;
  onSelect: (kind: string, name: string) => void;
}) {
  const icon = item.kind === "hotel" ? "🏨" : item.kind === "activity" ? "🎯" : "✈️";
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="font-medium text-ink">
            {icon} {item.name}
          </div>
          {item.address && <div className="text-xs text-slate-500">{item.address}</div>}
        </div>
        <Stars rating={item.rating} count={item.review_count} />
      </div>

      {item.photos.length > 0 && (
        <div className="mt-2 flex gap-2 overflow-x-auto">
          {item.photos.map((p, i) => (
            <img
              key={i}
              src={p}
              alt={item.name}
              className="h-24 w-32 flex-shrink-0 rounded-lg object-cover"
            />
          ))}
        </div>
      )}

      {item.summary && <p className="mt-2 text-sm text-slate-600">{item.summary}</p>}

      {item.reviews.length > 0 && (
        <div className="mt-2 space-y-1">
          {item.reviews.slice(0, 2).map((r, i) => (
            <p key={i} className="text-xs text-slate-500">
              “{r.text}” — {r.author}
            </p>
          ))}
        </div>
      )}

      <div className="mt-2 flex gap-2">
        <button
          onClick={() => onFocus(item.kind, item.name)}
          className="rounded-lg bg-slate-100 px-3 py-1 text-xs text-slate-600 hover:bg-slate-200"
        >
          Focus
        </button>
        {!item.selected && (item.kind === "hotel" || item.kind === "activity") && (
          <button
            onClick={() => onSelect(item.kind, item.name)}
            className="rounded-lg bg-brand px-3 py-1 text-xs text-white hover:opacity-90"
          >
            Add to trip
          </button>
        )}
        {item.selected && (
          <span className="rounded-lg bg-emerald-50 px-3 py-1 text-xs text-emerald-600">
            ✓ In trip
          </span>
        )}
        {item.website && (
          <a
            href={item.website}
            target="_blank"
            rel="noreferrer"
            className="rounded-lg bg-slate-100 px-3 py-1 text-xs text-slate-600 hover:bg-slate-200"
          >
            Website
          </a>
        )}
      </div>
    </div>
  );
}

export default function TripPanel({
  view,
  loading,
  onFocus,
  onClearFocus,
  onSelect,
}: Props) {
  if (loading && !view) {
    return <div className="p-5 text-sm text-slate-400">Loading trip…</div>;
  }
  if (!view || !view.has_trip) {
    return (
      <div className="p-6 text-center text-sm text-slate-400">
        {view?.empty_message || "No active trip yet. Start chatting to plan one."}
      </div>
    );
  }

  const ov = view.overview;
  return (
    <div className="h-full overflow-y-auto bg-slate-50 p-4">
      <div className="rounded-xl bg-white p-4 shadow-sm">
        <h2 className="text-lg font-semibold text-ink">{view.title}</h2>
        <div className="mt-1 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-slate-600">
          {ov.origin && (
            <div>
              <span className="text-slate-400">From</span> {ov.origin}
            </div>
          )}
          {ov.destination && (
            <div>
              <span className="text-slate-400">To</span> {ov.destination}
            </div>
          )}
          {ov.departure_date && (
            <div>
              <span className="text-slate-400">Depart</span> {ov.departure_date}
            </div>
          )}
          {ov.return_date && (
            <div>
              <span className="text-slate-400">Return</span> {ov.return_date}
            </div>
          )}
          <div>
            <span className="text-slate-400">Travelers</span> {ov.travelers}
          </div>
          <div>
            <span className="text-slate-400">Status</span> {ov.status}
          </div>
        </div>
        {ov.total_cost_display && (
          <div className="mt-2 text-sm font-medium text-ink">
            Total: {ov.total_cost_display}
          </div>
        )}
        <div className="mt-2 flex gap-3 text-xs text-slate-500">
          <span>✈️ {ov.counts.flights}</span>
          <span>🏨 {ov.counts.hotels}</span>
          <span>🎯 {ov.counts.activities}</span>
          {ov.counts.days > 0 && <span>📅 {ov.counts.days}d</span>}
        </div>
      </div>

      {view.is_fallback && (
        <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700">
          Showing popular spots — nothing selected yet.
        </p>
      )}

      {view.focus && (
        <button
          onClick={onClearFocus}
          className="mt-3 text-xs font-medium text-brand hover:underline"
        >
          ← Back to whole trip
        </button>
      )}

      <div className="mt-3 space-y-3">
        {view.items.map((it, i) => (
          <ItemCard key={i} item={it} onFocus={onFocus} onSelect={onSelect} />
        ))}
      </div>
    </div>
  );
}
