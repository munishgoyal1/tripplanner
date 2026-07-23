import { ArrowLeft, CalendarPlus, ChevronLeft, ChevronRight, FileDown, Link2 } from "lucide-react";
import { useEffect, useState } from "react";
import {
  shareActiveTrip,
  tripIcsUrl,
  type SelectItemOptions,
} from "../api";
import type { Budget, TripItem, TripView } from "../types";
import DestinationOverview from "./DestinationOverview";
import ExportModal from "./ExportModal";
import Lightbox from "./Lightbox";
import TripSwitcher from "./TripSwitcher";

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
  onSelect: (kind: string, name: string, options?: SelectItemOptions) => void;
  onDeselect: (kind: string, name: string) => void;
  tripVersion: number;
  onSwitched: (tripId?: string, view?: TripView | null) => void;
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
function ItemCard({
  item,
  focused,
  onFocus,
  onSelect,
  onHotelStay,
  onDeselect,
  onOpenPhoto,
}: {
  item: TripItem;
  focused: boolean;
  onFocus: (kind: string, name: string) => void;
  onSelect: (kind: string, name: string) => void;
  onHotelStay: (name: string) => void;
  onDeselect: (kind: string, name: string) => void;
  onOpenPhoto: (photos: string[], index: number, alt: string) => void;
}) {
  const icon = ICONS[item.kind] ?? "\u{1F4CD}";
  const photos = item.photos;
  const heroHeight = focused ? "h-72" : "h-52";
  // Two-step remove: the first click arms, a second confirms. Auto-disarms
  // after a moment so a stray click never drops a place from the trip.
  const [confirmRemove, setConfirmRemove] = useState(false);
  useEffect(() => {
    if (!confirmRemove) return;
    const t = setTimeout(() => setConfirmRemove(false), 3000);
    return () => clearTimeout(t);
  }, [confirmRemove]);
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
                onClick={() => {
                  if (confirmRemove) {
                    setConfirmRemove(false);
                    onDeselect(item.kind, item.name);
                  } else {
                    setConfirmRemove(true);
                  }
                }}
                title={
                  confirmRemove
                    ? "Click again to remove this from your trip"
                    : "Remove this from your trip"
                }
                className={
                  confirmRemove
                    ? "inline-flex items-center justify-center gap-1.5 rounded-full bg-rose-600 px-4 py-1.5 text-xs font-semibold text-white ring-1 ring-rose-600 transition"
                    : "group/btn inline-flex items-center justify-center gap-1.5 rounded-full bg-emerald-50 px-4 py-1.5 text-xs font-semibold text-emerald-700 ring-1 ring-emerald-200 transition hover:bg-rose-50 hover:text-rose-700 hover:ring-rose-200"
                }
              >
                {confirmRemove ? (
                  <span>Click again to remove</span>
                ) : (
                  <>
                    <span className="group-hover/btn:hidden">✓ In trip</span>
                    <span className="hidden group-hover/btn:inline">✕ Remove</span>
                  </>
                )}
              </button>
            ) : (
              <button
                onClick={() =>
                  item.kind === "hotel" ? onHotelStay(item.name) : onSelect(item.kind, item.name)
                }
                title="Save this to your trip so the agent keeps it in the plan"
                className="btn-primary px-4 py-1.5 text-xs"
              >
                {item.kind === "hotel" ? "+ Add stay" : "+ Add to trip"}
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
  const [showExport, setShowExport] = useState(false);
  const [pendingHotel, setPendingHotel] = useState<string | null>(null);
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
  const itineraryDays = Math.max(ov.counts.days || 0, 1);
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
            <ArrowLeft size={15} aria-hidden /> Whole trip
          </button>
          {total > 1 && (
            <div className="ml-auto flex items-center gap-1.5">
              <button
                onClick={() => onStep(-1)}
                className="grid h-8 w-8 place-items-center rounded-full bg-white text-slate-600 ring-1 ring-slate-200 transition hover:bg-slate-50 hover:text-ink"
                title="Previous"
              >
                <ChevronLeft size={17} aria-hidden />
              </button>
              <span className="text-xs font-medium text-muted">
                {focusIndex >= 0 ? focusIndex + 1 : "–"} / {total}
              </span>
              <button
                onClick={() => onStep(1)}
                className="grid h-8 w-8 place-items-center rounded-full bg-white text-slate-600 ring-1 ring-slate-200 transition hover:bg-slate-50 hover:text-ink"
                title="Next"
              >
                <ChevronRight size={17} aria-hidden />
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
                    onClick={() => setShowExport(true)}
                    title="Export day-wise itinerary for PDF/print or email"
                    className="pill bg-white/10 text-white ring-1 ring-white/20 transition hover:bg-white/20"
                  >
                    <FileDown size={14} aria-hidden />
                    <span>Export</span>
                  </button>
                  <button
                    type="button"
                    onClick={onShare}
                    title="Get a read-only share link anyone can open"
                    className="pill bg-white/10 text-white ring-1 ring-white/20 transition hover:bg-white/20"
                  >
                    <Link2 size={14} aria-hidden />
                    <span>Share</span>
                  </button>
                  <a
                    href={tripIcsUrl()}
                    download
                    title="Download .ics for your calendar"
                    className="pill bg-white/10 text-white ring-1 ring-white/20 transition hover:bg-white/20"
                  >
                    <CalendarPlus size={14} aria-hidden />
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

            {ov.constraints && ov.constraints.length > 0 && (
              <div className="mt-3 rounded-2xl bg-white/10 px-3 py-2 ring-1 ring-white/15">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-white/70">
                  Just for this trip
                </p>
                <ul className="mt-1 space-y-0.5">
                  {ov.constraints.map((c) => (
                    <li key={c} className="text-xs text-white/90">
                      • {c}
                    </li>
                  ))}
                </ul>
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

        {view.alerts && view.alerts.length > 0 && (
          <div className="rounded-2xl border border-amber-100 bg-amber-50 px-4 py-3 text-sm text-amber-900 ring-1 ring-amber-100">
            <div className="font-semibold">Trip update</div>
            <ul className="mt-1 space-y-1">
              {view.alerts.map((alert, index) => (
                <li key={index}>{alert}</li>
              ))}
            </ul>
          </div>
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
                onHotelStay={(name) => setPendingHotel(name)}
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
      {pendingHotel && (
        <HotelStayModal
          hotelName={pendingHotel}
          maxDay={itineraryDays}
          onClose={() => setPendingHotel(null)}
          onApply={(start, end, replace) => {
            onSelect("hotel", pendingHotel, {
              start_day: start,
              end_day: end,
              replace_stay: replace,
            });
            setPendingHotel(null);
          }}
        />
      )}
      {showExport && <ExportModal onClose={() => setShowExport(false)} />}
    </div>
  );
}

function HotelStayModal({
  hotelName,
  maxDay,
  onClose,
  onApply,
}: {
  hotelName: string;
  maxDay: number;
  onClose: () => void;
  onApply: (startDay: number, endDay: number, replaceExisting: boolean) => void;
}) {
  const [startDay, setStartDay] = useState(1);
  const [endDay, setEndDay] = useState(maxDay);
  const [replace, setReplace] = useState(true);

  useEffect(() => {
    setStartDay(1);
    setEndDay(maxDay);
  }, [maxDay, hotelName]);

  const start = Math.min(startDay, endDay);
  const end = Math.max(startDay, endDay);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div
        className="w-full max-w-md rounded-2xl bg-white p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-base font-semibold text-ink">Add hotel stay</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-ink">✕</button>
        </div>
        <p className="text-sm text-slate-600">
          Set where <span className="font-medium text-ink">{hotelName}</span> should apply in your itinerary.
        </p>
        <div className="mt-4 grid grid-cols-2 gap-3">
          <label className="text-sm">
            <span className="mb-1 block text-xs font-medium text-slate-500">From day</span>
            <select className="input" value={startDay} onChange={(e) => setStartDay(Number(e.target.value))}>
              {Array.from({ length: maxDay }, (_, i) => i + 1).map((d) => (
                <option key={d} value={d}>Day {d}</option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-xs font-medium text-slate-500">To day</span>
            <select className="input" value={endDay} onChange={(e) => setEndDay(Number(e.target.value))}>
              {Array.from({ length: maxDay }, (_, i) => i + 1).map((d) => (
                <option key={d} value={d}>Day {d}</option>
              ))}
            </select>
          </label>
        </div>
        <label className="mt-3 flex items-center gap-2 text-sm text-slate-700">
          <input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} />
          Replace any existing hotel stop in that range
        </label>
        <div className="mt-5 flex justify-end gap-2">
          <button onClick={onClose} className="btn-ghost">Cancel</button>
          <button onClick={() => onApply(start, end, replace)} className="btn-primary">
            Apply to Day {start}{start !== end ? `-${end}` : ""}
          </button>
        </div>
      </div>
    </div>
  );
}

