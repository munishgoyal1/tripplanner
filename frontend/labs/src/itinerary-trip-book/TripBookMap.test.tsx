import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DayCircuitMap, dayCircuit } from "./TripBookMap";

describe("DayCircuitMap", () => {
  it("draws the day as a closed hotel-to-hotel circuit numbered in itinerary order", () => {
    const { container } = render(<DayCircuitMap />);

    const markers = Array.from(container.querySelectorAll("text"))
      .map((node) => node.textContent)
      .filter((text) => text === "H" || /^\d$/.test(text ?? ""));
    expect(markers).toEqual(["H", "1", "2", "3", "4"]);

    const points = container.querySelector("polyline")!.getAttribute("points")!.split(" ");
    expect(points).toHaveLength(dayCircuit.length + 1);
    expect(points[0]).toBe(points[points.length - 1]);
  });

  it("prints stop names only on the full-page map", () => {
    const inset = render(<DayCircuitMap />).container;
    expect(inset.textContent).not.toContain("Tower of London");

    const page = render(<DayCircuitMap labels />).container;
    expect(page.textContent).toContain("Tower of London");
  });
});
