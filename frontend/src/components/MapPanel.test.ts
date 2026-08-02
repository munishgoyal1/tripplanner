import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createElement } from "react";
import { describe, expect, it, vi } from "vitest";
import {
  capCircuitZoom,
  airportIcon,
  focusedDayForPin,
  fitDayCircuit,
  formatLegLabel,
  hotelIcon,
  hotelLabelsForDay,
  hotelReturnForDay,
  kindForGooglePlace,
  mapPinFromGooglePlace,
  optionsForStopDay,
  pinIcon,
  pinMatchesFocus,
  pinsForDayCircuit,
  placeNameMatches,
  routePathForPinIds,
  routeStyleForLeg,
  syncPinMarkerFocus,
  visitOrdersForDay,
  zoomToPin,
} from "./MapPanel";
import MapPanel from "./MapPanel";

const { fetchMapsConfigMock, fetchMapViewMock } = vi.hoisted(() => ({
  fetchMapsConfigMock: vi.fn(),
  fetchMapViewMock: vi.fn(),
}));

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    fetchMapsConfig: fetchMapsConfigMock,
    fetchMapView: fetchMapViewMock,
  };
});

describe("placeNameMatches", () => {
  it("matches exact and canonicalized restaurant names", () => {
    expect(placeNameMatches("Peter Cat", "Peter Cat")).toBe(true);
    expect(placeNameMatches("Peter Cat Restaurant, Park Street", "Peter Cat")).toBe(true);
    expect(placeNameMatches("Peter Cat", "Peter Cat Kolkata")).toBe(true);
    expect(placeNameMatches(
      "Britto’s Bar & Restaurant – Authentic Goan Family Kitchen",
      "Britto's Bar & Restaurant",
    )).toBe(true);
    expect(placeNameMatches("Mapusa Municipal Market", "Mapusa Market")).toBe(true);
  });

  it("does not match unrelated restaurants or empty names", () => {
    expect(placeNameMatches("Peter Cat", "Mocambo")).toBe(false);
    expect(placeNameMatches("", "Peter Cat")).toBe(false);
  });
});

describe("map stop selection", () => {
  it("uses an A label for airport markers", () => {
    expect(decodeURIComponent(airportIcon())).toContain(">A</text>");
  });

  it("numbers two hotels in their same-day route order", () => {
    const hotel = (id: string, name: string) => ({
      id,
      name,
      kind: "hotel",
      selected: true,
      day: 3,
      lat: 24.5,
      lng: 73.5,
      rating: null,
      address: "Rajasthan",
      photo: null,
      occurrences: [{ day: 3, stop: 1, time: "" }],
    });
    const view = {
      enabled: true,
      destination: "Rajasthan",
      center: null,
      pins: [hotel("udaipur", "Trident Udaipur"), hotel("mount-abu", "Hotel Hillock")],
      days: [{
        day: 3,
        label: "Day 3",
        color: "#2563eb",
        pin_ids: ["udaipur", "mount-abu", "udaipur"],
        route: { distance_km: 0, duration_min: 0, mode: "", distance_display: "", duration_display: "" },
      }],
      available_days: [3],
      unscheduled_pin_ids: [],
      airport: null,
      empty_message: "",
    };

    expect(Object.fromEntries(hotelLabelsForDay(view, 3))).toEqual({
      udaipur: "H1",
      "mount-abu": "H2",
    });
    expect(Object.fromEntries(hotelLabelsForDay({
      ...view,
      days: [{ ...view.days[0], pin_ids: ["udaipur"] }],
    }, 3))).toEqual({ udaipur: "H" });
    expect(decodeURIComponent(hotelIcon(false, "H1"))).toContain(">H1</text>");
    expect(decodeURIComponent(hotelIcon(false, "H2"))).toContain(">H2</text>");
  });

  it("zooms an airport like any exact itinerary stop", () => {
    const map = { panTo: vi.fn(), setZoom: vi.fn() };
    zoomToPin(map, {
      id: "arrival-airport",
      name: "Udaipur Airport",
      kind: "airport",
      lat: 24.6177,
      lng: 73.8961,
    });

    expect(map.panTo).toHaveBeenCalledWith({ lat: 24.6177, lng: 73.8961 });
    expect(map.setZoom).toHaveBeenCalledWith(15);
  });

  it("numbers pins by itinerary occurrence when route pin order drifts", () => {
    const pin = (id: string, name: string, stop: number) => ({
      id,
      name,
      kind: "attraction",
      selected: true,
      day: 2,
      lat: 15 + stop,
      lng: 73 + stop,
      rating: null,
      address: "Goa",
      photo: null,
      occurrences: [{ day: 2, stop, time: "" }],
    });
    const view = {
      enabled: true,
      destination: "Goa",
      center: null,
      pins: [pin("fort", "Fort Aguada", 2), pin("mapusa", "Mapusa Market", 3), pin("chapora", "Chapora Fort", 4)],
      days: [{ day: 2, label: "Day 2", color: "#e11d48", pin_ids: ["fort", "chapora", "mapusa"], route: { distance_km: 4, duration_min: 20, mode: "car", distance_display: "4 km", duration_display: "20 min" } }],
      available_days: [2],
      unscheduled_pin_ids: [],
      airport: null,
      empty_message: "",
    };

    expect(Object.fromEntries(visitOrdersForDay(view, 2))).toEqual({ fort: 1, mapusa: 2, chapora: 3 });
  });

  it("does not number transport terminals as sightseeing stops", () => {
    const pin = (id: string, kind: string, stop: number) => ({
      id,
      name: id,
      kind,
      selected: true,
      day: 1,
      lat: 15 + stop,
      lng: 73 + stop,
      rating: null,
      address: "Rajasthan",
      photo: null,
      occurrences: [{ day: 1, stop, time: "" }],
    });
    const view = {
      enabled: true,
      destination: "Rajasthan",
      center: null,
      pins: [pin("origin-airport", "airport", 1), pin("palace", "attraction", 2)],
      days: [{ day: 1, label: "Day 1", color: "#e11d48", pin_ids: ["origin-airport", "palace"], route: { distance_km: 0, duration_min: 0, mode: "", distance_display: "0 km", duration_display: "0 min" } }],
      available_days: [1],
      unscheduled_pin_ids: [],
      airport: null,
      empty_message: "",
    };

    expect(Object.fromEntries(visitOrdersForDay(view, 1))).toEqual({ palace: 1 });
  });

  it("numbers both Mount Abu visits in a closed transfer-day circuit", () => {
    const pin = (id: string, name: string, kind: string, stop: number) => ({
      id,
      name,
      kind,
      selected: true,
      day: 3,
      lat: 24 + stop / 100,
      lng: 72 + stop / 100,
      rating: null,
      address: "Mount Abu",
      photo: null,
      occurrences: [{ day: 3, stop, time: "" }],
    });
    const view = {
      enabled: true,
      destination: "Rajasthan",
      center: null,
      pins: [
        pin("hillock", "Hotel Hillock", "hotel", 3),
        pin("dilwara", "Dilwara Temples", "attraction", 4),
        pin("nakki", "Nakki Lake", "attraction", 5),
      ],
      days: [{
        day: 3,
        label: "Day 3",
        color: "#2563eb",
        pin_ids: ["hillock", "dilwara", "nakki", "hillock"],
        route: { distance_km: 8, duration_min: 90, mode: "car", distance_display: "8 km", duration_display: "1 hr 30 min" },
      }],
      available_days: [3],
      unscheduled_pin_ids: [],
      airport: null,
      empty_message: "",
    };

    expect(Object.fromEntries(visitOrdersForDay(view, 3))).toEqual({ dilwara: 1, nakki: 2 });
  });

  it("uses the requested occurrence day for a repeated hotel", () => {
    const hotel = {
      id: "p0",
      name: "Goa Marriott Resort & Spa",
      kind: "hotel",
      selected: true,
      day: 1,
      lat: 15.49,
      lng: 73.81,
      rating: 4.5,
      address: "Panjim, Goa",
      photo: null,
      occurrences: [{ day: 1, stop: 1, time: "" }, { day: 2, stop: 1, time: "" }],
    };
    expect(focusedDayForPin(hotel, 2)).toBe(2);
    expect(focusedDayForPin(hotel, 3)).toBe(1);
    expect(pinMatchesFocus(hotel, "Goa Marriott Resort", 2)).toBe(true);
    expect(pinMatchesFocus(hotel, "Goa Marriott Resort", 3)).toBe(false);
  });

  it("uses the requested stop to distinguish similarly named pins on one day", () => {
    const pin = (id: string, name: string, stop: number) => ({
      id,
      name,
      kind: "attraction",
      selected: true,
      day: 6,
      lat: 26.9 + stop / 100,
      lng: 70.9 + stop / 100,
      rating: null,
      address: "Jaisalmer",
      photo: null,
      occurrences: [{ day: 6, stop, time: "" }],
    });
    const camp = pin("camel-camp", "Camel Safari Camp", 2);
    const safari = pin("camel-safari", "Camel Safari", 4);

    expect(pinMatchesFocus(camp, "Camel Safari", 6, 4)).toBe(false);
    expect(pinMatchesFocus(safari, "Camel Safari", 6, 4)).toBe(true);
  });

  it("builds an inspectable candidate only from real Google geometry", () => {
    expect(mapPinFromGooglePlace({ name: "Britto's", types: ["restaurant"] })).toBeNull();
    expect(mapPinFromGooglePlace({
      place_id: "britto-1",
      name: "Britto's",
      types: ["restaurant"],
      geometry: { location: { lat: () => 15.56, lng: () => 73.75 } },
      formatted_address: "Baga, Goa",
      rating: 4.3,
    })).toMatchObject({
      id: "candidate:britto-1",
      name: "Britto's",
      kind: "meal",
      lat: 15.56,
      lng: 73.75,
      address: "Baga, Goa",
      rating: 4.3,
    });
  });

  it("formats compact map leg labels", () => {
    expect(formatLegLabel({ distance_display: "4.6 km", duration_display: "15 min" }))
      .toBe("4.6 km · 15 min");
  });

  it("distinguishes local, road, bus, rail, and flight route geometry", () => {
    const leg = {
      from_pin_id: "origin",
      to_pin_id: "destination",
      distance_km: 100,
      duration_min: 90,
      mode: "Taxi",
      distance_display: "100 km",
      duration_display: "1 hr 30 min",
    };

    expect(routeStyleForLeg(leg, "#2563eb")).toMatchObject({
      strokeColor: "#2563eb",
      strokeOpacity: 0.85,
      strokeWeight: 3,
    });
    expect(routeStyleForLeg({ ...leg, intercity: true, mode: "Drive" }, "#2563eb"))
      .toMatchObject({ strokeColor: "#e11d48", strokeOpacity: 0.9, strokeWeight: 5 });
    expect(routeStyleForLeg({ ...leg, intercity: true, mode: "Bus" }, "#2563eb"))
      .toMatchObject({ strokeColor: "#0f766e", strokeOpacity: 0.9, strokeWeight: 5 });
    expect(routeStyleForLeg({ ...leg, intercity: true, mode: "Train" }, "#2563eb"))
      .toMatchObject({ strokeColor: "#e11d48", strokeOpacity: 0, strokeWeight: 4 });
    expect(routeStyleForLeg({ ...leg, intercity: true, mode: "Flight" }, "#2563eb"))
      .toMatchObject({ strokeColor: "#0284c7", strokeOpacity: 0, strokeWeight: 3 });
    expect(routeStyleForLeg({ ...leg, intercity: true, mode: "Drive" }, "#2563eb", true))
      .toMatchObject({
        strokeColor: "#2563eb",
        strokeOpacity: 0,
        strokeWeight: 3,
        icons: [{ icon: { strokeColor: "#2563eb" }, repeat: "10px" }],
      });
  });

  it("retains ordered route geometry when leg metadata is absent", () => {
    const pins = [
      { id: "origin", name: "Origin", kind: "hotel", selected: true, day: 1, lat: 26.9, lng: 75.8, rating: null, address: "", photo: null, occurrences: [] },
      { id: "station", name: "Station", kind: "station", selected: false, day: 1, lat: 25.7, lng: 74.7, rating: null, address: "", photo: null, occurrences: [] },
      { id: "destination", name: "Destination", kind: "hotel", selected: true, day: 1, lat: 24.6, lng: 73.7, rating: null, address: "", photo: null, occurrences: [] },
    ];

    expect(routePathForPinIds(["origin", "station", "destination"], pins)).toEqual([
      { lat: 26.9, lng: 75.8 },
      { lat: 25.7, lng: 74.7 },
      { lat: 24.6, lng: 73.7 },
    ]);
  });

  it("fits every pin in the requested day circuit", () => {
    const extend = vi.fn();
    const bounds = { extend };
    const fitBounds = vi.fn();
    const google = { maps: { LatLngBounds: vi.fn(function () { return bounds; }) } };
    const view = {
      enabled: true,
      destination: "Goa",
      center: null,
      pins: [
        { id: "hotel", name: "Hotel", kind: "hotel", selected: true, day: 2, lat: 15.1, lng: 73.1, rating: null, address: "", photo: null, occurrences: [] },
        { id: "beach", name: "Beach", kind: "attraction", selected: true, day: 2, lat: 15.2, lng: 73.2, rating: null, address: "", photo: null, occurrences: [] },
      ],
      days: [{ day: 2, label: "Day 2", color: "#e11d48", pin_ids: ["hotel", "beach", "hotel"], route: { distance_km: 4, duration_min: 20, mode: "car", distance_display: "4 km", duration_display: "20 min" } }],
      available_days: [2],
      unscheduled_pin_ids: [],
      airport: null,
      empty_message: "",
    };

    expect(fitDayCircuit(google, { fitBounds }, view, 2)).toBe(true);
    expect(extend).toHaveBeenCalledWith({ lat: 15.1, lng: 73.1 });
    expect(extend).toHaveBeenCalledWith({ lat: 15.2, lng: 73.2 });
    expect(fitBounds).toHaveBeenCalledWith(bounds, 64);
  });

  it("limits a selected day to its own circuit and exposes the hotel return time", () => {
    const hotel = { id: "udaipur-hotel", name: "Trident Udaipur", kind: "hotel", selected: true, day: 1, lat: 24.577, lng: 73.683, rating: null, address: "", photo: null, occurrences: [] };
    const palace = { id: "udaipur-palace", name: "City Palace Udaipur", kind: "attraction", selected: true, day: 1, lat: 24.576, lng: 73.683, rating: null, address: "", photo: null, occurrences: [] };
    const otherCityHotel = { id: "jodhpur-hotel", name: "Taj Hari Mahal Jodhpur", kind: "hotel", selected: true, day: 3, lat: 26.269, lng: 73.01, rating: null, address: "", photo: null, occurrences: [] };
    const view = {
      enabled: true,
      destination: "Rajasthan",
      center: null,
      pins: [hotel, palace, otherCityHotel],
      days: [{
        day: 1,
        label: "Day 1",
        color: "#e11d48",
        pin_ids: [hotel.id, palace.id, hotel.id],
        route: { distance_km: 4, duration_min: 20, mode: "car", distance_display: "4 km", duration_display: "20 min" },
        schedule: { start: "09:00", end: "21:30", duration_min: 750, duration_display: "12 hr 30 min", travel_duration_min: 20, travel_duration_display: "20 min", estimated: true },
      }],
      available_days: [1],
      unscheduled_pin_ids: [otherCityHotel.id],
      airport: null,
      empty_message: "",
    };

    expect(pinsForDayCircuit(view, 1).map((pin) => pin.name)).toEqual([
      "Trident Udaipur",
      "City Palace Udaipur",
      "Trident Udaipur",
    ]);
    expect(hotelReturnForDay(view, 1)).toEqual({
      pin: hotel,
      label: "Return · 21:30 est.",
    });
  });

  it("keeps circuit framing after the active-day redraw", async () => {
    const fitBounds = vi.fn();
    const marker = vi.fn(function (_options: { title?: string; icon?: { url?: string } }) {
      return { addListener: vi.fn(), setMap: vi.fn(), setIcon: vi.fn(), setZIndex: vi.fn() };
    });
    const polyline = vi.fn(function () { return { setMap: vi.fn() }; });
    const map = {
      addListener: vi.fn(() => ({ remove: vi.fn() })),
      fitBounds,
      getZoom: vi.fn(() => 11),
      panTo: vi.fn(),
      setZoom: vi.fn(),
    };
    window.google = {
      maps: {
        Map: vi.fn(function () { return map; }),
        Marker: marker,
        Polyline: polyline,
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
        places: {
          Autocomplete: vi.fn(function () {
            return {
              addListener: vi.fn(() => ({ remove: vi.fn() })),
              bindTo: vi.fn(),
              unbindAll: vi.fn(),
            };
          }),
        },
      },
    };
    fetchMapsConfigMock.mockResolvedValue({ enabled: true, key: "test-key" });
    fetchMapViewMock.mockResolvedValue({
      enabled: true,
      destination: "Goa",
      center: { lat: 15.2, lng: 73.2 },
      pins: [
        { id: "day-1-hotel", name: "North Hotel", kind: "hotel", selected: true, day: 1, lat: 16, lng: 74, rating: null, address: "", photo: null, occurrences: [{ day: 1, stop: 1, time: "" }] },
        { id: "day-2-origin", name: "Udaipur Hotel", kind: "hotel", selected: true, day: 2, lat: 15.1, lng: 73.1, rating: null, address: "", photo: null, occurrences: [{ day: 2, stop: 1, time: "" }] },
        { id: "day-2-destination", name: "Mount Abu Hotel", kind: "hotel", selected: true, day: 2, lat: 15.15, lng: 73.15, rating: null, address: "", photo: null, occurrences: [{ day: 2, stop: 2, time: "" }] },
        { id: "day-2-beach", name: "South Beach", kind: "attraction", selected: true, day: 2, lat: 15.2, lng: 73.2, rating: null, address: "", photo: null, occurrences: [{ day: 2, stop: 2, time: "" }] },
      ],
      days: [
        { day: 1, label: "Day 1", color: "#e11d48", pin_ids: ["day-1-hotel"], route: { distance_km: 0, duration_min: 0, mode: "walk", distance_display: "0 km", duration_display: "0 min" } },
        { day: 2, label: "Day 2", color: "#0d9488", pin_ids: ["day-2-origin", "day-2-destination", "day-2-beach", "day-2-destination"], route: { distance_km: 4, duration_min: 20, mode: "car", distance_display: "4 km", duration_display: "20 min" } },
      ],
      available_days: [1, 2],
      unscheduled_pin_ids: [],
      airport: null,
      empty_message: "",
    });

    const rendered = render(createElement(MapPanel, {
      circuitFocusDay: 2,
      circuitFocusToken: 1,
    }));

    await waitFor(() => expect(fitBounds).toHaveBeenCalled());
    await waitFor(() => expect(fitBounds.mock.calls[fitBounds.mock.calls.length - 1]?.[0].points).toEqual([
      { lat: 15.1, lng: 73.1 },
      { lat: 15.15, lng: 73.15 },
      { lat: 15.2, lng: 73.2 },
      { lat: 15.15, lng: 73.15 },
    ]));
    const markerIcon = (title: string) => marker.mock.calls
      .map(([options]) => options)
      .find((options) => options.title === title)?.icon?.url ?? "";
    expect(decodeURIComponent(markerIcon("North Hotel")))
      .toContain(">H</text>");
    expect(decodeURIComponent(markerIcon("Udaipur Hotel")))
      .toContain(">H1</text>");
    expect(decodeURIComponent(markerIcon("Mount Abu Hotel")))
      .toContain(">H2</text>");
    expect(polyline).toHaveBeenCalledWith(expect.objectContaining({
      path: [{ lat: 15.1, lng: 73.1 }, { lat: 15.15, lng: 73.15 }],
      strokeColor: "#0d9488",
      strokeOpacity: 0,
      icons: [{
        icon: expect.objectContaining({ strokeColor: "#0d9488" }),
        repeat: "10px",
      }],
    }));
    rendered.unmount();
    delete window.google;
  });

  it("caps a tight circuit without tightening an already wider view", () => {
    const tightSetZoom = vi.fn();
    capCircuitZoom({ getZoom: () => 16, setZoom: tightSetZoom });
    expect(tightSetZoom).toHaveBeenCalledWith(14);

    const wideSetZoom = vi.fn();
    capCircuitZoom({ getZoom: () => 11, setZoom: wideSetZoom });
    expect(wideSetZoom).not.toHaveBeenCalled();
  });

  it("infers hotel stops from Google place types", () => {
    expect(kindForGooglePlace(["lodging", "point_of_interest"])).toBe("hotel");
    expect(kindForGooglePlace(["restaurant", "food"])).toBe("meal");
    expect(kindForGooglePlace(["museum", "tourist_attraction"])).toBe("attraction");
    expect(kindForGooglePlace(undefined)).toBe("attraction");
  });

  it("passes an explicit day only when selected", () => {
    expect(optionsForStopDay("auto")).toBeUndefined();
    expect(optionsForStopDay("2")).toEqual({ day: 2 });
    expect(optionsForStopDay("0")).toBeUndefined();
  });

  it("changes only the focused circuit number contrast", () => {
    const normal = decodeURIComponent(pinIcon("#2563eb", "2", false).split(",")[1]);
    const focused = decodeURIComponent(pinIcon("#2563eb", "2", true).split(",")[1]);
    expect(normal).toContain('fill="white" fill-opacity="0.97"');
    expect(focused).toContain('fill="#0f172a" fill-opacity="0.97"');
    expect(focused).toContain('fill="white">2</text>');
    expect(focused).toContain('fill="#2563eb" stroke="white" stroke-width="2"');
  });

  it("switches focus between existing markers without leaving the previous marker selected", () => {
    const beachMarker = { setIcon: vi.fn(), setZIndex: vi.fn() };
    const restaurantMarker = { setIcon: vi.fn(), setZIndex: vi.fn() };
    const pin = (name: string, stop: number) => ({
      id: `p${stop}`,
      name,
      kind: "attraction",
      selected: true,
      day: 1,
      lat: 15 + stop,
      lng: 73 + stop,
      rating: null,
      address: "Goa",
      photo: null,
      occurrences: [{ day: 1, stop, time: "" }],
    });
    const entries = [
      {
        pin: pin("Betalbatim Beach", 1),
        marker: beachMarker,
        normalIcon: "beach-normal",
        focusedIcon: "beach-focused",
        baseZIndex: 600,
      },
      {
        pin: pin("Britto's Bar & Restaurant", 2),
        marker: restaurantMarker,
        normalIcon: "restaurant-normal",
        focusedIcon: "restaurant-focused",
        baseZIndex: 600,
      },
    ];

    syncPinMarkerFocus(entries, "Betalbatim Beach", 1);
    syncPinMarkerFocus(entries, "Britto's Bar & Restaurant", 1);

    expect(beachMarker.setIcon).toHaveBeenLastCalledWith("beach-normal");
    expect(beachMarker.setZIndex).toHaveBeenLastCalledWith(600);
    expect(restaurantMarker.setIcon).toHaveBeenLastCalledWith("restaurant-focused");
    expect(restaurantMarker.setZIndex).toHaveBeenLastCalledWith(1400);
  });

  it("keeps the place and day when explicit placement is rejected", async () => {
    fetchMapsConfigMock.mockResolvedValue({ enabled: false, key: "" });
    fetchMapViewMock.mockResolvedValue({
      enabled: true,
      destination: "Goa",
      center: null,
      pins: [],
      days: [{
        day: 1,
        label: "Day 1",
        color: "#e11d48",
        pin_ids: [],
        route: {
          distance_km: 0,
          duration_min: 25,
          mode: "car",
          distance_display: "8 km",
          duration_display: "25 min",
        },
        schedule: {
          duration_min: 480,
          duration_display: "8 hr",
          start: "09:00",
          end: "17:00",
          estimated: true,
        },
      }],
      available_days: [1],
      unscheduled_pin_ids: [],
      airport: null,
      empty_message: "No places yet.",
    });
    const onSelect = vi.fn().mockResolvedValue(false);
    render(createElement(MapPanel, { onSelect }));

    expect(await screen.findByText("Choose a day for schedule and route-only travel.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Day 1" }));
    expect(screen.getByText("Schedule 8 hr, 09:00–17:00 est.")).toBeInTheDocument();
    expect(screen.getByText("Travel 25 min, 8 km, car")).toBeInTheDocument();

    const input = await screen.findByPlaceholderText("Search places on this map…");
    const stopType = screen.getByRole("combobox", { name: "Stop type (optional)" });
    const day = screen.getByRole("combobox", { name: "Add stop to day" });
    expect(stopType).toHaveValue("");
    expect(stopType).toHaveTextContent("Type (optional)");
    expect(day).toHaveValue("1");
    fireEvent.change(input, { target: { value: "North Market" } });
    fireEvent.change(day, { target: { value: "1" } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));

    await waitFor(() => expect(onSelect).toHaveBeenCalledWith(
      "attraction",
      "North Market",
      { day: 1 },
    ));
    expect(input).toHaveValue("North Market");
    expect(day).toHaveValue("1");
  });

  it("chooses Best day or an explicit day from a new Google place tile", async () => {
    let placeChanged: (() => void) | undefined;
    const googlePlace = {
      place_id: "dudhsagar-1",
      name: "Dudhsagar Falls",
      types: ["tourist_attraction"],
      geometry: { location: { lat: () => 15.3144, lng: () => 74.3143 } },
      formatted_address: "Sonauli, Goa",
      rating: 4.6,
    };
    const autocomplete = {
      bindTo: vi.fn(),
      getPlace: vi.fn(() => googlePlace),
      addListener: vi.fn((_event: string, callback: () => void) => {
        placeChanged = callback;
        return { remove: vi.fn() };
      }),
      unbindAll: vi.fn(),
    };
    const map = {
      addListener: vi.fn(() => ({ remove: vi.fn() })),
      fitBounds: vi.fn(),
      panTo: vi.fn(),
      setZoom: vi.fn(),
    };
    window.google = {
      maps: {
        Map: vi.fn(function () { return map; }),
        Marker: vi.fn(function () { return { addListener: vi.fn(), setMap: vi.fn(), setIcon: vi.fn(), setZIndex: vi.fn() }; }),
        Polyline: vi.fn(function () { return { setMap: vi.fn() }; }),
        Size: vi.fn(function () {}),
        Point: vi.fn(function () {}),
        LatLngBounds: vi.fn(function () { return { extend: vi.fn(), isEmpty: vi.fn(() => false) }; }),
        places: { Autocomplete: vi.fn(function () { return autocomplete; }) },
      },
    };
    fetchMapsConfigMock.mockResolvedValue({ enabled: true, key: "test-key" });
    fetchMapViewMock.mockResolvedValue({
      enabled: true,
      destination: "Goa",
      center: { lat: 15.3, lng: 74.1 },
      pins: [],
      days: [
        { day: 1, label: "Day 1", color: "#e11d48", pin_ids: [], route: { distance_km: 0, duration_min: 0, mode: "walk", distance_display: "0 km", duration_display: "0 min" } },
        { day: 2, label: "Day 2", color: "#0d9488", pin_ids: [], route: { distance_km: 0, duration_min: 0, mode: "walk", distance_display: "0 km", duration_display: "0 min" } },
      ],
      available_days: [1, 2],
      unscheduled_pin_ids: [],
      airport: null,
      empty_message: "No places yet.",
    });
    const onSelect = vi.fn().mockResolvedValue(true);
    const rendered = render(createElement(MapPanel, { onSelect }));

    await waitFor(() => expect(placeChanged).toBeTypeOf("function"));
    act(() => placeChanged?.());

    const stopType = await screen.findByRole("combobox", { name: "Stop type (optional)" });
    expect(stopType).toHaveValue("attraction");
    expect(stopType).toHaveTextContent("Attraction · auto-filled");
    expect(stopType).toHaveClass("bg-emerald-50");
    const day = await screen.findByRole("combobox", { name: "Add Dudhsagar Falls to day" });
    expect(day).toHaveValue("auto");
    expect(day).toHaveTextContent("Best day");
    fireEvent.change(day, { target: { value: "2" } });
    fireEvent.click(screen.getByRole("button", { name: "+ Add to trip" }));

    await waitFor(() => expect(onSelect).toHaveBeenCalledWith(
      "attraction",
      "Dudhsagar Falls",
      { day: 2 },
    ));
    rendered.unmount();
    delete window.google;
  });
});
