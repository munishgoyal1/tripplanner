import { ChevronLeft, ChevronRight, LayoutGrid } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { type DeselectItemOptions, type SelectItemOptions } from "../api";
import type { TripItem, TripView, TripWorkspaceView } from "../types";
import DecisionPanel from "./DecisionPanel";
import DestinationGuide from "./DestinationGuide";
import DestinationOverview from "./DestinationOverview";
import GuideScopeBar, { type KindTab } from "./GuideScopeBar";
import Lightbox from "./Lightbox";
import PlaceTripActions from "./PlaceTripActions";
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
  onSelect: (
    kind: string,
    name: string,
    options?: SelectItemOptions,
  ) => void | Promise<boolean>;
  onDeselect: (
    kind: string,
    name: string,
    options?: DeselectItemOptions,
  ) => void | Promise<boolean>;
  focusContext?: { day?: number; stop?: number } | null;
  tripVersion: number;
  onSwitched: (tripId?: string, workspace?: TripWorkspaceView | null) => void;
  /** Applying a traveller's overrule goes through the workspace state owner. */
  onDecisionApplied?: (view: TripView, message: string, warnings: string[]) => void;
  onDecisionStale?: (view: TripView | undefined, message: string) => void;
  onDecisionError?: (message: string) => void;
  /** Hide the internal saved-trips switcher (RightRail renders it persistently). */
  hideSwitcher?: boolean;
}

const ICONS: Record<string, string> = {
  hotel: "\u{1F3E8}",
  activity: "\u{1F3AF}",
  attraction: "\u{1F3AF}",
  flight: "\u2708\uFE0F",
};

// Mirrors browse_kind() server-side: hotel aliases get the stay picker, every
// other real place (attraction, restaurant, meal, ...) gets add/remove actions.
const HOTEL_KINDS = ["hotel", "lodging", "stay", "accommodation"];
const PLACE_KINDS = ["activity", "attraction", "restaurant", "meal", "food", "dining", "cafe", "eatery"];

function isHotel(kind: string): boolean {
  return HOTEL_KINDS.includes(kind);
}

function isSelectable(kind: string): boolean {
  return isHotel(kind) || PLACE_KINDS.includes(kind);
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

function ItemCard({
  item,
  focused,
  onFocus,
  onSelect,
  onHotelStay,
  onDeselect,
  focusContext,
  availableDays,
  onOpenPhoto,
}: {
  item: TripItem;
  focused: boolean;
  onFocus: (kind: string, name: string) => void;
  onSelect: (
    kind: string,
    name: string,
    options?: SelectItemOptions,
  ) => void | Promise<boolean>;
  onHotelStay: (name: string) => void;
  onDeselect: (
    kind: string,
    name: string,
    options?: DeselectItemOptions,
  ) => void | Promise<boolean>;
  focusContext?: { day?: number; stop?: number } | null;
  availableDays: number[];
  onOpenPhoto: (photos: string[], index: number, alt: string) => void;
}) {
  const icon = ICONS[item.kind] ?? "\u{1F4CD}";
  const photos = item.photos;
  const [addDay, setAddDay] = useState<string>("auto");
  return (
    <article className={focused
      ? "group overflow-hidden bg-white"
      : "group grid grid-cols-[5.5rem_minmax(0,1fr)] gap-3 border-b border-slate-100 py-3 last:border-b-0"}
    >
      {photos.length > 0 ? (
        <div className={`relative ${focused ? "" : "self-start"}`}>
          <button onClick={() => onOpenPhoto(photos, 0, item.name)} className="block w-full">
            <img
              src={photos[0]}
              alt={item.name}
              className={`${focused ? "h-72 w-full" : "h-[5.5rem] w-[5.5rem] rounded-lg"} object-cover transition-transform duration-500 group-hover:scale-[1.02]`}
            />
          </button>

          {focused && (
            <span className="pill absolute left-3 top-3 bg-white/95 text-ink shadow-sm backdrop-blur">
              {icon}
              <span className="capitalize">{item.kind === "attraction" ? "activity" : item.kind}</span>
            </span>
          )}

          {focused && photos.length > 1 && (
            <button
              onClick={() => onOpenPhoto(photos, 0, item.name)}
              className="absolute bottom-3 right-3 rounded-full bg-black/55 px-3 py-1 text-xs font-medium text-white backdrop-blur transition hover:bg-black/75"
            >
              📷 {photos.length} photos
            </button>
          )}
        </div>
      ) : (
        !focused && <div className="grid h-[5.5rem] w-[5.5rem] place-items-center rounded-lg bg-slate-100 text-xl">{icon}</div>
      )}

      <div className={focused ? "p-4" : "min-w-0 py-0.5"}>
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
          <p className={`${focused ? "mt-3 leading-relaxed" : "mt-1 line-clamp-2 leading-snug"} text-sm text-slate-600`}>{item.summary}</p>
        )}

        {focused && item.reviews.length > 0 && (
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

        <div className={`${focused ? "mt-4" : "mt-2"} flex flex-wrap items-center gap-2`}>
          {!focused && (
            <button
              onClick={() => onFocus(item.kind, item.name)}
              title="See this item on its own with all photos and reviews"
              className="text-xs font-medium text-brand hover:text-brand/80"
            >
              View details
            </button>
          )}

          {isSelectable(item.kind) &&
            (item.selected ? (
              <PlaceTripActions
                kind={item.kind}
                name={item.name}
                occurrences={item.occurrences}
                availableDays={availableDays}
                preferredDay={focusContext?.day}
                onMove={onSelect}
                onRemove={onDeselect}
              />
            ) : isHotel(item.kind) ? (
              <button
                onClick={() => onHotelStay(item.name)}
                title="Save this to your trip so the agent keeps it in the plan"
                className="btn-primary px-4 py-1.5 text-xs"
              >
                + Add stay
              </button>
            ) : focused && availableDays.length > 0 ? (
              <div className="flex items-center gap-2">
                <select
                  value={addDay}
                  onChange={(event) => setAddDay(event.target.value)}
                  aria-label={`Choose day to add ${item.name}`}
                  className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700"
                >
                  <option value="auto">Best day</option>
                  {availableDays.map((day) => (
                    <option key={day} value={day}>Day {day}</option>
                  ))}
                </select>
                <button
                  onClick={() =>
                    onSelect(
                      item.kind,
                      item.name,
                      addDay === "auto" ? undefined : { day: Number(addDay) },
                    )
                  }
                  title="Save this to your trip so the agent keeps it in the plan"
                  className="btn-primary px-4 py-1.5 text-xs"
                >
                  + Add to trip
                </button>
              </div>
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
  focusContext,
  tripVersion,
  onSwitched,
  onDecisionApplied,
  onDecisionStale,
  onDecisionError,
  hideSwitcher = false,
}: Props) {
  const [lb, setLb] = useState<{ photos: string[]; index: number; alt: string }>({
    photos: [],
    index: -1,
    alt: "",
  });
  const openPhoto = (photos: string[], index: number, alt: string) =>
    setLb({ photos, index, alt });
  const [pendingHotel, setPendingHotel] = useState<string | null>(null);
  const [cities, setCities] = useState<string[]>([]);
  const [city, setCity] = useState("all");
  const [kind, setKind] = useState<KindTab>("highlights");
  const [query, setQuery] = useState("");
  const handleCities = useCallback((next: string[]) => setCities(next), []);

  // The guide scope belongs to the trip that was showing. Reset it during
  // render when the trip changes: an effect would paint one frame of the old
  // trip's city chips and filter, which reads as a half-finished switch. The
  // tracker must be state, not a ref — React can discard a concurrent render,
  // and a mutated ref would then swallow the reset that went with it.
  const destination = view?.overview?.destination ?? "";
  const [scopedDestination, setScopedDestination] = useState(destination);
  if (scopedDestination !== destination) {
    setScopedDestination(destination);
    setCities([]);
    setCity("all");
    setKind("highlights");
    setQuery("");
  }

  // Retuning the scope means "show me that list", so it also leaves the focused place.
  const rescope = <T,>(apply: (value: T) => void) => (value: T) => {
    apply(value);
    if (view?.focus) onClearFocus();
  };

  if (loading && !view) {
    return (
      <div className="grid h-full place-items-center bg-white p-6 text-sm text-muted">
        Loading your trip…
      </div>
    );
  }
  if (!view || !view.has_trip || !view.overview) {
    return (
      <div className="flex h-full flex-col bg-white">
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
    <div className="flex h-full flex-col bg-white">
      <div className="sticky top-0 z-10 border-b border-slate-100 bg-white/85 px-4 py-2.5 backdrop-blur">
        {!hideSwitcher && (
          <div className="mb-2.5 flex items-center">
            <TripSwitcher version={tripVersion} onSwitched={onSwitched} />
          </div>
        )}
        <GuideScopeBar
          cities={cities}
          city={city}
          kind={kind}
          query={query}
          onCity={rescope(setCity)}
          onKind={rescope(setKind)}
          onQuery={rescope(setQuery)}
        />
        {focused && (
          <div className="mt-2.5 flex items-center gap-2">
            <button
              onClick={onClearFocus}
              className="inline-flex h-7 shrink-0 items-center gap-1.5 rounded-md bg-slate-50 px-2.5 text-[11px] font-semibold text-slate-600 hover:bg-slate-100"
            >
              <LayoutGrid size={12} aria-hidden /> All places
            </button>
            <span className="truncate text-[11px] font-semibold text-ink">
              {view.items[0]?.name ?? view.focus?.name}
            </span>
            {total > 1 && (
              <div className="ml-auto flex shrink-0 items-center gap-1">
                <button
                  onClick={() => onStep(-1)}
                  className="grid h-7 w-7 place-items-center rounded-full text-slate-500 ring-1 ring-slate-200 transition hover:bg-slate-50 hover:text-ink"
                  title="Previous"
                >
                  <ChevronLeft size={15} aria-hidden />
                </button>
                <span className="text-[11px] font-medium text-muted">
                  {focusIndex >= 0 ? focusIndex + 1 : "–"} / {total}
                </span>
                <button
                  onClick={() => onStep(1)}
                  className="grid h-7 w-7 place-items-center rounded-full text-slate-500 ring-1 ring-slate-200 transition hover:bg-slate-50 hover:text-ink"
                  title="Next"
                >
                  <ChevronRight size={15} aria-hidden />
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto">
        {view.is_fallback && (
          <p className="mx-4 mt-4 rounded-lg bg-amber-50 px-3 py-2.5 text-xs font-medium text-amber-800 ring-1 ring-amber-100">
            ✨ Popular spots in {ov.destination || "your destination"} — nothing
            picked yet. Tap “+ Add to trip” on any card to save it.
          </p>
        )}

        {!focused && ov.destination && (
          <DestinationOverview destination={ov.destination} />
        )}

        {!focused && onDecisionApplied && (
          <DecisionPanel
            decisions={view.decisions ?? []}
            updatedAt={view.updated_at}
            baseline={ov.cost_baseline}
            onApplied={onDecisionApplied}
            onStale={onDecisionStale ?? (() => undefined)}
            onError={onDecisionError ?? (() => undefined)}
          />
        )}

        <section className="border-t border-slate-100 px-4 py-4">
          {focused && (
            view.items.length === 0 ? (
              <p className="px-3 py-6 text-center text-sm text-muted">
                Nothing to show for this item.
              </p>
            ) : (
              <>
                <ItemCard
                  item={view.items[0]}
                  focused
                  onFocus={onFocus}
                  onSelect={onSelect}
                  onHotelStay={(name) => setPendingHotel(name)}
                  onDeselect={onDeselect}
                  focusContext={focusContext}
                  availableDays={view.available_days}
                  onOpenPhoto={openPhoto}
                />
                <DestinationGuide
                  destination={ov.destination}
                  tripVersion={tripVersion}
                  focus={{
                    kind: view.items[0].kind,
                    name: view.items[0].name,
                    city: view.items[0].city,
                  }}
                  onFocus={onFocus}
                />
              </>
            )
          )}
          {/* Keep the browse guide mounted (hidden while a place is focused) so
              returning to it — e.g. clicking a day row after a stop — is instant
              instead of blanking out and refetching the whole guide. */}
          <div className={focused ? "hidden" : ""}>
            <DestinationGuide
              destination={ov.destination}
              tripVersion={tripVersion}
              focus={null}
              onFocus={onFocus}
              city={city}
              kind={kind}
              query={query}
              onCities={handleCities}
            />
          </div>
        </section>
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

