import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createElement } from "react";
import { describe, expect, it, vi } from "vitest";
import {
  focusedDayForPin,
  formatLegLabel,
  kindForGooglePlace,
  mapPinFromGooglePlace,
  optionsForStopDay,
  pinIcon,
  pinMatchesFocus,
  placeNameMatches,
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
  });

  it("does not match unrelated restaurants or empty names", () => {
    expect(placeNameMatches("Peter Cat", "Mocambo")).toBe(false);
    expect(placeNameMatches("", "Peter Cat")).toBe(false);
  });
});

describe("map stop selection", () => {
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

  it("inverts the focused circuit number for stronger map contrast", () => {
    const svg = decodeURIComponent(pinIcon("#2563eb", "2", true).split(",")[1]);
    expect(svg).toContain('fill="#0f172a"');
    expect(svg).toContain('fill="white">2</text>');
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
          duration_min: 0,
          mode: "walk",
          distance_display: "0 km",
          duration_display: "0 min",
        },
      }],
      available_days: [1],
      unscheduled_pin_ids: [],
      airport: null,
      empty_message: "No places yet.",
    });
    const onSelect = vi.fn().mockResolvedValue(false);
    render(createElement(MapPanel, { onSelect }));

    const input = await screen.findByPlaceholderText("Search places on this map…");
    const day = screen.getByRole("combobox", { name: "Add stop to day" });
    fireEvent.change(input, { target: { value: "North Market" } });
    fireEvent.change(day, { target: { value: "1" } });
    fireEvent.click(screen.getByRole("button", { name: "Add stop" }));

    await waitFor(() => expect(onSelect).toHaveBeenCalledWith(
      "attraction",
      "North Market",
      { day: 1 },
    ));
    expect(input).toHaveValue("North Market");
    expect(day).toHaveValue("1");
  });
});
