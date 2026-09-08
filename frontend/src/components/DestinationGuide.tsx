import { BedDouble, ChevronRight, Compass, MapPin, Star, Utensils } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { fetchPlaceGuide } from "../api";
import type { PlaceRow } from "../types";
import type { KindTab } from "./GuideScopeBar";

// Lab 13 — paged "Contextual explorer" destination guide (option A + search).
// Mixed highlights balanced across the route by default; the scope (city, place
// type, search) is owned by TripPanel so it stays visible while a place is
// focused. Focusing a place surfaces same-city, same-type alternatives.
// Selection stays in the focused inspector (ItemCard) — rows here are navigational.

const KIND_ICON: Record<string, typeof Compass> = {
  hotel: BedDouble,
  restaurant: Utensils,
  attraction: Compass,
};

function kindPlural(kind: string): string {
  if (kind === "hotel") return "hotels";
  if (kind === "restaurant") return "restaurants";
  return "attractions";
}

interface Props {
  destination: string;
  tripVersion: number;
  /** When set, render same-city/same-kind alternatives instead of the browser. */
  focus?: { kind: string; name: string; city?: string } | null;
  onFocus: (kind: string, name: string) => void;
  city?: string;
  kind?: KindTab;
  query?: string;
  onCities?: (cities: string[]) => void;
}

function GuideRow({ row, onFocus }: { row: PlaceRow; onFocus: (kind: string, name: string) => void }) {
  const Icon = KIND_ICON[row.kind] ?? Compass;
  return (
    <button
      type="button"
      onClick={() => onFocus(row.kind, row.name)}
      className="group grid w-full grid-cols-[4.5rem_minmax(0,1fr)_auto] gap-3 border-b border-slate-100 py-3 text-left last:border-b-0"
    >
      {row.photo ? (
        <img src={row.photo} alt="" className="h-[4.5rem] w-[4.5rem] rounded-md object-cover" />
      ) : (
        <span className="grid h-[4.5rem] w-[4.5rem] place-items-center rounded-md bg-slate-100 text-slate-400">
          <Icon size={20} aria-hidden />
        </span>
      )}
      <span className="min-w-0 self-center">
        <span className="flex items-center gap-1.5">
          <strong className="truncate text-sm text-ink">{row.name}</strong>
          {row.selected && (
            <span className="rounded-sm bg-emerald-50 px-1.5 py-0.5 text-[9px] font-bold text-emerald-700">
              IN TRIP
            </span>
          )}
        </span>
        <span className="mt-1 flex items-center gap-1 text-[11px] text-slate-500">
          <MapPin size={11} aria-hidden />
          <span className="truncate">{[row.city, row.address].filter(Boolean).join(" · ") || "Nearby"}</span>
        </span>
      </span>
      <span className="flex items-center gap-1 self-center text-xs font-semibold text-amber-700">
        {row.rating != null && (
          <>
            <Star size={12} fill="currentColor" aria-hidden />
            {row.rating.toFixed(1)}
          </>
        )}
        <ChevronRight size={13} className="ml-1 text-slate-300 group-hover:text-brand" aria-hidden />
      </span>
    </button>
  );
}

export default function DestinationGuide({
  destination,
  tripVersion,
  focus,
  onFocus,
  city = "all",
  kind = "highlights",
  query: rawQuery = "",
  onCities,
}: Props) {
  const alternatives = !!focus?.name;
  const [query, setQuery] = useState(rawQuery.trim());
  const [rows, setRows] = useState<PlaceRow[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [remaining, setRemaining] = useState(0);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const controller = useRef<AbortController | null>(null);

  // Debounce the search box so typing doesn't fire a request per keystroke.
  useEffect(() => {
    const handle = setTimeout(() => setQuery(rawQuery.trim()), 250);
    return () => clearTimeout(handle);
  }, [rawQuery]);

  const focusKey = alternatives ? `${focus!.kind}:${focus!.name.toLowerCase()}` : "";

  const load = useCallback(
    async (nextCursor: string | null, append: boolean) => {
      controller.current?.abort();
      const ctrl = new AbortController();
      controller.current = ctrl;
      // Clear rows the instant the scope changes so a slow fetch never leaves the
      // previous filter's places on screen (they'd look like they ignore the filter).
      if (!append) setRows([]);
      setLoading(true);
      try {
        const page = await fetchPlaceGuide(
          {
            city: alternatives || city === "all" ? undefined : city,
            kind: alternatives || kind === "highlights" ? undefined : kind,
            query: alternatives ? undefined : query || undefined,
            cursor: nextCursor,
            focus: alternatives ? { kind: focus!.kind, name: focus!.name } : null,
          },
          ctrl.signal,
        );
        if (controller.current !== ctrl) return;
        setRows((prev) => (append ? [...prev, ...page.items] : page.items));
        setCursor(page.cursor);
        setRemaining(page.remaining_count);
        setTotal(page.total_count);
        if (!alternatives) onCities?.(page.available_cities);
      } catch (error) {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          console.error("Could not load destination guide", error);
        }
      } finally {
        if (controller.current === ctrl) setLoading(false);
      }
    },
    [alternatives, city, kind, query, focus, onCities],
  );

  // Reset and fetch the first page whenever the scope, focus or trip changes.
  useEffect(() => {
    void load(null, false);
    return () => controller.current?.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [city, kind, query, focusKey, tripVersion]);

  const showMore = () => {
    if (cursor) void load(cursor, true);
  };

  if (alternatives) {
    if (!loading && rows.length === 0) return null;
    return (
      <div data-guide="alternatives" className="mt-5 border-t border-slate-100 pt-4">
        <p className="text-[10px] font-bold uppercase text-slate-400">Compare nearby</p>
        <h2 className="mt-0.5 text-sm font-semibold text-ink">
          Other {kindPlural(focus!.kind)}
          {focus?.city ? ` in ${focus.city}` : ""}
        </h2>
        <div className="mt-2">
          {rows.map((row) => (
            <GuideRow key={`${row.kind}:${row.name.toLowerCase()}`} row={row} onFocus={onFocus} />
          ))}
        </div>
        {cursor && (
          <button
            type="button"
            onClick={showMore}
            className="mt-3 h-9 w-full rounded-md bg-slate-50 text-xs font-semibold text-slate-600 hover:bg-slate-100"
          >
            Show {Math.min(6, remaining)} more
          </button>
        )}
      </div>
    );
  }

  const cityLabel = city === "all" ? "" : city;
  return (
    <div data-guide="browse">
      <div className="py-3">
        <p className="text-[10px] font-bold uppercase text-brand">
          {kind === "highlights" ? "Curated across your route" : cityLabel || "Across your route"}
        </p>
        <h2 className="mt-0.5 text-base font-semibold text-ink">
          {kind === "highlights"
            ? `${destination || "Trip"} highlights`
            : kindPlural(kind).replace(/^./, (letter) => letter.toUpperCase())}
        </h2>
        <p className="mt-1 text-xs text-slate-500">
          {total} grounded {total === 1 ? "place" : "places"} · showing {rows.length}
        </p>
      </div>

      {rows.length === 0 && !loading ? (
        <p className="px-3 py-6 text-center text-sm text-muted">No places match these filters.</p>
      ) : rows.length === 0 && loading ? (
        <div aria-hidden>
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="grid grid-cols-[4.5rem_minmax(0,1fr)] gap-3 border-b border-slate-100 py-3 last:border-b-0">
              <span className="h-[4.5rem] w-[4.5rem] animate-pulse rounded-md bg-slate-100" />
              <span className="flex flex-col justify-center gap-2">
                <span className="h-3 w-2/3 animate-pulse rounded bg-slate-100" />
                <span className="h-2.5 w-1/2 animate-pulse rounded bg-slate-100" />
              </span>
            </div>
          ))}
        </div>
      ) : (
        <div>
          {rows.map((row) => (
            <GuideRow key={`${row.kind}:${row.name.toLowerCase()}`} row={row} onFocus={onFocus} />
          ))}
        </div>
      )}

      {cursor && (
        <button
          type="button"
          onClick={showMore}
          className="mt-3 h-9 w-full rounded-md bg-slate-50 text-xs font-semibold text-slate-600 hover:bg-slate-100"
        >
          Show {Math.min(6, remaining)} more
        </button>
      )}
    </div>
  );
}
