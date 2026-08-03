import { describe, expect, it, vi } from "vitest";
import type { MapPin, MapView } from "../../types";
import { clearMapOverlays, synchronizeMapOverlays } from "./overlaySync";

function createGoogleMapsDouble() {
  const markerClicks = new Map<string, () => void>();
  const markers: Array<{ options: Record<string, unknown>; setMap: ReturnType<typeof vi.fn> }> = [];
  const polylines: Array<{ setMap: ReturnType<typeof vi.fn> }> = [];
  const google = {
    maps: {
      Marker: vi.fn(function (options: Record<string, unknown>) {
        const marker = {
          addListener: vi.fn((event: string, callback: () => void) => {
            if (event === "click" && typeof options.title === "string") {
              markerClicks.set(options.title, callback);
            }
          }),
          setIcon: vi.fn(),
          setMap: vi.fn(),
          setZIndex: vi.fn(),
        };
        markers.push({ options, setMap: marker.setMap });
        return marker;
      }),
      Polyline: vi.fn(function () {
        const polyline = { setMap: vi.fn() };
        polylines.push(polyline);
        return polyline;
      }),
      Size: vi.fn(function () {}),
      Point: vi.fn(function () {}),
      LatLngBounds: vi.fn(function () {
        const points: Array<{ lat: number; lng: number }> = [];
        return {
          points,
          extend: (point: { lat: number; lng: number }) => points.push(point),
          isEmpty: () => points.length === 0,
        };
      }),
    },
  };
  return { google, markerClicks, markers, polylines };
}

function mapView(pins: MapPin[], pinIds: string[]): MapView {
  return {
    enabled: true,
    destination: "Rajasthan",
    center: null,
    pins,
    days: [{
      day: 1,
      label: "Day 1",
      color: "#e11d48",
      pin_ids: pinIds,
      route: {
        distance_km: 10,
        duration_min: 20,
        mode: "car",
        distance_display: "10 km",
        duration_display: "20 min",
      },
    }],
    available_days: [1],
    unscheduled_pin_ids: [],
    airport: null,
    empty_message: "",
  };
}

describe("synchronizeMapOverlays", () => {
  it("detaches every owned overlay during redraw or teardown", () => {
    const overlays = [{ setMap: vi.fn() }, { setMap: vi.fn() }];

    clearMapOverlays(overlays);

    overlays.forEach((overlay) => expect(overlay.setMap).toHaveBeenCalledWith(null));
  });

  it("clears stale overlays and lets pending exact focus win over aggregate bounds", () => {
    const pin: MapPin = {
      id: "palace",
      name: "City Palace Udaipur",
      kind: "attraction",
      selected: true,
      day: 1,
      lat: 24.5764,
      lng: 73.6835,
      rating: null,
      address: "Udaipur",
      photo: null,
      occurrences: [{ day: 1, stop: 2, time: "10:00" }],
    };
    const staleOverlay = { setMap: vi.fn() };
    const map = {
      fitBounds: vi.fn(),
      panTo: vi.fn(),
      setZoom: vi.fn(),
    };
    const { google, markerClicks } = createGoogleMapsDouble();
    const onPinClick = vi.fn();

    const result = synchronizeMapOverlays({
      google,
      map,
      view: mapView([pin], [pin.id]),
      activeDay: 1,
      candidatePin: null,
      focus: { name: pin.name, day: 1, stop: 2 },
      pendingFocus: pin,
      pendingRouteFocus: null,
      previousOverlays: [staleOverlay],
      onPinClick,
      onCandidateClick: vi.fn(),
      onAirportClick: vi.fn(),
    });

    expect(staleOverlay.setMap).toHaveBeenCalledWith(null);
    expect(result.pinMarkers).toHaveLength(1);
    expect(result.focusedPin).toBe(pin);
    expect(result.consumedPendingFocus).toBe(true);
    expect(map.panTo).toHaveBeenCalledWith({ lat: pin.lat, lng: pin.lng });
    expect(map.setZoom).toHaveBeenCalledWith(15);
    expect(map.fitBounds).not.toHaveBeenCalled();

    markerClicks.get(pin.name)?.();
    expect(onPinClick).toHaveBeenCalledWith(pin);
  });

  it("consumes pending route focus by fitting every ordered endpoint", () => {
    const source: MapPin = {
      id: "source",
      name: "Bengaluru Airport",
      kind: "airport",
      selected: true,
      day: 1,
      lat: 13.1986,
      lng: 77.7066,
      rating: null,
      address: "Bengaluru",
      photo: null,
      occurrences: [{ day: 1, stop: 1, time: "08:00" }],
    };
    const destination: MapPin = {
      ...source,
      id: "destination",
      name: "Udaipur Airport",
      lat: 24.6177,
      lng: 73.8961,
      occurrences: [{ day: 1, stop: 2, time: "10:05" }],
    };
    const map = {
      fitBounds: vi.fn(),
      panTo: vi.fn(),
      setZoom: vi.fn(),
    };
    const { google } = createGoogleMapsDouble();

    const result = synchronizeMapOverlays({
      google,
      map,
      view: mapView([source, destination], [source.id, destination.id]),
      activeDay: 1,
      candidatePin: null,
      focus: {},
      pendingFocus: null,
      pendingRouteFocus: 1,
      previousOverlays: [],
      onPinClick: vi.fn(),
      onCandidateClick: vi.fn(),
      onAirportClick: vi.fn(),
    });

    expect(result.consumedPendingRouteFocus).toBe(true);
    expect(map.fitBounds).toHaveBeenCalledTimes(1);
    expect(map.fitBounds.mock.calls[0][0].points).toEqual([
      { lat: source.lat, lng: source.lng },
      { lat: destination.lat, lng: destination.lng },
    ]);
  });
});