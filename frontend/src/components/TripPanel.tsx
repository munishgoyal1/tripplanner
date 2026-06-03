import { useState } from "react";
import type { TripItem, TripView } from "../types";
import DestinationOverview from "./DestinationOverview";
import Lightbox from "./Lightbox";

interface NavRef {
  kind: string;
  name: string;
}

interface Props {
  view: TripView | null;
  loading: boolean;
  navList: NavRef[];
  focusIndex: number;
  onFocus: (kind: string, name: string) => void;
  onClearFocus: () => void;
  onStep: (delta: number) => void;
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
    <span className="rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-600">
      ★ {rating.toFixed(1)}
      {count != null && <span className="text-amber-400/80"> ({count})</span>}
    </span>
  );
}

function ItemCard({
  item,
  focused,
  onFocus,
  onSelect,
  onDeselect,
  onOpenPhoto,
}: {
  item: TripItem;
  focused: boolean;
  onFocus: (kind: string, name: string) => void;
  onSelect: (kind: string, name: string) => void;
  onDeselect: (kind: string, name: string) => void;
  onOpenPhoto: (photos: string[], index: number, alt: string) => void;
}) {
  const icon = ICONS[item.kind] ?? "\u{1F4CD}";
  const photos = item.photos;
  const heroHeight = focused ? "h-60" : "h-40";
  return (
    <div className="overflow-hidden rounded-2xl bg-white shadow-sm ring-1 ring-slate-100 transition hover:shadow-md">
      {photos.length > 0 && (
        <div className="relative">
          <button onClick={() => onOpenPhoto(photos, 0, item.name)} className="block w-full">
            <img
              src={photos[0]}
              alt={item.name}
              className={`w-full ${heroHeight} object-cover transition-transform duration-500 hover:scale-105`}
            />
          </button>
          {photos.length > 1 && (
            <button
              onClick={() => onOpenPhoto(photos, 0, item.name)}
              className="absolute right-3 top-3 rounded-full bg-black/40 px-2.5 py-1 text-xs font-medium text-white backdrop-blur hover:bg-black/60"
            >
              📷 {photos.length}
            </button>
          )}
        </div>
      )}

      <div className="p-3.5">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="font-semibold text-ink">
              {icon} {item.name}
            </div>
            {item.address && <div className="text-xs text-slate-500">{item.address}</div>}
          </div>
          <Stars rating={item.rating} count={item.review_count} />
        </div>

        {focused && photos.length > 1 && (
          <div className="mt-2.5 flex gap-2 overflow-x-auto pb-1">
            {photos.slice(1).map((p, i) => (
              <button
                key={i}
                onClick={() => onOpenPhoto(photos, i + 1, item.name)}
                className="flex-shrink-0 overflow-hidden rounded-lg"
              >
                <img
                  src={p}
                  alt={item.name}
                  className="h-20 w-28 object-cover transition-transform duration-300 hover:scale-110"
                />
              </button>
            ))}
          </div>
        )}

        {item.summary && <p className="mt-2.5 text-sm leading-relaxed text-slate-600">{item.summary}</p>}

        {item.reviews.length > 0 && (
          <div className="mt-2.5 space-y-2">
            {item.reviews.slice(0, focused ? 4 : 2).map((r, i) => (
              <div key={i} className="rounded-xl border border-slate-100 bg-slate-50 px-3 py-2">
                <p className="text-xs text-slate-600">“{r.text}”</p>
                <p className="mt-1 text-[11px] text-slate-400">{r.author}</p>
              </div>
            ))}
          </div>
        )}

        <div className="mt-3 flex flex-wrap gap-2">
          {!focused && (
            <button
              onClick={() => onFocus(item.kind, item.name)}
              title="See this item on its own with all photos and reviews"
              className="rounded-lg bg-slate-100 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-200"
            >
              View details
            </button>
          )}

          {isSelectable(item.kind) &&
            (item.selected ? (
              <button
                onClick={() => onDeselect(item.kind, item.name)}
                title="Remove this from your saved trip picks"
                className="group rounded-lg bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-600 hover:bg-rose-50 hover:text-rose-600"
              >
                <span className="group-hover:hidden">✓ In trip</span>
                <span className="hidden group-hover:inline">✕ Remove</span>
              </button>
            ) : (
              <button
                onClick={() => onSelect(item.kind, item.name)}
                title="Save this to your trip so the agent keeps it in the plan"
                className="rounded-lg bg-brand px-3 py-1.5 text-xs font-medium text-white shadow-sm hover:opacity-90"
              >
                + Add to trip
              </button>
            ))}

          {item.website && (
            <a
              href={item.website}
              target="_blank"
              rel="noreferrer"
              className="rounded-lg bg-slate-100 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-200"
            >
              Website ↗
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

// Horizontal, click-based navigator: a pill per hotel/attraction. Clicking
// jumps to that item; the active one is highlighted. Replaces the old dropdown.
function NavStrip({
  navList,
  focusIndex,
  onFocus,
  onClearFocus,
}: {
  navList: NavRef[];
  focusIndex: number;
  onFocus: (kind: string, name: string) => void;
  onClearFocus: () => void;
}) {
  if (navList.length === 0) return null;
  return (
    <div className="flex gap-2 overflow-x-auto pb-1">
      <button
        onClick={onClearFocus}
        className={`flex-shrink-0 rounded-full px-3 py-1.5 text-xs font-medium transition ${
          focusIndex < 0
            ? "bg-brand text-white shadow-sm"
            : "bg-white text-slate-600 ring-1 ring-slate-200 hover:ring-brand"
        }`}
      >
        🗺️ Whole trip
      </button>
      {navList.map((n, i) => (
        <button
          key={i}
          onClick={() => onFocus(n.kind, n.name)}
          className={`flex-shrink-0 rounded-full px-3 py-1.5 text-xs font-medium transition ${
            i === focusIndex
              ? "bg-brand text-white shadow-sm"
              : "bg-white text-slate-600 ring-1 ring-slate-200 hover:ring-brand"
          }`}
        >
          {(ICONS[n.kind] ?? "📍") + " " + n.name}
        </button>
      ))}
    </div>
  );
}

export default function TripPanel({
  view,
  loading,
  navList,
  focusIndex,
  onFocus,
  onClearFocus,
  onStep,
  onSelect,
  onDeselect,
}: Props) {
  const [lb, setLb] = useState<{ photos: string[]; index: number; alt: string }>({
    photos: [],
    index: -1,
    alt: "",
  });
  const openPhoto = (photos: string[], index: number, alt: string) =>
    setLb({ photos, index, alt });

  if (loading && !view) {
    return <div className="p-5 text-sm text-slate-400">Loading trip…</div>;
  }
  if (!view || !view.has_trip) {
    return (
      <div className="grid h-full place-items-center p-6 text-center text-sm text-slate-400">
        {view?.empty_message || "No active trip yet. Start chatting to plan one."}
      </div>
    );
  }

  const ov = view.overview;
  const focused = !!view.focus;
  const total = navList.length;

  return (
    <div className="flex h-full flex-col bg-slate-100">
      {focused && (
        <div className="sticky top-0 z-10 flex items-center gap-2 border-b border-slate-200 bg-white/90 px-4 py-2 backdrop-blur">
          <button
            onClick={onClearFocus}
            className="rounded-lg bg-slate-100 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-200"
          >
            ← Whole trip
          </button>
          {total > 1 && (
            <div className="ml-auto flex items-center gap-1.5">
              <button
                onClick={() => onStep(-1)}
                className="grid h-7 w-7 place-items-center rounded-lg bg-slate-100 text-slate-600 hover:bg-slate-200"
                title="Previous"
              >
                ‹
              </button>
              <span className="text-xs text-slate-500">
                {focusIndex >= 0 ? focusIndex + 1 : "–"} / {total}
              </span>
              <button
                onClick={() => onStep(1)}
                className="grid h-7 w-7 place-items-center rounded-lg bg-slate-100 text-slate-600 hover:bg-slate-200"
                title="Next"
              >
                ›
              </button>
            </div>
          )}
        </div>
      )}

      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        <div className="rounded-2xl bg-gradient-to-br from-brand to-indigo-600 p-4 text-white shadow-sm">
          <h2 className="text-lg font-semibold">{view.title}</h2>
          <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-white/85">
            {ov.origin && (
              <div>
                <span className="text-white/60">From</span> {ov.origin}
              </div>
            )}
            {ov.destination && (
              <div>
                <span className="text-white/60">To</span> {ov.destination}
              </div>
            )}
            {ov.departure_date && (
              <div>
                <span className="text-white/60">Depart</span> {ov.departure_date}
              </div>
            )}
            {ov.return_date && (
              <div>
                <span className="text-white/60">Return</span> {ov.return_date}
              </div>
            )}
            <div>
              <span className="text-white/60">Travelers</span> {ov.travelers}
            </div>
            <div>
              <span className="text-white/60">Status</span> {ov.status}
            </div>
          </div>
          {ov.total_cost_display && (
            <div className="mt-2 text-sm font-semibold">Total: {ov.total_cost_display}</div>
          )}
          <div className="mt-2 flex gap-3 text-xs text-white/85">
            <span>✈️ {ov.counts.flights}</span>
            <span>🏨 {ov.counts.hotels}</span>
            <span>🎯 {ov.counts.activities}</span>
            {ov.counts.days > 0 && <span>📅 {ov.counts.days}d</span>}
          </div>
        </div>

        {/* Click-based navigator (replaces the dropdown) */}
        {total > 0 && (
          <NavStrip
            navList={navList}
            focusIndex={focusIndex}
            onFocus={onFocus}
            onClearFocus={onClearFocus}
          />
        )}

        {view.is_fallback && (
          <p className="rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-700">
            Popular spots in {ov.destination || "your destination"} — nothing picked yet.
            Hit “+ Add to trip” to save any of these.
          </p>
        )}

        {!focused && ov.destination && (
          <DestinationOverview destination={ov.destination} onFocus={onFocus} />
        )}

        <div className="space-y-3">
          {view.items.length === 0 ? (
            <p className="rounded-xl bg-white px-3 py-4 text-center text-xs text-slate-400">
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
                onOpenPhoto={openPhoto}
              />
            ))
          )}
        </div>
      </div>

      <Lightbox
        photos={lb.photos}
        index={lb.index}
        alt={lb.alt}
        onClose={() => setLb((s) => ({ ...s, index: -1 }))}
        onIndex={(i) => setLb((s) => ({ ...s, index: i }))}
      />
    </div>
  );
}
