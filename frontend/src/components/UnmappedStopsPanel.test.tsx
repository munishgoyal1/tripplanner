import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import UnmappedStopsPanel, { loudStops, reasonLabel } from "./UnmappedStopsPanel";
import type { UnmappedStop } from "../types";

const stop = (over: Partial<UnmappedStop> = {}): UnmappedStop => ({
  name: "Seine River Cruise",
  kind: "attraction",
  day: 2,
  tier: "place",
  reason: "no_match",
  candidate: { name: "Bateaux Parisiens", place_id: "pid", lat: 48.8, lng: 2.2 },
  ...over,
});

describe("UnmappedStopsPanel", () => {
  it("says nothing when every stop is on the map", () => {
    const { container } = render(
      <UnmappedStopsPanel stops={[]} onConfirm={vi.fn()} busyName={null} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("summarizes the count and reveals the stops on request", () => {
    render(<UnmappedStopsPanel stops={[stop()]} onConfirm={vi.fn()} busyName={null} />);

    expect(screen.getByText("1 stop not on the map")).toBeInTheDocument();
    expect(screen.queryByText(/Day 2/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /not on the map/ }));
    expect(screen.getByText(/Day 2 · Seine River Cruise/)).toBeInTheDocument();
    expect(screen.getByText("Found “Bateaux Parisiens” instead")).toBeInTheDocument();
  });

  it("offers the candidate and hands it back when accepted", () => {
    const onConfirm = vi.fn();
    render(<UnmappedStopsPanel stops={[stop()]} onConfirm={onConfirm} busyName={null} />);
    fireEvent.click(screen.getByRole("button", { name: /not on the map/ }));

    fireEvent.click(screen.getByRole("button", { name: "Use it" }));

    expect(onConfirm).toHaveBeenCalledWith(expect.objectContaining({ name: "Seine River Cruise" }));
  });

  it("offers nothing to accept when there is no candidate", () => {
    render(
      <UnmappedStopsPanel
        stops={[stop({ reason: "no_location", candidate: null })]}
        onConfirm={vi.fn()}
        busyName={null}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /not on the map/ }));

    expect(screen.getByText("No location found")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Use it" })).not.toBeInTheDocument();
  });

  it("puts anchors first so the costly ones read first", () => {
    render(
      <UnmappedStopsPanel
        stops={[stop(), stop({ name: "Hotel Chambiges", tier: "anchor", day: 1 })]}
        onConfirm={vi.fn()}
        busyName={null}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /not on the map/ }));

    const rows = screen.getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("Hotel Chambiges");
  });
});

describe("unmapped stop tiers", () => {
  it("treats only an anchor as loud", () => {
    const loud = loudStops([stop(), stop({ tier: "anchor" }), stop({ tier: "label" })]);
    expect(loud).toHaveLength(1);
    expect(loud[0].tier).toBe("anchor");
  });

  it("explains a label without blaming the geocoder", () => {
    expect(reasonLabel(stop({ reason: "not_a_place", candidate: null }))).toBe("Not a place");
  });
});
