import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Plus, Search } from "lucide-react";
import { fetchMapView, fetchMapsConfig, type DeselectItemOptions, type SelectItemOptions } from "../api";
import type { MapAirport, MapView, MapPin } from "../types";
import PlaceTripActions from "./PlaceTripActions";

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
  if (window.google?.maps?.places) return Promise.resolve(window.google);
  if (window.google?.maps?.importLibrary) {
    return window.google.maps.importLibrary("places").then(() => window.google);
  }
  if (loaderPromise) return loaderPromise;
  loaderPromise = new Promise((resolve, reject) => {
    window.__gmapsReady__ = () => resolve(window.google);
    const s = document.createElement("script");
    s.src =
      `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}` +
      `&callback=__gmapsReady__&libraries=places&loading=async&v=weekly`;
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
export function pinIcon(color: string, label: string, focused = false): string {
  const svg = `
<svg xmlns="http://www.w3.org/2000/svg" width="34" height="44" viewBox="0 0 34 44">
  <path d="M17 0C7.6 0 0 7.6 0 17c0 12 17 27 17 27s17-15 17-27C34 7.6 26.4 0 17 0z"
      fill="${color}" stroke="white" stroke-width="2"/>
    <circle cx="17" cy="16" r="11" fill="${focused ? "#0f172a" : "white"}" fill-opacity="0.97"
      stroke="white" stroke-width="${focused ? 2 : 0}"/>
  <text x="17" y="21" font-family="Inter,Arial,sans-serif" font-size="14"
        font-weight="700" text-anchor="middle" fill="${focused ? "white" : color}">${label}</text>
</svg>`.trim();
  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
}

export function formatLegLabel(leg: { distance_display: string; duration_display: string }): string {
  return `${leg.distance_display} · ${leg.duration_display}`;
}

function routeLegIcon(label: string, color: string): string {
  const svg = `
<svg xmlns="http://www.w3.org/2000/svg" width="112" height="26" viewBox="0 0 112 26">
  <rect x="1" y="1" width="110" height="24" rx="12" fill="white" fill-opacity="0.94"
        stroke="${color}" stroke-opacity="0.35"/>
  <text x="56" y="17" font-family="Inter,Arial,sans-serif" font-size="10"
        font-weight="600" text-anchor="middle" fill="#475569">${label}</text>
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
export function hotelIcon(focused = false): string {
  const svg = `
<svg xmlns="http://www.w3.org/2000/svg" width="34" height="44" viewBox="0 0 34 44">
  <path d="M17 0C7.6 0 0 7.6 0 17c0 12 17 27 17 27s17-15 17-27C34 7.6 26.4 0 17 0z"
        fill="${HOTEL_COLOR}" stroke="white" stroke-width="2"/>
    <circle cx="17" cy="16" r="11" fill="${focused ? "#0f172a" : "white"}" fill-opacity="0.97"
      stroke="white" stroke-width="${focused ? 2 : 0}"/>
  <text x="17" y="21" font-family="Inter,Arial,sans-serif" font-size="13"
        font-weight="700" text-anchor="middle" fill="${focused ? "white" : HOTEL_COLOR}">H</text>
</svg>`.trim();
  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
}

// A small filled dot for un-scheduled "suggested" places — present but quiet
// so it doesn't compete with the numbered day pins.
function dotIcon(color: string, focused = false): string {
  const svg = `
<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 18 18">
  <circle cx="9" cy="9" r="6" fill="${color}" stroke="${focused ? "#0f172a" : "white"}" stroke-width="${focused ? 3 : 2}"/>
</svg>`.trim();
  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
}

function isAirportTarget(pin: MapPin | MapAirport): pin is MapAirport {
  return pin.id === "airport";
}

export function placeNameMatches(candidate: string, focusName: string): boolean {
  const normalize = (value: string) => value
    .normalize("NFKD")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
  const normalizedCandidate = normalize(candidate);
  const normalizedFocus = normalize(focusName);
  if (!normalizedCandidate || !normalizedFocus) return false;
  return normalizedCandidate === normalizedFocus
    || normalizedCandidate.includes(normalizedFocus)
    || normalizedFocus.includes(normalizedCandidate)
    || normalizedFocus.split(" ").every((token) => normalizedCandidate.split(" ").includes(token));
}

export function focusedDayForPin(pin: MapPin, focusDay?: number): number | null {
  return focusDay && pin.occurrences.some((occurrence) => occurrence.day === focusDay)
    ? focusDay
    : pin.day;
}

export function visitOrdersForDay(view: MapView, dayNumber: number): Map<string, number> {
  const day = view.days.find((candidate) => candidate.day === dayNumber);
  const pins = (day?.pin_ids ?? [])
    .map((id) => view.pins.find((candidate) => candidate.id === id))
    .filter((pin): pin is MapPin => !!pin && pin.kind !== "hotel");
  const ordered = [...new Map(pins.map((pin) => [pin.id, pin])).values()].sort((left, right) => {
    const leftStop = left.occurrences.find((occurrence) => occurrence.day === dayNumber)?.stop;
    const rightStop = right.occurrences.find((occurrence) => occurrence.day === dayNumber)?.stop;
    return (leftStop ?? Number.MAX_SAFE_INTEGER) - (rightStop ?? Number.MAX_SAFE_INTEGER);
  });
  return new Map(ordered.map((pin, index) => [pin.id, index + 1]));
}

export function pinMatchesFocus(pin: MapPin, focusName?: string | null, focusDay?: number): boolean {
  if (!focusName || !placeNameMatches(pin.name, focusName)) return false;
  return focusDay == null || pin.occurrences.some((occurrence) => occurrence.day === focusDay);
}

interface PinMarkerEntry {
  pin: MapPin;
  marker: any;
  normalIcon: any;
  focusedIcon: any;
  baseZIndex: number;
}

export function syncPinMarkerFocus(
  entries: PinMarkerEntry[],
  focusName?: string | null,
  focusDay?: number,
): void {
  entries.forEach(({ pin, marker, normalIcon, focusedIcon, baseZIndex }) => {
    const focused = pinMatchesFocus(pin, focusName, focusDay);
    marker.setIcon(focused ? focusedIcon : normalIcon);
    marker.setZIndex(focused ? 1400 : baseZIndex);
  });
}

export function kindForGooglePlace(types: string[] | undefined): "attraction" | "hotel" | "meal" {
  if (types?.some((type) => type === "lodging" || type === "hotel")) return "hotel";
  if (types?.some((type) => type === "restaurant" || type === "meal_takeaway")) return "meal";
  return "attraction";
}

export function mapPinFromGooglePlace(place: any): MapPin | null {
  const name = String(place?.name || "").trim();
  const location = place?.geometry?.location;
  const lat = typeof location?.lat === "function" ? location.lat() : location?.lat;
  const lng = typeof location?.lng === "function" ? location.lng() : location?.lng;
  if (!name || !Number.isFinite(lat) || !Number.isFinite(lng)) return null;
  let photo: string | null = null;
  try {
    photo = place.photos?.[0]?.getUrl?.({ maxWidth: 800 }) ?? null;
  } catch {
    photo = null;
  }
  return {
    id: `candidate:${String(place.place_id || name).trim().toLowerCase()}`,
    name,
    kind: kindForGooglePlace(place.types),
    selected: false,
    day: null,
    lat,
    lng,
    rating: typeof place.rating === "number" ? place.rating : null,
    address: String(place.formatted_address || ""),
    photo,
    occurrences: [],
  };
}

export function optionsForStopDay(day: string): SelectItemOptions | undefined {
  const parsed = Number(day);
  return day !== "auto" && Number.isInteger(parsed) && parsed > 0 ? { day: parsed } : undefined;
}

export function fitDayCircuit(google: any, map: any, view: MapView, dayNumber: number): boolean {
  const day = view.days.find((candidate) => candidate.day === dayNumber);
  if (!day) return false;
  const pins = day.pin_ids
    .map((id) => view.pins.find((pin) => pin.id === id))
    .filter((pin): pin is MapPin => !!pin);
  if (pins.length === 0) return false;
  const bounds = new google.maps.LatLngBounds();
  pins.forEach((pin) => bounds.extend({ lat: pin.lat, lng: pin.lng }));
  map.fitBounds(bounds, 64);
  return true;
}

export function capCircuitZoom(map: any): void {
  if ((map.getZoom() ?? 0) > 14) map.setZoom(14);
}


interface Props {
  /** Bump to refetch the map after the trip changes. */
  reloadToken?: number;
  /** When set, highlight the pin with this name (filter to its day, pan, open info). */
  focusName?: string | null;
  /** Exact itinerary occurrence day for repeated places such as a multi-day hotel. */
  focusDay?: number;
  /** Changes for every focus request, including repeated clicks on the same stop. */
  focusToken?: number;
  /** Itinerary day whose complete circuit should be framed. */
  circuitFocusDay?: number;
  /** Changes for every circuit framing request, including repeated clicks. */
  circuitFocusToken?: number;
  /** User clicked a pin and wants other sections synced to that place. */
  onPinFocus?: (kind: string, name: string, day?: number, stop?: number) => void;
  /** User selected a day filter and wants the itinerary synced to that day. */
  onDayFocus?: (day: number) => void;
  /** User selected all circuits and wants the itinerary synced to its summary. */
  onAllDaysFocus?: () => void;
  /** Add a place to the trip (from a pin's info window). */
  onSelect?: (
    kind: string,
    name: string,
    options?: SelectItemOptions,
  ) => void | Promise<boolean>;
  /** Remove a place from the trip (from a pin's info window). */
  onDeselect?: (
    kind: string,
    name: string,
    options?: DeselectItemOptions,
  ) => void | Promise<boolean>;
  headerTarget?: HTMLElement | null;
}

export default function MapPanel({ reloadToken = 0, focusName, focusDay, focusToken = 0, circuitFocusDay, circuitFocusToken = 0, onPinFocus, onDayFocus, onAllDaysFocus, onSelect, onDeselect, headerTarget }: Props) {
  const [view, setView] = useState<MapView | null>(null);
  const [key, setKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeDay, setActiveDay] = useState<number | null>(null); // null = all days
  const [selectedPin, setSelectedPin] = useState<MapPin | MapAirport | null>(null);
  const [candidatePin, setCandidatePin] = useState<MapPin | null>(null);
  const [newStopName, setNewStopName] = useState("");
  const [newStopKind, setNewStopKind] = useState<"" | "attraction" | "hotel" | "meal">("");
  const [stopKindAutoFilled, setStopKindAutoFilled] = useState(false);
  const [newStopDay, setNewStopDay] = useState("auto");
  const [addingStop, setAddingStop] = useState(false);
  const [retryToken, setRetryToken] = useState(0);

  const mapEl = useRef<HTMLDivElement>(null);
  const stopInputRef = useRef<HTMLInputElement>(null);
  const onPinFocusRef = useRef(onPinFocus);
  const mapRef = useRef<any>(null);
  const autocompleteRef = useRef<any>(null);
  const autocompleteListenerRef = useRef<any>(null);
  const mapClickListenerRef = useRef<any>(null);
  const circuitZoomTimerRef = useRef<number | null>(null);
  const overlaysRef = useRef<any[]>([]); // markers + polylines to clear on redraw
  const pinMarkersRef = useRef<PinMarkerEntry[]>([]);
  const focusRef = useRef({ name: focusName, day: focusDay });
  focusRef.current = { name: focusName, day: focusDay };
  // A pin the itinerary asked us to zoom into. Applied inside draw() so a
  // redraw (e.g. lazy map mount or day-filter change) can't fight the zoom by
  // re-running fitBounds. Survives the async map init.
  const pendingFocusRef = useRef<MapPin | MapAirport | null>(null);
  const pendingCircuitFocusRef = useRef<number | null>(null);

  useEffect(() => {
    onPinFocusRef.current = onPinFocus;
  }, [onPinFocus]);

  const populateStopFromGooglePlace = useCallback(
    (place: any) => {
      const candidate = mapPinFromGooglePlace(place);
      if (!candidate) return;
      setNewStopName(candidate.name);
      setNewStopKind(candidate.kind as "attraction" | "hotel" | "meal");
      setStopKindAutoFilled(true);
      setCandidatePin(candidate);
      setSelectedPin(candidate);
      pendingFocusRef.current = candidate;
      onPinFocusRef.current?.(candidate.kind, candidate.name);
      stopInputRef.current?.focus();
    },
    []
  );

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
      if (pin.id.startsWith("candidate:")) return pin;
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
          clickableIcons: true,
        });
        if (stopInputRef.current && google.maps.places?.Autocomplete) {
          const autocomplete = new google.maps.places.Autocomplete(stopInputRef.current, {
            fields: ["place_id", "name", "types", "geometry", "formatted_address", "rating", "photos"],
            strictBounds: false,
          });
          autocomplete.bindTo("bounds", mapRef.current);
          autocompleteRef.current = autocomplete;
          autocompleteListenerRef.current = autocomplete.addListener("place_changed", () => {
            populateStopFromGooglePlace(autocomplete.getPlace());
          });
        }
        if (google.maps.places?.PlacesService) {
          const placesService = new google.maps.places.PlacesService(mapRef.current);
          mapClickListenerRef.current = mapRef.current.addListener("click", (event: any) => {
            if (!event.placeId) return;
            event.stop?.();
            placesService.getDetails(
              {
                placeId: event.placeId,
                fields: ["place_id", "name", "types", "geometry", "formatted_address", "rating", "photos"],
              },
              (place: any, status: string) => {
                if (status === google.maps.places.PlacesServiceStatus.OK) {
                  populateStopFromGooglePlace(place);
                }
              }
            );
          });
        }
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
  }, [key, view?.enabled, view?.center, populateStopFromGooglePlace]);

  // Drop the stale map instance if the component is torn down, so a remount
  // (e.g. toggling "Show map") rebinds to a fresh container instead of an
  // orphaned, detached node (which renders blank).
  useEffect(() => {
    return () => {
      autocompleteListenerRef.current?.remove();
      autocompleteRef.current?.unbindAll?.();
      mapClickListenerRef.current?.remove();
      autocompleteListenerRef.current = null;
      autocompleteRef.current = null;
      mapClickListenerRef.current = null;
      if (circuitZoomTimerRef.current !== null) {
        window.clearTimeout(circuitZoomTimerRef.current);
      }
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
    pinMarkersRef.current = [];

    const dayColor = new Map<number, string>();
    view.days.forEach((d) => dayColor.set(d.day, d.color));
    const visitOrderByPinId = new Map<string, number>();
    const orderDays = activeDay == null
      ? view.days
      : view.days.filter((day) => day.day === activeDay);
    orderDays.forEach((d) => {
      visitOrdersForDay(view, d.day).forEach((order, id) => {
        if (!visitOrderByPinId.has(id)) visitOrderByPinId.set(id, order);
      });
    });

    const activeDayPinIds = new Set(
      activeDay === null
        ? []
        : view.days.find((day) => day.day === activeDay)?.pin_ids ?? []
    );
    const visible = (p: MapPin) =>
      p.kind === "hotel" || activeDay === null || activeDayPinIds.has(p.id);
    const bounds = new google.maps.LatLngBounds();
    let any = false;

    const pinById = new Map(view.pins.map((p) => [p.id, p] as const));
    const currentFocus = focusRef.current;

    for (const p of view.pins) {
      if (!visible(p)) continue;
      // Choose a marker style: hotels get a slate "H" pin (always shown),
      // day-scheduled places get a bold numbered teardrop in their day color,
      // and un-scheduled suggestions get a quiet dot.
      const focused = pinMatchesFocus(p, currentFocus.name, currentFocus.day);
      const visitOrder = visitOrderByPinId.get(p.id);
      const markerDay = activeDay !== null && activeDayPinIds.has(p.id) ? activeDay : p.day;
      const iconFor = (isFocused: boolean) => {
        if (p.kind === "hotel") return {
          url: hotelIcon(isFocused),
          scaledSize: new google.maps.Size(34, 44),
          anchor: new google.maps.Point(17, 44),
        };
        if (markerDay && visitOrder) {
          const color = dayColor.get(markerDay) || "#64748b";
          return {
            url: pinIcon(color, String(visitOrder), isFocused),
            scaledSize: new google.maps.Size(34, 44),
            anchor: new google.maps.Point(17, 44),
          };
        }
        return {
          url: dotIcon(p.selected ? "#0d9488" : SUGGEST_COLOR, isFocused),
          scaledSize: new google.maps.Size(isFocused ? 24 : 18, isFocused ? 24 : 18),
          anchor: new google.maps.Point(isFocused ? 12 : 9, isFocused ? 12 : 9),
        };
      };
      const normalIcon = iconFor(false);
      const focusedIcon = iconFor(true);
      const baseZIndex = p.selected ? 1000 : p.day ? 600 : 400;
      const marker = new google.maps.Marker({
        position: { lat: p.lat, lng: p.lng },
        map,
        title: p.name,
        icon: focused ? focusedIcon : normalIcon,
        zIndex: focused ? 1400 : baseZIndex,
      });
      marker.addListener("click", () => {
        setCandidatePin(null);
        if (["hotel", "attraction", "meal", "restaurant"].includes(p.kind)) {
          const occurrence = p.occurrences.find(
            (candidate) => candidate.day === (activeDay ?? p.day),
          ) ?? p.occurrences[0];
          onPinFocusRef.current?.(p.kind, p.name, occurrence?.day, occurrence?.stop);
        }
        setSelectedPin(p);
      });
      pinMarkersRef.current.push({ pin: p, marker, normalIcon, focusedIcon, baseZIndex });
      overlaysRef.current.push(marker);
      bounds.extend({ lat: p.lat, lng: p.lng });
      any = true;
    }

    if (candidatePin) {
      const marker = new google.maps.Marker({
        position: { lat: candidatePin.lat, lng: candidatePin.lng },
        map,
        title: candidatePin.name,
        icon: {
          url: dotIcon("#e11d48"),
          scaledSize: new google.maps.Size(24, 24),
          anchor: new google.maps.Point(12, 12),
        },
        zIndex: 1200,
      });
      marker.addListener("click", () => {
        setSelectedPin(candidatePin);
        onPinFocusRef.current?.(candidatePin.kind, candidatePin.name);
      });
      overlaysRef.current.push(marker);
      bounds.extend({ lat: candidatePin.lat, lng: candidatePin.lng });
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

      if (activeDay === d.day) {
        for (const leg of d.legs ?? []) {
          const start = pinById.get(leg.from_pin_id);
          const end = pinById.get(leg.to_pin_id);
          if (!start || !end) continue;
          const label = formatLegLabel(leg);
          const marker = new google.maps.Marker({
            position: {
              lat: (start.lat + end.lat) / 2,
              lng: (start.lng + end.lng) / 2,
            },
            map,
            clickable: false,
            title: `${label} · ${leg.mode}`,
            icon: {
              url: routeLegIcon(label, d.color),
              scaledSize: new google.maps.Size(112, 26),
              anchor: new google.maps.Point(56, 13),
            },
            zIndex: 500,
          });
          overlaysRef.current.push(marker);
        }
      }
    }

    // If the itinerary asked to focus a pin, zoom into it instead of fitting
    // all bounds — and do it here so a redraw can't undo the zoom.
    const circuitDay = pendingCircuitFocusRef.current;
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
    } else if (circuitDay && fitDayCircuit(google, map, view, circuitDay)) {
      pendingCircuitFocusRef.current = null;
      if (circuitZoomTimerRef.current !== null) {
        window.clearTimeout(circuitZoomTimerRef.current);
      }
      circuitZoomTimerRef.current = window.setTimeout(() => {
        capCircuitZoom(map);
        circuitZoomTimerRef.current = null;
      }, 1200);
    } else if (any && !bounds.isEmpty()) {
      map.fitBounds(bounds, 64);
    }
  }, [view, activeDay, candidatePin]);

  useEffect(() => {
    draw();
  }, [draw]);

  // ---- focus a pin by name (driven from the itinerary tab) -----------------
  // Same-day changes update existing marker icons immediately. If the target
  // is filtered out, changing activeDay lets draw() reveal and focus it.
  useEffect(() => {
    if (!view) return;
    if (circuitZoomTimerRef.current !== null) {
      window.clearTimeout(circuitZoomTimerRef.current);
      circuitZoomTimerRef.current = null;
    }
    if (!focusName) {
      syncPinMarkerFocus(pinMarkersRef.current);
      return;
    }
    pendingCircuitFocusRef.current = null;
    const normalizedFocus = focusName.trim().toLowerCase();
    let target: MapPin | MapAirport | undefined = view.pins.find((p) =>
      placeNameMatches(p.name, focusName)
    );
    // Check airport if not found in pins
    if (!target && view.airport && view.airport.name.trim().toLowerCase() === normalizedFocus) {
      target = view.airport;
    }
    if (!target) return;
    pendingFocusRef.current = target;
    const clearingCandidate = candidatePin !== null;
    setCandidatePin(null);
    // Reveal the pin's day so it isn't filtered out. Changing activeDay
    // recreates draw and triggers the redraw effect. draw() resolves the
    // current requested target itself, so fitBounds can never race ahead of
    // installing a same-day pending focus.
    const day = "day" in target ? focusedDayForPin(target, focusDay) : null;
    if (day && day !== activeDay) {
      setActiveDay(day);
      return;
    }
    syncPinMarkerFocus(pinMarkersRef.current, focusName, focusDay);
    const map = mapRef.current;
    map?.panTo({ lat: target.lat, lng: target.lng });
    map?.setZoom(15);
    setSelectedPin(target);
    if (map && !clearingCandidate) pendingFocusRef.current = null;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusName, focusDay, focusToken, view]);

  useEffect(() => {
    if (!view || !circuitFocusDay || circuitFocusToken === 0) return;
    pendingFocusRef.current = null;
    pendingCircuitFocusRef.current = circuitFocusDay;
    if (activeDay !== circuitFocusDay) {
      setActiveDay(circuitFocusDay);
      return;
    }

    const google = window.google;
    const map = mapRef.current;
    if (!google || !map) return;
    if (!fitDayCircuit(google, map, view, circuitFocusDay)) return;
    pendingCircuitFocusRef.current = null;
    if (circuitZoomTimerRef.current !== null) {
      window.clearTimeout(circuitZoomTimerRef.current);
    }
    circuitZoomTimerRef.current = window.setTimeout(() => {
      capCircuitZoom(map);
      circuitZoomTimerRef.current = null;
    }, 1200);
  }, [activeDay, circuitFocusDay, circuitFocusToken, view]);

  const isPlacePin = (p: MapPin | MapAirport | null): p is MapPin => {
    return !!p && !isAirportTarget(p);
  };

  const handleAddStop = async () => {
    const name = newStopName.trim();
    if (!name) return;
    setAddingStop(true);
    try {
      const added = await onSelect?.(
        newStopKind || "attraction",
        name,
        optionsForStopDay(newStopDay),
      );
      if (added !== false) {
        setNewStopName("");
        setNewStopKind("");
        setStopKindAutoFilled(false);
      }
    } finally {
      setAddingStop(false);
    }
  };

  const handleAddSelected = async () => {
    if (!isPlacePin(selectedPin)) return;
    setAddingStop(true);
    try {
      await onSelect?.(
        selectedPin.kind,
        selectedPin.name,
        optionsForStopDay(newStopDay),
      );
    } finally {
      setAddingStop(false);
    }
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
  const dayScopeControls = view ? (
    <div className="flex min-w-0 items-center gap-1 overflow-x-auto" aria-label="Map day scope">
      <button
        type="button"
        onClick={() => {
          if (circuitZoomTimerRef.current !== null) {
            window.clearTimeout(circuitZoomTimerRef.current);
            circuitZoomTimerRef.current = null;
          }
          pendingFocusRef.current = null;
          pendingCircuitFocusRef.current = null;
          setActiveDay(null);
          setSelectedPin(null);
          setNewStopDay("auto");
          onAllDaysFocus?.();
        }}
        className={`shrink-0 rounded-md px-2 py-1 text-[11px] font-semibold transition ${
          activeDay === null ? "bg-ink text-white" : "text-slate-500 hover:bg-slate-100 hover:text-ink"
        }`}
      >
        All days
      </button>
      {view.days.map((day) => (
        <button
          key={day.day}
          type="button"
          onClick={() => {
            if (circuitZoomTimerRef.current !== null) {
              window.clearTimeout(circuitZoomTimerRef.current);
              circuitZoomTimerRef.current = null;
            }
            setActiveDay(day.day);
            setNewStopDay(String(day.day));
            onDayFocus?.(day.day);
          }}
          className={`shrink-0 rounded-md px-2 py-1 text-[11px] font-semibold transition ${
            activeDay === day.day ? "text-white" : "text-slate-500 hover:bg-slate-100 hover:text-ink"
          }`}
          style={activeDay === day.day ? { backgroundColor: day.color } : undefined}
        >
          {day.label}
        </button>
      ))}
    </div>
  ) : null;

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
      {view && (
        <div className="border-b border-slate-200 bg-white/95" aria-label="Map commands">
          {headerTarget ? createPortal(dayScopeControls, headerTarget) : (
            <div className="border-b border-slate-100 px-3 py-1.5">{dayScopeControls}</div>
          )}
          <div className="px-3 py-2">
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative min-w-[9rem] flex-1">
                <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" aria-hidden />
                <input
                  ref={stopInputRef}
                  type="text"
                  value={newStopName}
                  onChange={(event) => {
                    setNewStopName(event.target.value);
                    if (stopKindAutoFilled) {
                      setNewStopKind("");
                      setStopKindAutoFilled(false);
                    }
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") void handleAddStop();
                  }}
                  className="w-full rounded-md border border-slate-200 py-1.5 pl-8 pr-3 text-xs text-slate-700 placeholder:text-slate-400"
                  placeholder="Search places on this map…"
                  title="Search Google Maps places near the current map view"
                />
              </div>
              <select
                value={newStopKind}
                onChange={(event) => {
                  setNewStopKind(event.target.value as "" | "attraction" | "hotel" | "meal");
                  setStopKindAutoFilled(false);
                }}
                className={`rounded-md border px-3 py-1.5 text-xs ${stopKindAutoFilled ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-slate-200 bg-white text-slate-500"}`}
                title={stopKindAutoFilled ? "Type auto-filled from Google; change it if needed" : "Stop type is optional"}
                aria-label="Stop type (optional)"
              >
                <option value="">Type (optional)</option>
                <option value="attraction">Attraction{stopKindAutoFilled && newStopKind === "attraction" ? " · auto-filled" : ""}</option>
                <option value="hotel">Hotel{stopKindAutoFilled && newStopKind === "hotel" ? " · auto-filled" : ""}</option>
                <option value="meal">Restaurant{stopKindAutoFilled && newStopKind === "meal" ? " · auto-filled" : ""}</option>
              </select>
              {view.days.length > 0 && (
                <select
                  value={newStopDay}
                  onChange={(event) => setNewStopDay(event.target.value)}
                  className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-600"
                  title="Choose which itinerary day receives this stop"
                  aria-label="Add stop to day"
                >
                  <option value="auto">Best day</option>
                  {view.days.map((day) => (
                    <option key={day.day} value={day.day}>Day {day.day}</option>
                  ))}
                </select>
              )}
              <button
                type="button"
                onClick={handleAddStop}
                disabled={!newStopName.trim() || addingStop}
                className="inline-flex items-center gap-1 rounded-md bg-brand px-3 py-1.5 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Plus className="h-3.5 w-3.5" aria-hidden />
                {addingStop ? "Adding…" : "Add"}
              </button>
            </div>
          </div>
          <div className="flex min-h-6 items-center gap-1.5 border-t border-slate-100 px-3 py-1 text-[10px] text-slate-500">
            {activeDayObj ? (
              <>
                <span className="font-semibold text-slate-700">{activeDayObj.label}</span>
                <span aria-hidden>·</span>
                <span>Schedule {activeDayObj.schedule?.duration_display || "unavailable"}{activeDayObj.schedule?.start && activeDayObj.schedule?.end ? `, ${activeDayObj.schedule.start}–${activeDayObj.schedule.end}${activeDayObj.schedule.estimated ? " est." : ""}` : ""}</span>
                <span aria-hidden>·</span>
                <span>Travel {activeDayObj.route.duration_display}, {activeDayObj.route.distance_display}, {activeDayObj.route.mode}</span>
              </>
            ) : (
              <span>Choose a day for schedule and route-only travel.</span>
            )}
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
                  onClick={() => {
                    const occurrence = selectedPin.occurrences.find(
                      (candidate) => candidate.day === (activeDay ?? selectedPin.day),
                    ) ?? selectedPin.occurrences[0];
                    onPinFocus?.(
                      selectedPin.kind,
                      selectedPin.name,
                      occurrence?.day,
                      occurrence?.stop,
                    );
                  }}
                  className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-200"
                  title="Open this place in details section"
                >
                  Open details
                </button>
                {selectedPin.selected ? (
                  <PlaceTripActions
                    kind={selectedPin.kind}
                    name={selectedPin.name}
                    occurrences={selectedPin.occurrences}
                    availableDays={view?.available_days ?? []}
                    preferredDay={activeDay ?? selectedPin.day}
                    onMove={onSelect ?? (() => {})}
                    onRemove={onDeselect ?? (() => {})}
                  />
                ) : (
                  <>
                    {view && view.days.length > 0 && (
                      <select
                        value={newStopDay}
                        onChange={(event) => setNewStopDay(event.target.value)}
                        aria-label={`Add ${selectedPin.name} to day`}
                        className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 disabled:opacity-50"
                        disabled={addingStop}
                      >
                        <option value="auto">Best day</option>
                        {view.days.map((day) => (
                          <option key={day.day} value={day.day}>Day {day.day}</option>
                        ))}
                      </select>
                    )}
                    <button
                      type="button"
                      onClick={handleAddSelected}
                      disabled={addingStop}
                      className="rounded-full bg-brand px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
                    >
                      {addingStop ? "Adding…" : "+ Add to trip"}
                    </button>
                  </>
                )}
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
