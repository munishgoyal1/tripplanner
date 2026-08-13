import { describe, expect, it } from "vitest";

import type { MapPin } from "../../types";
import { parallelLegPath } from "./routeDerivations";

function pin(id: string, lat: number, lng: number): MapPin {
  return {
    id,
    name: id,
    kind: "airport",
    selected: true,
    day: null,
    lat,
    lng,
    rating: null,
    address: "",
    photo: null,
    occurrences: [],
  };
}

describe("parallelLegPath", () => {
  it("keeps a route direct when no other day reuses its terminal pair", () => {
    const start = pin("blr", 13.2, 77.7);
    const end = pin("del", 28.6, 77.1);

    expect(parallelLegPath(start, end, 0, 1)).toEqual([
      { lat: start.lat, lng: start.lng },
      { lat: end.lat, lng: end.lng },
    ]);
  });

  it("separates outbound and return while keeping both attached to the terminals", () => {
    const blr = pin("blr", 13.2, 77.7);
    const del = pin("del", 28.6, 77.1);
    const outbound = parallelLegPath(blr, del, 0, 2);
    const returning = parallelLegPath(del, blr, 1, 2);

    expect(outbound[0]).toEqual({ lat: blr.lat, lng: blr.lng });
    expect(outbound[outbound.length - 1]).toEqual({ lat: del.lat, lng: del.lng });
    expect(returning[0]).toEqual({ lat: del.lat, lng: del.lng });
    expect(returning[returning.length - 1]).toEqual({ lat: blr.lat, lng: blr.lng });
    expect(outbound[1]).not.toEqual(returning[1]);
  });
});