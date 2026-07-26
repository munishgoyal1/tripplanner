import { useCallback, useEffect, useRef, useState } from "react";
import { Plus } from "lucide-react";
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
function pinIcon(color: string, label: string, focused = false): string {
  const svg = `
<svg xmlns="http://www.w3.org/2000/svg" width="34" height="44" viewBox="0 0 34 44">
  <path d="M17 0C7.6 0 0 7.6 0 17c0 12 17 27 17 27s17-15 17-27C34 7.6 26.4 0 17 0z"
        fill="${color}" stroke="white" stroke-width="2"/>
    <circle cx="17" cy="16" r="11" fill="white" fill-opacity="0.95"
      stroke="${focused ? color : "white"}" stroke-width="${focused ? 2 : 0}"/>
  <text x="17" y="21" font-family="Inter,Arial,sans-serif" font-size="14"
        font-weight="700" text-anchor="middle" fill="${color}">${label}</text>
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
function hotelIcon(focused = false): string {
  const svg = `
<svg xmlns="http://www.w3.org/2000/svg" width="34" height="44" viewBox="0 0 34 44">
  <path d="M17 0C7.6 0 0 7.6 0 17c0 12 17 27 17 27s17-15 17-27C34 7.6 26.4 0 17 0z"
        fill="${HOTEL_COLOR}" stroke="white" stroke-width="2"/>
    <circle cx="17" cy="16" r="11" fill="white" fill-opacity="0.95"
      stroke="${focused ? HOTEL_COLOR : "white"}" stroke-width="${focused ? 2 : 0}"/>
  <text x="17" y="21" font-family="Inter,Arial,sans-serif" font-size="13"
        font-weight="700" text-anchor="middle" fill="${HOTEL_COLOR}">H</text>
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
    || normalizedFocus.includes(normalizedCandidate);
}

export function focusedDayForPin(pin: MapPin, focusDay?: number): number | null {
  return focusDay && pin.occurrences.some((occurrence) => occurrence.day === focusDay)
    ? focusDay
    : pin.day;
}

export function pinMatchesFocus(pin: MapPin, focusName?: string | null, focusDay?: number): boolean {
  if (!focusName || !placeNameMatches(pin.name, focusName)) return false;
  return focusDay == null || pin.occurrences.some((occurrence) => occurrence.day === focusDay);
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


interface Props {
  /** Bump to refetch the map after the trip changes. */
  reloadToken?: number;
  /** When set, highlight the pin with this name (filter to its day, pan, open info). */
  focusName?: string | null;
  /** Exact itinerary occurrence day for repeated places such as a multi-day hotel. */
  focusDay?: number;
  /** Changes for every focus request, including repeated clicks on the same stop. */
  focusToken?: number;
  /** User clicked a pin and wants other sections synced to that place. */
  onPinFocus?: (kind: string, name: string, day?: number, stop?: number) => void;
  /** User selected a day filter and wants the itinerary synced to that day. */
  onDayFocus?: (day: number, place?: MapPin) => void;
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
}

export default function MapPanel({ reloadToken = 0, focusName, focusDay, focusToken = 0, onPinFocus, onDayFocus, onSelect, onDeselect }: Props) {
  const [view, setView] = useState<MapView | null>(null);
  const [key, setKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeDay, setActiveDay] = useState<number | null>(null); // null = all days
  const [selectedPin, setSelectedPin] = useState<MapPin | MapAirport | null>(null);
  const [candidatePin, setCandidatePin] = useState<MapPin | null>(null);
  const [newStopName, setNewStopName] = useState("");
  const [newStopKind, setNewStopKind] = useState<"attraction" | "hotel" | "meal">("attraction");
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
  const overlaysRef = useRef<any[]>([]); // markers + polylines to clear on redraw
  // A pin the itinerary asked us to zoom into. Applied inside draw() so a
  // redraw (e.g. lazy map mount or day-filter change) can't fight the zoom by
  // re-running fitBounds. Survives the async map init.
  const pendingFocusRef = useRef<MapPin | MapAirport | null>(null);

  useEffect(() => {
    onPinFocusRef.current = onPinFocus;
  }, [onPinFocus]);

  const populateStopFromGooglePlace = useCallback(
    (place: any) => {
      const candidate = mapPinFromGooglePlace(place);
      if (!candidate) return;
      setNewStopName(candidate.name);
      setNewStopKind(candidate.kind as "attraction" | "hotel" | "meal");
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
    const orderDays = activeDay == null
      ? view.days
      : view.days.filter((day) => day.day === activeDay);
    orderDays.forEach((d) => {
      let visitOrder = 0;
      d.pin_ids.forEach((id) => {
        const pin = view.pins.find((candidate) => candidate.id === id);
        if (pin?.kind === "hotel") return;
        visitOrder += 1;
        if (!visitOrderByPinId.has(id)) visitOrderByPinId.set(id, visitOrder);
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

    for (const p of view.pins) {
      if (!visible(p)) continue;
      // Choose a marker style: hotels get a slate "H" pin (always shown),
      // day-scheduled places get a bold numbered teardrop in their day color,
      // and un-scheduled suggestions get a quiet dot.
      let icon: any;
      const focused = pinMatchesFocus(p, focusName, focusDay);
      const visitOrder = visitOrderByPinId.get(p.id);
      const markerDay = activeDay !== null && activeDayPinIds.has(p.id) ? activeDay : p.day;
      if (p.kind === "hotel") {
        icon = {
          url: hotelIcon(focused),
          scaledSize: new google.maps.Size(focused ? 40 : 34, focused ? 52 : 44),
          anchor: new google.maps.Point(focused ? 20 : 17, focused ? 52 : 44),
        };
      } else if (markerDay && visitOrder) {
        const color = dayColor.get(markerDay) || "#64748b";
        icon = {
          url: pinIcon(color, String(visitOrder), focused),
          scaledSize: new google.maps.Size(focused ? 40 : 34, focused ? 52 : 44),
          anchor: new google.maps.Point(focused ? 20 : 17, focused ? 52 : 44),
        };
      } else {
        icon = {
          url: dotIcon(p.selected ? "#0d9488" : SUGGEST_COLOR, focused),
          scaledSize: new google.maps.Size(focused ? 24 : 18, focused ? 24 : 18),
          anchor: new google.maps.Point(focused ? 12 : 9, focused ? 12 : 9),
        };
      }
      const marker = new google.maps.Marker({
        position: { lat: p.lat, lng: p.lng },
        map,
        title: p.name,
        icon,
        zIndex: focused ? 1400 : p.selected ? 1000 : p.day ? 600 : 400,
      });
      marker.addListener("click", () => {
        setCandidatePin(null);
        if (["hotel", "attraction", "meal", "restaurant"].includes(p.kind)) {
          const occurrence = p.occurrences.find(
            (candidate) => candidate.day === (activeDay ?? p.day),
          ) ?? p.occurrences[0];
          onPinFocus?.(p.kind, p.name, occurrence?.day, occurrence?.stop);
        }
        setSelectedPin(p);
      });
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
        onPinFocus?.(candidatePin.kind, candidatePin.name);
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
  }, [view, activeDay, candidatePin, focusName, focusDay, onPinFocus]);

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
    const normalizedFocus = focusName.trim().toLowerCase();
    let target: MapPin | MapAirport | undefined = view.pins.find((p) =>
      placeNameMatches(p.name, focusName)
    );
    // Check airport if not found in pins
    if (!target && view.airport && view.airport.name.trim().toLowerCase() === normalizedFocus) {
      target = view.airport;
    }
    if (!target) return;
    setCandidatePin(null);
    pendingFocusRef.current = target;
    // Reveal the pin's day so it isn't filtered out. Changing activeDay
    // recreates draw and triggers the redraw effect (which applies the focus);
    // if the day is already active, redraw explicitly.
    const day = "day" in target ? focusedDayForPin(target, focusDay) : null;
    if (day && day !== activeDay) {
      setActiveDay(day);
    } else {
      draw();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusName, focusDay, focusToken, view]);

  const isPlacePin = (p: MapPin | MapAirport | null): p is MapPin => {
    return !!p && !isAirportTarget(p);
  };

  const handleAddStop = async () => {
    const name = newStopName.trim();
    if (!name) return;
    setAddingStop(true);
    try {
      const added = await onSelect?.(
        newStopKind,
        name,
        optionsForStopDay(newStopDay),
      );
      if (added !== false) setNewStopName("");
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
            <option value="meal">Restaurant</option>
          </select>
          <input
            ref={stopInputRef}
            type="text"
            value={newStopName}
            onChange={(e) => setNewStopName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void handleAddStop();
            }}
            className="min-w-[9rem] flex-1 rounded-full border border-slate-200 px-3 py-1.5 text-xs text-slate-700 placeholder:text-slate-400"
            placeholder="Search places on this map…"
            title="Search Google Maps places near the current map view"
          />
          {view && view.days.length > 0 && (
            <select
              value={newStopDay}
              onChange={(event) => setNewStopDay(event.target.value)}
              className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-600"
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
            className="inline-flex items-center gap-1 rounded-full bg-brand px-3 py-1.5 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Plus className="h-3.5 w-3.5" aria-hidden />
            {addingStop ? "Adding…" : "Add stop"}
          </button>
        </div>
      </div>
      {/* Day filter chips */}
      {view && view.days.length > 0 && (
        <div className="border-b border-slate-100 px-3 py-2">
          <div className="flex flex-wrap items-center gap-1.5">
            <button
              type="button"
              onClick={() => {
                setActiveDay(null);
                setNewStopDay("auto");
              }}
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
                  setNewStopDay(String(d.day));
                  const dayPins = d.pin_ids
                    .map((id) => view.pins.find((pin) => pin.id === id))
                    .filter((pin): pin is MapPin => !!pin);
                  const place = dayPins.find((pin) => pin.kind !== "hotel") ?? dayPins[0];
                  onDayFocus?.(d.day, place);
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
                  <button
                    type="button"
                    onClick={handleAddSelected}
                    disabled={addingStop}
                    className="rounded-full bg-brand px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
                  >
                    {addingStop ? "Adding…" : "+ Add to trip"}
                  </button>
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
