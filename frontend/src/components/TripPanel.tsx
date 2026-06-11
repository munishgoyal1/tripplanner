import { useEffect, useRef, useState } from "react";
import {
  deleteTrip,
  fetchSavedTrips,
  shareActiveTrip,
  switchTrip,
  tripIcsUrl,
} from "../api";
import type { Budget, SavedTrip, TripItem, TripView } from "../types";
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
  tripVersion: number;
  onSwitched: () => void;
  /** Hide the internal saved-trips switcher (RightRail renders it persistently). */
  hideSwitcher?: boolean;
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
    <span className="pill bg-amber-50 text-amber-700 ring-1 ring-amber-100">
      ★ {rating.toFixed(1)}
      {count != null && <span className="text-amber-500/80"> ({count})</span>}
    </span>
  );
}

// Live budget meter for the hero: running spend, per-traveler split, and a
// remaining-vs-target bar when the user gave the agent a budget. Styled for the
// dark hero background.
function BudgetMeter({ budget }: { budget: Budget }) {
  const hasTarget = budget.target != null && budget.target > 0;
  const pct = budget.pct_used ?? 0;
  const over = budget.over_budget;
  const barColor = over ? "bg-rose-400" : pct >= 80 ? "bg-amber-300" : "bg-emerald-400";
  const money = (n: number) => `${budget.currency}${Math.round(n).toLocaleString()}`;
  const segs: { icon: string; value: number }[] = [
    { icon: "✈️", value: budget.breakdown.flights ?? 0 },
    { icon: "🏨", value: budget.breakdown.hotels ?? 0 },
    { icon: "🎯", value: budget.breakdown.activities ?? 0 },
  ].filter((s) => s.value > 0);

  return (
    <div className="mt-4 rounded-2xl bg-white/10 p-3.5 ring-1 ring-white/10">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[10px] uppercase tracking-wider text-white/50">Budget</span>
        <span className="text-xs text-white/70">
          {budget.per_traveler_display}
          <span className="text-white/40"> / traveler</span>
        </span>
      </div>
      <div className="mt-1 flex items-baseline gap-1.5">
        <span className="text-lg font-semibold text-white">{budget.spent_display}</span>
        {hasTarget && <span className="text-sm text-white/60">/ {budget.target_display}</span>}
      </div>
      {hasTarget && (
        <>
          <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-white/15">
            <div
              className={`h-full rounded-full ${barColor} transition-all duration-500`}
              style={{ width: `${Math.min(pct, 100)}%` }}
            />
          </div>
          <div className="mt-1.5 flex items-center justify-between text-xs">
            <span className={over ? "font-medium text-rose-200" : "text-white/70"}>
              {over
                ? `${budget.remaining_display} over budget`
                : `${budget.remaining_display} left`}
            </span>
            <span className="text-white/50">{pct}% used</span>
          </div>
        </>
      )}
      {segs.length > 0 && (
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          {segs.map((s) => (
            <span key={s.icon} className="chip bg-white/10 text-white/80">
              {s.icon} {money(s.value)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

const STATUS_BADGE: Record<string, string> = {
  draft: "bg-slate-100 text-slate-600",
  finalized: "bg-emerald-50 text-emerald-700",
  booked: "bg-brand/10 text-brand",
};

// "My trips" switcher: remembered trips persist across logins, so the user can
// resume any saved plan instead of starting over. Self-contained — it fetches
// its own list, re-fetching whenever the active trip changes (version token).
export function TripSwitcher({
  version,
  onSwitched,
}: {
  version: number;
  onSwitched: () => void;
}) {
  const [trips, setTrips] = useState<SavedTrip[]>([]);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let alive = true;
    fetchSavedTrips()
      .then((t) => alive && setTrips(t))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [version]);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  if (trips.length === 0) return null;

  const onPick = async (tripId: string) => {
    setOpen(false);
    const v = await switchTrip(tripId);
    if (v) onSwitched();
  };

  const onRemove = async (e: React.MouseEvent, tripId: string) => {
    e.stopPropagation();
    const remaining = await deleteTrip(tripId);
    setTrips(remaining);
    onSwitched();
  };

  const active = trips.find((t) => t.is_active);
  const label = active ? active.destination || "Untitled" : "My trips";

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="pill bg-white text-ink ring-1 ring-slate-200 transition hover:bg-slate-50"
        title="Switch between your saved trips"
      >
        <span>{"\uD83E\uDDF3"}</span>
        <span className="max-w-[9rem] truncate">{label}</span>
        <span className="text-slate-400">({trips.length})</span>
        <span className="text-slate-400">▾</span>
      </button>
      {open && (
        <div className="absolute left-0 top-full z-30 mt-1.5 max-h-80 w-72 overflow-y-auto rounded-2xl bg-white p-1.5 shadow-pop ring-1 ring-slate-100">
          {trips.map((t) => {
            const dates =
              t.departure_date && t.return_date
                ? `${t.departure_date} → ${t.return_date}`
                : t.departure_date || "dates TBD";
            const badge = STATUS_BADGE[t.status] || STATUS_BADGE.draft;
            return (
              <button
                key={t.trip_id}
                type="button"
                onClick={() => onPick(t.trip_id)}
                className={`flex w-full items-start gap-2 rounded-xl px-2.5 py-2 text-left transition hover:bg-slate-50 ${
                  t.is_active ? "bg-brand/5 ring-1 ring-brand/20" : ""
                }`}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <span className="truncate text-sm font-medium text-ink">
                      {t.destination || "Untitled trip"}
                    </span>
                    <span className={`chip ${badge}`}>{t.status}</span>
                  </div>
                  <div className="truncate text-xs text-muted">{dates}</div>
                  <div className="mt-0.5 text-[11px] text-slate-400">
                    {t.counts.flights}✈ · {t.counts.hotels}🏨 · {t.counts.activities}🎯
                  </div>
                </div>
                <span
                  role="button"
                  tabIndex={0}
                  onClick={(e) => onRemove(e, t.trip_id)}
                  className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full text-slate-300 transition hover:bg-rose-50 hover:text-rose-500"
                  title="Delete this saved trip"
                >
                  ✕
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
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
  const heroHeight = focused ? "h-72" : "h-52";
  return (
    <article className="card card-hover group">
      {photos.length > 0 ? (
        <div className="relative">
          <button onClick={() => onOpenPhoto(photos, 0, item.name)} className="block w-full">
            <img
              src={photos[0]}
              alt={item.name}
              className={`w-full ${heroHeight} object-cover transition-transform duration-700 group-hover:scale-[1.03]`}
            />
          </button>

          {/* Top-left "kind" badge so the eye can scan the list quickly. */}
          <span className="pill absolute left-3 top-3 bg-white/95 text-ink shadow-sm backdrop-blur">
            {icon}
            <span className="capitalize">{item.kind === "attraction" ? "activity" : item.kind}</span>
          </span>

          {item.selected && (
            <span className="pill absolute right-3 top-3 bg-emerald-500/95 text-white shadow-sm backdrop-blur">
              ✓ In trip
            </span>
          )}

          {photos.length > 1 && (
            <button
              onClick={() => onOpenPhoto(photos, 0, item.name)}
              className="absolute bottom-3 right-3 rounded-full bg-black/55 px-3 py-1 text-xs font-medium text-white backdrop-blur transition hover:bg-black/75"
            >
              📷 {photos.length} photos
            </button>
          )}
        </div>
      ) : null}

      <div className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 className="display truncate text-base font-semibold text-ink">
              {item.name}
            </h3>
            {item.address && (
              <p className="mt-0.5 truncate text-xs text-muted">{item.address}</p>
            )}
          </div>
          <Stars rating={item.rating} count={item.review_count} />
        </div>

        {focused && photos.length > 1 && (
          <div className="mt-3 flex gap-2 overflow-x-auto pb-1">
            {photos.slice(1).map((p, i) => (
              <button
                key={i}
                onClick={() => onOpenPhoto(photos, i + 1, item.name)}
                className="flex-shrink-0 overflow-hidden rounded-2xl"
              >
                <img
                  src={p}
                  alt={item.name}
                  className="h-24 w-32 object-cover transition-transform duration-300 hover:scale-110"
                />
              </button>
            ))}
          </div>
        )}

        {item.summary && (
          <p className="mt-3 text-sm leading-relaxed text-slate-600">{item.summary}</p>
        )}

        {item.reviews.length > 0 && (
          <div className="mt-3 space-y-2">
            {item.reviews.slice(0, focused ? 4 : 2).map((r, i) => (
              <blockquote
                key={i}
                className="rounded-2xl border border-slate-100 bg-slate-50/70 px-3 py-2"
              >
                <p className="text-xs italic text-slate-600">“{r.text}”</p>
                <footer className="mt-1 text-[11px] text-muted">— {r.author}</footer>
              </blockquote>
            ))}
          </div>
        )}

        <div className="mt-4 flex flex-wrap items-center gap-2">
          {!focused && (
            <button
              onClick={() => onFocus(item.kind, item.name)}
              title="See this item on its own with all photos and reviews"
              className="btn-ghost"
            >
              View details
            </button>
          )}

          {isSelectable(item.kind) &&
            (item.selected ? (
              <button
                onClick={() => onDeselect(item.kind, item.name)}
                title="Remove this from your saved trip picks"
                className="group/btn inline-flex items-center justify-center gap-1.5 rounded-full bg-emerald-50 px-4 py-1.5 text-xs font-semibold text-emerald-700 ring-1 ring-emerald-200 transition hover:bg-rose-50 hover:text-rose-700 hover:ring-rose-200"
              >
                <span className="group-hover/btn:hidden">✓ Saved</span>
                <span className="hidden group-hover/btn:inline">✕ Remove</span>
              </button>
            ) : (
              <button
                onClick={() => onSelect(item.kind, item.name)}
                title="Save this to your trip so the agent keeps it in the plan"
                className="btn-primary px-4 py-1.5 text-xs"
              >
                + Add to trip
              </button>
            ))}

          {item.website && (
            <a
              href={item.website}
              target="_blank"
              rel="noreferrer"
              className="btn-ghost"
            >
              Website ↗
            </a>
          )}
        </div>
      </div>
    </article>
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
    <div className="flex gap-2 overflow-x-auto pb-1.5">
      <button
        onClick={onClearFocus}
        className={`flex-shrink-0 rounded-full px-4 py-1.5 text-xs font-semibold transition ${
          focusIndex < 0
            ? "bg-ink text-white shadow-sm"
            : "bg-white text-slate-700 ring-1 ring-slate-200 hover:ring-ink"
        }`}
      >
        🗺️ Whole trip
      </button>
      {navList.map((n, i) => (
        <button
          key={i}
          onClick={() => onFocus(n.kind, n.name)}
          className={`flex-shrink-0 rounded-full px-4 py-1.5 text-xs font-medium transition ${
            i === focusIndex
              ? "bg-brand text-white shadow-sm"
              : "bg-white text-slate-700 ring-1 ring-slate-200 hover:ring-brand"
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
  tripVersion,
  onSwitched,
  hideSwitcher = false,
}: Props) {
  const [lb, setLb] = useState<{ photos: string[]; index: number; alt: string }>({
    photos: [],
    index: -1,
    alt: "",
  });
  const openPhoto = (photos: string[], index: number, alt: string) =>
    setLb({ photos, index, alt });
  const [shareState, setShareState] = useState<{ url: string; copied: boolean } | null>(
    null,
  );
  const onShare = async () => {
    try {
      const url = await shareActiveTrip();
      let copied = false;
      try {
        await navigator.clipboard.writeText(url);
        copied = true;
      } catch {
        // Clipboard may be blocked (non-HTTPS, permissions) — still show the URL.
      }
      setShareState({ url, copied });
    } catch (err) {
      setShareState({ url: String((err as Error).message || err), copied: false });
    }
  };

  if (loading && !view) {
    return (
      <div className="grid h-full place-items-center bg-surface p-6 text-sm text-muted">
        Loading your trip…
      </div>
    );
  }
  if (!view || !view.has_trip) {
    return (
      <div className="flex h-full flex-col bg-surface">
        {!hideSwitcher && (
          <div className="flex items-center border-b border-slate-100 bg-white/85 px-4 py-2.5 backdrop-blur">
            <TripSwitcher version={tripVersion} onSwitched={onSwitched} />
          </div>
        )}
        <div className="grid flex-1 place-items-center p-8 text-center">
          <div className="max-w-sm">
            <div className="mx-auto mb-3 grid h-14 w-14 place-items-center rounded-3xl bg-white text-2xl shadow-card ring-1 ring-slate-100">
              🌍
            </div>
            <p className="display text-base font-semibold text-ink">
              Your trip canvas is empty
            </p>
            <p className="mt-1 text-sm text-muted">
              {view?.empty_message ||
                "Tell the chat where and when you'd like to go — I'll fill this side with photos, ratings and details."}
            </p>
          </div>
        </div>
      </div>
    );
  }

  const ov = view.overview;
  const focused = !!view.focus;
  const total = navList.length;

  return (
    <div className="flex h-full flex-col bg-surface">
      {!focused && !hideSwitcher && (
        <div className="sticky top-0 z-10 flex items-center border-b border-slate-100 bg-white/85 px-4 py-2.5 backdrop-blur">
          <TripSwitcher version={tripVersion} onSwitched={onSwitched} />
        </div>
      )}
      {focused && (
        <div className="sticky top-0 z-10 flex items-center gap-2 border-b border-slate-100 bg-white/85 px-4 py-2.5 backdrop-blur">
          <button onClick={onClearFocus} className="btn-ghost">
            ← Whole trip
          </button>
          {total > 1 && (
            <div className="ml-auto flex items-center gap-1.5">
              <button
                onClick={() => onStep(-1)}
                className="grid h-8 w-8 place-items-center rounded-full bg-white text-slate-600 ring-1 ring-slate-200 transition hover:bg-slate-50 hover:text-ink"
                title="Previous"
              >
                ‹
              </button>
              <span className="text-xs font-medium text-muted">
                {focusIndex >= 0 ? focusIndex + 1 : "–"} / {total}
              </span>
              <button
                onClick={() => onStep(1)}
                className="grid h-8 w-8 place-items-center rounded-full bg-white text-slate-600 ring-1 ring-slate-200 transition hover:bg-slate-50 hover:text-ink"
                title="Next"
              >
                ›
              </button>
            </div>
          )}
        </div>
      )}

      <div className="flex-1 space-y-4 overflow-y-auto p-5">
        {/* Hero summary — high-contrast, travel-magazine vibe. */}
        <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-ink via-slate-800 to-slate-900 p-5 text-white shadow-card">
          <div
            className="pointer-events-none absolute inset-0 opacity-20"
            style={{
              backgroundImage:
                "radial-gradient(60% 80% at 110% -10%, rgba(225,29,72,0.5), transparent 60%), radial-gradient(60% 80% at -10% 110%, rgba(15,118,110,0.4), transparent 60%)",
            }}
          />
          <div className="relative">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-white/60">
              Your trip
            </p>
            <div className="mt-1 flex items-start justify-between gap-3">
              <h2 className="display text-2xl font-semibold leading-tight">
                {view.title}
              </h2>
              <div className="mt-1 flex shrink-0 flex-col items-end gap-1.5">
                <div className="flex flex-wrap items-center justify-end gap-1.5">
                  <button
                    type="button"
                    onClick={onShare}
                    title="Get a read-only share link anyone can open"
                    className="pill bg-white/10 text-white ring-1 ring-white/20 transition hover:bg-white/20"
                  >
                    <span>{"\uD83D\uDD17"}</span>
                    <span>Share</span>
                  </button>
                  <a
                    href={tripIcsUrl()}
                    download
                    title="Download .ics for your calendar"
                    className="pill bg-white/10 text-white ring-1 ring-white/20 transition hover:bg-white/20"
                  >
                    <span>{"\uD83D\uDCC5"}</span>
                    <span>Add to calendar</span>
                  </a>
                </div>
                {shareState && (
                  <div className="max-w-[18rem] truncate rounded-xl bg-white/10 px-2.5 py-1 text-[10px] text-white/85 ring-1 ring-white/20">
                    {shareState.copied
                      ? "Link copied to clipboard"
                      : shareState.url}
                  </div>
                )}
              </div>
            </div>

            <div className="mt-4 grid grid-cols-2 gap-x-5 gap-y-2 text-sm">
              {ov.origin && (
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-white/50">From</div>
                  <div className="font-medium">{ov.origin}</div>
                </div>
              )}
              {ov.destination && (
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-white/50">To</div>
                  <div className="font-medium">{ov.destination}</div>
                </div>
              )}
              {ov.departure_date && (
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-white/50">
                    Depart
                  </div>
                  <div className="font-medium">{ov.departure_date}</div>
                </div>
              )}
              {ov.return_date && (
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-white/50">
                    Return
                  </div>
                  <div className="font-medium">{ov.return_date}</div>
                </div>
              )}
              <div>
                <div className="text-[10px] uppercase tracking-wider text-white/50">
                  Travelers
                </div>
                <div className="font-medium">{ov.travelers}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wider text-white/50">
                  Status
                </div>
                <div className="font-medium capitalize">{ov.status}</div>
              </div>
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-white/10 pt-4">
              <span className="chip bg-white/10 text-white/90">
                ✈️ {ov.counts.flights} flights
              </span>
              <span className="chip bg-white/10 text-white/90">
                🏨 {ov.counts.hotels} hotels
              </span>
              <span className="chip bg-white/10 text-white/90">
                🎯 {ov.counts.activities} activities
              </span>
              {ov.counts.days > 0 && (
                <span className="chip bg-white/10 text-white/90">
                  📅 {ov.counts.days} days
                </span>
              )}
              {ov.total_cost_display && (
                <span className="ml-auto rounded-full bg-white px-3.5 py-1 text-sm font-semibold text-ink shadow-sm">
                  {ov.total_cost_display}
                </span>
              )}
            </div>

            {ov.budget && <BudgetMeter budget={ov.budget} />}

            {ov.family_pills && ov.family_pills.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {ov.family_pills.map((pill) => (
                  <span
                    key={pill}
                    className="chip bg-accent/20 text-white/95 ring-1 ring-white/15"
                    title="Inferred from your saved family / dietary / accessibility preferences"
                  >
                    {pill}
                  </span>
                ))}
              </div>
            )}
          </div>
        </section>

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
          <p className="rounded-2xl bg-amber-50 px-4 py-2.5 text-xs font-medium text-amber-800 ring-1 ring-amber-100">
            ✨ Popular spots in {ov.destination || "your destination"} — nothing
            picked yet. Tap “+ Add to trip” on any card to save it.
          </p>
        )}

        {!focused && ov.destination && (
          <DestinationOverview destination={ov.destination} onFocus={onFocus} />
        )}

        <div className="space-y-4">
          {view.items.length === 0 ? (
            <p className="rounded-2xl bg-white px-3 py-6 text-center text-sm text-muted ring-1 ring-slate-100">
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
