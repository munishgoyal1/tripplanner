import { useCallback, useEffect, useRef, useState } from "react";
import { fetchMapView, fetchMapsConfig } from "../api";
import type { MapAirport, MapView, MapPin } from "../types";

// Google Maps JS isn't typed (we don't ship @types/google.maps), so we lean on
// `any` for the map objects. The browser key is referrer-restricted server-side.
declare global {
  interface Window {
    google?: any;
    __gmapsReady__?: () => void;
  }
}

let loaderPromise: Promise<any> | null = null;

function loadGoogleMaps(key: string): Promise<any> {
  if (window.google?.maps) return Promise.resolve(window.google);
  if (loaderPromise) return loaderPromise;
  loaderPromise = new Promise((resolve, reject) => {
    window.__gmapsReady__ = () => resolve(window.google);
    const s = document.createElement("script");
    s.src =
      `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}` +
      `&callback=__gmapsReady__&v=weekly`;
    s.async = true;
    s.onerror = () => {
      loaderPromise = null;
      reject(new Error("Failed to load Google Maps"));
    };
    document.head.appendChild(s);
  });
  return loaderPromise;
}

// Teardrop pin as an SVG data URL, tinted per day, with a number label baked in.
function pinIcon(color: string, label: string): string {
  const svg = `
<svg xmlns="http://www.w3.org/2000/svg" width="34" height="44" viewBox="0 0 34 44">
  <path d="M17 0C7.6 0 0 7.6 0 17c0 12 17 27 17 27s17-15 17-27C34 7.6 26.4 0 17 0z"
        fill="${color}" stroke="white" stroke-width="2"/>
  <circle cx="17" cy="16" r="11" fill="white" fill-opacity="0.95"/>
  <text x="17" y="21" font-family="Inter,Arial,sans-serif" font-size="14"
        font-weight="700" text-anchor="middle" fill="${color}">${label}</text>
</svg>`.trim();
  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
}

const AIRPORT_COLOR = "#0f172a";
const HOTEL_COLOR = "#334155"; // slate — distinct from the day palette
const SUGGEST_COLOR = "#94a3b8";

function airportIcon(): string {
  const svg = `
<svg xmlns="http://www.w3.org/2000/svg" width="34" height="44" viewBox="0 0 34 44">
  <path d="M17 0C7.6 0 0 7.6 0 17c0 12 17 27 17 27s17-15 17-27C34 7.6 26.4 0 17 0z"
        fill="${AIRPORT_COLOR}" stroke="white" stroke-width="2"/>
  <text x="17" y="22" font-size="15" text-anchor="middle">${"\u2708"}</text>
</svg>`.trim();
  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
}

// Hotel/lodging pin — a lettered teardrop ("H") in slate so a place you're
// staying reads differently from a day-numbered attraction.
function hotelIcon(): string {
  const svg = `
<svg xmlns="http://www.w3.org/2000/svg" width="34" height="44" viewBox="0 0 34 44">
  <path d="M17 0C7.6 0 0 7.6 0 17c0 12 17 27 17 27s17-15 17-27C34 7.6 26.4 0 17 0z"
        fill="${HOTEL_COLOR}" stroke="white" stroke-width="2"/>
  <circle cx="17" cy="16" r="11" fill="white" fill-opacity="0.95"/>
  <text x="17" y="21" font-family="Inter,Arial,sans-serif" font-size="13"
        font-weight="700" text-anchor="middle" fill="${HOTEL_COLOR}">H</text>
</svg>`.trim();
  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
}

// A small filled dot for un-scheduled "suggested" places — present but quiet
// so it doesn't compete with the numbered day pins.
function dotIcon(color: string): string {
  const svg = `
<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 18 18">
  <circle cx="9" cy="9" r="6" fill="${color}" stroke="white" stroke-width="2"/>
</svg>`.trim();
  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
}

function isAirportTarget(pin: MapPin | MapAirport): pin is MapAirport {
  return pin.id === "airport";
}


interface Props {
  /** Bump to refetch the map after the trip changes. */
  reloadToken?: number;
  /** When set, highlight the pin with this name (filter to its day, pan, open info). */
  focusName?: string | null;
  /** User clicked a pin and wants other sections synced to that place. */
  onPinFocus?: (kind: string, name: string) => void;
  /** User selected a day filter and wants the itinerary synced to that day. */
  onDayFocus?: (day: number) => void;
  /** Add a place to the trip (from a pin's info window). */
  onSelect?: (kind: string, name: string) => void;
  /** Remove a place from the trip (from a pin's info window). */
  onDeselect?: (kind: string, name: string) => void;
}

export default function MapPanel({ reloadToken = 0, focusName, onPinFocus, onDayFocus, onSelect, onDeselect }: Props) {
  const [view, setView] = useState<MapView | null>(null);
  const [key, setKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeDay, setActiveDay] = useState<number | null>(null); // null = all days
  const [selectedPin, setSelectedPin] = useState<MapPin | MapAirport | null>(null);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [newStopName, setNewStopName] = useState("");
  const [newStopKind, setNewStopKind] = useState<"attraction" | "hotel">("attraction");
  const [retryToken, setRetryToken] = useState(0);

  const mapEl = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const overlaysRef = useRef<any[]>([]); // markers + polylines to clear on redraw
  // A pin the itinerary asked us to zoom into. Applied inside draw() so a
  // redraw (e.g. lazy map mount or day-filter change) can't fight the zoom by
  // re-running fitBounds. Survives the async map init.
  const pendingFocusRef = useRef<MapPin | MapAirport | null>(null);

  // ---- data + config -------------------------------------------------------
  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const [cfg, mv] = await Promise.all([fetchMapsConfig(), fetchMapView(controller.signal)]);
        if (cancelled) return;
        setView(mv);
        setKey(cfg.enabled ? cfg.key : null);
      } catch (requestError) {
        if (!cancelled && !(requestError instanceof DOMException && requestError.name === "AbortError")) {
          setError("Could not load the map.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [reloadToken, retryToken]);

  useEffect(() => {
    if (!view) return;
    setActiveDay((day) =>
      day != null && !view.days.some((candidate) => candidate.day === day) ? null : day
    );
    setSelectedPin((pin) => {
      if (!pin) return null;
      if (pin.id === "airport") {
        return view.airport?.id === pin.id ? view.airport : null;
      }
      return view.pins.find((candidate) => candidate.id === pin.id) ?? null;
    });
  }, [view]);

  // ---- init the map once the script + container + key are ready ------------
  useEffect(() => {
    if (!key || !view?.enabled || !mapEl.current || mapRef.current) return;
    let cancelled = false;
    loadGoogleMaps(key)
      .then((google) => {
        if (cancelled || !mapEl.current) return;
        mapRef.current = new google.maps.Map(mapEl.current, {
          center: view.center || { lat: 20, lng: 0 },
          zoom: view.center ? 12 : 2,
          mapTypeControl: false,
          streetViewControl: false,
          fullscreenControl: true,
        });
        draw();
      })
      .catch(() => {
        if (!cancelled) setError("Could not load Google Maps. Check the browser key.");
      });
    return () => {
      cancelled = true;
    };
    // `draw` is intentionally omitted: it's called once here to paint the
    // initial overlays, then the dedicated redraw effect keeps it in sync.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, view?.enabled, view?.center]);

  // Drop the stale map instance if the component is torn down, so a remount
  // (e.g. toggling "Show map") rebinds to a fresh container instead of an
  // orphaned, detached node (which renders blank).
  useEffect(() => {
    return () => {
      mapRef.current = null;
    };
  }, []);

  // ---- (re)draw markers + per-day route lines ------------------------------
  const draw = useCallback(() => {
    const google = window.google;
    const map = mapRef.current;
    if (!google || !map || !view) return;

    overlaysRef.current.forEach((o) => o.setMap(null));
    overlaysRef.current = [];

    const dayColor = new Map<number, string>();
    view.days.forEach((d) => dayColor.set(d.day, d.color));
    const visitOrderByPinId = new Map<string, number>();
    view.days.forEach((d) => {
      d.pin_ids.forEach((id, idx) => visitOrderByPinId.set(id, idx + 1));
    });

    const visible = (p: MapPin) =>
      p.kind === "hotel" || activeDay === null || p.day === activeDay;
    const bounds = new google.maps.LatLngBounds();
    let any = false;

    const pinById = new Map(view.pins.map((p) => [p.id, p] as const));

    for (const p of view.pins) {
      if (!visible(p)) continue;
      // Choose a marker style: hotels get a slate "H" pin (always shown),
      // day-scheduled places get a bold numbered teardrop in their day color,
      // and un-scheduled suggestions get a quiet dot.
      let icon: any;
      const visitOrder = visitOrderByPinId.get(p.id);
      if (p.day && visitOrder) {
        const color = dayColor.get(p.day) || "#64748b";
        icon = {
          url: pinIcon(color, String(visitOrder)),
          scaledSize: new google.maps.Size(34, 44),
          anchor: new google.maps.Point(17, 44),
        };
      } else if (p.kind === "hotel") {
        icon = {
          url: hotelIcon(),
          scaledSize: new google.maps.Size(34, 44),
          anchor: new google.maps.Point(17, 44),
        };
      } else {
        icon = {
          url: dotIcon(p.selected ? "#0d9488" : SUGGEST_COLOR),
          scaledSize: new google.maps.Size(18, 18),
          anchor: new google.maps.Point(9, 9),
        };
      }
      const marker = new google.maps.Marker({
        position: { lat: p.lat, lng: p.lng },
        map,
        title: p.name,
        icon,
        zIndex: p.selected ? 1000 : p.day ? 600 : 400,
      });
      marker.addListener("click", () => {
        if (["hotel", "attraction", "meal", "restaurant"].includes(p.kind)) {
          onPinFocus?.(p.kind, p.name);
        }
        setSelectedPin(p);
        setConfirmRemove(false);
      });
      overlaysRef.current.push(marker);
      bounds.extend({ lat: p.lat, lng: p.lng });
      any = true;
    }

    // Airport pin (always shown for context).
    if (view.airport) {
      const a = view.airport;
      const marker = new google.maps.Marker({
        position: { lat: a.lat, lng: a.lng },
        map,
        title: a.name,
        icon: {
          url: airportIcon(),
          scaledSize: new google.maps.Size(34, 44),
          anchor: new google.maps.Point(17, 44),
        },
        zIndex: 200,
      });
      marker.addListener("click", () => {
        setSelectedPin(a);
        setConfirmRemove(false);
      });
      overlaysRef.current.push(marker);
      // Only include airport in bounds when viewing all days (for context);
      // when a specific day is selected, omit it so fitBounds zooms to day pins only.
      if (activeDay === null) {
        bounds.extend({ lat: a.lat, lng: a.lng });
        any = true;
      }
    }

    // Geodesic route lines connecting each day's stops in order. (Straight
    // arcs, not road directions, to avoid the billed Directions API.)
    for (const d of view.days) {
      if (activeDay !== null && d.day !== activeDay) continue;
      const path = d.pin_ids
        .map((id) => pinById.get(id))
        .filter((p): p is MapPin => !!p)
        .map((p) => ({ lat: p.lat, lng: p.lng }));
      if (path.length < 2) continue;
      const line = new google.maps.Polyline({
        path,
        geodesic: true,
        strokeColor: d.color,
        strokeOpacity: 0.85,
        strokeWeight: 3,
        map,
      });
      overlaysRef.current.push(line);
    }

    // If the itinerary asked to focus a pin, zoom into it instead of fitting
    // all bounds — and do it here so a redraw can't undo the zoom.
    const focus = pendingFocusRef.current;
    if (focus) {
      map.panTo({ lat: focus.lat, lng: focus.lng });
      map.setZoom(15);
      pendingFocusRef.current = null;
      if (isAirportTarget(focus)) {
        setSelectedPin(focus);
      } else {
        setSelectedPin(focus);
      }
    } else if (any && !bounds.isEmpty()) {
      map.fitBounds(bounds, 64);
    }
  }, [view, activeDay, onPinFocus]);

  useEffect(() => {
    draw();
  }, [draw]);

  // ---- focus a pin by name (driven from the itinerary tab) -----------------
  // We stash the target pin in pendingFocusRef and let draw() apply the
  // pan+zoom. That makes the focus robust to (a) a lazy map mount where
  // mapRef.current isn't ready yet — the init's draw() will pick it up — and
  // (b) a follow-up redraw that would otherwise reset the zoom via fitBounds.
  useEffect(() => {
    if (!focusName || !view) return;
    let target: MapPin | MapAirport | undefined = view.pins.find(
      (p) => p.name.toLowerCase() === focusName.toLowerCase()
    );
    // Check airport if not found in pins
    if (!target && view.airport && view.airport.name.toLowerCase() === focusName.toLowerCase()) {
      target = view.airport;
    }
    if (!target) return;
    pendingFocusRef.current = target;
    // Reveal the pin's day so it isn't filtered out. Changing activeDay
    // recreates draw and triggers the redraw effect (which applies the focus);
    // if the day is already active, redraw explicitly.
    const day = "day" in target ? target.day : null;
    if (day && day !== activeDay) {
      setActiveDay(day);
    } else {
      draw();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusName, view]);

  useEffect(() => {
    setConfirmRemove(false);
  }, [selectedPin?.id]);

  const isPlacePin = (p: MapPin | MapAirport | null): p is MapPin => {
    return !!p && !isAirportTarget(p);
  };

  const handleAddStop = () => {
    const name = newStopName.trim();
    if (!name) return;
    onSelect?.(newStopKind, name);
    onPinFocus?.(newStopKind, name);
    setNewStopName("");
  };

  const handleToggleSelected = () => {
    if (!isPlacePin(selectedPin)) return;
    if (selectedPin.selected) {
      if (!confirmRemove) {
        setConfirmRemove(true);
        return;
      }
      setConfirmRemove(false);
      onDeselect?.(selectedPin.kind, selectedPin.name);
      return;
    }
    onSelect?.(selectedPin.kind, selectedPin.name);
  };

  // ---- render --------------------------------------------------------------
  // "Not configured" is a terminal state — no map will ever mount, so it's safe
  // to return early.
  if (view && !view.enabled) {
    return (
      <div className="grid h-full place-items-center p-6 text-center">
        <div className="max-w-xs text-sm text-slate-500">
          The interactive map isn't configured. Set <code>GOOGLE_MAPS_BROWSER_KEY</code> (a
          referrer-restricted browser key with the Maps JavaScript API enabled) to enable it.
        </div>
      </div>
    );
  }

  // For every other state (loading, error, empty, populated) we keep the map
  // container mounted and layer status messages on top. Unmounting the <div>
  // during a reload would orphan the live map instance and leave it blank.
  const overlay =
    error != null && !view
      ? { text: error, tone: "text-rose-500" }
      : loading && !view
        ? { text: "Loading map…", tone: "text-slate-400" }
        : view && view.pins.length === 0
          ? { text: view.empty_message || "No mappable places yet.", tone: "text-slate-500" }
          : null;
  const activeDayObj =
    view && activeDay != null ? view.days.find((d) => d.day === activeDay) : null;

  return (
    <div className="relative flex h-full flex-col">
      {(loading && view || error && view) && (
        <div className="absolute left-1/2 top-3 z-30 flex -translate-x-1/2 items-center gap-2 rounded-full bg-white/95 px-3 py-1.5 text-xs text-slate-600 shadow-card ring-1 ring-slate-200">
          <span>{error || "Refreshing map…"}</span>
          {error && (
            <button type="button" onClick={() => setRetryToken((token) => token + 1)} className="font-semibold text-brand">
              Retry
            </button>
          )}
        </div>
      )}
      <div className="border-b border-slate-100 px-3 py-2">
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={newStopKind}
            onChange={(e) => setNewStopKind((e.target.value as "attraction" | "hotel") || "attraction")}
            className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-600"
            title="Choose stop type"
          >
            <option value="attraction">Attraction</option>
            <option value="hotel">Hotel</option>
          </select>
          <input
            type="text"
            value={newStopName}
            onChange={(e) => setNewStopName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleAddStop();
            }}
            className="min-w-[9rem] flex-1 rounded-full border border-slate-200 px-3 py-1.5 text-xs text-slate-700 placeholder:text-slate-400"
            placeholder="Add stop from map…"
            title="Type a place name to add directly to trip"
          />
          <button
            type="button"
            onClick={handleAddStop}
            disabled={!newStopName.trim()}
            className="rounded-full bg-brand px-3 py-1.5 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            Add stop
          </button>
        </div>
      </div>
      {/* Day filter chips */}
      {view && view.days.length > 0 && (
        <div className="border-b border-slate-100 px-3 py-2">
          <div className="flex flex-wrap items-center gap-1.5">
            <button
              type="button"
              onClick={() => setActiveDay(null)}
              className={`rounded-full px-3 py-1 text-xs font-medium transition ${
                activeDay === null ? "bg-ink text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              All days
            </button>
            {view.days.map((d) => (
              <button
                key={d.day}
                type="button"
                onClick={() => {
                  setActiveDay(d.day);
                  onDayFocus?.(d.day);
                }}
                className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium transition ${
                  activeDay === d.day ? "text-white" : "text-slate-700 hover:opacity-80"
                }`}
                style={
                  activeDay === d.day
                    ? { backgroundColor: d.color }
                    : { backgroundColor: `${d.color}22` }
                }
              >
                <span
                  className="h-2.5 w-2.5 rounded-full"
                  style={{ backgroundColor: d.color }}
                  aria-hidden
                />
                {d.label}
              </button>
            ))}
          </div>
          <div className="mt-1 text-[11px] text-slate-500">
            {activeDayObj
              ? `${activeDayObj.label} route: ${activeDayObj.route.distance_display} · ${activeDayObj.route.duration_display} · ${activeDayObj.route.mode} (estimated)`
              : "Select a day to view route distance, travel time, and mode."}
          </div>
        </div>
      )}
      <div className="relative min-h-0 flex-1">
        <div ref={mapEl} className="h-full w-full" />
        {selectedPin && (
          <aside className="pointer-events-auto absolute right-3 top-3 z-20 w-[18.5rem] rounded-2xl border border-slate-200 bg-white/95 p-3 shadow-pop backdrop-blur">
            {isPlacePin(selectedPin) && selectedPin.photo && (
              <img
                src={selectedPin.photo}
                alt={selectedPin.name}
                className="mb-2 h-24 w-full rounded-xl object-cover"
              />
            )}
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-ink">{selectedPin.name}</p>
                {isPlacePin(selectedPin) && selectedPin.rating ? (
                  <p className="text-xs text-slate-500">★ {selectedPin.rating}</p>
                ) : null}
                {isPlacePin(selectedPin) && selectedPin.address ? (
                  <p className="mt-0.5 line-clamp-2 text-[11px] text-slate-500">{selectedPin.address}</p>
                ) : null}
              </div>
              <button
                type="button"
                onClick={() => setSelectedPin(null)}
                className="grid h-7 w-7 place-items-center rounded-full text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                title="Close"
              >
                ×
              </button>
            </div>

            {isPlacePin(selectedPin) ? (
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => onPinFocus?.(selectedPin.kind, selectedPin.name)}
                  className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-200"
                  title="Open this place in details section"
                >
                  Open details
                </button>
                <button
                  type="button"
                  onClick={handleToggleSelected}
                  className={`rounded-full px-3 py-1.5 text-xs font-semibold ${
                    selectedPin.selected
                      ? confirmRemove
                        ? "bg-rose-600 text-white"
                        : "bg-rose-50 text-rose-700 ring-1 ring-rose-200"
                      : "bg-brand text-white"
                  }`}
                >
                  {selectedPin.selected
                    ? confirmRemove
                      ? "Click again to remove"
                      : "Remove from trip"
                    : "+ Add to trip"}
                </button>
              </div>
            ) : (
              <p className="mt-2 text-xs text-slate-500">Arrival airport context pin</p>
            )}
          </aside>
        )}
        {overlay && (
          <div className="absolute inset-0 grid place-items-center bg-white/85 p-6 text-center">
            <div className={`max-w-xs text-sm ${overlay.tone}`}>{overlay.text}</div>
          </div>
        )}
      </div>
    </div>
  );
}
