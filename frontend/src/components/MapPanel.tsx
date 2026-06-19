import { useCallback, useEffect, useRef, useState } from "react";
import { fetchMapView, fetchMapsConfig } from "../api";
import type { MapView, MapPin } from "../types";

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


interface Props {
  /** Bump to refetch the map after the trip changes. */
  reloadToken?: number;
  /** When set, highlight the pin with this name (filter to its day, pan, open info). */
  focusName?: string | null;
  /** Add a place to the trip (from a pin's info window). */
  onSelect?: (kind: string, name: string) => void;
  /** Remove a place from the trip (from a pin's info window). */
  onDeselect?: (kind: string, name: string) => void;
}

export default function MapPanel({ reloadToken = 0, focusName, onSelect, onDeselect }: Props) {
  const [view, setView] = useState<MapView | null>(null);
  const [key, setKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeDay, setActiveDay] = useState<number | null>(null); // null = all days

  const mapEl = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const infoRef = useRef<any>(null);
  const overlaysRef = useRef<any[]>([]); // markers + polylines to clear on redraw
  const openInfoRef = useRef<((p: MapPin) => void) | null>(null); // latest draw's info opener
  // Latest add/remove callbacks + the pin whose info window is open, read by
  // the InfoWindow's (raw-HTML) toggle button. Kept in refs so the one-time
  // domready listener always sees current values without re-binding.
  const cbRef = useRef<{
    onSelect?: (kind: string, name: string) => void;
    onDeselect?: (kind: string, name: string) => void;
  }>({});
  cbRef.current = { onSelect, onDeselect };
  const openPinRef = useRef<MapPin | null>(null);
  const confirmRef = useRef(false); // armed for a two-click remove

  // ---- data + config -------------------------------------------------------
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const [cfg, mv] = await Promise.all([fetchMapsConfig(), fetchMapView()]);
        if (cancelled) return;
        setView(mv);
        setKey(cfg.enabled ? cfg.key : null);
      } catch {
        if (!cancelled) setError("Could not load the map.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

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
        infoRef.current = new google.maps.InfoWindow();
        // Wire the info-window's in-HTML add/remove button once. The handler
        // reads the open pin + latest callbacks from refs. Removal is a
        // two-click confirm so a stray tap can't drop a place.
        google.maps.event.addListener(infoRef.current, "domready", () => {
          const btn = document.getElementById("gm-trip-toggle");
          if (!btn) return;
          (btn as HTMLButtonElement).onclick = () => {
            const p = openPinRef.current;
            if (!p) return;
            const cb = cbRef.current;
            if (p.selected) {
              if (!confirmRef.current) {
                confirmRef.current = true;
                btn.textContent = "Click again to remove";
                (btn as HTMLButtonElement).style.background = "#e11d48";
                (btn as HTMLButtonElement).style.color = "#fff";
                setTimeout(() => {
                  confirmRef.current = false;
                }, 3000);
                return;
              }
              confirmRef.current = false;
              cb.onDeselect?.(p.kind, p.name);
            } else {
              cb.onSelect?.(p.kind, p.name);
            }
          };
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
      infoRef.current = null;
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
      marker.addListener("click", () => openInfo(p));
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
        if (!infoRef.current) return;
        infoRef.current.setContent(
          `<div style="font:600 13px Inter,sans-serif">${"\u2708 "}${escapeHtml(a.name)}</div>`
        );
        infoRef.current.setPosition({ lat: a.lat, lng: a.lng });
        infoRef.current.open(map);
      });
      overlaysRef.current.push(marker);
      bounds.extend({ lat: a.lat, lng: a.lng });
      any = true;
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

    if (any && !bounds.isEmpty()) {
      map.fitBounds(bounds, 64);
    }

    function openInfo(p: MapPin) {
      if (!infoRef.current) return;
      openPinRef.current = p;
      confirmRef.current = false;
      const badge = p.selected
        ? `<span style="background:#e11d48;color:#fff;border-radius:9999px;padding:1px 8px;font-size:11px;font-weight:600">In trip</span>`
        : `<span style="background:#f1f5f9;color:#475569;border-radius:9999px;padding:1px 8px;font-size:11px">Suggested</span>`;
      const dayTag = p.day
        ? `<span style="background:${dayColor.get(p.day) || "#64748b"};color:#fff;border-radius:9999px;padding:1px 8px;font-size:11px;font-weight:600">Day ${p.day}</span>`
        : "";
      const seqTag = p.day && visitOrderByPinId.get(p.id)
        ? `<span style="background:#111827;color:#fff;border-radius:9999px;padding:1px 8px;font-size:11px;font-weight:600">Stop ${visitOrderByPinId.get(p.id)}</span>`
        : "";
      const rating = p.rating ? `<div style="color:#475569;font-size:12px">${"\u2605"} ${p.rating}</div>` : "";
      const photo = p.photo
        ? `<img src="${escapeAttr(p.photo)}" style="width:100%;height:96px;object-fit:cover;border-radius:8px;margin-bottom:6px"/>`
        : "";
      // Add/remove control. Hotels and attractions can be toggled; other pins
      // (airport) can't. Selected → rose "Remove", else brand "+ Add to trip".
      const togglable = p.kind === "hotel" || p.kind === "attraction";
      const toggleBtn = togglable
        ? `<button id="gm-trip-toggle" style="margin-top:8px;width:100%;border:none;border-radius:9999px;padding:7px 10px;font-size:12px;font-weight:600;cursor:pointer;${
            p.selected
              ? "background:#fff1f2;color:#be123c;box-shadow:inset 0 0 0 1px #fecdd3"
              : "background:#e11d48;color:#fff"
          }">${p.selected ? "\u2715 Remove from trip" : "+ Add to trip"}</button>`
        : "";
      infoRef.current.setContent(
        `<div style="max-width:220px;font-family:Inter,sans-serif">
           ${photo}
           <div style="font-weight:700;font-size:14px;margin-bottom:3px">${escapeHtml(p.name)}</div>
           <div style="display:flex;gap:6px;align-items:center;margin-bottom:4px">${badge}${dayTag}${seqTag}</div>
           ${rating}
           <div style="color:#64748b;font-size:11px;margin-top:2px">${escapeHtml(p.address || "")}</div>
           ${toggleBtn}
         </div>`
      );
      infoRef.current.setPosition({ lat: p.lat, lng: p.lng });
      infoRef.current.open(map);
    }

    openInfoRef.current = openInfo;
  }, [view, activeDay]);

  useEffect(() => {
    draw();
  }, [draw]);

  // ---- focus a pin by name (driven from the itinerary tab) -----------------
  useEffect(() => {
    if (!focusName || !view || !mapRef.current) return;
    const pin = view.pins.find(
      (p) => p.name.toLowerCase() === focusName.toLowerCase()
    );
    if (!pin) return;
    // Reveal the pin's day so it isn't filtered out, then pan + open its info.
    if (pin.day && pin.day !== activeDay) setActiveDay(pin.day);
    const t = setTimeout(() => {
      mapRef.current?.panTo({ lat: pin.lat, lng: pin.lng });
      mapRef.current?.setZoom(15);
      openInfoRef.current?.(pin);
    }, 0);
    return () => clearTimeout(t);
    // activeDay omitted: we set it here and don't want to re-trigger on it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusName, view]);

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
    error != null
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
                onClick={() => setActiveDay(d.day)}
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
        {overlay && (
          <div className="absolute inset-0 grid place-items-center bg-white/85 p-6 text-center">
            <div className={`max-w-xs text-sm ${overlay.tone}`}>{overlay.text}</div>
          </div>
        )}
      </div>
    </div>
  );
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c] as string)
  );
}

function escapeAttr(s: string): string {
  return s.replace(/"/g, "&quot;");
}
