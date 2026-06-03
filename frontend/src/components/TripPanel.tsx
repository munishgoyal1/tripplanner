import type { TripItem, TripView } from "../types";
import DestinationOverview from "./DestinationOverview";

interface Props {
  view: TripView | null;
  loading: boolean;
  onFocus: (kind: string, name: string) => void;
  onClearFocus: () => void;
  onSelect: (kind: string, name: string) => void;
  onDeselect: (kind: string, name: string) => void;
}

const ICONS: Record<string, string> = {
  hotel: "\u{1F3E8}",
  activity: "\u{1F3AF}",
  attraction: "\u{1F3AF}",
  flight: "\u2708\uFE0F",
};

// Both "activity" and "attraction" map to the same trip bucket server-side.
function isSelectable(kind: string): boolean {
  return kind === "hotel" || kind === "activity" || kind === "attraction";
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
  focused,
  onFocus,
  onSelect,
  onDeselect,
}: {
  item: TripItem;
  focused: boolean;
  onFocus: (kind: string, name: string) => void;
  onSelect: (kind: string, name: string) => void;
  onDeselect: (kind: string, name: string) => void;
}) {
  const icon = ICONS[item.kind] ?? "\u{1F4CD}";
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

      <div className="mt-2 flex flex-wrap gap-2">
        {!focused && (
          <button
            onClick={() => onFocus(item.kind, item.name)}
            title="See this item on its own with all photos and reviews"
            className="rounded-lg bg-slate-100 px-3 py-1 text-xs text-slate-600 hover:bg-slate-200"
          >
            View details
          </button>
        )}

        {isSelectable(item.kind) &&
          (item.selected ? (
            <button
              onClick={() => onDeselect(item.kind, item.name)}
              title="Remove this from your saved trip picks"
              className="group rounded-lg bg-emerald-50 px-3 py-1 text-xs text-emerald-600 hover:bg-rose-50 hover:text-rose-600"
            >
              <span className="group-hover:hidden">✓ In trip</span>
              <span className="hidden group-hover:inline">✕ Remove</span>
            </button>
          ) : (
            <button
              onClick={() => onSelect(item.kind, item.name)}
              title="Save this to your trip so the agent keeps it in the plan"
              className="rounded-lg bg-brand px-3 py-1 text-xs text-white hover:opacity-90"
            >
              + Add to trip
            </button>
          ))}

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
  onDeselect,
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
  const focused = !!view.focus;
  return (
    <div className="flex h-full flex-col bg-slate-50">
      {focused && (
        <div className="sticky top-0 z-10 flex items-center gap-2 border-b border-slate-200 bg-white px-4 py-2">
          <button
            onClick={onClearFocus}
            className="rounded-lg bg-slate-100 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-200"
          >
            ← Back to whole trip
          </button>
          <span className="truncate text-xs text-slate-500">
            Viewing {view.focus?.name}
          </span>
        </div>
      )}
      <div className="flex-1 overflow-y-auto p-4">
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
          Popular spots in {ov.destination || "your destination"} — nothing
          picked yet. Hit “+ Add to trip” to save any of these.
        </p>
      )}

      {!focused && ov.destination && (
        <div className="mt-3">
          <DestinationOverview destination={ov.destination} onFocus={onFocus} />
        </div>
      )}

      {!focused && view.items.length > 0 && (
        <div className="mt-3">
          <label className="mb-1 block text-xs font-medium text-slate-500">
            Jump to a hotel or attraction
          </label>
          <select
            className="input"
            value=""
            onChange={(e) => {
              if (!e.target.value) return;
              const [kind, ...rest] = e.target.value.split("::");
              onFocus(kind, rest.join("::"));
            }}
          >
            <option value="">Select to see its photos, reviews & details…</option>
            {view.items.map((it, i) => (
              <option key={i} value={`${it.kind}::${it.name}`}>
                {(ICONS[it.kind] ?? "📍") + " " + it.name}
              </option>
            ))}
          </select>
        </div>
      )}

      <div className="mt-3 space-y-3">
        {view.items.length === 0 ? (
          <p className="rounded-lg bg-white px-3 py-4 text-center text-xs text-slate-400">
            {focused
              ? "Nothing to show for this item."
              : "No hotels or activities saved yet. Ask the agent for options, then add the ones you like."}
          </p>
        ) : (
          view.items.map((it, i) => (
            <ItemCard
              key={i}
              item={it}
              focused={focused}
              onFocus={onFocus}
              onSelect={onSelect}
              onDeselect={onDeselect}
            />
          ))
        )}
      </div>
      </div>
    </div>
  );
}
